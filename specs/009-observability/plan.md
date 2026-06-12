# Implementation Plan: Observability (LangFuse + OpenTelemetry)

**Branch**: `009-observability` | **Date**: 2026-06-10 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/009-observability/spec.md`
**Steering input**: "Cross-cutting OpenTelemetry-compatible tracing + structured logs + Kafka audit
events + LangFuse for LangGraph/LLM + AgentCore/CloudWatch compatibility; named spans + attributes;
no PII by default; keep Kafka audit events as the replayable record."
**Incorporates**: spec Clarifications Session 2026-06-10 (FR-013…FR-019, SC-007).

## Summary

Add **cross-cutting operational observability** to the decentralized refund PoC by instrumenting the
existing seams with **OpenTelemetry-compatible** spans and routing telemetry to a self-hosted
**LangFuse** backend (LangFuse v3's SDK is OTel-based, so the same instrumentation can later export to
**AgentCore/CloudWatch** — config-only in this PoC, not wired/tested locally; FR-015). The deliverable
is a new in-process `src/agent_foundation/observability/` package plus thin, auto-instrumenting
wrappers so all three agents produce end-to-end traces, metrics, prompts, and evaluations with **no
observability code in agent handlers** (US3, SC-003).

Eight named spans are emitted (FR-013): four at **foundation transport/runtime seams** —
`event.consume`, `kafka.publish`, `a2a.task.send`, `a2a.task.receive`, plus `llm.invoke` at the LLM
runtime — and three at the **pure deterministic engine entry points** — `ticket.classify`
(`ticket_classifier.classify`), `policy.evaluate` (`rules_engine.evaluate` and
`scoring.assess_signals`), and `case.decision` (`decision_engine.decide`). The engine functions live
in the agent packages but are pure (no I/O); we instrument them with a **foundation-provided
decorator** applied at the function definition — one declarative line, zero logic in handlers or
service orchestration — so SC-003 ("no observability code in handler logic") holds. Every span carries
the FR-014 attributes where applicable: `correlation_id`, `case_id`, `ticket_id`, `agent_id`,
`event_id`, `task_id`, `capability`, `model_id`, `topic`.

Trace context crosses agent boundaries through the **existing event envelope** via an additive,
optional `trace_context` field (W3C `traceparent`), injected on publish and extracted on consume
(FR-001/010/011). **LLM calls become LangFuse generations** carrying model/latency/token-usage/cache
status (FR-005) plus prompts, completions, LangGraph node traces, tool calls, prompt versions, and
evaluation scores (FR-016). **PII is redacted before export** (FR-017/SC-007): prompts/completions are
captured to LangFuse but pass the existing 008 `Redactor` first (default `REDACT_PII=true`,
`LOG_RAW_*=false`); span attributes carry only IDs and non-PII metadata.

**Kafka stays the replayable system of record; LangFuse is the debugging/LLM-observability layer**
(FR-018). The four logical audit events ride the **existing** audit trail — `audit.agent-task.requested`
/ `audit.agent-task.completed` via `write_task_audit` (`agent.audit.v1`), `audit.llm.invocation.completed`
via the existing `emit_llm_invocation_event`, and `audit.policy.decision.completed` added as a thin
`write_audit` emission at the decision boundary (no new topic) — and one **genuinely new** lightweight
liveness event, `system.agent.heartbeat`, is emitted periodically from the foundation runtime loop
(the single new event/topic the clarification permits). The layer is **non-blocking and fail-open**
with a default-on toggle (`AGENT_OBSERVABILITY_ENABLED`, FR-012), and introduces **no supervisor,
router, orchestrator, or decision-maker** (FR-019).

## Technical Context

**Language/Version**: Python 3.12 (`requires-python = ">=3.12"`).

**Primary Dependencies**: pydantic v2, structlog, aiokafka, typer, boto3 (existing). **New**:
`langfuse` (v3, OpenTelemetry-based) as an optional `[observability]` extra; it pulls transitive
`opentelemetry-*` (SDK + API + W3C propagators). The default offline/test path needs **no** new
runtime dependency — when the toggle is off (or `langfuse` is absent) the package short-circuits to
no-op shims. The existing `[langgraph]` extra is reused for the LangFuse `CallbackHandler` graph path.

**Storage**: No new application datastore. Telemetry lives in the self-hosted LangFuse stack
(Postgres + ClickHouse + Redis + MinIO), **out-of-band** — never on the agent coordination path. The
**Kafka** `agent.audit.v1` / `audit.llm.invocation.*` audit trail remains the **system of record**
(FR-018); structlog stdout logging and the audit trail are complemented, not replaced.

**Testing**: pytest + pytest-asyncio. Unit tests `tests/unit/observability/` run fully offline with
the toggle **off** (no LangFuse/OTel network): no-op behavior, `traceparent` round-trip, span-name +
attribute mapping, generation/score mapping, **PII redaction before export**, heartbeat emission, and
the decorator preserving engine return values. Opt-in `tests/integration/observability/` require a
running LangFuse and are **skipped** otherwise (Bedrock opt-in pattern).

**Target Platform**: Local developer workstation / CI (Linux). LangFuse via Docker Compose alongside
the existing Redpanda broker. OTel-compatible spans make a future AWS (AgentCore/CloudWatch) export a
config change, not a code change.

**Project Type**: Single Python project — new shared capability in `src/agent_foundation/`, a
one-line `configure_observability()` per agent `main.py`, and a one-line span decorator per pure
engine function (no handler edits).

**Performance Goals**: Not a throughput feature. Target < 5% added per-case latency (SC-005); spans
batch and flush on a background thread; sampling (`AGENT_OBSERVABILITY_SAMPLE_RATE`) bounds high-volume
overhead. Heartbeat interval is configurable and coarse (seconds).

**Constraints**: Non-blocking/fail-open (FR-008); toggle default-on (FR-012); missing trace context →
new root (FR-010); no new agent; no supervisor/router/orchestrator/decision-maker (FR-019); exactly
**one** new event (`system.agent.heartbeat`); binding decisions and idempotency keys untouched;
**no raw PII exported by default** (FR-017/SC-007); LangFuse out-of-band, Kafka authoritative (FR-018).

**Scale/Scope**: One observability package (~9 modules), 5 foundation seam wrappers + 4 engine
decorators (= 8 named spans), one additive envelope field, one new heartbeat event+emitter, one new
`audit.policy.decision.completed` emission (existing topic), three agent startup-wiring edits, four
engine-decorator annotations, one LangFuse Docker Compose addition, programmatic eval scores + a
documented LLM-as-judge path. Validated under typical PoC load (tens of requests).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Assessment | Status |
|-----------|-----------|--------|
| **I. Agent Autonomy** | No new agent; no supervisor/router/orchestrator/decision-maker (FR-019). Instrumentation is shared-foundation + declarative engine decorators; agents inherit it. Cross-agent telemetry is read only in the out-of-band LangFuse sink, never via an agent. Domain isolation untouched. | PASS |
| **II. Event-Driven Coordination** | Agents still coordinate solely via existing Kafka events. Two additions, both justified in Complexity Tracking: (a) an **additive optional** `EventEnvelope.trace_context` (W3C `traceparent`), backward-compatible, default `None`; (b) exactly **one** new event, `system.agent.heartbeat` (liveness only, no domain payload, not a coordination back-channel) on its own topic. The four audit events reuse the existing audit trail. LangFuse is an out-of-band sink. | PASS (1 new event + additive field, tracked) |
| **III. Idempotency & Safety** | Instrumentation is side-effect-free w.r.t. decisions and idempotency keys; trace IDs are not part of any dedup key, so replay is byte-stable. Engine decorators wrap **pure** functions and must return the identical value. Heartbeat is liveness, never consumed by domain logic. | PASS |
| **IV. Observability-First** | Directly advances Principle IV: OTel-compatible end-to-end traceability + LangFuse LLM observability, **complementing** (not replacing) structlog and the Kafka audit trail, which stays the replayable record (FR-018). | PASS |
| **V. PoC Scope Discipline** | LangFuse is the single wired backend (traces + metrics + prompts + evals); CloudWatch/AgentCore export is config-only/documented, not built (FR-015) — scope held local. No auth/HA hardening. Default-on but fail-open and zero-overhead when off. New deps (`langfuse`, OTel) and the LangFuse container footprint justified and tracked. | PASS (with tracked deps) |

**Gate result: PASS.** No unjustified violations. Re-evaluated post-design (Phase 1) — still PASS:
the heartbeat is the only new event, the envelope change is additive, and engine decorators add no
handler logic.

## Project Structure

### Documentation (this feature)

```text
specs/009-observability/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── observability-api.md         # public surface + OTel/LangFuse exporter posture
│   ├── span-catalog.md              # the 8 named spans, their seams, and FR-014 attributes
│   ├── trace-context-propagation.md # envelope trace_context + W3C inject/extract + seam wrappers
│   ├── llm-generation-attributes.md # AssistiveResult/TokenUsage → generation + scores + PII redaction
│   ├── prompt-management.md         # LangFuse prompt registration/fetch with local-template fallback
│   ├── evaluation-scores.md         # programmatic scores + LLM-as-judge dataset/config
│   ├── kafka-audit-events.md        # 4 logical audit events → existing trail + heartbeat (new event)
│   └── observability-config.md      # env toggles + LangFuse Docker Compose contract
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
src/agent_foundation/
└── observability/                # NEW shared observability package
    ├── __init__.py               # public surface: configure_observability(), span(), generation(), score(), traced
    ├── config.py                 # ObservabilityConfig.from_env(): toggle, keys, host, sample rate, heartbeat interval
    ├── client.py                 # guarded OTel/LangFuse client singleton; no-op fallback when off/unavailable
    ├── tracing.py                # span()/generation() context managers; OTel-compatible; fail-open; flush()
    ├── propagation.py            # W3C traceparent inject→envelope / extract→context (FR-001/010/011)
    ├── attributes.py             # FR-014 attribute assembly from envelope/task/case (IDs + non-PII metadata)
    ├── decorators.py             # @traced(span_name) for pure engine entry points (FR-013 domain spans)
    ├── scores.py                 # AssistiveResult → eval scores (schema_valid, used_fallback, cache_hit…)
    ├── prompts.py                # LangFuse prompt fetch w/ local PromptTemplate fallback (non-blocking)
    └── heartbeat.py              # periodic system.agent.heartbeat emitter (driven by runtime serve loop)

src/agent_foundation/             # EDITS (additive, backward-compatible)
├── envelope.py                   # EDIT: add optional trace_context: dict[str,str] | None = None
├── transport/publisher.py        # EDIT: wrap publish()/publish_raw() — span "kafka.publish" + inject traceparent
├── transport/consumer.py         # EDIT: wrap handler dispatch — extract traceparent, span "event.consume"
├── transport/topics.py           # EDIT: add TOPIC_HEARTBEAT (system.agent.heartbeat)
├── runtime/client.py             # EDIT: wrap A2AClient.submit() — span "a2a.task.send"
├── runtime/runtime.py            # EDIT: wrap handler dispatch — span "a2a.task.receive"; drive heartbeat in serve()
├── audit/store.py                # EDIT: add audit.policy.decision.completed emission via existing write_audit
└── llm/
    ├── runtime.py                # EDIT: LLMRuntime.reason() — span "llm.invoke" (generation) + scores + redacted I/O
    ├── factory.py                # EDIT: thread ObservabilityConfig into runtime
    ├── redaction.py              # REUSE: Redactor.scrub() applied to prompts/completions before LangFuse export
    └── langgraph.py              # EDIT(optional): expose LangFuse CallbackHandler wiring for graph runs

apps/agents/                      # EDITS: startup wiring + declarative engine decorators (no handler logic)
├── customer_resolution/
│   ├── main.py / agent.py        # EDIT: configure_observability() at startup
│   ├── ticket_classifier.py      # EDIT: @traced("ticket.classify") on classify()
│   └── decision_engine.py        # EDIT: @traced("case.decision") on decide()
├── billing_entitlement/
│   ├── main.py                   # EDIT: configure_observability() at startup
│   └── rules_engine.py           # EDIT: @traced("policy.evaluate") on evaluate()
└── risk_fraud/
    ├── main.py                   # EDIT: configure_observability() at startup
    └── scoring.py                # EDIT: @traced("policy.evaluate") on assess_signals()

infra/local/
├── docker-compose.langfuse.yml   # NEW: self-hosted LangFuse stack (web, worker, postgres, clickhouse, redis, minio)
├── run-demo-agents.sh            # EDIT: optionally bring up LangFuse; export LANGFUSE_*/observability env
└── .env.langfuse.example         # NEW: LANGFUSE_* + AGENT_OBSERVABILITY_* env template

tests/
├── unit/observability/           # offline, toggle OFF — no LangFuse/OTel network
│   ├── test_toggle_noop.py
│   ├── test_traceparent_roundtrip.py
│   ├── test_span_catalog.py           # 8 span names + FR-014 attributes assembled correctly
│   ├── test_engine_decorator.py       # @traced preserves pure-function return value; span emitted
│   ├── test_generation_attributes.py
│   ├── test_pii_redaction.py          # prompts/completions redacted before export (SC-007)
│   ├── test_heartbeat.py              # periodic system.agent.heartbeat emitted with agent_id
│   └── test_prompt_fallback.py
└── integration/observability/    # opt-in; SKIPPED without a running LangFuse
    └── test_e2e_trace_appears.py
```

**Structure Decision**: Single-project layout. Observability is a **new sub-package of the shared
foundation** (`src/agent_foundation/observability/`) beside `audit/`, `transport/`, `runtime/`, and
`llm/`. Five spans are emitted by **foundation seam wrappers** (transport + runtime + LLM). The three
**domain spans** are emitted by a **foundation-provided `@traced` decorator** applied at the four pure
engine entry points; although those functions physically live in `apps/agents/*`, they are pure
(no I/O) and the decorator is a single declarative annotation — handler and service-orchestration code
remain free of observability logic, satisfying SC-003. The heartbeat emitter is driven by the existing
`runtime.serve()` loop so every agent gets liveness with no per-agent code. Tests mirror the
foundation unit/integration split and the Bedrock opt-in skip pattern.

> **Note on FR-002 wording vs. reality**: the spec says engines are instrumented "at the
> foundation/shared level." The engine *functions* live in agent packages, so the instrumentation
> *mechanism* (the `@traced` decorator and all span logic) is foundation-owned and the only per-engine
> footprint is one annotation line. This preserves the intent — no per-call boilerplate, no handler
> logic — while being accurate about where the pure functions sit.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| New dependency: `langfuse` v3 + transitive `opentelemetry-*` (`[observability]` extra) | LangFuse for LLM/LangGraph traces, prompts, token usage, evals (FR-005/006/016) on an OTel-compatible base that can later export to AgentCore/CloudWatch (FR-015). | A bespoke OTLP exporter to a generic collector still needs a viewer + dashboards + prompt store + eval store — i.e., re-implementing LangFuse. A separate Jaeger + Prometheus/Grafana stack is more services for less LLM capability. Isolated behind an optional extra; offline/test path no-ops. |
| Self-hosted LangFuse multi-container stack (web, worker, Postgres, ClickHouse, Redis, MinIO) | FR-006/007/009 require a local browser-accessible viewer + dashboards launched with the standard command; v3's self-host topology is these containers. | LangFuse Cloud violates "stay local" + needs network/keys. v2 single-container lacks the v3 prompt/eval/dashboard features. Added as a separate compose file; fail-open if absent. |
| Additive optional `EventEnvelope.trace_context` | FR-001/011 require W3C span parentage to cross agents so multi-agent workflows form one trace. | `correlation_id`/`causation_id` cannot carry span parentage. Putting `traceparent` in the domain `payload` pollutes per-event schemas. Optional default-`None` field is the minimal backward-compatible change (old events → new root, FR-010). |
| **One new event + topic: `system.agent.heartbeat`** | FR-018 requires keeping liveness as a Kafka signal; no heartbeat exists today. Emitted periodically from the foundation runtime loop so every agent reports liveness with no per-agent code. | Reusing the compacted audit topic would discard heartbeat history (compaction keeps latest-per-key) and conflate liveness with audit. A dedicated lightweight topic is cleaner. This is the **single** new event the clarification permits; logged here per Principle II. |
| New audit emission `audit.policy.decision.completed` on the **existing** audit topic | FR-018 lists it as a retained audit event; it is the one logical name not yet emitted. | Adding a new topic/contract is unnecessary — the decision boundary already publishes a decision event; we add a thin `write_audit` emission on `TOPIC_AUDIT` (no new topic), keeping the four audit events on the existing trail. |
| Programmatic eval scores from the LLM runtime | FR-016 "evaluation scores"; links LLM quality to traces without human labeling, including offline runs. | Manual-only UI evaluation leaves default/CI runs with no quality signal. Scores are **non-binding** (never re-enter a decision — FR-019) and best-effort. |

> Note on transport & coordination: this feature adds **no** new *coordination* event. The heartbeat
> is liveness-only and never consumed by domain logic; LangFuse is an out-of-band HTTP sink, never on
> the agent-to-agent path. Kafka (`agent.audit.v1` + `audit.llm.invocation.*` + the new heartbeat) is
> the replayable record (FR-018); LangFuse is the debugging/LLM-observability view.
