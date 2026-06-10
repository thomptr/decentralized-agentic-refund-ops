---
description: "Focused task list — Timeout & Peer-Failure Scenario Tests for Decentralized Workflow & Event Choreography (006)"
---

# Tasks: Timeout Scenario Tests (006 · User Story 3 — Deterministic failure paths)

**Input**: Design documents from `/specs/006-workflow-choreography/`

**Scope**: This is a **focused subset** of the full feature tasks (`tasks.md`), covering only the
timeout / peer-unavailable scenario tests requested. It realizes part of **User Story 3 (Priority P2)**
and maps to the same code; if you later run the full feature, these tasks correspond to `tasks.md` US3
(T016–T023) and the timeout fixtures (T042/T043) and may be merged there. IDs here are prefixed `TT`
("timeout tests") to avoid collision with the shared `tasks.md`.

**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅,
contracts/timeout-and-failure-paths.md ✅, contracts/choreography.md ✅. Depends on the shared
multi-agent integration harness (`tasks.md` T006, `tests/integration/conftest.py`), the deadline/reaper
config knobs (`tasks.md` T002 — `CASE_DEADLINE_SECONDS`, `REAPER_TICK_SECONDS`), the store query
(`tasks.md` T003 — `list_timed_out_cases`), and the **reaper itself** (`tasks.md` T021 module +
T022 `serve()` wiring). If those are not yet in place, complete them first or stub a minimal harness;
the **result-never-arrives** scenarios cannot pass until the reaper exists.

**Tests**: INCLUDED — FR-016/FR-017/SC-004/SC-007 explicitly require automated failure-path tests. Test
tasks are written before the implementation they cover and must FAIL first (the result-never-arrives
tests fail until the reaper lands).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US3 (maps to spec User Story 3 — Deterministic failure paths)
- All paths are repository-root-relative

---

## The two failure mechanisms behind the five requested scenarios

The five requested scenarios are **not one mechanism** — they split into two distinct, separately-tested
code paths that resolve to the **same terminal decision** with **different reasons**. Encoding that split
is the core value of this focused list.

| Requested scenario | How it is simulated | Detected by | escalation_reason | Maps to requested audit output |
|---|---|---|---|---|
| **Billing Agent unavailable** | billing peer **absent from discovery** (no `AgentCard`) | `intake_handler` `except` branch (`event_handlers.py:350`) — `delegate()` raises at send time | `peer_failure` | `audit.agent-task.failed` |
| **Risk Agent unavailable** | risk peer **absent from discovery** | `intake_handler` `except` branch | `peer_failure` | `audit.agent-task.failed` |
| **Billing result never arrives** | billing peer **discoverable but not serving / silent** (request published, never consumed) | **reaper sweep** past `CASE_DEADLINE_SECONDS` | `analysis_timeout` | `audit.agent-task.timeout` |
| **Risk result never arrives** | risk peer **discoverable but silent** | reaper sweep | `analysis_timeout` | `audit.agent-task.timeout` |
| **Both results never arrive** | both peers **discoverable but silent** | reaper sweep | `analysis_timeout` | `audit.agent-task.timeout` |

**Why this distinction matters**: "unavailable" (undiscoverable ⇒ delegation cannot be *sent*) is caught
synchronously at intake and is *not* a timeout — it never waits. "result never arrives" (request sent,
peer silent) is the genuine timeout the reaper enforces. The user's `audit.agent-task.failed` vs
`audit.agent-task.timeout` distinction is exactly this `peer_failure` vs `analysis_timeout` split.

## Mapping the requested "expected outputs" onto existing topics (no new topic — Principle V)

| Requested output name | Actual event (no new topic/contract introduced) | Discriminator |
|---|---|---|
| `resolution.case.escalated` | `local.customer.resolution.decided.v1` (`TOPIC_RESOLUTION_DECIDED`) with `outcome = ResolutionOutcome.ESCALATE_HUMAN`; case lifecycle reaches `CaseStatus.ESCALATED` | `outcome == escalate_human` |
| `audit.agent-task.failed` | `local.audit.envelope.recorded.v1` (`TOPIC_AUDIT`) | audit record carries `escalation_reason="peer_failure"` (delegation-failure / failed-slot path) |
| `audit.agent-task.timeout` | `local.audit.envelope.recorded.v1` (`TOPIC_AUDIT`) | audit record carries `escalation_reason="analysis_timeout"` (reaper path) |

There is **no separate `resolution.case.escalated` topic and no separate audit-failed/audit-timeout
topic** — escalation is the terminal `decided` event with `ESCALATE_HUMAN`, and the failed/timeout
distinction is the audit record's `escalation_reason`/outcome. Tests assert against the existing topics
(`TOPIC_RESOLUTION_DECIDED`, `TOPIC_AUDIT`) using `query_by_correlation(...)` from
`src/agent_foundation/audit/store.py`.

---

## Acceptance criteria → task map

| Acceptance criterion (from request) | Spec refs | Realizing test(s) |
|---|---|---|
| **Workflow never waits forever** — every scenario reaches a terminal state within `deadline + ≤ REAPER_TICK_SECONDS` grace; no case left open | FR-017, FR-018, SC-004, US3 AC1/AC2 | **TT03, TT04, TT05, TT06, TT07**, asserted bound in **TT09** |
| **Timeout behavior is deterministic** — injected clock + fixed sub-second deadline ⇒ same terminal outcome/reason every run, order-independent | FR-017, SC-004, SC-007, contracts §"Determinism for tests/replay" | **TT02** (clock-injected unit), reused fixed-deadline config in **TT05–TT07** |
| **Timeout result is auditable** — the escalation emits an audit record queryable by `correlation_id`, naming actor/case/action/reason | FR-022, SC-005, US3 AC2 | **TT08** (auditability assertion shared by all five scenarios) |

---

## Phase 1: Foundational (failure-injection harness — blocks the scenario tests)

**Purpose**: Two deterministic ways to break a peer — *undiscoverable* (no `AgentCard` ⇒ delegation
raises) and *discoverable-but-silent* (request published, never consumed ⇒ reaper). Reuses the shared
multi-agent harness (`tasks.md` T006); adds **no new dependency, no new topic, no new event contract**.

- [ ] TT01 [US3] Extend the shared end-to-end fixture (`tests/integration/conftest.py`, building on `tasks.md` T006) with a `start_resolution_workflow(*, silent_peers=(), undiscoverable_peers=())` knob: (a) for each id in `undiscoverable_peers`, omit that peer's `AgentCard` from the resolution agent's discovery registry so `delegate()` raises and the `intake_handler` `except` branch fires (`event_handlers.py:350`); (b) for each id in `silent_peers`, register the peer's `AgentCard` (discoverable) but do **not** start its `AgentRuntime` handler (request is published to its `endpoint_topic` and never consumed); start the resolution agent with sub-second `CASE_DEADLINE_SECONDS`/`REAPER_TICK_SECONDS` overrides and per-test unique consumer groups. Yields the broker URL + a stop handle.
- [ ] TT02 [P] [US3] Reaper determinism unit test (injected clock, **no Kafka**) in `apps/agents/customer_resolution/tests/test_reaper.py`: with a fixed `clock()` and a fixed `CASE_DEADLINE_SECONDS`, assert a case with **one** missing slot and a case with **both** slots missing each escalate to `ResolutionOutcome.ESCALATE_HUMAN` / `escalation_reason="analysis_timeout"` deterministically (same result across repeated runs and regardless of which slot, if any, was filled); assert an already-`DECIDED` case is **skipped** under the guard; assert escalation fires only once `now > deadline_at` and within one tick. (Corresponds to / extends `tasks.md` T016.)

**Checkpoint**: A test can spin up the three-agent workflow with any peer made undiscoverable or silent, and the reaper's timeout decision is provably deterministic in isolation.

---

## Phase 2: Scenario tests (write first; the result-never-arrives tests must FAIL until the reaper lands)

All five scenario tests live in `tests/integration/test_workflow_choreography.py` as separate `[P]`
functions (logically parallel, coordinating on one file), each marked `@pytest.mark.integration`. Each
injects a refund ticket for an eligible/low-risk customer (so only the broken peer, not the decision
rule, drives the escalation) and asserts: terminal `decided` with `ESCALATE_HUMAN`, case status
`ESCALATED`, the documented `escalation_reason`, and that **no second decision** is emitted.

- [ ] TT03 [P] [US3] **Billing Agent unavailable.** Start the workflow with `undiscoverable_peers=("billing-entitlement-agent",)`; inject a refund ticket; assert exactly one `customer.resolution.decided` for the `correlation_id` with `outcome=ESCALATE_HUMAN` and `escalation_reason="peer_failure"`, case reaches `CaseStatus.ESCALATED`, and **no** billing task request was resolvable (delegation failed at send). (FR-018, SC-007 → `audit.agent-task.failed`.) In `tests/integration/test_workflow_choreography.py`.
- [ ] TT04 [P] [US3] **Risk Agent unavailable.** Mirror of TT03 with `undiscoverable_peers=("risk-fraud-agent",)`; assert one `decided(ESCALATE_HUMAN)` / `escalation_reason="peer_failure"`, `CaseStatus.ESCALATED`. (FR-018, SC-007 → `audit.agent-task.failed`.) In `tests/integration/test_workflow_choreography.py`.
- [ ] TT05 [P] [US3] **Billing result never arrives.** Start with `silent_peers=("billing-entitlement-agent",)` (billing discoverable, not serving; risk serves normally and its result *does* arrive); inject a refund ticket; assert the reaper escalates the case to one `decided(ESCALATE_HUMAN)` / `escalation_reason="analysis_timeout"`, `CaseStatus.ESCALATED`, the risk slot is present but billing slot missing, and the case is resolved within `CASE_DEADLINE_SECONDS + ≤ REAPER_TICK_SECONDS`. (FR-017, SC-004 → `audit.agent-task.timeout`.) In `tests/integration/test_workflow_choreography.py`. (Corresponds to `tasks.md` T042 `billing_timeout`.)
- [ ] TT06 [P] [US3] **Risk result never arrives.** Mirror of TT05 with `silent_peers=("risk-fraud-agent",)` (risk silent, billing result arrives); assert one `decided(ESCALATE_HUMAN)` / `escalation_reason="analysis_timeout"`, `CaseStatus.ESCALATED`, billing slot present / risk slot missing, resolved within the deadline+grace bound. (FR-017, SC-004 → `audit.agent-task.timeout`.) In `tests/integration/test_workflow_choreography.py`. (Corresponds to `tasks.md` T043 `risk_timeout`.)
- [ ] TT07 [P] [US3] **Both results never arrive.** Start with `silent_peers=("billing-entitlement-agent","risk-fraud-agent")`; inject a refund ticket; assert the reaper escalates to one `decided(ESCALATE_HUMAN)` / `escalation_reason="analysis_timeout"`, `CaseStatus.ESCALATED`, **both** opinion slots missing, and the case resolves within the deadline+grace bound (Edge case "Both opinions missing"). (FR-017, SC-004 → `audit.agent-task.timeout`.) In `tests/integration/test_workflow_choreography.py`.

**Checkpoint**: All five requested scenarios are encoded as tests asserting the correct terminal outcome and the correct `peer_failure`-vs-`analysis_timeout` reason.

---

## Phase 3: Cross-cutting acceptance-criteria assertions (auditability + never-waits-forever bound)

- [ ] TT08 [P] [US3] **Timeout/failure result is auditable.** Add a parametrized assertion (helper reused by TT03–TT07, or a dedicated test) in `tests/integration/test_workflow_choreography.py`: for each scenario's `correlation_id`, call `query_by_correlation(broker, correlation_id)` (`src/agent_foundation/audit/store.py`) and assert an audit record exists for the escalation that names the **actor** (`customer-resolution-agent`), the **case** (`correlation_id`), the **action**, and an **outcome/reason** equal to the expected `escalation_reason` (`peer_failure` for TT03/TT04, `analysis_timeout` for TT05–TT07) — proving the terminal decision is reconstructible from the audit trail alone. (FR-022, SC-005, US3 AC2.)
- [ ] TT09 [P] [US3] **Workflow never waits forever (bounded termination).** Add an assertion (shared helper) that every scenario reaches its terminal `decided` event within `CASE_DEADLINE_SECONDS + REAPER_TICK_SECONDS + small_fixed_grace` measured from ticket injection, and that the case is **not** left in a non-terminal status afterward (poll `list_timed_out_cases`/case status shows zero stuck cases). Run with sub-second config so the suite is fast and the bound is meaningful. (SC-004, FR-017.) In `tests/integration/test_workflow_choreography.py`.

**Checkpoint**: The three acceptance criteria — never-waits-forever, deterministic, auditable — are each backed by a passing assertion across all five scenarios.

---

## Phase 4: Implementation / wiring gate (make the result-never-arrives tests pass)

These are the **reused/new agent code** the timeout tests depend on; they are owned by `tasks.md` US3
and listed here only as the gate this focused suite turns green against. Do not duplicate the code —
complete the `tasks.md` task and check the box here.

- [ ] TT10 [US3] Confirm the reaper module exists and routes timed-out cases through `_apply_decision` with `TimeoutStatus(any_missing=True, deadline_exceeded=True)` ⇒ `ESCALATE_HUMAN`/`analysis_timeout`, under the store `asyncio.Lock`, skipping already-`DECIDED` cases (re-uses `tasks.md` T021 `apps/agents/customer_resolution/reaper.py` + T003 `list_timed_out_cases`). TT02/TT05/TT06/TT07 go green here.
- [ ] TT11 [US3] Confirm the reaper is gathered as a concurrent task in `ResolutionService.serve()` with graceful stop-event shutdown (re-uses `tasks.md` T022 `apps/agents/customer_resolution/agent.py`), so the integration harness (TT01) actually runs the sweep.
- [ ] TT12 [US3] Verify the delegation-failure path stays mapped to `escalation_reason="peer_failure"` for undiscoverable peers (`apps/agents/customer_resolution/event_handlers.py:350`) so TT03/TT04 go green; confirm the suite introduces **no new dependency, no new topic, no new event contract** (Constitution Principle V) and that the decentralization guards stay green (`apps/agents/customer_resolution/tests/test_no_supervisor.py`, `tests/integration/test_no_router.py` — the harness directs no agent, FR-021). Run `pytest tests/integration/test_workflow_choreography.py -m integration -k "timeout or unavailable"` and `apps/agents/customer_resolution/tests/test_reaper.py` to confirm all timeout/failure tests are green.

**Checkpoint**: All five scenarios resolve deterministically to an auditable `escalate_human` terminal within a bounded deadline, with `peer_failure` vs `analysis_timeout` correctly distinguished.

---

## Dependencies & Execution Order

- **Foundational (Phase 1)**: TT01 (harness injection knobs) depends on `tasks.md` T006 (shared harness) + T002 (config). TT02 (reaper unit) depends only on the reaper module shape (`tasks.md` T021) — can be authored against the interface and run once T021 lands.
- **Scenario tests (Phase 2)**: TT03/TT04 (unavailable) depend on TT01 only — they pass as soon as the delegation-failure path (TT12) is confirmed. TT05/TT06/TT07 (result-never-arrives) depend on TT01 **and** the reaper (TT10/TT11) — they FAIL until the reaper lands.
- **Acceptance assertions (Phase 3)**: TT08/TT09 depend on TT03–TT07 (they assert over the same runs).
- **Gate (Phase 4)**: TT10/TT11/TT12 are the `tasks.md` US3 implementation this suite verifies; check them as those land.

```
T006 ─► TT01 ─►┬─ TT03 ─┐                    (unavailable → peer_failure: green w/ TT12)
T002 ─►        ├─ TT04 ─┤
T021 ─► TT02   ├─ TT05 ─┼─► TT08 ─► TT09     (result-never-arrives → analysis_timeout: green w/ TT10/TT11)
               ├─ TT06 ─┤
               └─ TT07 ─┘
```

## Parallel Opportunities

```bash
# After TT01 (+ reaper for the silent-peer cases) lands, author the five scenarios together:
Task: "Billing Agent unavailable → peer_failure (TT03) in tests/integration/test_workflow_choreography.py"
Task: "Risk Agent unavailable → peer_failure (TT04) in tests/integration/test_workflow_choreography.py"
Task: "Billing result never arrives → analysis_timeout (TT05) in tests/integration/test_workflow_choreography.py"
Task: "Risk result never arrives → analysis_timeout (TT06) in tests/integration/test_workflow_choreography.py"
Task: "Both results never arrive → analysis_timeout (TT07) in tests/integration/test_workflow_choreography.py"
# TT02 (reaper unit) is fully parallel — separate file (apps/.../tests/test_reaper.py).
```

## Notes

- **No new dependency, no new topic, no new event contract** — the suite drives the **existing** three
  agents through the **existing** decided/audit topics; the only genuinely-new test code is the
  failure-injection harness knob (TT01) and the scenario/assertion functions. "Escalated" is the
  terminal `decided(ESCALATE_HUMAN)` event; "failed vs timeout" is the audit `escalation_reason`.
- The two `unavailable` scenarios (TT03/TT04) do **not** exercise the reaper at all — they prove the
  workflow never even *starts* waiting when a peer is undiscoverable (synchronous `peer_failure`). Only
  the three `never-arrives` scenarios (TT05–TT07) exercise the wall-clock reaper path.
- Determinism (SC-004) rests on the injectable `clock`/`CASE_DEADLINE_SECONDS` (contracts
  §"Determinism for tests/replay") and on `decision_engine.decide()` being pure/total — the same inputs
  always yield `ESCALATE_HUMAN`/`analysis_timeout`.
- This focused list corresponds to `tasks.md` US3 (T016–T023) plus the timeout fixtures (T042/T043).
  Keep `tasks.md` as the authoritative full-feature list; fold these in there if/when you implement the
  whole feature.
- Verify each result-never-arrives test FAILS before the reaper lands; commit after each task or logical
  group.
