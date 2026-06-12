# Phase 0 Research: Observability (LangFuse)

This document resolves the open technical questions for instrumenting the refund PoC with LangFuse.
Each decision records what was chosen, why, and the alternatives rejected. There are no remaining
`NEEDS CLARIFICATION` items after this phase.

## R1. Observability backend: one tool or several?

**Decision**: Use **LangFuse v3 (self-hosted)** as the single backend for traces, metrics dashboards,
prompt management, and evaluations. Do **not** add Jaeger/Tempo (traces) or Prometheus/Grafana
(metrics) as separate systems.

**Rationale**:
- The steering input explicitly names LangFuse for LLM/LangGraph traces, prompts, token usage, and
  evaluations.
- LangFuse's v3 Python SDK is built on OpenTelemetry, so non-LLM operations (event publish/consume,
  A2A delegation) can be recorded as ordinary nested spans, while LLM calls are recorded as
  **generations** with model/latency/token/cost attributes. One SDK covers both FR-003 (generic
  spans) and FR-005 (LLM specifics).
- LangFuse ships built-in **dashboards** (trace/observation counts, latency percentiles, token/cost,
  score aggregates) that satisfy the per-agent metrics view (FR-004/FR-007) when traces are tagged
  with the agent identity and operation, removing the need for a parallel Prometheus/Grafana stack.
- One backend = fewer containers, one URL set, one mental model — directly serving Principle V
  (PoC Scope Discipline).

**Alternatives considered**:
- *OTel Collector → Jaeger + Prometheus + Grafana*: industry-standard, but three more services plus
  dashboard authoring, and no native prompt/eval store — we would still need LangFuse for the LLM
  features the steering input asks for. Rejected as strictly more complexity for less LLM capability.
- *LangFuse Cloud (free tier)*: zero local footprint, but violates the spec's "without leaving the
  local development environment," requires outbound network and account keys, and couples CI to an
  external service. Rejected for the default; the same SDK/env can point at cloud if a developer opts
  in.

## R2. LangFuse deployment topology for local dev

**Decision**: Add LangFuse's **official self-hosted v3 stack** as a dedicated
`infra/local/docker-compose.langfuse.yml`: `langfuse-web`, `langfuse-worker`, `postgres`,
`clickhouse`, `redis`, and `minio` (S3-compatible blob store). It is launched alongside the existing
Redpanda broker by the standard startup path (FR-009) but kept in a **separate compose file** so the
broker + agents still run if it is omitted.

**Rationale**:
- v3 separates ingestion (worker) from serving (web), uses ClickHouse for analytics-grade trace
  queries, Redis for queues/caching, and S3/MinIO for large payloads — this topology is what unlocks
  the dashboards, prompt store, and eval features (R1).
- A separate compose file keeps the footprint opt-in and makes "stop cleanly with no orphaned state"
  (FR/AC US4-2) a simple `docker compose -f docker-compose.langfuse.yml down -v`.

**Alternatives considered**:
- *LangFuse v2 single container + Postgres*: much smaller footprint, but v2 is the legacy line and
  lacks the v3 dashboard/eval ergonomics the steering input wants. Rejected.
- *Bake LangFuse services into the existing `docker-compose.yml`*: couples broker lifecycle to the
  heavier stack and makes the "broker-only" path impossible. Rejected in favor of a second file.

**Footprint is logged** in plan.md Complexity Tracking as a justified deviation.

## R3. Cross-agent trace context propagation

**Decision**: Propagate **W3C Trace Context** (`traceparent`, optional `tracestate`) by adding an
**additive, optional** `trace_context: dict[str, str] | None = None` field to `EventEnvelope`
(`src/agent_foundation/envelope.py`). Inject on publish, extract on consume.

**Rationale**:
- `correlation_id`/`causation_id` already group a case, but they do not encode span parentage, so
  spans emitted by different agents would not nest into one trace. W3C `traceparent` carries the
  trace-id + parent span-id that LangFuse/OTel need to stitch a single end-to-end trace (FR-001).
- An optional field defaulting to `None` is backward-compatible: envelopes serialized before this
  feature still validate, and a consumer that finds no `trace_context` simply starts a **new trace
  root** (FR-010), never dropping the event.
- The field is linked back to the audit subsystem because the same envelope still carries
  `correlation_id`/`causation_id`, satisfying FR-011 (spans include those IDs as attributes).

**Alternatives considered**:
- *Embed `traceparent` in the domain `payload` dict*: payloads are per-event-type Pydantic-validated;
  injecting transport metadata there pollutes every domain schema. Rejected.
- *Kafka record headers*: aiokafka supports headers, but the codebase serializes a self-contained
  `EventEnvelope` JSON as the record value and validates that; routing context through headers would
  bypass the envelope-as-contract pattern and complicate the in-memory/replay paths. Rejected for
  consistency with the existing envelope-centric design.

## R4. Foundation-level auto-instrumentation seams (no per-agent code)

**Decision**: Wrap exactly four existing foundation seams; agents inherit instrumentation by using
them (US3, SC-003). The only agent edit is a single `configure_observability()` call at startup.

| Seam | File / entry | Span kind |
|------|--------------|-----------|
| Event publish | `transport/publisher.py` → `publish()` / `publish_raw()` | producer span; **inject** `traceparent` into envelope |
| Event consume | `transport/consumer.py` → handler dispatch (`await handler(envelope)`) | consumer span; **extract** `traceparent`, run handler within context |
| A2A delegate (send) | `runtime/client.py` → `A2AClient.submit()` | client span `a2a.delegate {capability}` |
| A2A handle (receive) | `runtime/runtime.py` → handler dispatch in `_handle_message()` | server span `a2a.handle {capability}` (child of caller via propagated context) |
| LLM reason | `llm/runtime.py` → `LLMRuntime.reason()` | **generation** (model, latency, tokens, cache hit) + eval scores |

**Rationale**: These five points are the only places cross-agent work crosses a process or library
boundary, so instrumenting them yields complete traces with no handler-level boilerplate. The wrappers
live in `observability/instrument.py` and are imported by the foundation modules, keeping LangFuse
imports out of the hot domain code paths.

**Alternatives considered**:
- *Per-handler decorators in each agent*: violates US3/SC-003 and adds maintenance to every agent.
  Rejected.
- *OpenTelemetry auto-instrumentation libraries (e.g., aiokafka instrumentor)*: would trace Kafka
  client mechanics but not the agent-semantic operations (capability, task, verdict) we care about,
  and would not inject our envelope `trace_context`. Rejected in favor of explicit semantic spans.

## R5. LLM generation attributes, token usage, and cache hit

**Decision**: In `LLMRuntime.reason()`, emit a LangFuse **generation** populated from the existing
result objects: `model_id`, `latency_ms`, `TokenUsage` (`input_tokens`, `output_tokens`,
`cache_read_tokens`, `cache_write_tokens`), `cache_hit`, `task_kind`, `agent_id`, and the validated
output presence/`failure_reason`. Token usage maps to LangFuse's `usage`/cost fields so the dashboards
compute per-agent token and (when configured) cost aggregates (FR-005).

**Rationale**: 008 already captures all of this on `RawCompletion`/`AssistiveResult`/`TokenUsage`
(`llm/result.py`, `llm/providers/base.py`); the work is a mapping, not new measurement. The stub
provider yields zero/no-token generations tagged to indicate no real model call (spec edge case:
stub fallback still appears in traces).

**Alternatives considered**: Recomputing token counts in the observability layer — rejected;
the provider already returns authoritative usage.

## R6. Prompt management

**Decision**: Register the 008 runtime prompts in LangFuse **Prompt Management** and fetch them via
the SDK (client-side cached) so each generation links to a prompt name + version for analytics. The
**in-code `PromptTemplate` (`llm/prompts.py`) remains the runtime source of truth and fallback**: if
LangFuse is disabled or the fetch fails, the runtime uses the local template unchanged.

**Rationale**: Gives prompt versioning/diffing and links prompt → generation → score in the LangFuse
UI (the "prompts" half of the steering input) without making an external service authoritative for a
value the deterministic/offline path depends on. This preserves offline-first behavior and
non-blocking guarantees (FR-008).

**Alternatives considered**: Making LangFuse the authoritative prompt store — rejected; it would break
the offline stub/test path and add a network dependency to a hot path. Prompt-cache `cache_control`
breakpoints from 008 are preserved regardless of source.

## R7. Evaluations

**Decision**: Two layers, both **non-binding** (never fed back into any decision — assistive-only
boundary preserved):
1. **Programmatic scores** pushed from `reason()` per generation: `schema_valid` (1/0 from the
   validate-and-repair loop), `used_fallback` (1/0), `cache_hit` (1/0), and `latency_ms`. These give
   every run — including offline stub runs — an objective quality/health signal on the trace.
2. **LLM-as-judge** evaluators configured in the LangFuse UI over a small seeded **dataset** of
   representative assistive tasks (e.g., draft tone/faithfulness, summary grounding). Documented as an
   opt-in workflow; not required for the default offline suite.

**Rationale**: Covers the "evaluations" half of the steering input at two altitudes — automatic,
always-on signals and richer human/judge evaluation — without ever letting an eval outcome influence a
binding refund decision.

**Alternatives considered**: Only manual UI evaluation — rejected; offline/CI runs would carry no
quality signal. Feeding eval scores back into agent logic — rejected; violates the LLM-assistive
boundary inherited from 008 and the constitution.

## R8. LangGraph tracing

**Decision**: Because `LLMRuntime.reason()` is instrumented (R5), the 008 `as_node` adapter's node
executions already emit generations. Additionally expose LangFuse's **`CallbackHandler`** wiring
(optional, behind the existing `[langgraph]` extra) so a full compiled-graph run nests under a single
LangFuse trace. Documented as opt-in for graph-based agents.

**Rationale**: Satisfies "LangGraph traces" with no hard LangGraph dependency on the core path,
matching 008's lazy-import posture.

**Alternatives considered**: Forcing every agent through LangGraph to get traces — rejected; most
agents call `reason()` directly and get generations without a graph.

## R9. Non-blocking, fail-open, and the enable toggle

**Decision**: A global `ObservabilityConfig.from_env()` reads `AGENT_OBSERVABILITY_ENABLED`
(default `true`, FR-012) plus `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_HOST` and an
optional sample rate. The LangFuse client is initialized once, **guarded**; if disabled, keys are
missing, or `langfuse` is not installed, every span/generation/score helper becomes a **no-op**. All
helpers are wrapped so SDK/network errors are caught and logged at debug, never raised. The SDK
flushes on a background thread; a `flush()` is called on graceful shutdown.

**Rationale**: Directly meets FR-008 (backend unavailable → agents continue), FR-012 (toggle, default
on), SC-005 (<5% overhead — no-op when off, bounded constant work when on), and SC-006 (backend
stopped → no errors). Mirrors the existing 008 provider-selection and agent boolean-flag config
patterns (`RuntimeConfig.from_env`, `BILLING_LLM_SUMMARY_ENABLED`).

**Alternatives considered**: Synchronous span export — rejected; would add per-call network latency
and could block on backend outage, violating FR-008/SC-005/SC-006.

## R10. Configuration & startup wiring

**Decision**: Env-driven config following the established pattern. Agents call
`configure_observability()` once in `main.py` beside `configure_logging()`. The startup script
(`infra/local/run-demo-agents.sh`) optionally brings up `docker-compose.langfuse.yml` and exports the
`LANGFUSE_*` env so the three `uv run demo-*` agents register against the local LangFuse. A
`.env.langfuse.example` documents all variables.

**Rationale**: Keeps observability a process-startup concern (one line per agent, no handler edits —
US3/SC-003) and makes "launch with the standard startup command" (FR-009/SC-004) true without new
developer steps.

## Dependency & version summary

| Dependency | Where | Justification |
|------------|-------|---------------|
| `langfuse` (v3) + transitive `opentelemetry-*` | optional `[observability]` extra | LLM-native traces/prompts/token usage/evals (steering input, FR-005/006/007). Lazy-imported; no-op when off. |
| LangFuse self-host containers (web, worker, postgres, clickhouse, redis, minio) | `infra/local/docker-compose.langfuse.yml` | Local browser-accessible viewer + dashboards launched with standard command (FR-006/007/009). |
| `langfuse.langchain.CallbackHandler` | reuse existing `[langgraph]` extra | Full LangGraph-run traces (steering input), opt-in. |

All additions are logged in plan.md Complexity Tracking. No change to the constitution's Kafka
transport, the audit topic, or the idempotency machinery.

---

## Clarification-driven decisions (Session 2026-06-10)

These resolve the four `/speckit-clarify` answers and supersede any narrower earlier wording.

### R11. OpenTelemetry-compatible instrumentation; LangFuse default exporter; CloudWatch config-only

**Decision**: Build spans with **OpenTelemetry-compatible** semantics (OTel SDK + W3C propagation;
LangFuse v3's SDK is itself OTel-based). The **only wired exporter in this PoC is LangFuse**.
AgentCore/CloudWatch export is **configuration-only and documented** — selecting an OTLP→CloudWatch/
X-Ray exporter is a deploy-time config change, not new code, and is not built or tested locally
(FR-015).

**Rationale**: Satisfies "OTel-compatible + AgentCore/CloudWatch compatibility" without dragging an
AWS exporter, IAM, and X-Ray into the local PoC (Principle V). Because instrumentation is OTel-native,
the future AWS path is a config switch.

**Alternatives considered**: Wiring CloudWatch/X-Ray now (rejected — out of PoC scope, needs AWS);
structural-only naming with no OTel SDK (rejected — would not actually be exportable).

### R12. Domain spans via a foundation-provided decorator on pure engine entry points

**Decision**: Emit `ticket.classify`, `policy.evaluate`, and `case.decision` (FR-013) by applying a
foundation-owned `@traced(span_name)` decorator at the definition of the **pure** engine functions:
`apps/agents/customer_resolution/ticket_classifier.py::classify`,
`apps/agents/billing_entitlement/rules_engine.py::evaluate` and
`apps/agents/risk_fraud/scoring.py::assess_signals` (both → `policy.evaluate`, distinguished by
`agent_id`), and `apps/agents/customer_resolution/decision_engine.py::decide` (→ `case.decision`).

**Rationale**: The engines are pure (no I/O), so a decorator that opens a span, runs the function, and
returns its **unchanged** value is side-effect-free (Principle III) and adds **zero** logic to
handlers or service orchestration (SC-003). The decorator and all span logic are foundation-owned; the
per-engine footprint is one annotation line.

**Alternatives considered**: Wrapping at call sites in handlers/services (rejected — puts observability
code adjacent to handler logic, weakening SC-003); dropping domain spans (rejected — loses the
classify/policy/decision timing the steering input explicitly asked for). Note the spec's
"foundation/shared level" phrasing is honored by mechanism, not physical location (see plan Structure
Decision note).

### R13. Heartbeat: one new liveness event from the runtime loop

**Decision**: Add `system.agent.heartbeat` as the single new event, emitted periodically from the
**foundation** `runtime.serve()` loop (`src/agent_foundation/runtime/runtime.py`) via a new
`observability/heartbeat.py` emitter, on a dedicated lightweight `TOPIC_HEARTBEAT`. No heartbeat
exists today. Interval is configurable (default coarse, seconds).

**Rationale**: Every agent already runs the foundation serve loop, so one emitter gives all agents
liveness with no per-agent code. A dedicated topic avoids polluting the **compacted** audit topic
(which would discard heartbeat history) and keeps liveness semantically separate from audit.

**Alternatives considered**: Heartbeat on the audit topic (rejected — compaction drops history,
conflates concerns); heartbeat as a structlog/metric only (rejected — the steering input explicitly
lists it as a Kafka event to keep). This is the one new event Principle II is amended to allow.

### R14. Kafka audit events mapping (Kafka = system of record, LangFuse = debug)

**Decision**: Realize the four retained audit events on the **existing** trail (FR-018):

| Logical audit event | Realization (existing unless noted) |
|---------------------|--------------------------------------|
| `audit.agent-task.requested` | `write_task_audit(..., outcome="requested")` on `agent.audit.v1` |
| `audit.agent-task.completed` | `write_task_audit(..., outcome="completed")` on `agent.audit.v1` |
| `audit.llm.invocation.completed` | existing `emit_llm_invocation_event` (`audit.llm.invocation.completed`) |
| `audit.policy.decision.completed` | **new** thin `write_audit` emission at the decision boundary, **same** `TOPIC_AUDIT` (no new topic) |

**Rationale**: Three already exist; only `audit.policy.decision.completed` is missing and is added as a
small emission on the existing audit topic — no new contract/topic. LangFuse never becomes the record
of business truth; it is the debugging/LLM-observability layer.

**Alternatives considered**: Promoting all four to new typed events/topics (rejected — unnecessary new
contracts); moving audit into LangFuse (rejected — violates FR-018 and the constitution's Kafka
audit requirement).

### R15. PII: capture prompts/completions but redact before export

**Decision**: Per the clarification, LLM **prompts and completions ARE captured to LangFuse**, but the
existing 008 `Redactor` (`src/agent_foundation/llm/redaction.py`) runs on them **before export**, gated
by the existing config toggles (`REDACT_PII` default `true`; `LOG_RAW_LLM_PROMPTS` /
`LOG_RAW_LLM_OUTPUTS` default `false`). Span attributes carry only IDs + non-PII metadata
(FR-014/FR-017/SC-007).

**Rationale**: Reuses the audited, tested redaction path already in the runtime rather than building a
second redactor; default config means no raw customer PII leaves the process. Setting `LOG_RAW_*=true`
is an explicit developer opt-in for local debugging.

**Alternatives considered**: IDs-only (never sending prompt/completion text) — rejected by the user in
favor of redacted capture, which preserves prompt-debugging value while protecting PII. Building a new
redaction subsystem — rejected (duplicates `Redactor`).

### R16. Span catalog & attributes (FR-013/FR-014)

**Decision**: Eight named spans, sourced as below; each populated with the FR-014 attributes **where
applicable** (absent attributes are omitted, not blank):

| Span | Seam / entry point | Key attributes present |
|------|--------------------|------------------------|
| `event.consume` | `transport/consumer.py` dispatch | correlation_id, causation_id, event_id, agent_id, topic |
| `kafka.publish` | `transport/publisher.py` publish/raw | correlation_id, event_id, agent_id, topic |
| `a2a.task.send` | `runtime/client.py` `submit()` | correlation_id, task_id, capability, agent_id |
| `a2a.task.receive` | `runtime/runtime.py` dispatch | correlation_id, task_id, capability, agent_id |
| `llm.invoke` | `llm/runtime.py` `reason()` (generation) | correlation_id, agent_id, model_id, task_id?, cache_hit, tokens |
| `ticket.classify` | `ticket_classifier.classify` (`@traced`) | correlation_id, case_id, ticket_id, agent_id |
| `policy.evaluate` | `rules_engine.evaluate` / `scoring.assess_signals` (`@traced`) | correlation_id, case_id, agent_id, capability |
| `case.decision` | `decision_engine.decide` (`@traced`) | correlation_id, case_id, ticket_id, agent_id |

`case_id`/`ticket_id` are first-class on the customer-resolution `ResolutionCase` and arrive via task
input for billing/risk; `task_id`/`capability` are first-class on `TaskRequest`/`TaskResult`;
`correlation_id`/`causation_id`/`event_id`/`topic` come from the envelope. Attribute assembly lives in
`observability/attributes.py` and pulls only non-PII fields (R15).

**Rationale**: Centralizing attribute assembly keeps the FR-014 contract in one place and guarantees no
PII field is added. "Where applicable" avoids forcing irrelevant attributes onto spans that lack them
(e.g., no `task_id` on a pure publish).
