---
description: "Focused task list — Event Replay Test for Decentralized Workflow & Event Choreography (006)"
---

# Tasks: Event Replay Test (006 · User Story 4 — Idempotent, replay-safe processing)

**Input**: Design documents from `/specs/006-workflow-choreography/`

**Scope**: This is a **focused subset** of the full feature tasks (`tasks.md`), covering only the
event-replay test requested. It realizes **User Story 4 (Priority P3)** and maps to the same code; if you
later run the full feature, these tasks correspond to `tasks.md` Phase 6 (T024–T027) and may be merged
there. IDs here are prefixed `TR` to avoid collision with the shared `tasks.md`.

**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅,
contracts/replay-and-trace.md ✅, contracts/choreography.md ✅. Depends on the shared multi-agent
integration harness (`tasks.md` T006, `tests/integration/conftest.py`) and the deadline/config knobs
(`tasks.md` T002); if those are not yet in place, complete them first or stub a minimal harness.

**Tests**: INCLUDED — FR-016 explicitly requires automated replay tests. Test tasks are written before the
implementation they cover and must FAIL first.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US4 (maps to spec User Story 4)
- All paths are repository-root-relative

---

## The three replay events (the recorded input stream this test re-feeds)

| Requested name | Topic constant (`packages/contracts/topics.py`) | Resolved topic | Role |
|---|---|---|---|
| `support.ticket.created` | `topic_for("support","ticket","created")` (also `apps/agents/customer_resolution/agent.py:_TICKET_CREATED_TOPIC`) | `local.support.ticket.created.v1` | **root**, `causation_id == None` |
| `billing.refund-analysis.completed` | `TOPIC_BILLING_RESULT` | `local.billing.refund-analysis.completed.v1` | billing opinion (peer result) |
| `risk.review.completed` | `TOPIC_RISK_RESULT` | `local.risk.review.completed.v1` | risk opinion (peer result) |

Output/observation topics the test asserts against: `TOPIC_RESOLUTION_DECIDED`
(`customer.resolution.decided`), `TOPIC_RESPONSE_DRAFTED`, and `TOPIC_AUDIT`.

**Determinism basis** (why replay reproduces the original): `decision_engine.decide()` is pure/total;
`task_id = uuid5(correlation_id, capability)` is stable; ticket classification is deterministic; no
LLM/clock on the replay path (the reaper is neutralized for completed-run replay — research R2). Same
inputs ⇒ same decision.

---

## Acceptance criteria → task map

| Acceptance criterion (from request) | Spec refs | Realizing test |
|---|---|---|
| Replayed events do not create duplicate final decisions | FR-013/14/15, SC-003/006, US4 AC1/AC2 | **TR03** |
| Idempotency prevents repeated side effects | FR-011/12, SC-006, US4 AC1/AC3 | **TR04** |
| Case state can be rebuilt from events or safely reconciled | US4 AC2, Edge "replay of partially-completed case" | **TR05** |

---

## Phase 1: Foundational (replay infrastructure — blocks the tests)

**Purpose**: A way to record a scenario's events and re-feed them deterministically. Reuses the existing
`Consumer.seek_to_beginning()`, `IdempotencyTracker`, and `InMemoryCaseStateStore` — no new dependency,
no new topic, no new event contract.

- [ ] TR01 [US4] Implement the **recording helper** in `tests/integration/replay_harness.py`: after a scenario runs against the container broker, read back the ordered `EventEnvelope`s for a `correlation_id` across the three input topics (`support.ticket.created`, `TOPIC_BILLING_RESULT`, `TOPIC_RISK_RESULT`) plus the output topics (`TOPIC_RESOLUTION_DECIDED`, `TOPIC_RESPONSE_DRAFTED`) and `TOPIC_AUDIT`; return a `RecordedScenario` (input events in arrival order + the recorded decision payload + the audit set) for replay and equality assertions.
- [ ] TR02 [US4] Implement the **replay harness** in `tests/integration/replay_harness.py`: re-feed the recorded input events (ticket + the two peer results) into a **fresh** `ResolutionService` with a fresh `InMemoryCaseStateStore`, using `Consumer.seek_to_beginning()` on **uniquely-named** consumer groups (offsets at zero, empty `IdempotencyTracker`) and the **reaper disabled / given an effectively-infinite deadline** so no clock-dependent escalation is injected (contracts/replay-and-trace.md §1, research R2). Expose a reusable `replay(recorded) -> ReplayResult` entrypoint (re-derived decision + emitted-event set + audit outcomes).

**Checkpoint**: A scenario can be recorded and replayed into an isolated fresh service/store.

---

## Phase 2: Replay & idempotency tests (write first; must FAIL before TR06)

- [ ] TR03 [P] [US4] **Replayed events do not create duplicate final decisions.** In `tests/integration/test_workflow_choreography.py`: record a completed eligible+low-risk case, then replay `support.ticket.created` + `billing.refund-analysis.completed` + `risk.review.completed` via the harness; assert the `customer.resolution.decided` count for the `correlation_id` is **exactly 1**, and the re-derived decision **outcome + explanation/rationale equal** the originally recorded decision (FR-013/FR-014/FR-015, SC-003/SC-006, US4 AC1/AC2). Also assert a triggered-twice aggregation (both results redelivered) still emits **one** decision.
- [ ] TR04 [P] [US4] **Idempotency prevents repeated side effects.** In `tests/integration/test_workflow_choreography.py`: deliver each of the three named events **twice** to the same consumer group and assert (a) the `IdempotencyTracker` skips the redelivered `event_id` (audit outcome `duplicate_skipped`), (b) **zero** duplicate billing/risk opinions and **zero** duplicate A2A task requests are emitted, and (c) a repeated `task_id = uuid5(correlation_id, capability)` returns the **stored** result without re-running analysis (FR-011/FR-012, SC-006, US4 AC1/AC3). Pattern after the existing `tests/integration/test_idempotency.py::test_replay_deduplicates`.
- [ ] TR05 [P] [US4] **Case state can be rebuilt from events or safely reconciled.** In `tests/integration/test_workflow_choreography.py`: fold the three replayed events into a **fresh** `InMemoryCaseStateStore` and assert the reconstructed `ResolutionCase` (status, both opinion slots, decision) **equals** the original terminal case; a **partial** stream (`support.ticket.created` + one peer result, the other omitted) reproduces the same in-flight `waiting_for_peer_reviews` state and yields **no** spurious decision (reaper neutralized); applying the rebuild a second time is a **no-op** (reconciliation is idempotent under the `DECIDED`/terminal guard) (US4 AC2, Edge case "replay of a partially-completed case", FR-019).

**Checkpoint**: All three acceptance criteria are encoded as failing tests over the recorded three-event stream.

---

## Phase 3: Implementation (make the tests pass)

- [ ] TR06 [US4] Implement the **case-state rebuild/reconcile** function in `apps/agents/customer_resolution/` (e.g. `replay_rebuild.py` or extend `state_store.py`): deterministically fold a recorded event stream into a `ResolutionCase` through the **existing** intake/billing/risk handlers + `InMemoryCaseStateStore` (no `ResolutionCase` schema change), reusing `get_by_correlation_id`; expose a `reconcile(recorded, store)` entry that is a **no-op when the rebuilt state already matches** the live/terminal case (case-level guard ⇒ at-most-one decision, FR-013/FR-019). Reused by TR05; ensure TR03–TR05 pass with the reaper neutralized.
- [ ] TR07 [US4] Verify reuse-only & no regressions: confirm the harness/rebuild add **no new dependency, no new topic, no new event contract** (Constitution Principle V), that the decentralization guards stay green (`apps/agents/customer_resolution/tests/test_no_supervisor.py`, `tests/integration/test_no_router.py` — the replay harness directs no agent, FR-021), and run `pytest tests/integration/test_workflow_choreography.py -m integration -k replay` plus `tests/integration/test_idempotency.py` to confirm all replay/idempotency tests are green.

**Checkpoint**: The recorded three-event stream is provably idempotent, deterministically replayable, and the case is rebuildable/reconcilable from its events with zero duplicate side effects.

---

## Dependencies & Execution Order

- **Foundational (Phase 1, TR01→TR02)**: TR02 depends on TR01 (replay consumes what recording produces). Both depend on the shared multi-agent harness (`tasks.md` T006) and config knobs (`tasks.md` T002).
- **Tests (Phase 2, TR03/TR04/TR05)**: depend on TR01–TR02. All three share `test_workflow_choreography.py` — author as separate test functions; `[P]` = logically independent functions coordinating on one file. Write them to FAIL first.
- **Implementation (Phase 3)**: TR06 makes TR05 pass; TR07 is the final reuse/regression gate after TR03–TR06.

```
TR01 ─► TR02 ─►┬─ TR03 ─┐
               ├─ TR04 ─┼─► TR06 ─► TR07
               └─ TR05 ─┘
```

## Parallel Opportunities

```bash
# After TR01–TR02 land, author the three acceptance-criterion tests together:
Task: "Replay → exactly one decision, identical outcome (TR03) in tests/integration/test_workflow_choreography.py"
Task: "Idempotent re-delivery → no duplicate side effects (TR04) in tests/integration/test_workflow_choreography.py"
Task: "Rebuild/reconcile case state from events (TR05) in tests/integration/test_workflow_choreography.py"
```

## Notes

- **No new dependency, no new topic, no new event contract** — this replays the **existing** event set
  through the **existing** handlers/store; the only genuinely-new code is the recording helper (TR01),
  replay harness (TR02), and the rebuild/reconcile function (TR06).
- The reaper is neutralized (disabled or infinite deadline) for completed-run replay so determinism does
  not depend on wall-clock (research R2; contracts/replay-and-trace.md §1).
- This focused list corresponds to `tasks.md` Phase 6 / US4 (T024–T027). Keep `tasks.md` as the
  authoritative full-feature list; fold these in there if/when you implement the whole feature.
- Verify each test FAILS before implementing TR06; commit after each task or logical group.
