# Phase 15 (pending merge into tasks.md) — Peer-Result Timeout Handling

> **Why this is a separate file**: while this `/speckit-tasks` run was generating the section below,
> `specs/003-customer-resolution-agent/tasks.md` was being **actively rewritten by another concurrent
> session** (the read→write attempt failed with "file content has changed since last read", and the
> file gained a new *Phase 14 — Pluggable Case State Store* and tasks through **T098** mid-run). To
> avoid clobbering that session's work, this directive's tasks are parked here, numbered to continue
> cleanly **after** the current tail (**Phase 15**, **T099+**). **Action for the user**: once the other
> session settles, append this `Phase 15` block to the end of `tasks.md` — or tell me to merge it and I
> will.

This section is **additive** and **closes the liveness gap the spec deliberately deferred** (spec
*Assumptions* "Liveness and timeout handling are out of scope"; research **R6**; data-model.md §4 edge
"Only one analysis returns → case stays open"). Until now an `AWAITING_ANALYSES` case whose second peer
result never arrives would stay open **forever**. This phase makes such a case **resolve
deterministically at a deadline** instead. It reuses this file's package layout (`models.py`,
`decision_engine.py`, `state_store.py`, `event_handlers.py`, `agent.py`, `main.py`, `config.py`, tests
under `apps/agents/customer_resolution/tests/`).

**Reuse, not a parallel path (FR-016 / Principle V).** A timeout produces the **single, already-
registered** final decision event `customer.resolution.decided.v1` (data-model.md §7) with
`outcome = escalate_human` (or, in the one conservative case below, `deny_refund`) — this *is* the
directive's "resolution.case.escalated / failure event," expressed through the existing decision
contract. **No new topic, no new payload, no new transport, no second audit path** is introduced. This
keeps **exactly one final decision per case** (SC-003): a timeout is simply another *trigger* of the
final-decision path, racing the result loop through one shared decide-once guard (FR-012). It reuses
the existing `DELEGATION_TIMEOUT_SECONDS` constant (Phase 11 T063) and the `AnalysisSlot.received` /
`failed` state (data-model.md §3–§4), and composes with the pluggable `CaseStateStore` interface
introduced in the concurrent Phase 14 (T087–T098) if present — otherwise the in-process `CaseStore`.

**A "failed" slot is *not* a timeout.** A peer that returns `failed`/`rejected` already makes the case
immediately decidable via decision-policy **row 2** (`peer_failure`/`peer_rejection`). Timeout handles
only the **silent** case — a slot that is **neither `received` nor `failed`** when the deadline passes.

## Phase 15: Peer-Result Timeout Handling — deterministic deadline → escalation/failure (extends US3/US4)

### Directive rules → deterministic timeout policy (the heart of "deterministic")

A slot is **present** = `received` with a finding; **missing** = not `received` and not `failed`.
Evaluated for an undecided `AWAITING_ANALYSES` (or `PENDING_RISK`) case once its deadline passes:

| billing | risk | `outcome` | `escalation_reason` | Directive rule |
|---------|------|-----------|---------------------|----------------|
| missing | present | `escalate_human` | `billing_timeout` | "billing missing + risk present = escalate" |
| present | missing | **conservative**: `billing.eligible == false` → `deny_refund`; else `escalate_human` | `risk_timeout` (when escalated) | "risk missing + billing present = escalate **or conservative decision**" |
| missing | missing | `escalate_human` | `analysis_timeout` | "both missing = failed or escalated" |
| present | present | not a timeout — already decidable; run the **normal** `decide()` (race guard) | — | — |

The conservative `deny_refund` is the only non-escalation timeout outcome and is itself safe and
deterministic: with billing already **ineligible**, denying never pays out a refund the risk peer
hasn't cleared (mirrors decision-policy row 5). It never **approves** without a risk signal. The mode
is gated by a single config flag so it can be turned off (→ always escalate) without code change.

### Acceptance criteria → how each is met (from the `/speckit-tasks` request)

| Criterion | How it is satisfied | Verified by |
|-----------|---------------------|-------------|
| **Timeout does not block forever** | A timeout sweeper loop (a 4th concurrent loop) scans the case store each interval, finds cases whose `delegated_at + DELEGATION_TIMEOUT_SECONDS < now`, and drives each through the decide-once path — so every silent case leaves `AWAITING_ANALYSES` at the deadline (closes the research-R6 gap) | T103, T104, T105, T110 |
| **Timeout emits `resolution.case.escalated` / failure event** | `decide_on_timeout(case)` builds the registered `customer.resolution.decided.v1` with `outcome=escalate_human` (or conservative `deny_refund`) and a timeout `escalation_reason`; it is published via the shared `Publisher` (no parallel path, FR-016) and a "case timed out" audit step is written (FR-013) | T102, T106, T110 |
| **Timeout decision is deterministic** | `decide_on_timeout` is a **pure** function of the case's slot state implementing the table above (same state → same outcome); the deadline check uses an **injectable clock** (`now_fn`) so tests are time-deterministic; the timeout path and result loop share one atomic decide-once guard, so the outcome never depends on scheduling races | T102, T107, T108, T109 |

> **One decision, even under the race (FR-012 / SC-003).** The timeout sweeper and the result loop can
> both reach a case at nearly the same instant. Both finalize **only** through the shared
> `finalize_case(...)` guard, which checks `status != DECIDED` under the store before emitting. Whichever
> fires first wins; the loser is **recorded, not applied** — exactly the existing late-result behavior.

### Foundational (case deadline state + config + reasons — blocks the timeout path & tests)

- [ ] T099 [US3] Extend `ResolutionCase` in `apps/agents/customer_resolution/models.py` with `delegated_at: datetime | None = None`, plus pure helpers `missing_slots() -> set[Literal["billing","risk"]]` (slots neither `received` nor `failed`) and `is_overdue(now: datetime, timeout_seconds: int) -> bool` (`delegated_at is not None and status in {AWAITING_ANALYSES, PENDING_RISK} and now >= delegated_at + timedelta(seconds=timeout_seconds)`) — no I/O, unit-testable (extends data-model.md §4)
- [ ] T100 [US3] Set `case.delegated_at` to the inbound-event timestamp (a deterministic recorded clock value, **not** a wall-clock read inside business logic) at the moment both `TaskRequest`s are published in `delegate(case)` / `request_*_analysis` (`a2a_handlers.py`, extends T024/T064/T071/T081), so the deadline is anchored to a recorded time and the case becomes eligible for the sweeper
- [ ] T101 [US3] Add timeout config to `apps/agents/customer_resolution/config.py` (extends T009/T063): reuse `DELEGATION_TIMEOUT_SECONDS` as the deadline window, add `TIMEOUT_SWEEP_INTERVAL_SECONDS` (illustrative PoC value, ≪ the timeout), and `TIMEOUT_CONSERVATIVE_DENY_ON_INELIGIBLE: bool = True` (the conservative-mode flag); define the timeout escalation-reason constants `BILLING_TIMEOUT="billing_timeout"`, `RISK_TIMEOUT="risk_timeout"`, `ANALYSIS_TIMEOUT="analysis_timeout"`

### Deterministic timeout decision (the policy)

- [ ] T102 [US3] Implement the **pure** `decide_on_timeout(case) -> CustomerResponseDecisionPayload` in `apps/agents/customer_resolution/decision_engine.py` implementing the Phase-15 table exactly: `{billing missing, risk present} → escalate_human(billing_timeout)`; `{billing present, risk missing} → deny_refund` when `TIMEOUT_CONSERVATIVE_DENY_ON_INELIGIBLE` and `billing.eligible is False` else `escalate_human(risk_timeout)`; `{both missing} → escalate_human(analysis_timeout)`; `{both present} → delegate to the normal decide()`; set `escalation_reason`, `rationale` (naming which slot(s) timed out), and carry through `billing_summary`/`risk_summary` for any present slot (traceability, SC-004) — no I/O, deterministic, total

### Decide-once mechanism shared with the result loop (FR-012 / SC-003)

- [ ] T103 [US3] Extract/establish a single `finalize_case(case, decision, *, trigger: Literal["result","timeout"]) -> bool` guard in `apps/agents/customer_resolution/agent.py` (refactoring the US3 emit path, T034/T035): under the case store, **atomically** check `status != DECIDED`, set `status=DECIDED` + `decision`, publish exactly one `customer.resolution.decided.v1`, and return `True`; if already `DECIDED`, **record (audit) not apply** the trigger and return `False`. Both the result loop and the timeout sweeper finalize **only** through this function (FR-012, SC-003)

### Timeout sweeper loop — "does not block forever" (4th concurrent loop)

- [ ] T104 [US3] Implement `async run_timeout_sweeper(store, publisher, *, now_fn, interval_seconds, timeout_seconds, stop_event) -> None` in `apps/agents/customer_resolution/event_handlers.py`: each tick, snapshot the case store, select cases where `case.is_overdue(now_fn(), timeout_seconds)`, and for each call `decide_on_timeout(case)` (T102) → `finalize_case(case, decision, trigger="timeout")` (T103); skip `DECIDED`/`CLOSED_DIRECT` cases; never raise out of the loop (log + continue on a per-case error); `await asyncio.sleep(interval_seconds)` between ticks and exit cleanly when `stop_event` is set. `now_fn`/`interval_seconds`/`timeout_seconds` are **injected** (defaults from `config.py`) so the loop is deterministic and testable without real sleeping
- [ ] T105 [US3] Wire the sweeper as a **fourth** concurrent loop in `apps/agents/customer_resolution/main.py` `run()` alongside the intake consumer, result consumer, and runtime/card (`asyncio.gather(...)`), passing the shared case store, `Publisher`, and config; ensure it is cancelled/stopped on shutdown with the other loops (extends T011)

### Audit (extends US4)

- [ ] T106 [US4] Emit a "case timed out" audit step via `agent_foundation.audit.store.write_audit` in the timeout path (`agent.py`/`event_handlers.py`) carrying agent identity, `correlation_id`, the surviving `causation_id` (ticket `event_id`), timestamp, `outcome="completed"`, and `reason=<billing_timeout|risk_timeout|analysis_timeout>` plus which slot(s) were missing — so a timed-out resolution is reconstructable by correlation id (FR-013/FR-014, SC-006); folds into the US4 step list (T037)

### Tests (write first — must FAIL before implementation)

- [ ] T107 [P] [US3] Unit-test the deterministic policy in `apps/agents/customer_resolution/tests/test_decision_engine.py`: assert `decide_on_timeout` returns `escalate_human`/`billing_timeout` for billing-missing+risk-present; `deny_refund` for risk-missing+billing-ineligible (and `escalate_human`/`risk_timeout` for risk-missing+billing-**eligible**, and when the conservative flag is off); `escalate_human`/`analysis_timeout` for both-missing; and that calling it **twice on the same case yields an identical payload** (determinism)
- [ ] T108 [P] [US3] Unit-test the sweeper with an **injected clock** in `apps/agents/customer_resolution/tests/test_event_handlers.py`: a case with `delegated_at` and one missing slot is **not** finalized before `now_fn` reaches the deadline and **is** finalized exactly once after; `DECIDED`/`CLOSED_DIRECT` and not-yet-delegated cases are skipped; a per-case error does not stop the loop; assert no real time is slept (drive `now_fn` and a single tick directly)
- [ ] T109 [P] [US3] Unit-test the decide-once race in `apps/agents/customer_resolution/tests/test_state_store.py`: `finalize_case(trigger="timeout")` then a later `finalize_case(trigger="result")` (and the reverse order) produce **exactly one** `customer.resolution.decided.v1`, with the second call returning `False` and the late trigger **recorded, not applied** (FR-012, SC-003)
- [ ] T110 [P] [US3] Integration test in `apps/agents/customer_resolution/tests/test_customer_resolution.py` with a **tiny** `DELEGATION_TIMEOUT_SECONDS`/sweep interval: drive a refund ticket, deliver **only** the billing result → after the deadline the agent emits exactly one `customer.resolution.decided` with `outcome=escalate_human` and `escalation_reason=risk_timeout`; a separate ticket with **no** results → one decision with `escalation_reason=analysis_timeout`; then inject a **late** risk result for the first case and assert **no second** decision is emitted (timeout does not block forever; emits the escalation event; late result recorded-not-applied)

**Checkpoint**: A refund case whose peer result never arrives resolves at the deadline to a single,
deterministic `customer.resolution.decided` (escalate, or conservative deny) with a timeout reason and
an audit record — never blocking forever and never emitting a second decision when a late result
finally lands. All three acceptance criteria satisfied.

### Phase 15 dependencies

- **Foundational T099–T101** block the rest of the phase (case deadline state + config + reasons).
  T099 ∥ T101 (different concerns; T099/T100 both touch the case — sequence if edited together).
- **T102** (pure policy) depends on T099 (slot helpers) + T101 (reasons/flag); **T103** (decide-once)
  refactors the US3 emit path (T034/T035); **T104** (sweeper) depends on T102 + T103; **T105** wires
  T104 into `main.py` (extends T011); **T106** (audit) follows T103/T104 (folds into T037).
- **Tests T107/T108/T109/T110** are `[P]` across different files and written **before** T102–T106;
  T110 also requires the Phase 2 process/`Publisher` (T011), the US2 delegation (T024), and the US3
  result loop (T034).
- Composes with the concurrent **Phase 14** pluggable `CaseStateStore` (T087–T098) when merged — the
  sweeper snapshots whatever store implementation is wired; no coupling beyond the read/finalize API.
- Reuses `001`/`002` transport, audit, idempotency, runtime, and the existing
  `customer.resolution.decided.v1` decision contract unchanged (FR-016, Principle V) — **no new
  dependency, no new topic/payload, no second audit path**. Closes the research-R6 liveness gap.
