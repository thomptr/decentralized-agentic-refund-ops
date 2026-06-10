---
description: "Focused task list — Peer Result Aggregation Rules for Decentralized Workflow & Event Choreography (006)"
---

# Tasks: Peer Result Aggregation Rules (006 · User Story 2 — Correlated async aggregation, with US3 escalation rules)

**Input**: Design documents from `/specs/006-workflow-choreography/`

**Scope**: This is a **focused subset** of the full feature tasks (`tasks.md`), covering only the
**peer-result aggregation rules** requested via `/speckit-tasks`. It pins down — and where it diverges,
hardens — the deterministic rule by which the Customer Resolution Agent combines the billing-eligibility
opinion and the fraud-risk opinion into exactly one terminal decision per case. It realizes **spec User
Story 2 (Priority P2 — correlated, async aggregation of independent opinions)** and the escalation slices
of **User Story 3 (P2)**, against FR-008, FR-009, FR-010, FR-013, FR-019, FR-024. IDs here are prefixed
`AG` to avoid collision with the shared `tasks.md` IDs and the `FP` failure-path slice
(`tasks-aggregation-rules.md` complements both — keep `tasks.md` as the authoritative full list).

**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅,
contracts/decision-rule.md ✅, contracts/choreography.md ✅. The aggregation surfaces already exist
(`event_handlers.py`, `state_store.py`, `decision_engine.py`, `models.py`); this slice is verification +
two targeted hardening fixes, **no new dependency, topic, or event contract** (Constitution V).

**Tests**: INCLUDED — the request's four acceptance criteria are themselves assertions, and FR-016
requires automated aggregation/correlation coverage. Test tasks are written **before** the
implementation they cover and must FAIL first (except verify-only tasks, noted inline).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US2 (correlated async aggregation) or US3 (escalation rules)
- All paths are repository-root-relative

---

## The five aggregation rules → surface → current status → gap to close

| # | Rule (from request) | Spec ref | Surface (file / function) | Current behavior | Gap this slice closes |
|---|---|---|---|---|---|
| **R1** | Decision allowed **only** when required Billing **and** Risk results are present | FR-008, FR-010 row 1 | `models.ResolutionCase.is_ready_to_decide` gate + `decision_engine.decide` Row 1 (`any_missing`) | Decision only fires once `pending_tasks` is empty (or a slot failed); `decide()` Row 1 escalates if still missing ✅ | **Verify-only** — pin with a deterministic test (AG04) |
| **R2** | Billing result **alone** is insufficient | FR-008 | `result_handler` / `billing_result_handler` → `is_ready_to_decide()` guard (`event_handlers.py:455,568`) | Billing-only leaves `risk_task_id` in `pending_tasks` → not ready → no decision ✅ | **Verify-only** — pin with test (AG05) |
| **R3** | Risk result **alone** is insufficient | FR-008 | `risk_result_handler` (`event_handlers.py:661`) → `is_ready_to_decide()` guard | Low/elevated risk-only is held ✅ — **but** the high-risk fast path (`:629`) decides on risk alone (see R4) | **Verify-only for low/elevated** (AG06); high handled by R4 |
| **R4** | High-risk result **may** force escalation (the one documented single-opinion exception) | FR-010 (high never auto-approves), US3 AC3 | `risk_result_handler` high-risk fast path (`event_handlers.py:629`) | Fires on `level in {elevated, high}` **or** `requires_human_review` **before billing arrives** | **FIX (AG10)** — `elevated` alone is **not** a documented exception: `ineligible+elevated → deny_refund` (decide Row 5), so escalating on `elevated`-before-billing makes the outcome arrival-order-dependent (violates "deterministic"). Narrow the fast path to `high` (+ `requires_human_review`); let `elevated` wait for billing |
| **R5** | Missing peer result after **timeout** forces escalation | FR-017, FR-010 row 1 | reaper (`tasks.md` T012–T015) → `_apply_decision` → `decide` Row 1 with `deadline_exceeded` → `escalate_human`/`analysis_timeout` | Reaper owned by `tasks.md`; aggregation side already maps `any_missing + deadline_exceeded` → `analysis_timeout` ✅ | **Verify-only at the aggregation boundary** (AG07) — assert `decide()` yields `escalate_human`/`analysis_timeout`; do **not** re-implement the reaper |

---

## The four acceptance criteria → surface → current status → gap to close

| Criterion (from request) | Spec ref | Surface | Current behavior | Gap this slice closes |
|---|---|---|---|---|
| **AC-A** Aggregation is **deterministic** | FR-009, SC-002 | `decide()` is pure & total; `build_timeout_status`/`compute_confidence` pure | Pure for the both-present path ✅ — **except** the R4 `elevated` fast-path arrival-order divergence | Fix via AG10; prove via AG04/AG08 (billing-first ≡ risk-first) |
| **AC-B** Partial results are **stored** | FR-008 | `state_store.apply_result` writes `billing_result`/`risk_result`, discards from `pending_tasks`, holds in `WAITING_FOR_PEER_REVIEWS` | Partial finding persisted on the case while the other slot is pending ✅ | **Verify-only** — pin with test (AG05/AG06) |
| **AC-C** Out-of-order result events are **handled** | FR-009, US2 AC1/AC2 | correlation by `correlation_id` (domain events) and `task_id` (A2A); per-case `pending_tasks`; parking buffers | Shuffled arrival across many cases attributes correctly ✅ — **but** a result that arrives **before** its case exists is parked and **never re-applied** (`state_store.park_*` is write-only) | **FIX (AG11)** — drain parked results for a `correlation_id` when its case is created/known, so an early result is not silently lost (it would otherwise force a needless timeout) |
| **AC-D** Unknown result events are **parked, logged, or ignored safely** | US2 (no cross-case contamination), FR-019 | unknown case → `park_*` (logged, bounded deque); terminal/decided case → `late_result_recorded_not_applied` audit; `task_id` not in `pending_tasks` → `apply_result` logged no-op; generic `result_handler` no-match → `result_no_matching_case` warn | All four "unknown" shapes are handled without crashing or contaminating another case ✅ | **Verify-only** (AG09); confirm AG11's drain does not resurrect a result into the wrong case |

**Determinism invariant asserted by this slice**: for a fixed `(triage, billing finding, risk finding,
timeout_status)`, `decide()` returns an identical `outcome` + `escalation_reason` regardless of the order
in which the two results arrived and regardless of wall-clock time (the only clock dependence is
`deadline_exceeded`, which is only read on the missing-opinion path). **No new outcome, threshold, topic,
event contract, or dependency is introduced** (Constitution V) — the only code deltas are narrowing one
fast-path condition (AG10) and draining the existing parking buffer (AG11).

---

## Phase 1: Foundational (blocking — shared aggregation test harness)

**Purpose**: A single in-process fixture set every aggregation test reuses: a `CapturingPublisher`, a
freshly-built `InMemoryCaseStateStore`, and helpers to (a) build a `WAITING_FOR_PEER_REVIEWS` case with
both `billing_task_id`/`risk_task_id` registered as pending and (b) feed a billing/risk domain-result
envelope. Reuses existing models/handlers — no new production code in this phase.

- [ ] AG01 [US2] Add aggregation test fixtures to `apps/agents/customer_resolution/tests/conftest.py` (or extend the existing one): a `make_waiting_case(store, *, billing_eligibility=None, risk_level=None)` helper that creates a refund case via `store.get_or_create`, sets `status=WAITING_FOR_PEER_REVIEWS`, assigns stable `billing_task_id`/`risk_task_id` and registers both via `store.add_pending_task`, plus `make_billing_envelope(correlation_id, recommendation, **kw)` / `make_risk_envelope(correlation_id, recommendation, **kw)` builders returning `EventEnvelope`s carrying `BillingRefundAnalysisCompletedPayload` / `RiskReviewCompletedPayload`. Reuse the `CapturingPublisher` from the failure-path slice if present, else add a minimal recording double.
- [ ] AG02 [P] [US2] Add a `decide_outcome(case)` assertion helper to the test module `apps/agents/customer_resolution/tests/test_aggregation_rules.py` that calls `decision_engine.decide` directly with a case's `(triage, billing_result, risk_result, build_timeout_status(case, now=...))` and returns `(outcome, escalation_reason)` — used by the determinism tests (AG04, AG08) to compare arrival orders without re-running the broker loop.

**Checkpoint**: Tests can build a waiting case, feed either result in any order, capture emitted decisions/audits, and call `decide()` directly — all in-process, no broker.

---

## Phase 2: Tests (write first — one per rule / criterion; MUST FAIL where a fix is pending)

All tests live in `apps/agents/customer_resolution/tests/test_aggregation_rules.py` as independent
functions (so they are logically `[P]` despite sharing one file — author them together).

- [ ] AG03 [P] [US2] **R1 — both required (verify).** Build a waiting case, feed **both** a billing (`eligible`) and a risk (`low`) result via the domain handlers; assert exactly one `customer.resolution.decided` is emitted with `approve_refund`, the case ends `DECIDED`, and `decide()` Row 1 (`any_missing`) was **not** taken. Expected to PASS against current code.
- [ ] AG04 [P] [US2] **AC-A — deterministic across arrival order (verify+pin).** For each combination in the truth table (`eligible×{low,elevated,high}`, `ineligible×{low,elevated,high}`, `partial×{low,elevated}`, `indeterminate×…`), drive the case **twice** — billing-then-risk and risk-then-billing — through the real handlers; assert the final `(outcome, escalation_reason)` is **identical** between the two orders. This is the headline determinism test; it FAILS today for `ineligible+elevated` and `eligible+elevated` because of the R4 `elevated` fast path (fixed by AG10).
- [ ] AG05 [P] [US2] **R2 + AC-B — billing alone insufficient, partial stored.** Feed only the billing result; assert **no** decision/draft is emitted, the case stays `WAITING_FOR_PEER_REVIEWS`, `case.billing_result` is populated (partial result stored) and `risk_task_id` remains in `pending_tasks`. Expected to PASS.
- [ ] AG06 [P] [US2] **R3 + AC-B — risk (low/elevated) alone insufficient, partial stored.** Feed only a `low` risk result, then separately only an `elevated` risk result; in both cases assert no decision is emitted, case stays `WAITING_FOR_PEER_REVIEWS`, `case.risk_result` is populated, and `billing_task_id` remains pending. The `elevated`-alone assertion FAILS today (fast path escalates) and passes after AG10.
- [ ] AG07 [P] [US3] **R5 — missing-after-timeout escalates (aggregation boundary, verify).** Build a waiting case with one slot still pending and `deadline_at` in the past; call `_apply_decision` (simulating the reaper's call site) and assert it emits exactly one `escalate_human` with `escalation_reason="analysis_timeout"` (vs `missing_analysis` when the deadline is in the future). Do **not** start the reaper loop here — this pins the rule the reaper depends on (`tasks.md` T012–T015 owns the loop).
- [ ] AG08 [P] [US3] **R4 — high risk forces escalation (the documented single-opinion exception).** Feed only a `high` risk result (no billing); assert the case escalates to `escalate_human` with `escalation_reason="elevated_risk"` and ends `ESCALATED`, and that this is the **only** single-opinion exception (cross-check AG06 proves `elevated`/`low` do not). Asserts the post-AG10 behavior; the `high` branch passes today, the "only high" part is what AG10 enforces.
- [ ] AG09 [P] [US2] **AC-D — unknown / late / mis-keyed results handled safely.** Four sub-assertions, no crash, no cross-case contamination: (a) a billing result whose `correlation_id` has **no** case is parked (`_parked_billing` grows by one, a `billing_result_unknown_case` warning is logged) and no decision is emitted; (b) a result for an already-`DECIDED`/terminal case writes a `duplicate_skipped`/`late_result` audit and does **not** alter the decision (FR-019); (c) a generic A2A `TaskResult` with an unknown `task_id` logs `result_no_matching_case` and returns; (d) `store.apply_result` with a `task_id` not in `pending_tasks` returns `AttachOutcome.DUPLICATE` (logged no-op). Expected to PASS.
- [ ] AG10-test [P] [US2] **AC-C — out-of-order: result arrives before its case (drain).** Park a billing result for a correlation id that has no case yet (call `risk_result_handler`/`billing_result_handler` first), then run `intake_handler` for that ticket; assert the parked billing result is **drained and applied** to the new case (`case.billing_result` populated, `_parked_billing` no longer holds it) and that once the risk result follows, a normal decision is produced — i.e. the early result is not lost to a needless timeout. This test FAILS today (parking is write-only) and passes after AG11.
- [ ] AG11-test [P] [US2] **AC-C — many concurrent cases, shuffled (verify, FR-009/SC-002).** Create ≥10 waiting cases, then feed their billing/risk results in a deterministically-shuffled, interleaved order through the handlers; assert each case's final decision is composed of **exactly its own** two opinions (no cross-case attribution) and exactly one decision per case is emitted. Use a fixed shuffle seed for determinism. Expected to PASS (correlation by `correlation_id`/`task_id` already isolates cases) — this pins the no-contamination guarantee.

**Checkpoint**: All five rules and four criteria are encoded as tests. AG04 (`elevated` rows), AG06
(`elevated`-alone), AG08 ("only high"), and AG10-test (parked-drain) FAIL pending Phase 3; the rest pass
against current code.

---

## Phase 3: Implementation (make the failing tests pass — two targeted fixes)

- [ ] AG10 [US2] **Fix the high-risk fast path to preserve determinism (R4 / AC-A).** In `apps/agents/customer_resolution/event_handlers.py` `risk_result_handler` (`:629`), narrow the single-opinion escalation trigger from `finding.level in ("elevated", "high") or finding.requires_human_review` to **`finding.level == "high" or finding.requires_human_review`**. Rationale: `high` (and an explicit peer review request) is the documented refund-safety exception that may escalate without billing; `elevated` is **not** — `ineligible+elevated → deny_refund` (decide Row 5) and `eligible+elevated → conflict→escalate` (Row 8), both of which require the billing opinion to be deterministic. An `elevated` (or `low`) result therefore falls through to the normal `apply_result` + `is_ready_to_decide()` gate and waits for billing. Update the handler's docstring/comment (the `# High risk can force immediate escalation` line) accordingly. Makes AG04 (`elevated` rows), AG06 (`elevated`-alone), AG08 ("only high") pass.
- [ ] AG11 [US2] **Drain parked results when a case becomes known (AC-C).** Add `drain_parked_results(correlation_id) -> list[tuple[bool, Any]]` to `apps/agents/customer_resolution/state_store.py` (`InMemoryCaseStateStore`) that pops and returns any parked billing/risk payloads matching `correlation_id` from `_parked_billing`/`_parked_risk` under the lock, and call it from `intake_handler` (`apps/agents/customer_resolution/event_handlers.py`) immediately after `store.get_or_create`, re-dispatching each drained payload through `billing_result_handler`/`risk_result_handler` (or a shared apply path) so an early-arriving opinion is applied rather than lost. Guard against re-parking (the case now exists) and preserve idempotency (`apply_result` still dedups by `task_id`/`pending_tasks`). Add the method to the `CaseStateStore` Protocol as a default-safe no-op so persistent backends remain compatible. Makes AG10-test pass; must not regress AG09(a) (a result with genuinely no case is still parked, not dropped).

**Checkpoint**: The aggregation rule is fully deterministic across arrival order (AG04 green), `elevated`
and `low` single opinions wait for billing (AG06 green), only `high`/`requires_human_review` escalates on
one opinion (AG08 green), and an opinion that races ahead of its case is drained and applied rather than
timing out (AG10-test green).

---

## Phase 4: Cross-cutting verification & regression gate

- [ ] AG12 [US2] Run the aggregation suite and regression gates: `pytest apps/agents/customer_resolution/tests/test_aggregation_rules.py` is green; the existing `apps/agents/customer_resolution/tests/test_decision_engine.py` and `test_state_store.py` stay green (no truth-table or store-contract regression); and the decentralization/domain-isolation guards stay green (`test_no_supervisor.py`, `test_domain_isolation.py`, `tests/integration/test_no_router.py` — aggregation adds no orchestrator and reads no peer store, FR-021/FR-025). Confirm **no new dependency, topic, or event contract** was added (Constitution V — only one narrowed condition and one parked-buffer drain).

---

## Dependencies & Execution Order

- **Foundational (Phase 1)**: AG01 (fixtures) → AG02 (decide helper, depends on the case builder). Both
  precede every Phase-2 test.
- **Tests (Phase 2)**: AG03–AG11-test are logically independent `[P]` but share
  `test_aggregation_rules.py` — author as separate functions. Write the four failing tests (AG04 elevated
  rows, AG06 elevated-alone, AG08 "only high", AG10-test) to FAIL before Phase 3.
- **Implementation (Phase 3)**: AG10 (one edit in `event_handlers.py` `risk_result_handler`) and AG11
  (new `state_store.py` method + an `intake_handler` call) touch different functions; AG11 also edits
  `event_handlers.py` (`intake_handler`) so sequence AG10 → AG11 to avoid edit conflicts in that file.
- **Gate (Phase 4)**: AG12 runs last, after AG03–AG11.

```
AG01 ─► AG02 ─┬─► AG03 ─┐
              ├─► AG04 ─┤
              ├─► AG05 ─┤
              ├─► AG06 ─┤
              ├─► AG07 ─┼─► AG10 ─► AG11 ─► AG12
              ├─► AG08 ─┤
              ├─► AG09 ─┤
              ├─► AG10-test ─┤
              └─► AG11-test ─┘
```

## Parallel Opportunities

```bash
# Phase 1: AG02 depends on AG01's case builder — run AG01 first, then AG02.
# Phase 2: author the rule/criterion tests together (independent functions, one file):
Task: "R1 both-required test (AG03)"
Task: "AC-A deterministic-across-order test (AG04)"
Task: "R2 billing-alone test (AG05)"
Task: "R3 risk-alone low/elevated test (AG06)"
Task: "R5 timeout-escalation boundary test (AG07)"
Task: "R4 high-risk fast-path test (AG08)"
Task: "AC-D unknown/late/mis-keyed test (AG09)"
Task: "AC-C parked-drain test (AG10-test)"
Task: "AC-C concurrent-shuffled test (AG11-test)"
```

## Notes

- **No new dependency, no new topic, no new event contract.** The two production deltas are: (1) narrowing
  the high-risk fast-path condition from `{elevated, high}` to `high` in `risk_result_handler`, and (2)
  draining the already-existing parking buffer when a case is created. Everything else is verification of
  behavior 003–005 already shipped.
- **Determinism is the headline.** AG04 is the criterion that exposes the real bug: today an
  `ineligible+elevated` case escalates if the risk opinion lands first but denies if billing lands first.
  Narrowing the fast path (AG10) makes both orders converge on `deny_refund`.
- **The high-risk exception is intentional.** Rule R4 ("high-risk **may** force escalation") is the one
  sanctioned single-opinion decision, justified by refund safety (high risk never auto-approves). It does
  not contradict R1 ("decision only when both present"): escalation-on-high is an explicit, documented
  carve-out, asserted by AG08 and bounded to `high`/`requires_human_review` by AG10.
- **Timeout (R5) is owned by the reaper** in `tasks.md` (T012–T015 / US3). This slice only pins the
  aggregation-side mapping (`any_missing + deadline_exceeded → escalate_human/analysis_timeout`) via AG07;
  it does not start or re-implement the reaper loop.
- **"Unknown result events" (AC-D)** already has four safe handlers (park / late-recorded-not-applied /
  unknown-task no-op / unmatched-generic warn). AG09 characterizes them; the only behavioral change is
  AG11 ensuring a *parked* result is later *drained*, which strengthens out-of-order handling without
  weakening the no-cross-case-contamination guarantee (AG11-test).
- Keep `tasks.md` as the authoritative full-feature list; fold these `AG` tasks into US2/US3 there if/when
  the whole feature is implemented. Verify each failing test FAILS before implementing its Phase-3
  counterpart; commit after each task or logical group.
