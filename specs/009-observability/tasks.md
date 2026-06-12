---
description: "Task list for Observability (LangFuse + OpenTelemetry) feature implementation"
---

# Tasks: Observability (LangFuse + OpenTelemetry)

**Input**: Design documents from `/specs/009-observability/`

**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

**Tests**: Test tasks ARE included — the plan's Technical Context explicitly enumerates an offline
`tests/unit/observability/` suite (toggle OFF) and an opt-in `tests/integration/observability/` suite.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

> **Steering note — "Add structured JSON logging"**: structlog JSON output to stdout already exists
> (`src/agent_foundation/logging.py` → `JSONRenderer`). The additive work for this feature is
> **trace-correlation enrichment** of those JSON logs (bind `trace_id`/`span_id`/`correlation_id` into
> every log line so logs join the LangFuse trace). These tasks are marked `[JSONLOG]` for traceability.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4)
- Include exact file paths in descriptions

## Path Conventions

Single Python project: source in `src/agent_foundation/`, agents in `apps/agents/`, tests in `tests/`,
local infra in `infra/local/`. Paths below follow the plan.md structure.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project scaffolding for the observability package, optional dependency, and test layout.

- [x] T001 Add `[observability]` optional extra (`langfuse` v3, pulls transitive `opentelemetry-*`) to `pyproject.toml`; confirm core install + default test suite do NOT require it
- [x] T002 [P] Create the observability package skeleton (empty/stub modules) in `src/agent_foundation/observability/`: `__init__.py`, `config.py`, `client.py`, `tracing.py`, `propagation.py`, `attributes.py`, `decorators.py`, `scores.py`, `prompts.py`, `heartbeat.py`
- [x] T003 [P] Create `infra/local/.env.langfuse.example` with `AGENT_OBSERVABILITY_*`, `LANGFUSE_*`, and reused `REDACT_PII`/`LOG_RAW_*` vars per contracts/observability-config.md
- [x] T004 [P] Create test package dirs `tests/unit/observability/` and `tests/integration/observability/` with `__init__.py` and a `conftest.py` that forces the toggle OFF by default for unit tests

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The observability primitives every user story builds on — config, guarded client, span
machinery, context propagation, attribute assembly, the `@traced` decorator, and the public surface.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T005 Add additive optional `trace_context: dict[str, str] | None = None` field to `EventEnvelope` in `src/agent_foundation/envelope.py`; confirm it is excluded from idempotency/dedup keys and audit equality (data-model.md "Modified existing entity")
- [x] T006 [P] Implement `ObservabilityConfig` + `from_env()` (toggle, keys, host, sample_rate clamp, environment, heartbeat interval, exporter) in `src/agent_foundation/observability/config.py` per data-model.md
- [x] T007 Implement the guarded LangFuse/OTel client singleton with no-op fallback (disabled / keys missing / `langfuse` unimportable) in `src/agent_foundation/observability/client.py` (depends on T006)
- [x] T008 Implement `span()` / `generation()` context managers (set_attribute, record_exception, status=error+re-raise on body exception, swallow machinery errors) and `flush()` in `src/agent_foundation/observability/tracing.py` (depends on T007)
- [x] T009 [P] Implement FR-014 attribute assembly (`correlation_id`, `causation_id`, `event_id`, `case_id`, `ticket_id`, `task_id`, `capability`, `agent_id`, `model_id`, `topic`; IDs + non-PII only) in `src/agent_foundation/observability/attributes.py`
- [x] T010 [P] Implement W3C `inject`/`extract`, `current_trace_context()`, and `start_consumer_span()` (new root when absent — FR-010) in `src/agent_foundation/observability/propagation.py`
- [x] T011 Implement the `@traced(span_name)` decorator (returns wrapped value unchanged, status=error+re-raise, no-op when off) in `src/agent_foundation/observability/decorators.py` (depends on T008)
- [x] T012 [P] Implement programmatic score helpers (`schema_valid`, `used_fallback`, `cache_hit`, `latency_ms`; write-only, non-binding) in `src/agent_foundation/observability/scores.py`
- [x] T013 [P] Implement LangFuse prompt fetch with local `PromptTemplate` fallback (non-blocking) in `src/agent_foundation/observability/prompts.py`
- [x] T014 Implement the public surface (`configure_observability`, `span`, `generation`, `traced`, `score`, `current_trace_context`, `start_consumer_span`, `flush`) in `src/agent_foundation/observability/__init__.py` (depends on T007–T013)
- [x] T015 [JSONLOG] Add a structlog processor that injects the active `trace_id`/`span_id` (when a span is active, else omit) into every JSON log line in `src/agent_foundation/logging.py`, keeping the existing `JSONRenderer` and no-op behavior when observability is off
- [x] T016 [P] Unit test for no-op mode (toggle OFF / keys missing → calls never raise, bodies still run) in `tests/unit/observability/test_toggle_noop.py`

**Checkpoint**: Foundation ready — user stories can now begin.

---

## Phase 3: User Story 1 - Trace a Refund Case End to End (Priority: P1) 🎯 MVP

**Goal**: A single hierarchical trace spans all three agents from intake to decision, built from the
eight named spans with parent-child links and FR-014 attributes, searchable by correlation/case ID.

**Independent Test**: Submit a refund case, open LangFuse → Traces, search by correlation ID, and
confirm one hierarchical trace with per-agent spans (operation, duration, status, parent-child links).

### Tests for User Story 1 ⚠️

- [x] T017 [P] [US1] Trace-context round-trip test (`inject(S) → envelope.trace_context → extract` parents to S; `None` → new root) in `tests/unit/observability/test_traceparent_roundtrip.py`
- [x] T018 [P] [US1] Span-catalog test asserting the 8 named spans and their applicable FR-014 attributes in `tests/unit/observability/test_span_catalog.py`
- [x] T019 [P] [US1] `@traced` decorator test (engine return value preserved, span emitted, error span on exception) in `tests/unit/observability/test_engine_decorator.py`

### Implementation for User Story 1

- [x] T020 [US1] Wrap `publish()`/`publish_raw()` with a `kafka.publish` span and set `trace_context = current_trace_context()` on the envelope before serialization in `src/agent_foundation/transport/publisher.py`
- [x] T021 [US1] Wrap handler dispatch with `start_consumer_span(...)` emitting `event.consume` (extract parent, new root if absent) in `src/agent_foundation/transport/consumer.py`
- [x] T022 [P] [US1] Wrap `A2AClient.submit()` with an `a2a.task.send` span (attrs `capability`, `task_id`) in `src/agent_foundation/runtime/client.py`
- [x] T023 [P] [US1] Wrap runtime handler dispatch with an `a2a.task.receive` span opened from the request envelope's `trace_context` in `src/agent_foundation/runtime/runtime.py`
- [x] T024 [P] [US1] Apply `@traced("ticket.classify")` to `classify()` in `apps/agents/customer_resolution/ticket_classifier.py` and `@traced("case.decision")` to `decide()` in `apps/agents/customer_resolution/decision_engine.py`
- [x] T025 [P] [US1] Apply `@traced("policy.evaluate")` to `evaluate()` in `apps/agents/billing_entitlement/rules_engine.py` and to `assess_signals()` in `apps/agents/risk_fraud/scoring.py`
- [x] T026 [US1] Add an `llm.invoke` generation span (model, latency, status) around `LLMRuntime.reason()` in `src/agent_foundation/llm/runtime.py` so LLM calls appear as child spans (AC US1-3 structural)
- [x] T027 [JSONLOG] [US1] Bind the active trace/correlation context into structlog contextvars at the consume seam so each case's JSON log lines carry `trace_id`/`correlation_id`, wired in `src/agent_foundation/transport/consumer.py`

**Checkpoint**: An end-to-end trace appears in LangFuse for a driven case; logs carry the trace id.

---

## Phase 4: User Story 2 - Monitor Agent Health and Performance Metrics (Priority: P1)

**Goal**: Per-agent request/latency/error metrics and LLM token/latency/cache metrics are available in
LangFuse dashboards, plus liveness via `system.agent.heartbeat` and the retained Kafka audit record.

**Independent Test**: Submit several cases, open LangFuse → Dashboards, confirm per-agent counts,
latency distributions, error rates, and an LLM panel update in near-real time; confirm heartbeats and
audit events flow on Kafka.

### Tests for User Story 2 ⚠️

- [x] T028 [P] [US2] LLM generation-attribute mapping test (model, token usage, cache hit, latency, provider_mode) in `tests/unit/observability/test_generation_attributes.py`
- [x] T029 [P] [US2] PII-redaction-before-export test (prompts/completions scrubbed by default; span attrs never carry PII; SC-007) in `tests/unit/observability/test_pii_redaction.py`
- [x] T030 [P] [US2] Heartbeat emission test (`system.agent.heartbeat` periodic, carries `agent_id`; interval `0` disables) in `tests/unit/observability/test_heartbeat.py`
- [x] T031 [P] [US2] Prompt-fetch fallback test (LangFuse prompt unmanaged → local template, non-blocking) in `tests/unit/observability/test_prompt_fallback.py`

### Implementation for User Story 2

- [x] T032 [US2] Enrich the `llm.invoke` generation with token usage / cache read+write / cache_hit / latency and `Redactor.scrub`-ed input/output before export in `src/agent_foundation/llm/runtime.py` (depends on T026)
- [x] T033 [US2] Thread `ObservabilityConfig` into the runtime in `src/agent_foundation/llm/factory.py`
- [x] T034 [P] [US2] Attach non-binding programmatic scores (`schema_valid`, `used_fallback`, `cache_hit`, `latency_ms`) at the reason() call site using `scores.py` in `src/agent_foundation/llm/runtime.py`
- [x] T035 [P] [US2] Add `TOPIC_HEARTBEAT` (`system.agent.heartbeat`) constant in `src/agent_foundation/transport/topics.py`
- [x] T036 [US2] Implement the periodic heartbeat emitter in `src/agent_foundation/observability/heartbeat.py` and drive it from the `serve()` loop in `src/agent_foundation/runtime/runtime.py` (depends on T035)
- [x] T037 [US2] Add the `audit.policy.decision.completed` emission via existing `write_audit` on `TOPIC_AUDIT` (no new topic) in `src/agent_foundation/audit/store.py`, called at the decision boundary
- [x] T038 [P] [US2] Document the LangFuse dashboard derivations (per-agent request/latency/error + LLM token/cache panels grouped by `agent_id`) in `specs/009-observability/contracts/evaluation-scores.md` / quickstart step 4

**Checkpoint**: Metrics + LLM panels populate in LangFuse; heartbeats and all four audit events on Kafka.

---

## Phase 5: User Story 3 - Instrument Agents with Minimal Code Changes (Priority: P2)

**Goal**: Each agent gets tracing/metrics from one `configure_observability()` call at startup plus the
declarative `@traced` annotations — zero observability code in any handler (SC-003).

**Independent Test**: `grep` agent handlers for tracing/metrics APIs → no matches; run an agent and
confirm traces/metrics still appear.

### Tests for User Story 3 ⚠️

- [x] T039 [P] [US3] Guard test asserting no observability/tracing API references in agent handler modules (`apps/agents/*/event_handlers.py`, `*/agent.py`) in `tests/unit/observability/test_no_handler_instrumentation.py`

### Implementation for User Story 3

- [x] T040 [P] [US3] Call `configure_observability()` once at startup (beside `configure_logging()`) in `apps/agents/customer_resolution/main.py`
- [x] T041 [P] [US3] Call `configure_observability()` once at startup in `apps/agents/billing_entitlement/main.py`
- [x] T042 [P] [US3] Call `configure_observability()` once at startup in `apps/agents/risk_fraud/main.py`

**Checkpoint**: All three agents instrumented; handlers remain free of observability logic.

---

## Phase 6: User Story 4 - Launch Observability Stack Locally (Priority: P2)

**Goal**: The LangFuse stack and env wiring come up with the standard startup command; one stop command
tears it down cleanly (SC-004).

**Independent Test**: Run the documented startup command → trace viewer + dashboards reachable at
`http://localhost:3000` alongside broker/agents; documented down command stops all services cleanly.

### Tests for User Story 4 ⚠️

- [x] T043 [US4] Opt-in integration test asserting a hierarchical trace appears via the LangFuse API for a driven case, auto-skipped without a running LangFuse, in `tests/integration/observability/test_e2e_trace_appears.py`

### Implementation for User Story 4

- [x] T044 [US4] Create `infra/local/docker-compose.langfuse.yml` (self-hosted v3: `langfuse-web` on 3000, `langfuse-worker`, `postgres`, `clickhouse`, `redis`, `minio`) per contracts/observability-config.md
- [x] T045 [US4] Edit `infra/local/run-demo-agents.sh` to optionally bring up the LangFuse compose and export `LANGFUSE_*` / `AGENT_OBSERVABILITY_*` before starting the three agents

**Checkpoint**: Single-command bring-up; agents register against local LangFuse; clean teardown.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, validation, and the non-blocking/perf guarantees that span all stories.

- [x] T046 [JSONLOG] [P] Document structured JSON logging + trace-correlation (note JSON renderer pre-exists; new processor adds `trace_id`/`correlation_id`) in `specs/009-observability/quickstart.md` / a docs note
- [x] T047 [P] Add fail-open / backend-down behavior note and exporter posture (FR-008/FR-015) to `specs/009-observability/contracts/observability-api.md` cross-references and any README
- [ ] T048 Perf check: measure < 5% added per-case latency with toggle on vs off (SC-005) and record the result
- [ ] T049 Run the full `quickstart.md` validation (steps 1–11) and confirm SC-001…SC-007 + FR-018 mappings

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories.
- **User Stories (Phases 3–6)**: All depend on Foundational completion.
  - US1 (P1) is the MVP. US2 (P1) builds on US1's `llm.invoke` span. US3/US4 (P2) are independent.
- **Polish (Phase 7)**: Depends on the desired user stories being complete.

### User Story Dependencies

- **US1 (P1)**: After Foundational. No dependency on other stories.
- **US2 (P1)**: After Foundational. T032/T034 extend US1's T026 (`llm/runtime.py`) — sequence US1→US2 for that file; everything else is independent.
- **US3 (P2)**: After Foundational. Independent (startup wiring only).
- **US4 (P2)**: After Foundational. Independent (infra only); the integration test exercises US1–US3 end to end.

### Within Each User Story

- Tests are written first and expected to FAIL before implementation.
- Foundational primitives before seam wrappers; seam wrappers before agent wiring.
- Same-file edits are sequential (e.g., T026 then T032/T034 in `llm/runtime.py`).

### Parallel Opportunities

- Setup: T002, T003, T004 in parallel.
- Foundational: T006, T009, T010, T012, T013, T016 in parallel (distinct files); T007→T008→T011→T014 chain.
- US1: all three tests (T017–T019) in parallel; seam wrappers T022/T023 and engine decorators T024/T025 in parallel (distinct files).
- US2: tests T028–T031 in parallel; T034/T035 parallelizable against T037.
- US3: T040/T041/T042 in parallel (distinct `main.py` files).

---

## Parallel Example: User Story 1

```bash
# Tests for User Story 1 together:
Task: "Trace-context round-trip test in tests/unit/observability/test_traceparent_roundtrip.py"
Task: "Span-catalog test in tests/unit/observability/test_span_catalog.py"
Task: "@traced decorator test in tests/unit/observability/test_engine_decorator.py"

# Seam wrappers + engine decorators in parallel (distinct files):
Task: "Wrap A2AClient.submit with a2a.task.send in src/agent_foundation/runtime/client.py"
Task: "Wrap runtime dispatch with a2a.task.receive in src/agent_foundation/runtime/runtime.py"
Task: "Apply @traced to classify()/decide() in apps/agents/customer_resolution/"
Task: "Apply @traced to evaluate()/assess_signals() in billing & risk"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup.
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories).
3. Complete Phase 3: User Story 1 (end-to-end trace).
4. **STOP and VALIDATE**: Submit a case, confirm one hierarchical trace in LangFuse.
5. Demo the trace viewer.

### Incremental Delivery

1. Setup + Foundational → primitives ready.
2. US1 → end-to-end trace (MVP) → demo.
3. US2 → metrics, LLM generations, heartbeat, audit record → demo.
4. US3 → confirm zero-handler-code instrumentation across all agents.
5. US4 → one-command local stack → demo.
6. Polish → perf check + quickstart validation.

---

<!-- SLICE:kafka-spans BEGIN — owner: "Add Kafka publish/consume spans"; far-ahead ID block T210-T211; additive hardening for the kafka.publish/event.consume transport seams (do not renumber/clobber) -->

## Phase 8: Kafka publish/consume span hardening (US1, additive)

**Purpose**: Strengthen the two transport seam spans `kafka.publish` (T020) and `event.consume`
(T021) with guarantees the general tests (T016/T017/T018) do not assert specifically. Depends on
T005 (`EventEnvelope.trace_context`), T010 (`propagation.py`), T020, T021.

- [ ] T210 [P] [US1] Transport-seam toggle-OFF byte-identity test: with `AGENT_OBSERVABILITY_ENABLED=false`, `publish()`/`publish_raw()` produce byte-identical envelopes to pre-feature with `trace_context` left `None`, and `event.consume` opens no span while handler dispatch is unchanged, in `tests/unit/observability/test_transport_seam_noop.py` (FR-008/FR-012; trace-context-propagation contract "byte-identical when off")
- [ ] T211 [P] [US1] Consume-seam FR-010 robustness test: an incoming envelope with absent **and** with malformed/unparseable `trace_context` both yield a new trace root (never a child, never a dropped event), and the `event.consume` span still carries `correlation_id`/`causation_id`/`event_id`/`topic` (FR-011/FR-014), in `tests/unit/observability/test_consume_seam_newroot.py`

<!-- SLICE:kafka-spans END -->

## Notes

- [P] = different files, no dependencies. [JSONLOG] = structured-JSON-logging steering tasks.
- Every observability call is fail-open (FR-008); the toggle defaults on but no-ops when off (FR-012).
- Kafka stays the system of record (FR-018); LangFuse is the out-of-band debugging/LLM view.
- No new agent, supervisor, router, orchestrator, or decision-maker (FR-019); the only new event is `system.agent.heartbeat`.
- Commit after each task or logical group; stop at any checkpoint to validate a story independently.


<!-- SLICE:langgraph-node-tracing v1 -->
### Slice: LangGraph Node Tracing (US3 / FR-016)

**Context**: Surface LangFuse **LangGraph node traces** (FR-016) by wiring a
guarded LangFuse `CallbackHandler` into the 008 graph adapters
(`as_node()` / `create_langgraph_llm_node()`), so graph-node execution emits
node-level traces with no handler code. Fail-open / no-op when the toggle is off
or `langfuse` is absent; PII redacted before export (FR-017/SC-007).

**Prerequisites**: T004 `ObservabilityConfig`, T005 guarded client, T006 `span()`/
`generation()` (Phase 2). Reuses the existing `[langgraph]` extra.

**Independent Test**: With the toggle OFF, `as_node()` / `create_langgraph_llm_node()`
return byte-identical state dicts and attach no callbacks (no `langfuse` import
required). With the toggle ON (no-op client), a LangFuse `CallbackHandler` is
present in the node's run config and the node return value is unchanged.

- [ ] T960 [P] [US3] Add a guarded `langfuse_callback_handler()` factory to `src/agent_foundation/observability/client.py` returning a LangFuse `CallbackHandler` when observability is enabled and `langfuse` is importable, else `None` (fail-open, lazy import)
- [ ] T961 [US3] Add an `observability_run_config(state, *, agent_id, task_kind)` helper in `src/agent_foundation/llm/langgraph.py` assembling a LangGraph run config `{"callbacks": [...], "metadata": {...}}` from the active client, threading FR-014 attrs (`correlation_id`, `causation_id`, `agent_id`, `task_kind`); returns `{}` when disabled
- [ ] T962 [US3] Wire the run config into `as_node()._node` in `src/agent_foundation/llm/langgraph.py` so the LangFuse handler observes node execution (FR-016); preserve the exact returned state dict
- [ ] T963 [US3] Wire the same run config into `create_langgraph_llm_node()._node` in `src/agent_foundation/llm/langgraph.py`; preserve return value and the lazy LangGraph import
- [ ] T964 [P] [US3] Redact node-trace metadata (grounding inputs + rendered instructions) via the 008 `Redactor` before attaching it to the run config in `src/agent_foundation/llm/langgraph.py` (FR-017/SC-007); never attach raw PII
- [ ] T965 [P] [US3] Surface node-completion attributes (`agent_id`, `task_kind`, `model_id`, `cache_hit`, `latency_ms`, input/output tokens) read from `AssistiveResult` onto the node trace in `src/agent_foundation/llm/langgraph.py` (read-only; no new measurement)
- [ ] T966 [P] [US3] Unit test `tests/unit/observability/test_langgraph_node_tracing.py::test_noop_when_disabled` - toggle OFF: both adapters return identical dicts, no callbacks attached, no `langfuse` import
- [ ] T967 [P] [US3] Unit test `tests/unit/observability/test_langgraph_node_tracing.py::test_callback_handler_injected_when_enabled` - toggle ON (fake client): run config carries the handler; node return value unchanged
- [ ] T968 [P] [US3] Unit test `tests/unit/observability/test_langgraph_node_tracing.py::test_node_metadata_redacts_pii` - PII in grounding is scrubbed before it reaches run-config metadata (SC-007)
- [ ] T969 [P] [US3] Unit test `tests/unit/observability/test_langgraph_node_tracing.py::test_node_attributes_from_result` - `model_id`/`cache_hit`/`latency_ms`/token usage surfaced from `AssistiveResult`
- [ ] T970 [US3] Document the LangGraph node-tracing path (env toggle, `[langgraph]`+`[observability]` extras, how node traces appear in LangFuse) in `specs/009-observability/quickstart.md`
- [ ] T971 [P] [US3] Update the module docstring of `src/agent_foundation/llm/langgraph.py` to note the optional LangFuse `CallbackHandler` node-tracing path and its no-op default

<!-- SLICE:llm-usage-cost-metadata v1 -->
### Slice: LLM Usage & Cost Metadata (US1 generation / US2 dashboards — FR-005)

**Context**: Surface LLM **token usage AND estimated cost** onto the `llm.invoke`
LangFuse **generation** and the per-agent dashboards. This is a mapping, not new
measurement: 008 already provides `TokenUsage` (`src/agent_foundation/llm/result.py`)
and `LLMUsage` / `build_llm_usage()` / `estimate_cost()` / `_PRICING_TABLE` /
`estimated_cost_usd` (`src/agent_foundation/llm/pricing.py`). The generation contract
currently maps token usage only — cost is the additive scope here. Fail-open / no-op
when the toggle is off; stub provider → cost `0`.

**Prerequisites**: Phase 2 client + `generation()` (T007/T008) and the US1 `llm.invoke`
generation (T026); cost tasks extend the same `llm/runtime.py` wrap, so sequence after T026/T032.

**Independent Test**: Drive an assistive call and open the `llm.invoke` generation in
LangFuse — it shows input/output (+cache read/write) token usage and an `estimated_cost_usd`
cost detail; the Dashboards LLM panel aggregates token usage and cost per `agent_id`. With
the toggle OFF, `reason()` is byte-identical to 008.

- [ ] T980 [US1] Map LLM **token usage** onto the `llm.invoke` generation `usage` (input/output/cache_read/cache_write) via `TokenUsage` / `build_llm_usage` from `src/agent_foundation/llm/pricing.py`, set in the `reason()` wrap in `src/agent_foundation/llm/runtime.py` (read-only; stub → zero tokens) [USAGE]
- [ ] T981 [US1] Add LLM **cost metadata** to the generation in `src/agent_foundation/llm/runtime.py`: compute `estimated_cost_usd` via `build_llm_usage`/`estimate_cost` and attach as LangFuse `cost_details` + `metadata.estimated_cost_usd` (stub → 0; unknown model → cost omitted, never raises) [COST]
- [ ] T982 [P] [US1] Update `specs/009-observability/contracts/llm-generation-attributes.md` and `specs/009-observability/data-model.md` Generation tables to document the cost attributes (`cost_details` / `metadata.estimated_cost_usd`) sourced from `LLMUsage.estimated_cost_usd` [COST]
- [ ] T983 [US2] Document the LangFuse LLM dashboard panel for per-agent **token usage + estimated cost** (call count, cache-hit rate, latency), noting `_PRICING_TABLE` in `src/agent_foundation/llm/pricing.py` is the cost source of truth feeding generation `cost_details`, in `specs/009-observability/quickstart.md` step 4 [USAGE+COST]
- [ ] T984 [P] [US1] Unit test generation **token usage** mapping in `tests/unit/observability/test_generation_usage.py` (input/output/cache_read/cache_write surfaced; stub → zero tokens) [USAGE]
- [ ] T985 [P] [US1] Unit test generation **cost metadata** in `tests/unit/observability/test_generation_cost.py` (each `_PRICING_TABLE` model: tokens → expected `estimated_cost_usd`; stub → 0; unknown model → cost omitted) [COST]
- [ ] T986 [P] [US2] Unit test per-agent **cost aggregation** inputs in `tests/unit/observability/test_cost_aggregation.py` (two generations on one `agent_id` carry summable `cost_details`/`estimated_cost_usd`) [COST]
- [ ] T987 [P] [US2] Add a cost-mapping case to the LLM-metrics integration check confirming `estimated_cost_usd` is non-null for a priced model and `0` for stub, in `tests/integration/observability/test_e2e_trace_appears.py` (opt-in, auto-skipped) [COST]


<!-- SLICE:cloudwatch-agentcore-docs v1 -->
### Slice: AgentCore / CloudWatch Export Docs (Polish / FR-015)

**Context**: FR-015 requires the OTel-compatible spans/metrics to be exportable to AWS
**AgentCore / CloudWatch** when deployed, while the **only locally-wired exporter is LangFuse**
(the AWS path is **configuration-only and documented — not wired or tested locally**). The existing
tasks cover this only in passing (T047). These `[AWSDOC]` tasks add the dedicated documentation so an
operator can switch exporters by config alone. No story label — cross-cutting/Polish, no runtime code.

**Prerequisites**: T006 `ObservabilityConfig` (defines `AGENT_OBSERVABILITY_EXPORTER`),
contracts/observability-config.md, contracts/observability-api.md. Pure docs — no code dependency.

**Independent Test**: A reader of `specs/009-observability/contracts/cloudwatch-agentcore-export.md`
can state (a) which env vars switch the exporter to `cloudwatch`/`otlp`, (b) that spans/attributes are
unchanged (OTel-compatible), and (c) that the AWS path is config-only and not wired/tested locally,
with no need to read source code.

- [ ] T915 [AWSDOC] [P] Create `specs/009-observability/contracts/cloudwatch-agentcore-export.md` documenting the config-only AWS export path (FR-015): OTel-compatible spans/metrics are unchanged; `AGENT_OBSERVABILITY_EXPORTER=cloudwatch|otlp` selects the exporter; required AWS config (ADOT/OTLP collector endpoint, AWS region, AgentCore observability sink, CloudWatch metric namespace); explicit statement that this path is NOT wired or tested in the local PoC
- [ ] T916 [AWSDOC] [P] Document the span-to-AWS mapping in the same `cloudwatch-agentcore-export.md`: how the 8 named spans + FR-014 attributes surface as CloudWatch (X-Ray segments / EMF metrics) and AgentCore traces, and that the Kafka audit trail (FR-018) remains the system of record regardless of exporter
- [ ] T917 [AWSDOC] [P] Extend the exporter row in `specs/009-observability/contracts/observability-config.md` and add the `cloudwatch`/`otlp` future values plus their required AWS env vars (e.g. `AWS_REGION`, OTLP endpoint) to `infra/local/.env.langfuse.example`, each marked config-only / not-wired-locally (FR-015)
- [ ] T918 [AWSDOC] [P] Add an "AWS export (config-only)" subsection to the exporter-posture notes in `specs/009-observability/contracts/observability-api.md`, cross-referencing `cloudwatch-agentcore-export.md` and stating LangFuse is the only locally-wired exporter (FR-008/FR-015)
- [ ] T919 [AWSDOC] [P] Add an appendix to `specs/009-observability/quickstart.md` noting that moving to AgentCore/CloudWatch is a configuration change (not a code change) and linking `cloudwatch-agentcore-export.md`; confirm SC mappings are unaffected


<!-- SLICE:policy-decision-audit v1 (ids T990-T998) -->
### Slice: Policy-Decision Audit Events (US2 / FR-018)

**Context**: Realize the `audit.policy.decision.completed` logical audit event (FR-018)
at the **actual case-decision boundary**, refining the coarse T037. The customer-resolution
decision is published in `apps/agents/customer_resolution/event_handlers.py`
(the `decided_envelope = await publisher.publish(...)` site, ~line 212), right after
`decision_engine.decide()`. The audit record reuses the existing
`write_audit(publisher, envelope, outcome, reason)` on `TOPIC_AUDIT` (`agent.audit.v1`)
with `outcome="completed"` — **no new topic or event contract**. Kafka stays the system of
record; the shared `correlation_id` lets an operator pivot to the LangFuse `case.decision`
span and back (contracts/kafka-audit-events.md).

**Prerequisites**: existing `write_audit` (already imported in `event_handlers.py`),
T024 `@traced("case.decision")`, and the 008 `Redactor` (for SC-007). Independent of the
LangFuse client — these Kafka audit events flow even with observability disabled / LangFuse down.

**Independent Test**: Drive a case to a decision; assert exactly one AuditPayload with
`outcome="completed"` is published to `TOPIC_AUDIT` whose `correlation_id` matches the case and
`causation_id == decided_envelope.event_id`; assert the emission is fail-open (a failing audit
write never blocks the decision publish) and the decision itself is byte-stable on replay.

- [ ] T990 [US2] Emit `audit.policy.decision.completed` by calling the existing `write_audit(publisher, decided_envelope, "completed", reason=<decision summary>)` immediately after the decision event publishes in `apps/agents/customer_resolution/event_handlers.py` (the `decided_envelope = await publisher.publish(...)` site, ~line 212); reuse the existing `write_audit` import, on `TOPIC_AUDIT`, with no new topic/contract (this realizes T037 at the real decision boundary)
- [ ] T991 [P] [US2] Assemble the decision-audit `reason` as a non-PII decision summary (final disposition + contributing billing/risk opinion ids only), scrubbed via the 008 `Redactor` if any free-text is included, so SC-007 holds, in `apps/agents/customer_resolution/event_handlers.py`
- [ ] T992 [US2] Set FR-014 attrs (`correlation_id`, `case_id`, `agent_id`, `event_id`) on the `case.decision` span (the T024 `@traced("case.decision")` on `decision_engine.decide`) so the LangFuse decision span and the Kafka `audit.policy.decision.completed` record share `correlation_id` for pivoting (contracts/kafka-audit-events.md)
- [ ] T993 [US2] Confirm the decision-audit emission is fail-open (FR-008): the decision publish in `apps/agents/customer_resolution/event_handlers.py` MUST NOT be gated on audit-write success; a write failure only logs `audit.write_failed` (already handled inside `write_audit`) and never raises into the decision path
- [ ] T994 [P] [US2] Unit test: decision boundary emits exactly one `audit.policy.decision.completed` (AuditPayload `outcome="completed"`) on `TOPIC_AUDIT` with `correlation_id` matching the case and `causation_id == decided_envelope.event_id`, using a fake publisher, in `tests/unit/observability/test_policy_decision_audit.py`
- [ ] T995 [P] [US2] Unit test: the audit emission is fail-open - a publisher that raises on the audit write does not propagate and the decision event is still published, in `tests/unit/observability/test_policy_decision_audit.py`
- [ ] T996 [P] [US2] Unit test: no raw customer PII appears in the decision-audit `reason` (SC-007), in `tests/unit/observability/test_policy_decision_audit.py`
- [ ] T997 [P] [US2] Idempotency/replay test: the decision-audit emission does not alter the case decision or any idempotency/dedup key (Principle III) - re-running the handler yields a byte-stable decision and no extra binding effects, in `tests/unit/observability/test_policy_decision_audit.py`
- [ ] T998 [US2] Document the `audit.policy.decision.completed` event (logical name -> `write_audit` realization, `TOPIC_AUDIT`, payload `outcome="completed"`, no new topic, Kafka-as-record + LangFuse-pivot) in `specs/009-observability/contracts/kafka-audit-events.md` and `specs/009-observability/quickstart.md` step 4

---

<!-- SLICE:DEMOUI-TRACE-LINKS START -->

## Phase 8: User Story 5 — Demo UI Trace Deep-Links & Event Correlation (Priority: P2) [DEMOUI]

> **Slice context — "Add Demo UI trace links/event correlation"**: a focused, additive slice over the
> existing **007** read-only Streamlit demo UI (`apps/demo_ui/`). The demo UI does **not** host trace
> visualization (spec Assumption: "the demo UI is not the host for metrics/trace visualization") — it
> **links out** to LangFuse and **correlates** audit/stream events by `trace_id`. Realizes FR-006 /
> FR-011 / SC-001 ("locate & inspect a case trace within 30s of knowing the case id") at the demo-UI
> entry point, built entirely on the additive `EventEnvelope.trace_context` (W3C `traceparent`) from
> US1 (T005/T020/T021). These tasks are tagged `[DEMOUI]` and numbered far ahead (T950+) to avoid
> colliding with concurrently-authored task IDs.

**Goal**: Each case timeline row and each audit-stream row surfaces its `trace_id` (derived from the
envelope `trace_context`) plus a "View in LangFuse" deep-link, and the case view shows a single
"Open full trace in LangFuse" link — degrading gracefully to a non-linked `—` when `trace_context` is
absent (pre-feature events or observability off, FR-010/FR-008).

**Dependencies**: Requires US1 envelope propagation (T005 `trace_context` field; T020/T021 inject on
publish / extract on consume) so audit envelopes actually carry a `traceparent`. Independent of
US2/US3/US4. Pure helpers (T950–T951) are unit-testable with the toggle OFF.

**Independent Test**: Drive a case with observability ON, open the demo UI **Case timeline**, confirm
an "Open full trace in LangFuse" link resolves to that case's trace and each row shows its `trace_id`;
then view an envelope without `trace_context` and confirm rows render `—` with no broken link.

### Tests for User Story 5 ⚠️

- [ ] T952 [P] [US5] Trace-link helper test (valid `traceparent` → 32-hex trace-id + `{LANGFUSE_HOST}/trace/{id}` URL; `trace_context=None`/malformed → `None`/no-link; host override honored) in `tests/unit/demo_ui/test_trace_links.py`
- [ ] T953 [P] [US5] Event-correlation projection test (`TimelineEntry.trace_id` and `StreamEvent.trace_id` populated from `EventEnvelope.trace_context`, `None` when absent) in `tests/unit/demo_ui/test_trace_correlation.py`

### Implementation for User Story 5

- [ ] T950 [P] [US5] Add demo-UI deep-link config — `LANGFUSE_HOST` (default `http://localhost:3000`) and optional `LANGFUSE_TRACE_URL_TEMPLATE` (default `{host}/trace/{trace_id}`) env constants — in `apps/demo_ui/config.py`, mirroring `specs/009-observability/contracts/observability-config.md`
- [ ] T951 [P] [US5] Create pure helper module `apps/demo_ui/trace_links.py` with `trace_id_from_envelope(envelope: EventEnvelope) -> str | None` (parse the W3C `traceparent` in `trace_context` → trace-id; `None` when absent/malformed) and `langfuse_trace_url(trace_id, host=config.LANGFUSE_HOST) -> str | None` (build the deep-link, `None` when trace_id falsy); no Streamlit import — unit-testable
- [ ] T954 [US5] Add `trace_id: str | None = None` to `TimelineEntry` and populate it in `build_timeline_from_records()` from each matched envelope via `trace_links.trace_id_from_envelope` in `apps/demo_ui/timeline.py` (depends on T951)
- [ ] T955 [US5] Add `trace_id: str | None = None` to `StreamEvent` and populate it in `build_stream_from_records()` from `env.trace_context` via `trace_links.trace_id_from_envelope` in `apps/demo_ui/event_stream.py` (depends on T951)
- [ ] T956 [US5] Render a per-case "Open full trace in LangFuse" link (using `langfuse_trace_url`) and add a per-row `trace` link column to the timeline dataframe — graceful `—` (no link) when `trace_id` is absent — in `apps/demo_ui/views/case_view.py` (depends on T954, T950)
- [ ] T957 [US5] Add a `trace` link column to the audit-stream rows (graceful `—` when absent), keeping dedup/filters unchanged, in `apps/demo_ui/views/stream_view.py` (depends on T955, T950)
- [ ] T958 [US5] Event correlation: add a `trace_id` group/filter to the stream (badge or filter events sharing a `trace_id`, alongside the existing `correlation_id` filter) in `apps/demo_ui/event_stream.py` + `apps/demo_ui/views/stream_view.py` (depends on T955, T957 — same files, sequence after)
- [ ] T959 [US5] Document the demo-UI trace-link/correlation behavior (LangFuse deep-links; links-not-hosts per spec Assumption; graceful no-link when observability off or pre-feature events) in `specs/009-observability/quickstart.md`

**Checkpoint**: Demo UI case timeline + audit stream show per-event `trace_id` and resolve "View in
LangFuse" deep-links for a driven case; absent `trace_context` degrades to a non-linked `—`.

### Parallel Opportunities (US5)

- Tests T952 + T953 in parallel (distinct files).
- Helpers T950 + T951 in parallel (distinct files); both gate the wiring tasks.
- T954 (`timeline.py`) and T955 (`event_stream.py`) in parallel; then T956 (`case_view.py`) and
  T957 (`stream_view.py`) in parallel; T958 follows T955/T957 (same files).

<!-- SLICE:DEMOUI-TRACE-LINKS END -->


<!-- SLICE:redaction-controls BEGIN - owner: "Add redaction controls for prompts/outputs"; far-ahead ID block T1300-T1309; centralizes the FR-017/SC-007 capture policy (do not renumber/clobber) -->

---

## Addendum - Redaction Controls for Prompts & Outputs (FR-017 / SC-007)

**Slice context**: `/speckit-tasks "Add redaction controls for prompts/outputs"`. Refines the PII-redaction
boundary already sketched in T029 (test), T032 (inline scrub), and T003 (env vars) into an explicit,
**centralized capture-policy control surface**: every free-text value bound for LangFuse - LLM prompts,
completions, and span/error status messages - passes one guarded redactor before export, with per-field
raw opt-in and a hard "span attributes never carry PII" invariant. Reuses the 008 `Redactor`
(`src/agent_foundation/llm/redaction.py`) and the `REDACT_PII` / `LOG_RAW_LLM_PROMPTS` /
`LOG_RAW_LLM_OUTPUTS` toggles (`src/agent_foundation/llm/config.py`) - no second redaction subsystem.

> **Sequencing**: extends US2 (the LLM-capture / PII-redaction story). Order after the
> `ObservabilityConfig` setup, the `tracing.py` span machinery, and T032 (the inline scrub these tasks
> centralize and replace). Far-ahead IDs (T1300+) avoid collision with the canonical block,
> `kafka-spans` (T210-T211), and `langgraph-node-tracing` (T960-T971).

### Setup / Config

- [ ] T1300 Add redaction-control fields (`redact_pii: bool = True`, `log_raw_prompts: bool = False`, `log_raw_outputs: bool = False`) to `ObservabilityConfig`, resolved in `from_env()` from the reused `REDACT_PII` / `LOG_RAW_LLM_PROMPTS` / `LOG_RAW_LLM_OUTPUTS` vars (mirroring 008 `RuntimeConfig.from_env()`), in `src/agent_foundation/observability/config.py`
- [ ] T1301 [P] Document the three redaction toggles and the default-redact / raw-opt-in / never-raw-span-attrs policy matrix in `infra/local/.env.langfuse.example` and `specs/009-observability/contracts/observability-config.md`

### Foundational

- [ ] T1302 Create a centralized capture-policy seam `redact_for_export(value, *, field, config)` (returns `None` to drop when redaction is off and the matching `log_raw_*` toggle is off; returns `Redactor.scrub(value)` by default; returns the raw `value` only when the matching `log_raw_*` toggle is set; on any `Redactor` error falls open to the scrubbed-or-dropped safe value) in a NEW `src/agent_foundation/observability/redaction.py`, wrapping the 008 `Redactor` (depends on T1300)

### Implementation for User Story 2

- [ ] T1303 [US2] Refactor the inline prompt/completion scrub in the `llm.invoke` generation to call `redact_for_export(..., field="prompt")` / `field="completion"` so the capture policy lives in one place (replaces the matrix sketched in T032) in `src/agent_foundation/llm/runtime.py` (depends on T1302)
- [ ] T1304 [US2] Route free-text status/error detail through `redact_for_export(..., field="status")` before `set_status(...)` / `record_exception(...)` so `AssistiveResult.failure_reason` and raw exception messages cannot leak PII to LangFuse, in `src/agent_foundation/observability/tracing.py` (depends on T1302)
- [ ] T1305 [P] [US2] Enforce the FR-014 attribute allowlist (IDs + non-PII metadata only) in span-attribute assembly so no free-text/payload value is ever set as a span attribute, in `src/agent_foundation/observability/attributes.py`

### Tests for User Story 2

- [ ] T1306 [P] [US2] Capture-policy matrix test (default `REDACT_PII=true` -> redacted; `LOG_RAW_LLM_PROMPTS`/`LOG_RAW_LLM_OUTPUTS=true` -> raw; all off -> field dropped) across prompt/completion/status fields in `tests/unit/observability/test_redaction_controls.py`
- [ ] T1307 [US2] Span-attribute redaction-invariant test (no PII appears in any span/generation attribute under any toggle combination - SC-007) in `tests/unit/observability/test_redaction_controls.py`
- [ ] T1308 [US2] Fail-open test (a raising `Redactor` still yields a safe redacted-or-dropped value and never breaks `reason()` or span emission - FR-008) in `tests/unit/observability/test_redaction_controls.py`

### Polish

- [ ] T1309 Verify SC-007 end-to-end on a sample trace (prompts/completions redacted, span attributes PII-free) and record the result in `specs/009-observability/quickstart.md`

<!-- SLICE:redaction-controls END -->


<!-- SLICE:correlation-id-propagation BEGIN — owner: "Add tests verifying correlation IDs propagate"; far-ahead ID block T1100-T1108 (chosen above the T960/T980 high-water to dodge the existing concurrent-slice collisions); additive correlation-ID propagation test suite — do NOT renumber/clobber. Extends, not replaces, T017/T018/T210/T211. -->

## Phase 10: Correlation-ID propagation test suite (US1, additive)

**Purpose**: Directly verify that **correlation IDs propagate** end to end — across the publish→consume
transport seam, across the A2A send→receive boundary, and across all three agents in one trace — beyond
the primitive round-trip (T017) and catalog (T018) checks. Proves FR-001 (cross-boundary propagation),
FR-011 (spans carry `correlation_id`/`causation_id`), the `correlation_id`/`causation_id` slice of
FR-014, and Principle III (replay-stable). All offline, toggle ON with a no-op/in-memory client.

**Depends on**: T005 (`EventEnvelope.trace_context`), T009 (attribute assembly), T010 (`propagation.py`),
T014 (public surface), T020/T021 (publish/consume seams), T022/T023 (A2A seams), T026 (`llm.invoke`),
T015/T027 (`[JSONLOG]` trace/correlation context binding).

- [ ] T1100 [US1] End-to-end cross-agent correlation test: drive one refund case through the in-memory transport/runtime harness and assert every span across all three agents shares one `trace_id` and a stable `correlation_id`, with parent-child links across both the publish→consume and `a2a.task.send`→`a2a.task.receive` hops, in `tests/unit/observability/test_correlation_propagation.py::test_correlation_id_stable_across_agents`
- [ ] T1101 [P] [US1] Publish→consume cross-seam test: a `kafka.publish` span injects `trace_context`, and the downstream `event.consume` span is its child (same `trace_id`, parent span-id = publish span-id) and carries the envelope's `correlation_id`/`causation_id`, in `tests/unit/observability/test_correlation_propagation.py::test_publish_consume_correlation_linked`
- [ ] T1102 [P] [US1] A2A send→receive correlation test: the performer's `a2a.task.receive` span is a child of the caller's `a2a.task.send` span (same `trace_id`) and both carry matching `correlation_id` plus `task_id`/`capability`, in `tests/unit/observability/test_correlation_propagation.py::test_a2a_send_receive_correlation_child`
- [ ] T1103 [P] [US1] All-spans correlation-coverage test: assert `correlation_id` is present on each of the eight named spans produced for a driven case (FR-011 + the `correlation_id` slice of FR-014), in `tests/unit/observability/test_all_spans_carry_correlation_id.py`
- [ ] T1104 [P] [US1] Causation-ID propagation test: the `event.consume` span's `causation_id` equals the incoming `EventEnvelope.causation_id`, and is omitted on non-consume spans (FR-011/FR-014 "where applicable"), in `tests/unit/observability/test_correlation_propagation.py::test_causation_id_on_consume`
- [ ] T1105 [P] [US1] New-root-preserves-correlation test: an envelope with no `trace_context` but a populated `correlation_id` yields a new trace root whose `event.consume` span still carries that `correlation_id` (FR-010 + FR-011 together — a new root must not lose the audit correlation link), in `tests/unit/observability/test_correlation_propagation.py::test_new_root_keeps_correlation_id`
- [ ] T1106 [JSONLOG] [P] [US1] Log/trace correlation-binding test: JSON log lines emitted while handling a case carry a `correlation_id` (and `trace_id`/`span_id` when a span is active) matching the case's spans, verifying the `[JSONLOG]` binding (T015/T027), in `tests/unit/observability/test_log_correlation_binding.py`
- [ ] T1107 [P] [US1] Replay-stability test: replaying an event with a stale/foreign `trace_context` produces an identical decision and idempotency key while the consume span still correlates by `correlation_id` (Principle III — trace context never enters dedup), in `tests/unit/observability/test_correlation_propagation.py::test_replay_stable_with_stale_trace_context`
- [ ] T1108 [P] [US1] LLM child-span correlation test: the `llm.invoke` generation opened inside a consume span shares the case `trace_id` and carries the same `correlation_id` as its parent (the assistive call joins the cross-agent trace), in `tests/unit/observability/test_correlation_propagation.py::test_llm_invoke_inherits_correlation`

<!-- SLICE:correlation-id-propagation END -->


<!-- SLICE:a2a-spans BEGIN — owner: "Add A2A client/server spans"; far-ahead ID block T1500-T1509 (chosen above the crowded T1100 zone to dodge concurrent-slice collisions); additive hardening of the a2a.task.send (client) / a2a.task.receive (server) seams from T022/T023 — do not renumber or clobber -->
### Slice: A2A Client/Server Span Hardening (US1 / FR-001/011/013/014)

**Context**: The base list creates the two A2A seam spans — `a2a.task.send` on `A2AClient.submit()`
(T022, `src/agent_foundation/runtime/client.py`) and `a2a.task.receive` on runtime handler dispatch
(T023, `src/agent_foundation/runtime/runtime.py`) — plus the round-trip test T017. These `[A2A]`
tasks add the cross-agent **client→server parent-child linkage**, the return-path context so the
caller continues the same trace on the `TaskResult`, full FR-014 attribute coverage, and the
fail-open / new-root guarantees specific to the A2A hop (mirrors the kafka-spans hardening slice
T210-T211). Depends on T005 (`EventEnvelope.trace_context`), T010 (`propagation.py`), T022, T023.

**Independent Test**: Delegate a task A→B; assert B's `a2a.task.receive` span is a child of A's
`a2a.task.send` span (same trace-id, parent span-id = send span-id), the `TaskResult` envelope carries
B's span context, A continues the same trace on receipt, and with the toggle OFF submit/dispatch are
byte-identical with `trace_context` left `None`.

- [ ] T1500 [US1] Inject the active `a2a.task.send` span context onto the outgoing request envelope in `A2AClient.submit()` (set `trace_context = current_trace_context()` before the request is published) so the performer can parent off it, in `src/agent_foundation/runtime/client.py` (extends T022; trace-context-propagation contract "A2A seams")
- [ ] T1501 [US1] Open the `a2a.task.receive` span from the incoming request envelope's `trace_context` (child of the caller's send span; new root if absent/unparseable — FR-010) in `src/agent_foundation/runtime/runtime.py` (extends T023)
- [ ] T1502 [US1] Publish the returned `TaskResult` with the performer's `a2a.task.receive` span context (set `trace_context = current_trace_context()` on the result envelope) so the caller continues the same trace on receipt, in `src/agent_foundation/runtime/runtime.py`
- [ ] T1503 [US1] Set full FR-014 attributes on both A2A spans — `capability`, `task_id`, `agent_id`, `correlation_id` (+ `causation_id`/`event_id` where present) via `attributes.py` — on `a2a.task.send` in `src/agent_foundation/runtime/client.py` and `a2a.task.receive` in `src/agent_foundation/runtime/runtime.py` (FR-014; IDs + non-PII only)
- [ ] T1504 [P] [US1] Client→server linkage test: a delegated task's `a2a.task.receive` span is a child of the caller's `a2a.task.send` span (same trace-id, parent span-id = send span-id) in `tests/unit/observability/test_a2a_span_linkage.py`
- [ ] T1505 [P] [US1] Return-path test: the `TaskResult` envelope carries the performer's span context and the caller's continuation span parents off it (one unbroken trace across the request→result round trip) in `tests/unit/observability/test_a2a_span_linkage.py`
- [ ] T1506 [P] [US1] A2A attribute test: both `a2a.task.send` and `a2a.task.receive` carry `capability`, `task_id`, `agent_id`, `correlation_id` and never carry PII (FR-014/SC-007) in `tests/unit/observability/test_a2a_span_attributes.py`
- [ ] T1507 [P] [US1] A2A fail-open / byte-identity test: with `AGENT_OBSERVABILITY_ENABLED=false`, `A2AClient.submit()` and runtime dispatch are byte-identical to pre-feature with `trace_context` left `None`, and a backend-down client never blocks delegation (FR-008/FR-012) in `tests/unit/observability/test_a2a_seam_noop.py`
- [ ] T1508 [P] [US1] A2A new-root test: an incoming request envelope with absent or malformed `trace_context` yields a new `a2a.task.receive` trace root (never a dropped task) while still carrying `capability`/`task_id`/`correlation_id` (FR-010/FR-014) in `tests/unit/observability/test_a2a_seam_noop.py`
- [ ] T1509 [US1] Document the A2A client/server span linkage (send→receive parent-child, return-path continuation, FR-014 attrs, new-root fallback) in `specs/009-observability/contracts/trace-context-propagation.md` "A2A seams" and `specs/009-observability/quickstart.md`

<!-- SLICE:a2a-spans END -->


<!-- SLICE:trace-context-model BEGIN — owner: "Define trace context model"; far-ahead ID block T1200-T1206 (above the T1100 high-water to dodge concurrent-slice collisions); fully specifies the TraceContextCarrier value object from data-model.md. ADDITIVE — refines, does not replace, T005 (envelope field) / T010 (inject-extract) / T017 (round-trip test). Do NOT renumber/clobber. -->

## Phase 11: Define the Trace Context Model (US1, foundational refinement)

**Slice context** — `/speckit-tasks "Define trace context model"`. The data model (data-model.md
"TraceContextCarrier") specifies a first-class value object for the W3C headers that ride the event
envelope; the canonical block covers this only implicitly via ad-hoc dicts in T010. This slice makes
the **TraceContextCarrier** an explicit, validated, single-serialization-point model whose serialized
form is *exactly* `EventEnvelope.trace_context` (`{"traceparent": ..., "tracestate"?: ...}`), with
lenient fail-to-None parsing so missing/malformed context yields a new trace root (FR-010) and never
raises (FR-008). Pure value-object + parsing work — offline-testable with the toggle OFF.

**Depends on**: T005 (`EventEnvelope.trace_context` field) and T010 (`propagation.py` inject/extract);
this slice refactors T010 to route all (de)serialization through the carrier. Independent of the
LangFuse client.

**Independent Test**: Construct a `TraceContextCarrier` from an active span, serialize via
`to_envelope_dict()`, round-trip back via `from_envelope_dict()`, and confirm the dict equals the
`EventEnvelope.trace_context` shape exactly; feed an absent/empty/malformed dict and confirm it returns
`None` (→ new root) without raising.

### Implementation for User Story 1

- [ ] T1200 [US1] Define the `TraceContextCarrier` value object (`traceparent: str`, `tracestate: str | None = None`) with `to_envelope_dict() -> dict[str, str]` (emits `{"traceparent": ...}`, adds `"tracestate"` only when non-None) and classmethod `from_envelope_dict(d: Mapping | None) -> TraceContextCarrier | None` (returns `None` for empty/missing input) in `src/agent_foundation/observability/propagation.py`, so its serialized form is exactly `EventEnvelope.trace_context` (data-model.md "TraceContextCarrier")
- [ ] T1201 [US1] Add W3C `traceparent` parse/validate to `TraceContextCarrier` (`version-traceid-spanid-flags`: 32-hex trace-id + 16-hex span-id + 2-hex flags) exposing `trace_id`/`span_id` accessors and lenient fail-to-`None` on malformed/empty input (never raises — FR-008/FR-010), in `src/agent_foundation/observability/propagation.py` (depends T1200)
- [ ] T1202 [US1] Route `inject`/`extract`/`current_trace_context()`/`start_consumer_span()` through `TraceContextCarrier.to_envelope_dict()` / `from_envelope_dict()` so the carrier is the single (de)serialization point for trace context (refactors T010; behavior unchanged when off), in `src/agent_foundation/observability/propagation.py` (depends T1200, T1201)
- [ ] T1203 [US1] Document the `TraceContextCarrier` model (fields, exact serialized shape, fail-to-None/new-root rule) in `specs/009-observability/contracts/trace-context-propagation.md`, cross-referencing data-model.md (docs only)

### Tests for User Story 1

- [ ] T1204 [P] [US1] Carrier round-trip + shape test: `to_envelope_dict()`/`from_envelope_dict()` are inverse, the dict matches the `EventEnvelope.trace_context` shape exactly, and `tracestate` is omitted when `None`, in `tests/unit/observability/test_trace_context_carrier.py`
- [ ] T1205 [P] [US1] Carrier validation test: malformed/empty/missing `traceparent` → `from_envelope_dict()` returns `None` (→ new root, FR-010) and never raises; valid input exposes the parsed 32-hex `trace_id` / 16-hex `span_id`, in `tests/unit/observability/test_trace_context_carrier.py`
- [ ] T1206 [P] [US1] Envelope backward-compat test: an `EventEnvelope` serialized before this feature deserializes unchanged with `trace_context is None`, and `trace_context` is excluded from idempotency/dedup keys and audit equality (Principle III), in `tests/unit/observability/test_trace_context_envelope.py`

<!-- SLICE:trace-context-model END -->

<!-- SLICE:otel-native-substrate v1 (ids T300-T308) BEGIN -->
### Slice: OpenTelemetry-native substrate (US1 / FR-003 / FR-013 / FR-015) [OTEL]

**Steering context — "Add OpenTelemetry instrumentation"**: the existing tasks instrument the eight
named spans through the LangFuse v3 SDK (which is OTel-based). This additive slice makes the
**OpenTelemetry substrate explicit** so spans are emitted via a real OTel `TracerProvider` (not solely
LangFuse-internal state) and FR-015's "export to AgentCore/CloudWatch is config-only, not a code
change" guarantee is concrete: the same `span()`/`generation()` calls (T008) feed an OTel
`BatchSpanProcessor` whose exporter is chosen by `AGENT_OBSERVABILITY_EXPORTER` (langfuse default;
`otlp`/`cloudwatch` documented-only per the AWSDOC slice). Fail-open / no-op when the toggle is off or
the OTel SDK is absent. These tasks are tagged `[OTEL]` and numbered far ahead (T300-block) to avoid
colliding with concurrently-authored task IDs.

**Prerequisites**: T001 (`[observability]` extra), T006 `ObservabilityConfig`
(`exporter`/`environment`/`service_name`/`sample_rate`), T007 guarded client, T008 `span()`/`generation()`,
T010 `propagation.py`. Reuses the W3C carrier already on `EventEnvelope.trace_context` (T005).

**Independent Test**: With the toggle OFF (or `opentelemetry-sdk` absent), `init_tracer_provider()` is a
no-op, installs no global provider, and `span()` stays a null context (byte-identical to pre-feature).
With the toggle ON, a `TracerProvider` whose `Resource` carries `service.name == agent_id` and
`deployment.environment == config.environment` is installed exactly once (idempotent), the global text
propagator is W3C `traceparent`, and `flush()`/shutdown drain the `BatchSpanProcessor` cleanly.

- [ ] T300 [OTEL] Extend the `[observability]` extra in `pyproject.toml` (refining T001) to pin `opentelemetry-sdk` and `opentelemetry-exporter-otlp-proto-http` explicitly (the OTel-native substrate + future OTLP exporter), keeping the default/offline path dependency-free
- [ ] T301 [OTEL] [US1] Create `src/agent_foundation/observability/otel.py` with `init_tracer_provider(config) -> TracerProvider | None`: build an OTel `Resource` (`service.name=config.service_name or agent_id`, `deployment.environment=config.environment`), a `TracerProvider` with a `ParentBased(TraceIdRatioBased(config.sample_rate))` sampler, and a `BatchSpanProcessor`; lazy-import the OTel SDK, return `None` (no-op) when disabled or the SDK is unimportable, and install the provider only once (idempotent)
- [ ] T302 [OTEL] [US1] Select the span exporter inside `init_tracer_provider()` from `config.exporter` in `src/agent_foundation/observability/otel.py`: `langfuse` (default) → the LangFuse/OTLP span processor already used by the guarded client; `otlp` → `OTLPSpanExporter` from `LANGFUSE_HOST`/OTLP endpoint env; `cloudwatch` → documented-only stub that logs "config-only, not wired locally" (FR-015) and falls back to no-op — never raises
- [ ] T303 [OTEL] [US1] Call `init_tracer_provider(config)` from `configure_observability()` / the guarded client bootstrap in `src/agent_foundation/observability/client.py` so `span()`/`generation()` (T008) emit through the OTel `TracerProvider`; keep a single shared provider across the process and remain a no-op when observability is off
- [ ] T304 [OTEL] [US1] Set the global OTel propagator to `TraceContextTextMapPropagator` (W3C `traceparent`) in `src/agent_foundation/observability/propagation.py` so `inject`/`extract` (T010) use the SDK-standard propagator and cross-agent parentage via `EventEnvelope.trace_context` (T005/T020/T021) is OTel-native
- [ ] T305 [OTEL] [US1] Route `flush()` and add a `shutdown_tracer_provider()` in `src/agent_foundation/observability/otel.py` that force-flushes and shuts down the `BatchSpanProcessor`, and call it from the runtime `serve()` teardown in `src/agent_foundation/runtime/runtime.py` (fail-open; no-op when no provider) so spans drain on clean exit
- [ ] T306 [OTEL] [P] [US1] Unit test in `tests/unit/observability/test_otel_provider.py`: toggle OFF (and SDK-absent) → `init_tracer_provider()` returns `None`, installs no global provider, `span()` is a null context, and behavior is byte-identical to pre-feature
- [ ] T307 [OTEL] [P] [US1] Unit test in `tests/unit/observability/test_otel_provider.py`: toggle ON → provider installed once (second call idempotent), `Resource` carries `service.name == agent_id` and `deployment.environment == config.environment`, and the sampler reflects `config.sample_rate`
- [ ] T308 [OTEL] [P] [US1] Unit test in `tests/unit/observability/test_otel_propagator.py`: after `init_tracer_provider()`, the global propagator is W3C, and a span round-trips through `inject` → `EventEnvelope.trace_context` → `extract` to the correct parent (and a missing carrier yields a new root — FR-010), aligning with T017
<!-- SLICE:otel-native-substrate v1 END -->
