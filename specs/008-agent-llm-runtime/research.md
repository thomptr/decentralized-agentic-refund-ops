# Phase 0 Research: Agent LLM Runtime

All NEEDS CLARIFICATION items from Technical Context are resolved below. Each decision is scoped to
prove the PoC hypothesis with the simplest path that satisfies the spec and constitution.

---

## R1. Where the runtime lives and how it reuses the foundation

**Decision**: Implement as a new sub-package `src/agent_foundation/llm/` inside the existing shared
foundation, reusing the established audit subsystem (`agent_foundation.audit.store.write_audit`),
the idempotency pattern (`agent_foundation.idempotency.IdempotencyTracker`), and the
correlation/causation conventions of `EventEnvelope`.

**Rationale**: The spec's Assumptions require reuse of the existing audit, idempotency, and
correlation machinery rather than parallel infrastructure. Co-locating with `audit/`, `runtime/`,
and `idempotency.py` makes that reuse natural and keeps the runtime importable in-process by every
agent (FR-001, FR-011).

**Alternatives considered**: A standalone top-level `packages/llm_runtime` package — rejected
because it invites a parallel audit/idempotency path and weakens the "one foundation" story. A
service/agent — rejected outright by FR-015 (no new agent/supervisor).

---

## R2. Model provider abstraction & offline-first default

**Decision**: Define a `ModelProvider` protocol with `invoke(prompt, profile, *, timeout) ->
RawCompletion`. Ship three implementations selected by config: **`stub`** (default, deterministic,
offline), **`bedrock`** (boto3 `bedrock-runtime`), and **`agentcore`** (local AgentCore entrypoint).
Default mode is `stub`; Bedrock/AgentCore are opt-in via `AGENT_LLM_MODE`.

**Rationale**: FR-014 and US8 require fully-offline operation by default with real Bedrock enabled
only by explicit configuration and **no calling-agent code change** between modes. A provider
protocol with config-driven selection isolates that switch in one place (FR-017).

**Alternatives considered**: Always-Bedrock with mocking in tests — rejected; it makes CI depend on
mocking discipline and risks accidental cloud calls. A LangChain `ChatModel` as the core seam —
rejected as the *core* (adds a hard dependency); LangChain/LangGraph are supported via an adapter
(R8) instead.

---

## R3. Bedrock invocation API + prompt caching

**Decision**: Use the Bedrock Runtime **Anthropic Messages** API (`invoke_model` with the
`anthropic_version` body, or `converse` with `cachePoint`) targeting the latest capable Claude model
on Bedrock, configurable. Mark the large stable prefix (system instructions + output schema +
few-shot examples) with prompt-cache breakpoints (`cache_control: {"type": "ephemeral"}` /
`cachePoint`) and keep the variable grounding inputs as the uncached suffix. Read token usage —
including `cache_read_input_tokens` / `cache_creation_input_tokens` — from the response and surface
it in result metadata + audit.

**Rationale**: Satisfies the constitution's "prompt caching MUST be enabled for all multi-turn agent
interactions" and FR-013/US7 (observable cache reuse). Structuring stable-prefix-then-variable-suffix
is the canonical way to make the prefix cache-eligible.

**Alternatives considered**: Titan/other Bedrock model families — rejected; the repo already targets
Anthropic Claude and the agents' `agentcore_app.py` assume it. No caching — violates the constitution.

---

## R4. Structured output enforcement & repair

**Decision**: The caller supplies a Pydantic model (or JSON Schema) as the expected output shape.
The runtime requests JSON output (tool-use / JSON instruction in the prompt), parses it, validates
against the schema **plus** a grounding check (no enum/range violations, no asserted facts outside
the supplied grounding inputs). On failure, retry within a bounded budget (default 2 repairs) with a
correction prompt; on exhaustion, return the defined fallback or an explicit
`unable_to_produce` outcome with a recorded reason. Invalid output is **never** returned.

**Rationale**: FR-005/FR-006 and US3 require schema/enum/range/grounding bounds with bounded repair
and no fabricated content. Pydantic is already the project's validation layer.

**Alternatives considered**: Trusting raw model JSON — rejected (US3 explicitly forbids surfacing
fluent-but-wrong output). Unbounded retries — rejected by FR-006's bounded budget and the time
budget (FR-009).

---

## R5. Idempotency & replay stability

**Decision**: Every `AssistiveRequest` carries an idempotency key (derived from the case/correlation
id + task kind + a hash of grounding inputs, or supplied by the caller). Completed results are
recorded in an `AssistiveResultStore` — an in-process LRU mirroring `IdempotencyTracker`, backed by
a compacted Kafka topic for durability across redelivery. A repeat request with a known key returns
the recorded result with **no** second model call, and records a `served-from-cache` audit step.
Deterministic decoding (temperature 0 / fixed parameters) is set additionally.

**Rationale**: FR-007/008 and US4 require zero re-invocation and identical output on replay, served
from the recorded result; reusing the established compacted-topic idempotency pattern keeps it in the
foundation's idiom and avoids a new datastore.

**Alternatives considered**: Relying solely on deterministic decoding — rejected; generation can
still drift and replay must be provably identical from a record, not re-derived. A new SQL/Redis
store — rejected by PoC scope; the compacted topic already exists.

---

## R6. Timeouts, retries, and safe fallback

**Decision**: Bound the model call with `asyncio.wait_for(timeout=AGENT_LLM_TIMEOUT_SECONDS)`. On
timeout, unreachable model, provider error, or invalid output beyond the repair budget, return a
**fallback** `AssistiveResult` flagged `reasoning_path = fallback` with a `failure_reason`, produced
by a caller-supplied fallback callable (each agent's pre-LLM behavior — keyword classify, templated
draft, or "no summary"). The binding decision is unaffected because it is already deterministic.

**Rationale**: FR-009 and US5 require a bounded wait and a safe, recorded degradation to pre-LLM
behavior, never blocking or fabricating. Passing the fallback as a callable keeps the agent's
existing deterministic code as the single source of fallback truth.

**Alternatives considered**: Raising on failure and letting the agent catch — rejected; it scatters
fallback logic and risks an unhandled path blocking the case. A runtime-owned generic fallback —
rejected; only the agent knows its correct pre-LLM behavior.

---

## R7. Audit record & reconstructability

**Decision**: Emit one `ReasoningAuditRecord` per reasoning step through the existing audit
subsystem, modeled as an `AuditPayload` outcome on the existing `agent.audit.v1` topic (or a typed
extension of it), carrying: calling `agent_id`, `correlation_id`, `causation_id`, timestamp, task
kind, model identity + parameters, a prompt reference/hash (enough to reconstruct what was asked),
reasoning path (model / cache / fallback), token usage, latency, validated result summary, and
outcome/failure reason. Queryable by correlation id via the existing
`audit.store.query_by_correlation` in causal order.

**Rationale**: FR-011/012, US6, SC-005 require an immutable, correlated, model-free-reconstructable
record distinguishable from the binding decision, reusing the existing audit path (not a parallel
one).

**Alternatives considered**: A new `llm.audit.v1` topic — rejected by FR-015 (no new topic) and by
the reuse assumption. Logging only — rejected; the constitution requires an auditable trail queryable
without code inspection.

---

## R8. LangGraph-compatible invocation

**Decision**: Provide `agent_foundation.llm.langgraph.as_node(runtime, request_builder)` returning a
plain callable `(state: dict) -> dict` that builds an `AssistiveRequest` from graph state, calls
`runtime.reason`, and merges the `AssistiveResult` back into state. LangGraph itself is imported
lazily and only required by the optional `[langgraph]` extra; the adapter works with any
state-dict graph framework.

**Rationale**: The feature input requires LangGraph-compatible invocation, but the constitution's PoC
discipline forbids speculative hard dependencies. A node-shaped callable satisfies LangGraph without
coupling the core runtime to it.

**Alternatives considered**: Building the runtime *as* a LangGraph graph — rejected; it forces the
dependency everywhere and conflicts with the simple in-process `reason()` seam every agent already
wants.

---

## R9. Local AgentCore CLI execution

**Decision**: Add an `agentcore` provider mode that routes a reasoning call through the local
`bedrock_agentcore` runtime the agents already use (`agentcore_app.py`), import-guarded exactly like
the existing entrypoints so the package imports cleanly without `bedrock-agentcore` installed.

**Rationale**: Feature input requires local AgentCore CLI execution; the agents already expose
`BedrockAgentCoreApp` entrypoints, so reusing them gives one coherent local-invocation story without
a second mechanism.

**Alternatives considered**: A bespoke subprocess CLI shell-out — rejected as duplicative and
brittle versus the in-process AgentCore runtime already present.

---

## R10. Per-agent model profiles

**Decision**: A `ModelProfile` captures model id, region, decoding params (temperature, max tokens,
top_p), time budget, and retry budget. A profile **registry** maps `(agent_id, task_kind)` to a
profile, with a default profile and env overrides (`AGENT_LLM_MODEL`, `AGENT_LLM_REGION`,
`AGENT_LLM_TIMEOUT_SECONDS`, `AGENT_LLM_MAX_REPAIRS`, `AGENT_LLM_MODE`). Agents pass their `agent_id`
and task kind; the runtime resolves the profile.

**Rationale**: FR-017/FR-018 require config-supplied model selection and per-agent adoption; profiles
let CRA's drafting task differ from billing/risk summarization without code forks, all from config.

**Alternatives considered**: A single global model config — rejected; it cannot express per-agent /
per-task differences the spec calls for. Hard-coded per-agent constants — rejected by FR-017
(config, not hard-coded).

---

## R11. Agent adoption mapping (what each agent uses the runtime for)

**Decision** (finalizing the spec's "illustrative, finalized in planning" assumption):

| Agent | Assistive task(s) | Fallback (pre-LLM) | Binding engine (unchanged) |
|-------|-------------------|--------------------|----------------------------|
| **Customer Resolution** | (a) classify ticket / extract intent; (b) draft customer-facing response | keyword `classify()`; `draft_structured_response()` templates | `decision_engine.decide()` |
| **Billing Entitlement** | summarize the deterministic eligibility reasoning into the result `summary` | existing terse/templated summary | `rules_engine.evaluate()` |
| **Risk & Fraud** | summarize the deterministic risk reasoning into the result `summary` | existing terse/templated summary | `scoring.assess_signals()` |

**Rationale**: Honors FR-018 (all three adopt) and FR-003/004 (binding verdict stays deterministic).
CRA gets the richer language tasks (US1); billing & risk are constrained to *summarizing their own
reasoning*, preserving domain isolation (Principle I) — they never use the LLM for the
recommendation itself.

**Alternatives considered**: Billing/risk using the LLM to extract/normalize inputs — allowed by the
spec but deferred; summarization is the smallest adoption that proves the boundary without risking
the deterministic recommendation. CRA drafting from raw ticket text without `AllowedFacts` — rejected
by US3 (must be fact-bounded; reuse the existing `AllowedFacts` whitelist).

---

## R12. Dependencies & extras packaging

**Decision**: Add optional extras to `pyproject.toml`: `llm = ["boto3>=1.34"]` and
`langgraph = ["langgraph>=0.2", "langchain-aws>=0.2"]`; keep `bedrock-agentcore` as the existing
optional. The default install and the full test suite require **none** of these — the stub path is
pure Python. CI runs offline against the stub.

**Rationale**: PoC scope discipline (Principle V) and FR-014 (offline default). Extras keep the cloud
and graph dependencies out of the core and out of CI while remaining one `pip install '.[llm]'`
away. Recorded in the plan's Complexity Tracking table per governance.

**Alternatives considered**: Adding boto3/langgraph as core deps — rejected; it burdens every install
and CI with cloud/graph libraries the offline PoC does not need.
