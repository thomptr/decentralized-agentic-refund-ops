# Contract: Replay Harness & Causal Trace Tool (006)

Two read-only utilities that prove the system is replay-safe and observable. Neither directs any agent
(Principle I, FR-021); both consume **already-recorded** events.

## 1. Replay harness (FR-014, FR-015, FR-016, SC-003, SC-006)

**Goal**: re-process a recorded end-to-end scenario and prove the **identical** decision with **zero**
additional side-effect events.

**Mechanism**:
- Record a scenario by capturing the full event set for one or more `correlation_id`s (the integration
  test simply runs a scenario against the container broker and reads back the topics).
- Replay re-feeds the recorded **input** events (ticket + peer results) into a *fresh* ResolutionService
  with a *fresh* in-memory store, using `Consumer.seek_to_beginning()` on **uniquely-named** consumer
  groups so offsets start at zero and the `IdempotencyTracker` starts empty.
- The reaper is disabled (or given an effectively-infinite deadline) for completed-run replay so no
  clock-dependent escalation is injected (research R2).

**Assertions**:
- Re-derived `customer.resolution.decided` payload (outcome + explanation/rationale) **equals** the
  originally recorded decision (SC-003).
- Count of `customer.resolution.decided` events for the `correlation_id` is **exactly 1**; no duplicate
  opinions, requests, or decisions (SC-006, FR-013/FR-015).
- A redelivered duplicate input event is skipped by the `IdempotencyTracker` (FR-011) and a repeated
  `task_id` returns the stored result (FR-012) — asserted via audit `duplicate_skipped` outcomes.

**Determinism basis**: `decide()` is pure/total; `task_id = uuid5(correlation_id, capability)` is stable;
classification is deterministic. Same inputs ⇒ same decision.

## 2. Causal trace tool (FR-023, US5, SC-005)

**Goal**: from a single `correlation_id`, reconstruct 100% of the workflow steps in causal order without
reading code.

**Location**: `apps/api/trace_case.py` (CLI) + a reusable function (resolution package or foundation
helper) over `agent_foundation.audit.store`.

**Input**: `correlation_id` (+ `--json`, `--broker`).

**Algorithm**:
1. Load all audit records via `query_by_correlation(broker, correlation_id)` (and, optionally, the
   domain/decision topics for richer detail).
2. Build the causation map `event_id → causation_id`; the root is the `support.ticket.created` event
   (`causation_id is None`).
3. Topologically order steps by causation (ties broken by timestamp then offset).

**Output (per step)**: `seq, actor (agent_id), correlation_id, event_type/action, outcome, task_id?,
timestamp`. For an escalated case, the trail must make the **escalation reason and the missing/failing
contributor** identifiable (US5 AC2) — surfaced from the audit `reason`/`outcome` fields.

**Acceptance**:
- For a completed case, every step from ticket → decision is present and causally ordered (SC-005,
  US5 AC1).
- For an escalated case, the reason and the missing/failed contributor are visible in the trail alone
  (US5 AC2).
