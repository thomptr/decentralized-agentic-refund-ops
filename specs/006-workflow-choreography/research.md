# Research: Decentralized Workflow & Event Choreography (006)

**Branch**: `006-workflow-choreography` | **Date**: 2026-06-10

This feature is **integration and choreography over already-shipped agents** (003 customer-resolution,
004 billing-entitlement, 005 risk-fraud) on the 001 event foundation and 002 A2A runtime. The research
below records the design decisions for the *gaps* that must be closed to make the system run
end-to-end, plus the explicit decisions to **reuse** existing mechanisms unchanged.

Each decision is `Decision / Rationale / Alternatives considered`.

---

## Reuse audit (what already exists — do NOT rebuild)

A code walk of `apps/agents/customer_resolution/` confirms the choreography is ~90% present:

| Capability | Where | Status |
|---|---|---|
| Ticket intake → triage → A2A delegation (billing + risk, concurrent) | `event_handlers.intake_handler`, `a2a_handlers.delegate` | ✅ done |
| Billing/Risk publish their **own** domain result events (dual-path: domain event + A2A TaskResult) | `apps/agents/risk_fraud/main.py` → `TOPIC_RISK_RESULT`; `apps/agents/billing_entitlement/main.py` → `TOPIC_BILLING_RESULT` | ✅ done |
| Correlate async results by `correlation_id` (case key) and `task_id` (slot), parking early results | `state_store` (`get_by_correlation_id`, `get_by_task_id`, `park_*_result`) | ✅ done |
| Deterministic decision rule (8-row truth table incl. conflict/missing) | `decision_engine.decide` | ✅ done |
| Exactly-one decision per case; late-result-recorded-not-applied | `_apply_decision` + `is_terminal`/`DECIDED` guards; `result_handler` late-result branch | ✅ done |
| Event-level idempotency (per consumer group) + case-status guards + stable `task_id` (`uuid5`) | `IdempotencyTracker`; `a2a_handlers` `uuid5(correlation_id, capability)` | ✅ done |
| Per-step audit emission; `query_by_correlation` | `audit/store.py` | ✅ done |

**Decision**: Treat all of the above as authoritative and frozen. 006 adds **no new domain logic and no
new event contract or topic**; it closes integration gaps and proves the flow.
**Rationale**: Spec Assumption "Reuse, not rebuild"; Constitution Principle V (PoC scope discipline) and
Principle I (no new agent unless an existing one cannot fulfill the responsibility).
**Alternatives considered**: Re-implementing aggregation as a blocking `gather(submit, submit)` —
rejected (003 already documents why: cannot represent "case open pending second result", cannot record
late-after-decision results). Introducing a new orchestrator/aggregator agent — rejected
(constitutional violation, Principle I).

---

## R1 — Timeout enforcement (the headline gap)

**Problem**: `ResolutionCase.deadline_at` is set at delegation time but is **"recorded but not enforced
(research R6)"** in 003. `build_timeout_status` and `decide()` already accept a `TimeoutStatus`, but no
component ever fires on deadline elapse. FR-017 / US3-AC1 / SC-004 require every case to reach a terminal
state within deadline + a small grace period.

**Decision**: Add a **timeout reaper loop** as a fourth concurrent task inside `ResolutionService.serve`
(it is the resolution agent's own autonomous responsibility for its own cases — not a separate process,
not a router). The reaper periodically (tick interval ≪ deadline) asks the store for cases that are
non-terminal, past `deadline_at`, and still have `pending_tasks`, and resolves each by calling the
existing `_apply_decision` path with a `TimeoutStatus(any_missing=True, deadline_exceeded=True)`. This
reuses the decision engine's Row 1 (`escalate_human`, reason `analysis_timeout`) and the existing
DECIDED/terminal guard, so it cannot double-decide a case that just received its last result (FR-013,
FR-019).

**Rationale**: One loop, one code path (`_apply_decision`), reuses the store lock and the existing
terminal guard → no new race surface and no duplicate-decision risk. Tick-based sweeping is the simplest
mechanism that proves bounded termination (Principle V).

**Alternatives considered**:
- *Per-case `asyncio.sleep(deadline)` timer task*: rejected — N timers to track, must be cancelled on
  early decision, and they evaporate on restart with no recovery; harder to reason about than a sweep.
- *Kafka delayed/scheduled messages*: rejected — no native broker support; over-engineered for a PoC.
- *Decide on partial info when one opinion is present*: rejected — spec Assumption "a missing opinion
  escalates rather than deciding on partial information" (conservative refund-safety default).

**Clock injection**: the reaper takes an injectable `now()`/clock and tick interval so tests drive
timeouts deterministically with a sub-second deadline (no real waiting). Default demo deadline is
introduced as `CASE_DEADLINE_SECONDS` (see R7).

---

## R2 — Replay determinism vs. a wall-clock reaper

**Problem**: Replay (FR-014/015, SC-003/006) requires re-processing a recorded stream to yield the
**identical** decision and **zero** additional side-effects. A wall-clock timeout is non-deterministic
and would conflict with "identical replay".

**Decision**: Define replay over **recorded, completed runs**. The replay harness consumes a recorded
event stream (from `seek_to_beginning` on fresh, uniquely-named consumer groups) into a fresh
ResolutionService backed by a fresh in-memory store, and asserts the re-derived decision equals the
originally recorded `customer.resolution.decided` payload. Because `decide()` is pure and total and
`task_id`s are stable (`uuid5`), the same inputs always produce the same outcome. The reaper is **disabled
or given an effectively-infinite deadline during a completed-run replay** so it never injects a
clock-dependent escalation; the timeout *path itself* is validated separately (R1) with a controlled
short deadline. Replaying a stream that already contains a timeout-escalation decision reproduces that
decision because the decision event is part of the recorded stream.

**Rationale**: Cleanly separates "deterministic decision reproduction" (the replay guarantee the spec
asks for) from "liveness/timeout" (a clock-driven behaviour that is inherently not replayable from raw
inputs). Matches SC-003's framing ("replaying a recorded end-to-end scenario").

**Alternatives considered**: Recording wall-clock timestamps and replaying the clock — rejected as
over-engineering for a PoC; the spec's replay scenarios are the happy path, async aggregation, and the
*defined* failure paths, all of which are reproducible without a simulated clock.

---

## R3 — End-to-end idempotency & "zero extra side-effects"

**Decision**: Idempotency rests on three existing layers, composed and *verified* by 006, not changed:
1. **Event-level**: each consumer group runs an `IdempotencyTracker` keyed by `event_id` → a redelivered
   envelope is skipped before the handler runs.
2. **Task-level**: `task_id = uuid5(correlation_id, capability)` is stable, so a re-issued delegation is
   the same task; billing/risk dedup by `task_id` before publishing a second result.
3. **Case-level**: `CaseStatus == DECIDED` / `is_terminal` guards make `_apply_decision` and
   late-result handling at-most-once per case.

The outbound `decided`/`drafted` publishes are **not** tracker-deduped (they are produced, not consumed);
the **case-status DECIDED guard is the idempotency anchor** for them. 006 adds an assertion-level check
("count of `customer.resolution.decided` events for a correlation_id == 1") in the replay/idempotency
tests (SC-006).

**Rationale**: The guarantee already exists structurally; the feature's job is to *prove* it end-to-end.
**Alternatives considered**: Adding an outbound-dedup store for decision events — rejected; the case
state machine already enforces single-decision and a second store is redundant complexity (Principle V).

---

## R4 — Correlation & async aggregation across topics

**Decision**: Reuse unchanged. Case key = envelope `correlation_id` (= ticket root id). Result→case
matching uses `task_id` (for A2A `TaskResult` on `TOPIC_TASK_RESULT`) and `correlation_id` (for the
domain result events `TOPIC_BILLING_RESULT` / `TOPIC_RISK_RESULT`). Results that arrive before the case
exists are **parked** in a bounded buffer and matched on case creation. Per-case attribution under
concurrency (US2 / SC-002) is guaranteed by these keys plus the store's `asyncio.Lock`.

**Rationale**: This is exactly the mechanism 003 shipped; 006 adds a concurrency stress test (≥10
shuffled cases) to *prove* no cross-case contamination, not new code.

**Alternatives considered**: Reworking to consume only the A2A `TaskResult` topic (drop domain result
topics) — rejected; the dual-path (domain event + A2A result) is an existing, deliberate design and the
spec requires billing/risk to publish their own result events.

---

## R5 — Causal-order trace tool (observability)

**Problem**: `query_by_correlation` returns audit records in **Kafka-offset** order. FR-006 makes
`causation_id` the contract for ordering, and FR-023 / US5 / SC-005 require reconstructing a case's
journey in **causal** order from a single correlation id, without reading code.

**Decision**: Add a read-only trace utility (`apps/api/trace_case.py`, plus a small reusable function in
the resolution package or a foundation helper) that: loads all audit + domain events for one
`correlation_id`, builds the causation DAG (root = the `support.ticket.created` event whose
`causation_id` is null), and emits the steps **topologically ordered by causation**, each line showing
actor (`agent_id`), case (`correlation_id`), action/event_type, outcome, and timestamp. Output is
human-readable text (and `--json`).

**Rationale**: Small, additive, read-only tool that turns the already-emitted audit trail into the
operator-facing journey the constitution (Principle IV) and spec require. Builds directly on
`consume_all_audit_records` / `query_by_correlation`.

**Alternatives considered**: Relying on offset order from `dev_consume_events.py` — rejected; offset
order across multiple topics is not guaranteed to equal causal order, and the spec names causation as the
ordering contract. A graph database / external tracing system (Jaeger/OTel) — rejected (production
hardening, out of PoC scope, Principle V).

---

## R6 — End-to-end multi-agent test harness

**Decision**: Add `tests/integration/test_workflow_choreography.py` (live Kafka via the existing
`testcontainers` pattern). For each scenario it: `create_topics`, starts the **real** billing and risk
`AgentRuntime`s (with their domain-result publishers) and an in-process `ResolutionService` against the
container broker, publishes a `support.ticket.created` event with a `Publisher`, and awaits the terminal
`customer.resolution.decided` event on `TOPIC_RESOLUTION_DECIDED` with a `Consumer`. Scenarios cover the
spec's user stories and success criteria:
- US1: approve (eligible+low), deny (ineligible+risky), non-refund → direct_response.
- US2 / SC-002: ≥10 concurrent cases with naturally interleaved results → per-case attribution.
- US3 / SC-007: timeout (peer silent, short `CASE_DEADLINE_SECONDS`) → escalate; rejected/failed request
  → escalate; conflict (eligible+high) → escalate; malformed ticket → escalate.
- US4 / SC-003/006: replay a recorded scenario → identical decision, exactly one decision event.
- US5 / SC-005: trace by correlation id reconstructs the full causal journey.

**Rationale**: In-process agents against a real broker is the established pattern in
`tests/integration/test_demo_agents_*.py`; it gives a true end-to-end proof while staying fast and
assertable.

**Alternatives considered**: Subprocess/Docker-composed agents — rejected (slower, harder to assert
internal state and to inject a short deadline). Mock broker — rejected (would not prove the real
choreography, defeating the feature's purpose).

---

## R7 — Deadline value & the SC-008 budget

**Problem**: `DELEGATION_TIMEOUT_SECONDS` is currently `30`, but SC-008 targets the **happy path under
30s**. A deadline equal to the SLA risks spurious timeouts.

**Decision**: Introduce `CASE_DEADLINE_SECONDS` (configurable, default chosen for the demo, e.g. `15`)
as the reaper's deadline, distinct from the request-annotation `DELEGATION_TIMEOUT_SECONDS`. Integration
tests override it to a sub-second/low value to exercise timeouts without waiting. The happy path
completes in well under the deadline on a single-broker local setup.

**Rationale**: Keeps the demo deadline comfortably above happy-path latency while making the timeout path
cheaply testable; one configurable knob, documented (Principle V).

**Alternatives considered**: Reusing `DELEGATION_TIMEOUT_SECONDS` for both — rejected (conflates request
annotation with case liveness and collides with SC-008).

---

## R8 — Decentralization compliance (no orchestrator)

**Decision**: The reaper, replay harness, and trace tool are **not agents and not routers**. The reaper
is an internal loop of the resolution agent acting only on *its own* cases (the same agent that opened
them); the replay harness and trace tool are **read-only operator/test utilities** that consume recorded
events and never direct any agent. No component tells billing or risk what to do beyond the existing A2A
task requests the resolution agent already issues.

**Rationale**: Principle I / FR-021. The existing `test_no_supervisor.py` / `test_no_router.py` guards
remain valid; 006 adds an assertion that the choreography still emerges purely from event reactions.

**Alternatives considered**: A standalone "timeout service" or "saga coordinator" — rejected
(constitutional violation; the responsibility belongs to the case owner).

---

## Resolved unknowns

All Technical Context items are resolved (no `NEEDS CLARIFICATION` remain): language/deps/transport/
testing all inherit 001–005 unchanged; the only new knobs are `CASE_DEADLINE_SECONDS` and the reaper tick
interval, both configurable with documented defaults.
