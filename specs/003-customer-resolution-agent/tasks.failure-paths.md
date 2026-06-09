# Tasks (sidecar): Failure-Path & Deliberate-Fault Test Suite

> **Why this is a sidecar.** `tasks.md` was being edited concurrently by other `/speckit-tasks`
> runs while this phase was generated — phases were being appended **and renumbered/reordered**,
> and the max task id moved **T140 → T217** during generation (new phases for the decision engine,
> architecture docs, case closure, E2E test, and structured response drafter all landed mid-run).
> To avoid clobbering that work or colliding on ids, this phase is staged here — matching the
> existing `tasks.phase15-timeout.md` / `tasks-classifier.md` / `tasks-state-store.md` sidecar
> precedent — and is **ready to merge** into `tasks.md` as the next phase.
>
> **Merge instructions — the phase number and task ids below are PROVISIONAL placeholders.**
> `tasks.md` is under active concurrent growth (its max id climbed past T217 → T230 and a *different*
> Phase 23 was claimed by another run while this file was being written), so the literal labels
> **`Phase 23` / `T218–T231` will collide** and MUST be renumbered at merge time:
>
> 1. Append this `## Phase NN: Failure-Path …` section to the **end** of `tasks.md`.
> 2. Set `NN` to the next free phase number (one past the then-current last `## Phase`).
> 3. Renumber the 14 tasks to a contiguous block starting one past the then-current max `T###`
>    (setup task → the 11 case tasks → audit task → gate task), and re-point the intra-phase
>    cross-references (setup blocks the rest; audit & gate run last) to the new ids.
>
> Only the numeric labels need reconciliation — the task **content, grouping, and order are stable**.
> The `T0xx`/`T1xx` references that point **into earlier phases** (e.g. T070/T094/T106/T148) are real
> dependencies and must NOT be renumbered.

---

## Phase 23: Failure-Path & Deliberate-Fault Test Suite (hardens US2/US3, SC-005/SC-007) 🛡️ FAILURE PATHS

**Goal**: Consolidate the eleven user-named failure/edge cases into one deliberately-runnable
deliberate-fault suite (`tests/test_failure_paths.py`) that proves the agent never fabricates a missing
judgment, never double-decides, and escalates with a recorded reason on every fault. Most cases already
have unit-level coverage scattered across Phases 10–18; this phase adds a single end-to-end fault suite
(the SC-005 idempotency evidence and the SC-007 "deliberate-fault tests" gathered in one place) plus the
two cases (billing-peer-unavailable, billing/risk **result timeout**) not yet exercised as explicit
failure paths.

**Independent test**: Run `uv run pytest apps/agents/customer_resolution/tests/test_failure_paths.py`
and confirm all eleven named cases pass — each fault resolves to a defined outcome (escalation, a
duplicate-suppressing no-op, or a parked unknown result) with the reason recorded in the audit trail,
and no peer judgment is ever fabricated.

> **Liveness note (authoritative)**: per spec **Assumptions → "Liveness and timeout handling are out of
> scope"** and **research R6 / the Phase 14 `deadline_at` task (T094)**, there is **no reaper**.
> `deadline_at` is *recorded but not enforced*. The two "result timeout" cases below therefore assert
> (a) the documented gap — a case whose deadline has elapsed stays open with **no** spontaneous
> decision — **and** (b) that when the Phase 18 decision engine is invoked with a `timeout_status`
> flagging the missing analysis it returns `escalate_human(analysis_timeout/missing_analysis)`, never
> approve/deny. They do **not** introduce a background timeout enforcer.

### User-named cases → expected behavior → verified by

| # | Case | Expected behavior | New test | Existing coverage |
|---|------|-------------------|----------|-------------------|
| 1 | **Billing Agent unavailable** | Discovery returns no `billing-entitlement-agent` card → fail-closed (no billing `TaskRequest`); case escalates with reason; no billing finding fabricated | T219 | Phase 13 (T084/T086) |
| 2 | **Risk Agent unavailable** | `RiskPeerUnavailable` → `PENDING_RISK`/`escalate_human` with reason; no risk `TaskRequest`; no risk finding fabricated | T220 | Phase 12 (T070/T072/T077) |
| 3 | **Billing result timeout** | No reaper: case stays `waiting_for_peer_reviews`, no spontaneous decision (documented gap); `decide(...)` with `timeout_status` flagging billing → `escalate_human(analysis_timeout/missing_analysis)` | T221 | T094, Phase 18 (T154/T158d) |
| 4 | **Risk result timeout** | Symmetric to #3 for the risk slot | T222 | T094, Phase 18 (T154/T158d) |
| 5 | **Duplicate ticket event** | One case, exactly one billing + one risk delegation, exactly one final decision; duplicate recorded in audit | T223 | T065/T093/T097 (SC-005) |
| 6 | **Duplicate billing result** | Second result for a `task_id` absent from `pending_tasks` (or an already-`decided` case) → logged no-op; no overwrite, no second decision | T224 | Phase 15 (T106) |
| 7 | **Unknown correlation ID** | Result whose `correlation_id` matches no case → parked in bounded buffer + warning; no case created, no exception; drained when the case later appears | T225 | Phase 15/16 (T105/T110/T119) |
| 8 | **Low classifier confidence** | Triage confidence below threshold is **not** dropped → defaults to "refund review required" with ambiguity recorded and `confidence` carried on the classification event | T226 | Phase 3/10 (T012/T015) |
| 9 | **High fraud risk** | `RiskFinding.level == high` → `decide(...)` returns `escalate_human` (elevated-risk), taking precedence over an eligible/pending billing finding | T227 | Phase 16/18 (T121/T152) |
| 10 | **Billing eligible but risk high** | Conflict/risk precedence → `escalate_human` (`conflicting_analyses`/elevated risk), never approve | T228 | Phase 18 (T148/T152) |
| 11 | **Billing ineligible but risk low** | Billing ineligible with no risk trigger → `deny_refund`, never escalate | T229 | Phase 18 (T148/T152) |

### Setup (blocks the suite)

- [ ] T218 [US3] Create `apps/agents/customer_resolution/tests/test_failure_paths.py` and add deliberate-fault fixtures to `apps/agents/customer_resolution/tests/conftest.py` (T002): a `no_billing_card`/`no_risk_card` discovery stub (`find_capable(...)` returns an empty list), an `elapsed_deadline_case` builder (case in `waiting_for_peer_reviews` with `deadline_at` in the past and a `timeout_status` flagging the still-`pending` analysis), a `duplicate_envelope` helper (re-delivers the same ticket identity / same result `task_id`), and an `unknown_correlation_result` builder (a billing/risk `TaskResult` whose envelope `correlation_id` matches no open case) — reuses the existing `TaskResult`/`CaseStore` fixtures, adds no new transport

### Peer-unavailability cases (US2, SC-007)

- [ ] T219 [P] [US2] **Billing Agent unavailable** in `apps/agents/customer_resolution/tests/test_failure_paths.py`: with `no_billing_card`, drive a refund ticket and assert the billing capability fails closed (mirroring the Phase 12 `RiskPeerUnavailable` pattern, T070/T072) — **no** billing `TaskRequest` is emitted, the case resolves to `escalate_human`/pending with a recorded reason, and **no** billing finding is fabricated (AC4, FR-005, SC-007)
- [ ] T220 [P] [US2] **Risk Agent unavailable** in `apps/agents/customer_resolution/tests/test_failure_paths.py`: with `no_risk_card`, drive a refund ticket and assert `RiskPeerUnavailable` drives the case to `PENDING_RISK`/`escalate_human` with a recorded reason — **no** risk `TaskRequest` is emitted and **no** risk finding is fabricated (reuses Phase 12 T070/T072/T077; AC4, SC-007)

### Result-timeout / liveness cases (US3 — documented gap, no reaper)

- [ ] T221 [P] [US3] **Billing result timeout** in `apps/agents/customer_resolution/tests/test_failure_paths.py`: from `elapsed_deadline_case` (risk received, billing still `pending`, `deadline_at` in the past) assert (a) **no** reaper fires — the case stays `waiting_for_peer_reviews` and emits **no** decision on its own (documented liveness gap, T094/research R6); and (b) invoking `decide(...)` with a `timeout_status` flagging the missing billing analysis returns `escalate_human` with reason `analysis_timeout`/`missing_analysis`, **never** approve/deny (Phase 18 T148/T154; FR-008; edge case "only one analysis returns")
- [ ] T222 [P] [US3] **Risk result timeout** in `apps/agents/customer_resolution/tests/test_failure_paths.py`: symmetric to T221 with billing received and the **risk** slot still `pending`/elapsed — case stays open with no spontaneous decision, and `decide(...)` with a risk-flagging `timeout_status` returns `escalate_human(analysis_timeout/missing_analysis)`, never approve/deny (Phase 18 T148/T154; FR-008)

### Idempotency / duplicate cases (US3, SC-005)

- [ ] T223 [P] [US3] **Duplicate ticket event** in `apps/agents/customer_resolution/tests/test_failure_paths.py`: deliver the same `support.ticket.created` (identical ticket identity) twice via `duplicate_envelope` and assert `get_or_create` yields one case, **exactly one** billing + **one** risk delegation in total, **exactly one** final decision, and that the duplicate re-delivery is recorded in the audit trail (FR-011, reuses T065/T093/T097; SC-005)
- [ ] T224 [P] [US3] **Duplicate billing result** in `apps/agents/customer_resolution/tests/test_failure_paths.py`: deliver a second billing `TaskResult` for a `task_id` already absent from `pending_tasks` (and one for an already-`decided` case) and assert a logged no-op — `billing_result` is not overwritten, `pending_tasks` is unchanged, and **no** second/contradictory decision is emitted (FR-012, reuses Phase 15 T106)

### Unknown-correlation case (US3)

- [ ] T225 [P] [US3] **Unknown correlation ID** in `apps/agents/customer_resolution/tests/test_failure_paths.py`: feed an `unknown_correlation_result` whose `correlation_id` matches no open case and assert it is parked in the bounded `parked_results` buffer with a structured warning — **no** case is created, **no** exception escapes — and that when a case with that `correlation_id` is later created the parked result is drained and applied (reuses Phase 15/16 T105/T110/T119; AC2)

### Classifier / decision-confidence case (US1/US3)

- [ ] T226 [P] [US1] **Low classifier confidence** in `apps/agents/customer_resolution/tests/test_failure_paths.py`: a ticket whose triage/classification confidence is below threshold is **not** dropped — assert it defaults to "refund review required" with the ambiguity recorded in the rationale and the `confidence` carried on the `customer-issue.classified` event (edge case "Ambiguous triage"; FR-002/FR-003; reuses Phase 3/10 T012/T015); and that a `decide(...)` whose `compute_confidence(...)` is below `CONFIDENCE_THRESHOLD` returns `escalate_human(low_confidence)`, never approve/deny/partial (Phase 18 T148/T152/T156)

### Decision-policy fault rows (US3, SC-003/SC-007)

- [ ] T227 [P] [US3] **High fraud risk** in `apps/agents/customer_resolution/tests/test_failure_paths.py`: `RiskFinding.level == high` (and `requires_human_review=True`) → `decide(...)` returns `escalate_human` (elevated-risk reason), taking precedence over an eligible or still-pending billing finding (Phase 16/18 T121/T148/T152; research R4, SC-007)
- [ ] T228 [P] [US3] **Billing eligible but risk high** in `apps/agents/customer_resolution/tests/test_failure_paths.py`: `BillingFinding.eligibility == eligible` with `RiskFinding.level == high` → `escalate_human` (`conflicting_analyses`/elevated risk), **never** approve — the named conflict row of the truth table (decision-policy §C/§D, Phase 18 T148/T152; FR-009, SC-007)
- [ ] T229 [P] [US3] **Billing ineligible but risk low** in `apps/agents/customer_resolution/tests/test_failure_paths.py`: `BillingFinding.eligibility == ineligible` with `RiskFinding.level == low` (no risk trigger) → `deny_refund`, **never** escalate — the named non-conflict deny row of the truth table (decision-policy §C/§D, Phase 18 T148/T152; FR-009, SC-003)

### Audit + gate (extends US4)

- [ ] T230 [US4] **Failure-path audit assertion** in `apps/agents/customer_resolution/tests/test_failure_paths.py`: for every escalating fault above (peer unavailable, result failure/timeout, low confidence, high risk, conflict) assert the escalation `reason` is written to the audit trail and reconstructable by `correlation_id`, and that each duplicate (ticket/result) re-delivery is recorded — extends the audit steps in T037/T038/T159 (FR-010/FR-013/FR-014, SC-006/SC-007)
- [ ] T231 [US3] **Run the failure-path suite green**: `uv run pytest apps/agents/customer_resolution/tests/test_failure_paths.py` (plus the referenced unit tests) and confirm all eleven named deliberate-fault cases pass; fold this module into the Phase 9 quality gate (T044)

**Checkpoint**: All eleven named failure/edge cases are covered by one runnable deliberate-fault suite —
peer-unavailability and result-timeout escalate (never fabricate), duplicate ticket/result events are
idempotent no-ops, unknown-correlation results are parked, low-confidence/high-risk/conflict cases
escalate, and `ineligible+low-risk` denies — each with the reason on the audit trail (SC-005/SC-007).

### Phase 23 dependencies

- **T218** (test module + fault fixtures) blocks T219–T230.
- **Peer-unavailability** T219/T220 depend on the Phase 12/13 discovery + fail-closed paths
  (T070/T072/T077, T084/T086) and the Phase 14 store statuses (T087/T091).
- **Timeout** T221/T222 depend on the Phase 14 `deadline_at` recording (T094) and the Phase 18
  `decide(...)`/`timeout_status` (T148/T154).
- **Idempotency** T223/T224 depend on the Phase 11/14/15 idempotency guards (T065/T093/T106).
- **Unknown-correlation** T225 depends on the Phase 15/16 parked-results buffer (T105/T110/T119).
- **Confidence/decision-policy** T226–T229 depend on the Phase 10 classifier confidence (T012/T015) and
  the **authoritative** Phase 18 decision engine (T148/T152/T156) — treat Phase 18, not Phase 5, as the
  decision source.
- **T230** (audit) follows T219–T229 and folds into the US4 audit steps (T037/T038/T159); **T231**
  (gate) runs last and extends T044.
- Pure test phase: reuses `001`/`002` transport/audit/idempotency and the existing fixtures (T002)
  unchanged — adds no new model, topic, or transport (FR-016, Principle V).
