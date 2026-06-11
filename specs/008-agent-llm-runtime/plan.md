# Implementation Plan: Agent LLM Runtime

**Branch**: `008-agent-llm-runtime` | **Date**: 2026-06-10 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/008-agent-llm-runtime/spec.md`

## Summary

Add a **shared, in-process LLM reasoning runtime** to the agent foundation
(`src/agent_foundation/llm/`) that any domain agent can call to perform bounded, *assistive*
cognitive tasks — classify a ticket, extract intent, draft a customer message, summarize the
reasoning behind a decision — and receive a grounded, schema-validated, prompt-cached, fully
audited result. The runtime is the deliverable; all three existing agents adopt it for at least
one assistive task each.

The runtime is **assistive, never authoritative**: every binding refund outcome
(`approve_refund` / `deny_refund` / `offer_partial_credit` / `escalate_to_human`, and each agent's
domain verdict) stays the exclusive output of the existing deterministic engines
(`decision_engine.decide`, billing `rules_engine.evaluate`, risk `scoring.assess_signals`). The
runtime helps agents *understand and communicate*; it does not decide. That boundary is what lets a
non-deterministic model live inside a system the constitution requires to be idempotent, replayable,
and auditable — the binding decision stays deterministic, and assistive outputs are recorded against
an idempotency key so replay is stable, with a deterministic offline stub model the default so the
whole suite and demo run with no AWS credentials.

**Technical approach**: a small package of pure-ish components behind one entry point
`LLMRuntime.reason(request) -> AssistiveResult`. A `ModelProvider` protocol has two implementations:
a deterministic **stub** (default, offline) and a **Bedrock** provider (boto3 `bedrock-runtime`,
Anthropic Messages API with prompt-cache `cache_control` breakpoints and token-usage accounting). A
local **AgentCore** invocation mode reuses the agents' existing `bedrock_agentcore` entrypoints for
laptop runs. Structured output is enforced by a validate-and-repair loop against a caller-supplied
Pydantic schema; per-agent **model profiles** select model/decoding/budgets by `agent_id` + task;
prompt **templates** keep large stable blocks (instructions, schema, examples) in a cache-eligible
prefix; **retries/timeouts/fallback** bound the model path and degrade to each agent's pre-LLM
behavior; **token usage + reasoning path** ride along in metadata; and each step emits a
`ReasoningAuditRecord` through the existing audit subsystem. A LangGraph-compatible node adapter
(`as_node`) lets graph-based agents invoke the runtime without a hard LangGraph dependency. No new
agent, event contract, topic, or supervisor is introduced.

## Technical Context

**Language/Version**: Python 3.12 (repo `requires-python = ">=3.12"`)

**Primary Dependencies**: pydantic v2, structlog, aiokafka (existing). **New**: `boto3` (AWS SDK
for Bedrock — constitution AI-SDK constraint) as an optional `[llm]` extra; optional
`langchain-aws` / `langgraph` behind a `[langgraph]` extra for the LangGraph-compatible path;
existing optional `bedrock-agentcore` for the local AgentCore CLI mode. Default offline path uses
**no** new runtime dependency (pure-Python stub).

**Storage**: No new datastore. Assistive results are recorded for idempotent replay on a compacted
Kafka topic via the existing idempotency/transport machinery; audit records ride the existing
`agent.audit.v1` audit topic. In-process LRU mirrors the existing `IdempotencyTracker` pattern.

**Testing**: pytest + pytest-asyncio (existing). Unit tests for the runtime under
`tests/unit/llm/`; per-agent adoption tests in each agent's `tests/`; an end-to-end choreography
test reusing `packages/testing/workflow_harness.py`. All green against the stub model with no AWS.

**Target Platform**: Local developer workstation / CI (Linux). Bedrock is opt-in via config only.

**Project Type**: Single Python project — shared library capability in `src/agent_foundation/` plus
adoption edits in `apps/agents/*`.

**Performance Goals**: Not a throughput feature. Bound per-call latency by a configurable time
budget (default a few seconds); stub path is sub-millisecond. Prompt caching demonstrably reuses the
stable prefix on warm calls.

**Constraints**: Offline-first (stub default, zero cloud access in tests/demo); fully in-process (no
new event/topic/agent/supervisor); binding decisions unchanged and deterministic; assistive output
schema-bounded; replay-stable by idempotency key; every step audited and reconstructable without a
live model.

**Scale/Scope**: One runtime package (~8–10 modules), three agent adoptions (CRA: classify + draft;
billing: reasoning summary; risk: reasoning summary), one stub model, one Bedrock provider, one
LangGraph adapter, one AgentCore local mode.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Assessment | Status |
|-----------|-----------|--------|
| **I. Agent Autonomy** | No new agent introduced; the runtime is an in-process library the *existing* agents call. No supervisor/router/orchestrator (FR-015). Domain isolation preserved: billing & risk use the LLM **only** to summarize their own deterministic reasoning; CRA uses it for classification & drafting over its own ticket inputs; no agent's domain logic leaks into another. | PASS |
| **II. Event-Driven Coordination** | No new event contract, topic, or back-channel. Assistive results are in-process return values; the only emission is an audit record on the **existing** `agent.audit.v1` topic. Agents continue to coordinate solely via their existing Kafka events (FR-015, FR-016). | PASS |
| **III. Idempotency & Safety** | Assistive results are recorded against an idempotency key; a redelivered request returns the recorded result with **zero** additional model calls (FR-007/008). Binding outcomes remain deterministic regardless of model output (FR-003/004), so replay is stable end to end. Deterministic decoding is used additionally. | PASS |
| **IV. Observability-First** | Every reasoning step emits a structured `ReasoningAuditRecord` (calling agent, correlation, causation, timestamp, model/params, reasoning path, validated result, latency, token usage, outcome) reconstructable by correlation id with no live model (FR-011/012). | PASS |
| **V. PoC Scope Discipline** | Offline stub is the default; Bedrock is opt-in. No auth/scaling/HA/secrets hardening. New dependencies are limited and justified (see Complexity Tracking): `boto3` is mandated by the constitution's AI-SDK constraint; LangGraph/AgentCore are optional extras requested in the feature input and isolated behind adapters so the core path needs neither. Prompt caching is implemented as the constitution requires. | PASS (with tracked deps) |

**Gate result: PASS.** No unjustified violations. Dependency additions recorded in Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/008-agent-llm-runtime/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── llm-runtime-api.md       # reason() entry point, request/result shapes
│   ├── model-config.md          # env config + per-agent model profiles
│   ├── reasoning-audit-record.md# audit payload fields & query
│   ├── stub-model-contract.md   # deterministic offline model behavior
│   └── provider-protocol.md     # ModelProvider protocol + Bedrock mapping
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
src/agent_foundation/
└── llm/                          # NEW shared runtime package
    ├── __init__.py               # public surface: LLMRuntime, AssistiveRequest, AssistiveResult
    ├── runtime.py                # LLMRuntime.reason(): idempotency → invoke → validate → fallback → audit
    ├── request.py                # AssistiveRequest, TaskKind, grounding inputs
    ├── result.py                 # AssistiveResult, ReasoningPath, TokenUsage, FailureReason
    ├── config.py                 # RuntimeConfig + ModelProfile + per-agent profile registry (env-driven)
    ├── prompts.py                # PromptTemplate: cache-eligible stable prefix + variable grounding suffix
    ├── structured.py             # schema validate-and-repair loop (Pydantic / JSON-schema)
    ├── store.py                  # assistive-result idempotency store (LRU + compacted Kafka topic)
    ├── audit.py                  # ReasoningAuditRecord + write via existing audit subsystem
    ├── langgraph.py              # as_node(): LangGraph-compatible adapter (no hard dependency)
    └── providers/
        ├── __init__.py           # provider selection from config
        ├── base.py               # ModelProvider protocol + RawCompletion
        ├── stub.py               # deterministic offline model (default)
        ├── bedrock.py            # boto3 bedrock-runtime + prompt-cache breakpoints + token usage
        └── agentcore.py          # local AgentCore CLI/runtime invocation mode

apps/agents/
├── customer_resolution/
│   ├── ticket_classifier.py      # EDIT: LLM-backed classify; keyword classify becomes the fallback
│   └── response_drafter.py       # EDIT: LLM drafting bounded by AllowedFacts; templates are the fallback
├── billing_entitlement/
│   └── service.py (or rules_engine adjacency)  # EDIT: LLM summarizes the deterministic recommendation only
└── risk_fraud/
    └── service.py (or scoring adjacency)        # EDIT: LLM summarizes the deterministic assessment only

tests/
├── unit/llm/                     # runtime unit tests (stub-backed, offline)
│   ├── test_runtime_reason.py
│   ├── test_structured_validation.py
│   ├── test_idempotency_replay.py
│   ├── test_fallback_paths.py
│   ├── test_prompt_cache.py
│   ├── test_model_profiles.py
│   └── test_stub_model.py
└── integration/llm/              # opt-in Bedrock smoke (skipped without AWS) + e2e choreography
    └── test_e2e_runtime_backed_agents.py

# Per-agent adoption tests live beside each agent (e.g. apps/agents/customer_resolution/tests/
# test_llm_classify_guardrail.py) asserting the binding verdict is unchanged when the LLM is forced
# to contradict it.
```

**Structure Decision**: Single-project layout. The runtime is a **new sub-package of the existing
shared foundation** (`src/agent_foundation/llm/`), placed alongside `audit/`, `runtime/`, and
`idempotency.py` so it reuses the established audit, idempotency, and correlation/causation
machinery rather than standing up parallel infrastructure (spec Assumptions). Agent adoption is
confined to the agents' existing assistive seams — `ticket_classifier.py` / `response_drafter.py`
for CRA, and a thin summarization call in billing/risk `service.py` — keeping each binding engine
untouched. Tests mirror the foundation/agent split already used in the repo.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| New dependency: `boto3` (`[llm]` extra) | The constitution mandates Bedrock LLMs **via the AWS SDK** with prompt caching; boto3 `bedrock-runtime` is that SDK and the only way to satisfy FR-002/FR-013. | A non-AWS HTTP client would violate the AI-SDK constraint; rolling our own SigV4 signer is strictly more complex and risk-prone than the official SDK. Isolated behind the Bedrock provider and an optional extra, so the offline core needs it not at all. |
| Optional deps: `langgraph` / `langchain-aws` (`[langgraph]` extra) | The feature input requires **LangGraph-compatible invocation** so graph-based agents can call the runtime as a node. | Hard-coupling the runtime to LangGraph would force the dependency on every agent and on CI. Rejected in favor of an `as_node()` adapter that exposes a graph-shaped callable; the package imports LangGraph lazily only when that path is used. |
| Optional dep: `bedrock-agentcore` (already present, optional) | Feature input requires **local AgentCore CLI execution**; the agents already ship `agentcore_app.py` entrypoints, and reusing them keeps a single local-invocation story. | A second bespoke local-invocation mechanism would duplicate what AgentCore already provides and diverge from the agents' existing entrypoints. Kept optional and import-guarded exactly as the current `agentcore_app.py` files are. |
| Assistive-result idempotency store (compacted Kafka topic) | FR-008 requires recorded results to survive redelivery within the workflow so replay is served from the recorded result. | Pure in-memory caching would not survive process restart/redelivery and would break replay determinism (Principle III). Mirrors the existing `IdempotencyTracker` rather than introducing a new datastore. |

> Note on transport: the constitution's *default* transport is an in-memory queue with Redis as the
> permitted swap. This project already standardized on Kafka in `001-event-foundation` (justified in
> that feature's plan); this feature adds **no** new transport — it reuses the existing Kafka-backed
> audit and idempotency topics only.
