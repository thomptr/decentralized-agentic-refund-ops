# Data Model: Decentralized Workflow & Event Choreography (006)

**Branch**: `006-workflow-choreography` | **Date**: 2026-06-10

006 introduces **no new event contract and no new topic**. Every entity in the spec already has a
concrete representation shipped by 001–005. This document maps the spec's Key Entities onto the existing
types and records the **small, additive deltas** the integration work requires (a reaper-facing store
query, an injectable clock, two config knobs, and a read-only trace view). All event payloads, the
envelope, and the decision payload are reused **as-is**.

## Entity mapping (spec → existing implementation)

| Spec entity | Existing type / location | Notes |
|---|---|---|
| **Refund Case** | `ResolutionCase` + `CaseStatus` (`apps/agents/customer_resolution/models.py`) | 9-state lifecycle; keyed by `correlation_id`; carries `deadline_at`. Reused unchanged. |
| **Support Ticket** | `SupportTicketCreatedPayload` (`src/agent_foundation/payloads/support_ticket.py`) | Root event; `causation_id == None`. |
| **Opinion Request** | `TaskRequest` (`src/agent_foundation/payloads/task.py`) | `task_id = uuid5(correlation_id, capability)` is the idempotency + matching key. |
| **Opinion Result** | A2A `TaskResult` **and** domain events `BillingRefundAnalysisCompletedPayload` / `RiskReviewCompletedPayload` (`packages/contracts/events/payloads.py`) | Dual-path delivery; both carry the `correlation_id`. |
| **Decision** | `CustomerResponseDecisionPayload` (+ `CustomerResponseDraftedPayload`) | Outcome ∈ approve/deny/escalate (+ direct_response/partial/more-info); references contributing opinions via evidence + `*_result_event_id`. |
| **Correlation Chain** | `EventEnvelope.correlation_id` + `causation_id` + `agent.audit.v1` records (`AuditPayload`) | The audit topic is the durable journey; the trace tool orders it causally. |
| **Replay Scenario** | A recorded set of `EventEnvelope`s for one or more `correlation_id`s, re-fed from `seek_to_beginning` | No new type; the harness reads existing topics. |

## Case lifecycle (reused, with the timeout edge now *enforced*)

`CaseStatus` transitions are already defined in `models._ALLOWED_TRANSITIONS`. 006 does not add states;
it makes the **timeout path reachable at runtime** via the reaper:

```
received → classified ─┬─ (non-refund) ─────────────→ decided → response_drafted → closed
                       └─ (refund) → waiting_for_peer_reviews
                                          │
              both results / a failed slot│           ┌─ reaper: deadline elapsed, still pending
                                          ▼           ▼
                                   ready_for_decision  └──────────────→ escalated   (terminal)
                                          │
                                          ▼
                                       decided → response_drafted → closed
                                          └────────────────────────→ escalated (conflict/high-risk/peer-fail)
```

Terminal states: `closed`, `escalated`, `failed`. The reaper only ever moves a **non-terminal** case to
`escalated` (via the decision engine's `escalate_human` / reason `analysis_timeout`), and only through the
existing `_apply_decision` guard, guaranteeing at-most-one terminal decision (FR-013/FR-019).

## Deltas introduced by 006 (additive only)

### D1 — Store query for the reaper
Add one read method to `CaseStateStore` (Protocol) and `InMemoryCaseStateStore`:

```
async def list_timed_out_cases(self, now: datetime) -> list[ResolutionCase]
    # returns non-terminal cases where deadline_at is not None,
    # now > deadline_at, and pending_tasks is non-empty
```

Pure query under the existing `asyncio.Lock`; no schema change to `ResolutionCase`. A persistent backend
satisfies the same Protocol method.

### D2 — Injectable clock + reaper config
- `CASE_DEADLINE_SECONDS: int` (new, in `config.py`; default e.g. `15`) — the reaper's deadline, distinct
  from the request-annotation `DELEGATION_TIMEOUT_SECONDS`. `intake_handler` sets
  `case.deadline_at = now + CASE_DEADLINE_SECONDS`.
- `REAPER_TICK_SECONDS: float` (new; default e.g. `1.0`) — sweep interval (≪ deadline).
- The reaper accepts an injectable `now: Callable[[], datetime]` (default `lambda: datetime.now(UTC)`) so
  tests drive timeouts deterministically and replay can neutralize it (research R2/R7).

No change to any Pydantic event model. `TimeoutStatus` and `build_timeout_status` already exist and are
reused; the reaper constructs `TimeoutStatus(any_missing=True, deadline_exceeded=True, missing_reviews=…)`.

### D3 — Trace view (read-only projection)
A derived, non-persisted view built by the trace tool from `AuditPayload` records:

```
TraceStep = { seq, actor (agent_id), correlation_id, event_type/action, outcome, task_id?, timestamp,
              caused_by (causation_id) }
TraceCase = ordered[TraceStep]   # topologically ordered by causation, root = ticket event
```

This is a projection over existing audit data — not a new event or stored entity.

## Validation rules (unchanged, enforced by reuse)
- Every non-root event MUST carry `correlation_id` (= case id) and a `causation_id` (envelope invariant,
  `ROOT_EVENT_TYPES`).
- `task_id` MUST be stable per (case, capability) → `uuid5` (delegation invariant).
- Exactly one `customer.resolution.decided` per `correlation_id` (case-status DECIDED/terminal guard).
- A result for a terminal/decided case is **recorded in audit, not applied** (existing
  late-result-recorded-not-applied branch).
