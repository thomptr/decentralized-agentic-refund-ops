---
description: "Focused task list — Failure-Path Choreography for Decentralized Workflow & Event Choreography (006)"
---

# Tasks: Failure-Path Choreography (006 · User Story 3 — Deterministic failure paths)

**Input**: Design documents from `/specs/006-workflow-choreography/`

**Scope**: This is a **focused subset** of the full feature tasks (`tasks.md`), covering only the
**failure-path choreography** requested via `/speckit-tasks`. It hardens the six fault classes below so
that every one of them (a) emits a structured `agent.audit.v1` event, (b) never crashes the consuming
agent, and (c) drives the affected case to a bounded terminal state (`escalated` or `failed`). It
realizes **spec User Story 3 (Priority P2)** plus the constitutional observability requirements
(FR-020, FR-022, FR-018). IDs here are prefixed `FP` to avoid collision with the shared `tasks.md`; the
behavioral failure integration tests in `tasks.md` (T017–T019, US3) remain authoritative and these
tasks complement them at the infrastructure/defensive tier.

**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅,
contracts/timeout-and-failure-paths.md ✅, contracts/choreography.md ✅. The reaper (`tasks.md`
T012–T015) and config knobs (`tasks.md` T002) bound the **timeout** failure path; this slice assumes
they exist (or are stubbed) only for FP05's "bounded-by-reaper" assertion — no other task depends on them.

**Tests**: INCLUDED — the request's acceptance criteria are themselves assertions, and FR-016 requires
automated failure-path coverage. Test tasks are written **before** the implementation they cover and
must FAIL first.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US3 (maps to spec User Story 3 — Deterministic failure paths)
- All paths are repository-root-relative

---

## The six failure cases → surface → current status → gap to close

| # | Failure case | Detecting surface (file / function) | Current behavior | Gap this slice closes |
|---|---|---|---|---|
| **F1** | A2A capability unavailable | `a2a_handlers.validate_billing_capability` / `validate_risk_capability` raise `*PeerUnavailable` → `delegate()` re-raises → `event_handlers.intake_handler` except branch (`event_handlers.py:350`) | Escalates to `escalate_human`/`peer_failure` ✅ but **emits no structured audit** at the failure | Emit `write_audit(..., "rejected", "peer_failure")` on the escalation branch |
| **F2** | A2A validation failure | `event_handlers.result_handler` → `TaskResult.model_validate` except (`event_handlers.py:391`) | **Silent `return`** — no audit, case left waiting | Emit `write_audit(..., "rejected", "a2a_validation_failure")`; case stays bounded (reaper deadline → `escalate_human`) |
| **F3** | Kafka publish failure | `event_handlers._emit_decision_and_draft` / `_apply_decision`; `a2a_handlers.delegate` publishes | Unguarded `publisher.publish` raises → propagates to `Consumer.run` (caught at `consumer.py:173`, agent survives) but case left non-terminal, **no audit** | Wrap emit in a safe helper → case → `FAILED` (or `ESCALATED`) + `write_audit(..., "failed", "publish_failure")`; never leave a half-decided case |
| **F4** | Malformed event | `Consumer.run` invalid-envelope branch (`consumer.py:108`); `intake_handler` redundant `SupportTicketCreatedPayload.model_validate` (`event_handlers.py:264`) | Consumer audits `"rejected"/"invalid_envelope"` + continues ✅; intake's own re-validation `return`s silently | Verify consumer tier (test); FR-020 — a malformed/un-triageable **ticket** must audit `"rejected"/"malformed_ticket"` instead of silent drop |
| **F5** | Unknown event type | `Consumer.run` payload-registry branch → `UnknownEventType` (`consumer.py:147`) | Audits `"rejected"/"unknown_schema_version"` + continues ✅ | Verify-only (test); no code change expected |
| **F6** | Invalid payload | `Consumer.run` payload-registry branch → `ValidationError` (`consumer.py:147`); handler-level re-validation in `billing_result_handler` / `risk_result_handler` (`event_handlers.py:518,588`) | Consumer audits `"rejected"/"payload_invalid"` + continues ✅; handler-level silent `return`s emit nothing | Verify consumer tier (test); replace handler-level silent `return`s with a `write_audit` |

**Audit vocabulary**: `AuditPayload.outcome` is the fixed literal set
`accepted | rejected | duplicate_skipped | completed | failed`, and a `reason` is **required** whenever
outcome is `rejected` or `failed` (`src/agent_foundation/payloads/sample.py`). Failure audits therefore
use `rejected` (validation/discovery faults) or `failed` (mid-flow emit faults) with one of the reasons
in `contracts/timeout-and-failure-paths.md` (`peer_failure`, `malformed_ticket`, …) plus two new audit
reasons introduced here — `a2a_validation_failure`, `publish_failure`. **These are audit `reason`
strings only — no new event contract, topic, or payload schema is introduced** (Constitution V).

---

## Acceptance criteria → task map

| Acceptance criterion (from request) | Spec refs | Realizing tests | Realizing impl |
|---|---|---|---|
| Failures emit structured audit events | FR-022, FR-018, FR-020 | FP04–FP09 | FP10, FP11, FP12, FP13 |
| Invalid events do not crash agents | FR-020 (no silent drop / no crash) | FP04–FP09 (assert loop survives) | FP13 (safe emit), FP14 (consumer verify) |
| Cases move to escalated or failed state safely | FR-018, FR-017, SC-004, SC-007 | FP04, FP05, FP06, FP07 | FP10, FP13 |

---

## Phase 1: Foundational (blocking — failure vocabulary + safe-emit + test capture harness)

**Purpose**: Shared scaffolding every other task reuses — the canonical failure-reason strings, a
crash-proof publish wrapper, and a capturing publisher so handler-tier failures can be asserted without
a live broker. Reuses the existing `write_audit` / `write_task_audit` and `CaseStatus.{ESCALATED,FAILED}`
— no new dependency, topic, or event contract.

- [ ] FP01 [US3] Add the failure-reason constants `PEER_FAILURE = "peer_failure"`, `MALFORMED_TICKET = "malformed_ticket"`, `A2A_VALIDATION_FAILURE = "a2a_validation_failure"`, and `PUBLISH_FAILURE = "publish_failure"` (single source of truth, matching `contracts/timeout-and-failure-paths.md`) in `apps/agents/customer_resolution/config.py`, so handlers reference symbols instead of string literals.
- [ ] FP02 [US3] Implement a crash-proof emit helper `safe_emit_decision(...)` in `apps/agents/customer_resolution/event_handlers.py` that wraps `_emit_decision_and_draft` in `try/except`: on a publish exception it logs, moves the case to `CaseStatus.FAILED`, persists via `store.save`, and writes `write_audit(publisher, envelope, "failed", PUBLISH_FAILURE)` — and itself never re-raises (so the consumer loop survives, F3 / AC2).
- [ ] FP03 [P] [US3] Add a `CapturingPublisher` test double (records every `publish` / `publish_raw` call, with an optional `fail_after_n` knob to simulate Kafka publish failure) plus an `audit_events_for(correlation_id)` helper, in `apps/agents/customer_resolution/tests/conftest.py`, so FP04–FP09 can assert emitted audit events and inject publish faults without a broker.

**Checkpoint**: Failure reasons are centralized, decision emission is crash-proof, and tests can capture audits / inject publish faults in-process.

---

## Phase 2: Tests (write first — one per failure case; MUST FAIL before Phase 3)

Each test asserts the three acceptance criteria as applicable to its case: **(audit)** the expected
`agent.audit.v1` outcome+reason is emitted, **(no-crash)** the handler returns normally / the consumer
loop continues, **(terminal)** the case reaches `ESCALATED` or `FAILED` (or, for transport-tier drops
with no case, that nothing is created and the event is rejected).

- [ ] FP04 [P] [US3] **F1 — A2A capability unavailable.** In `apps/agents/customer_resolution/tests/test_failure_paths.py`: drive `intake_handler` for a refund ticket with `delegate` patched to raise `BillingPeerUnavailable`; assert the case ends `ESCALATED` with `ResolutionOutcome.ESCALATE_HUMAN`/`escalation_reason="peer_failure"`, exactly one `agent.audit.v1` with outcome `rejected`+reason `peer_failure` is captured, and no exception escapes the handler (FR-018, SC-007).
- [ ] FP05 [P] [US3] **F2 — A2A validation failure.** In `tests/test_failure_paths.py`: feed `result_handler` an envelope whose payload fails `TaskResult.model_validate`; assert the handler returns without raising, a `rejected`/`a2a_validation_failure` audit is captured, no decision/draft is emitted, and (with the reaper available) the still-`WAITING_FOR_PEER_REVIEWS` case is reaped to `ESCALATED`/`analysis_timeout` within `deadline + ≤ REAPER_TICK_SECONDS` (FR-018, FR-017, SC-004).
- [ ] FP06 [P] [US3] **F3 — Kafka publish failure.** In `tests/test_failure_paths.py`: use the `CapturingPublisher(fail_after_n=…)` so the decision publish raises during `safe_emit_decision`; assert the case ends `FAILED`, a `failed`/`publish_failure` audit is captured, and the handler/consumer-equivalent call site does not propagate the exception (F3, AC2/AC3).
- [ ] FP07 [P] [US3] **F4 — Malformed / un-triageable ticket.** In `tests/test_failure_paths.py`: feed `intake_handler` an envelope with a malformed `support.ticket.created` payload; assert it is **not** silently dropped — a `rejected`/`malformed_ticket` audit is captured and no half-open case is left (FR-020). Separately, in `tests/integration/test_failure_paths.py` (or `test_workflow_choreography.py`), publish raw bytes that fail `EventEnvelope.model_validate_json` and assert `Consumer.run` emits `EVENT_REJECTED`/`invalid_envelope` audit and keeps consuming (F4, AC1/AC2).
- [ ] FP08 [P] [US3] **F5 — Unknown event type.** In `apps/agents/customer_resolution/tests/test_failure_paths.py` (or a foundation-level `src/agent_foundation/.../tests` test): publish an envelope whose `event_type` is not in the payload registry and assert `Consumer.run` (via `lookup` → `UnknownEventType`) writes a `rejected`/`unknown_schema_version` audit and continues without invoking the handler or crashing (F5, AC1/AC2). Verify-only — expected to pass against current consumer code.
- [ ] FP09 [P] [US3] **F6 — Invalid payload.** Two assertions: (a) consumer tier — an envelope of a known `event_type` whose payload fails registry `model_validate` yields a `rejected`/`payload_invalid` audit and the loop continues; (b) handler tier — `billing_result_handler` / `risk_result_handler` fed a payload that fails `model_validate` emit a `rejected` audit instead of returning silently. In `apps/agents/customer_resolution/tests/test_failure_paths.py` (F6, AC1/AC2).

**Checkpoint**: All six failure cases are encoded as tests; the transport-tier cases (FP08, FP07-consumer, FP09a) pass now, the handler-tier cases (FP04, FP05, FP06, FP07-intake, FP09b) FAIL pending Phase 3.

---

## Phase 3: Implementation (make the failing tests pass — harden each surface)

- [ ] FP10 [US3] **F1 + F4 (intake).** In `apps/agents/customer_resolution/event_handlers.py`: (a) in the delegation-failure `except` branch (`:350`) add `await write_audit(publisher, envelope, "rejected", PEER_FAILURE)` alongside the existing escalation, before/after `_emit_decision_and_draft`; (b) in the invalid-ticket `except` branch (`:264`) replace the silent `return` with `await write_audit(publisher, envelope, "rejected", MALFORMED_TICKET)` so a malformed ticket is audited, not dropped (FR-020, FR-018). Makes FP04 + FP07-intake pass.
- [ ] FP11 [US3] **F2.** In `apps/agents/customer_resolution/event_handlers.py` `result_handler` (`:391`): replace the silent `return` on `TaskResult.model_validate` failure with `await write_audit(publisher, envelope, "rejected", A2A_VALIDATION_FAILURE)` (still returns — the reaper bounds the case). Makes FP05's audit assertion pass.
- [ ] FP12 [US3] **F6 (handler tier).** In `apps/agents/customer_resolution/event_handlers.py` `billing_result_handler` (`:518`) and `risk_result_handler` (`:588`): replace the silent `return`s on `model_validate` failure with `await write_audit(publisher, envelope, "rejected", "payload_invalid")` (keep returning; no crash). Makes FP09b pass.
- [ ] FP13 [US3] **F3.** Route every decision emission in `event_handlers.py` (`_apply_decision`, the non-refund direct-response branch in `intake_handler`, the high-risk fast path in `risk_result_handler`) through `safe_emit_decision` (FP02) instead of calling `_emit_decision_and_draft` directly, so a Kafka publish failure lands the case in `FAILED` with a `publish_failure` audit and never propagates. Makes FP06 pass.
- [ ] FP14 [US3] **F4 / F5 / F6 (consumer tier) — verify & document.** Confirm `src/agent_foundation/transport/consumer.py` already audits `invalid_envelope` (`:108`), `unknown_schema_version` / `payload_invalid` (`:147`) and `continue`s without breaking the loop, and that a handler exception is caught at `:173` (agent survives). No code change expected; if a gap is found, fix minimally and note it. Confirms FP07-consumer, FP08, FP09a.

**Checkpoint**: All six fault classes emit a structured audit, none crash the agent, and every case with an associated `ResolutionCase` reaches `ESCALATED` or `FAILED` (timeout cases bounded by the reaper).

---

## Phase 4: Cross-cutting verification & regression gate

- [ ] FP15 [US3] Run the failure-path suite and regression gates: `pytest apps/agents/customer_resolution/tests/test_failure_paths.py` and `pytest tests/integration/test_failure_paths.py -m integration` are green; the decentralization guards stay green (`apps/agents/customer_resolution/tests/test_no_supervisor.py`, `tests/integration/test_no_router.py` — failure handling adds no orchestrator, FR-021); and confirm **no new dependency, topic, or event contract** was added (Constitution V — only audit `reason` strings and one `FAILED` transition were introduced).

---

## Dependencies & Execution Order

- **Foundational (Phase 1)**: FP01 → FP02 (safe_emit uses the reason constants); FP03 is independent `[P]`. Phase 2 tests depend on FP03 (capture/fault-injection) and FP01–FP02 for the symbols they assert against.
- **Tests (Phase 2)**: FP04–FP09 are mutually independent `[P]` but several share `tests/test_failure_paths.py` — author as separate test functions. Write them to FAIL first (except the verify-only transport-tier cases).
- **Implementation (Phase 3)**: FP10 (intake) and FP11/FP12 (result/billing/risk handlers) touch the same file `event_handlers.py` — sequence them to avoid edit conflicts (FP10 → FP11 → FP12 → FP13). FP14 is independent of the others.
- **Gate (Phase 4)**: FP15 runs last, after FP04–FP14.

```
FP01 ─► FP02 ─┐
FP03 ─────────┼─► FP04 ─┐
              ├─► FP05 ─┤
              ├─► FP06 ─┼─► FP10 ─► FP11 ─► FP12 ─► FP13 ─┐
              ├─► FP07 ─┤                                  ├─► FP15
              ├─► FP08 ─┤            FP14 ─────────────────┘
              └─► FP09 ─┘
```

## Parallel Opportunities

```bash
# Phase 1: FP03 (test harness) in parallel with FP01→FP02 (different files).
# Phase 2: author the six failure-case tests together (logically independent functions):
Task: "F1 capability-unavailable test (FP04)"
Task: "F2 a2a-validation-failure test (FP05)"
Task: "F3 kafka-publish-failure test (FP06)"
Task: "F4 malformed-ticket/event test (FP07)"
Task: "F5 unknown-event-type test (FP08)"
Task: "F6 invalid-payload test (FP09)"
```

## Notes

- **No new dependency, no new topic, no new event contract** — this slice reuses the existing
  `write_audit` / `write_task_audit`, the existing `AuditPayload` outcome literals, and the existing
  `CaseStatus.{ESCALATED,FAILED}` terminals. The only additions are two audit `reason` strings
  (`a2a_validation_failure`, `publish_failure`) and routing emission through a crash-proof wrapper.
- The transport tier (`Consumer.run`) already satisfies AC1/AC2 for **malformed events (F4)**,
  **unknown event types (F5)**, and **registry-level invalid payloads (F6)**; FP08, FP14, and FP09a are
  verification/characterization tasks. The genuinely-new hardening is at the resolution-agent handler
  tier (FP10–FP13).
- The **timeout** failure path (peer silent past deadline) is owned by the reaper in `tasks.md`
  (T012–T015 / US3) and is not re-implemented here; FP05 only asserts that an A2A-validation-failed
  result leaves the case in a state the reaper will bound.
- This focused list complements `tasks.md` Phase 5 / US3 (T016–T019). Keep `tasks.md` as the
  authoritative full-feature list; fold these in there if/when you implement the whole feature.
- Verify each handler-tier test FAILS before implementing its Phase-3 counterpart; commit after each
  task or logical group.
