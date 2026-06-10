# No-Supervisor Verification

Authoritative sources: `specs/006-workflow-choreography/spec.md` FR-021, FR-025;
`specs/006-workflow-choreography/contracts/choreography.md` §Decentralization invariants.

## The claim

The refund workflow has **no central orchestrator, supervisor, or router**. The final decision emerges
purely from autonomous agents reacting to events. This is Constitution Principle I and FR-021.

This claim is enforced by two independent mechanisms: automated structural guards and the
correlation-id audit trail.

## a. Automated structural guards

### test_no_supervisor.py

Location: `apps/agents/customer_resolution/tests/test_no_supervisor.py`

This test inspects the resolution agent's source statically and asserts that no component:
- imports or invokes the billing agent's or risk agent's internal modules
- holds a list of "all agents to dispatch"
- issues directives to peer agents other than via the standard A2A task-request path

The resolution agent sends A2A task requests (peer delegation) but does **not** direct what the peer
does, interpret its internal state, or control its lifecycle. Sending an opinion request to an endpoint
topic is coordination, not supervision.

### test_no_router.py

Location: `tests/integration/test_no_router.py`

This integration test drives a full multi-agent scenario and asserts that:
- no single component is on every message path
- the billing and risk agents receive their task requests and publish results independently, without a
  relay or router sitting between them and the resolution agent
- the causal trace for a completed case shows decisions attributable to peer result events, not to any
  intermediate coordinator

Both tests must remain green for every commit (CI gate).

## b. Correlation-id audit trail

Every event in a case carries the same `correlation_id`. The causal trace tool
(`apps/api/trace_case.py`) reconstructs the full journey from a single id by reading only the
`audit.envelope.recorded.v1` stream — no code inspection required.

For a completed case the trace shows:

```
seq  actor                       event_type                              outcome
1    cli.dev                     support.ticket.created.v1               accepted
2    customer-resolution-agent   resolution.customer-issue.classified.v1 accepted
3    customer-resolution-agent   agent.billing-entitlement.task.requested accepted
4    customer-resolution-agent   agent.risk-fraud.task.requested         accepted
5    billing-entitlement-agent   billing.refund-analysis.completed.v1    accepted
6    risk-fraud-agent            risk.review.completed.v1                accepted
7    customer-resolution-agent   customer.resolution.decided.v1          accepted
```

The decision at step 7 is causally preceded by the two peer result events (steps 5–6) — not by any
intermediate agent. An inspector reading only this trace can confirm no additional actor intervened.

## Decentralization invariants (from contracts/choreography.md)

1. No participant consumes another agent's endpoint topic to *direct* it. The only cross-agent messages
   are the resolution agent's A2A task requests (peer delegation) and the peers' own result publishes.
2. The reaper, replay harness, and trace tool issue **no** task requests and **no** directives to any
   agent.
3. Billing and risk agents publish their results autonomously; the resolution agent subscribes and
   aggregates — it does not instruct them when or how to respond.

## Domain isolation invariant (FR-025, SC-010)

Each agent acts only on its own domain:
- The resolution agent learns billing-eligibility and fraud-risk facts **only** via peer opinion
  events. It never reads a billing or fraud data store directly.
- Billing and risk agents never read each other's stores or the resolution agent's case state.

An automated structural test (same proof style as `test_no_supervisor.py`) asserts that no component
imports or queries a domain data store it does not own.

## Constitution Principle I compliance

| Requirement | How it is met |
|---|---|
| No central supervisor/router | `test_no_supervisor.py` + `test_no_router.py` pass |
| Decision emerges from peer events | Audit trail shows causation: peer results → decision |
| Domain isolation | Structural test + resolution agent reads no billing/fraud store |
| Reaper is not a supervisor | Reaper acts only on the resolution agent's own cases; issues no directives to peers |
| Replay / trace are read-only | Both utilities consume recorded events and direct nothing |

## Related docs

- [decentralized-workflow.md](./decentralized-workflow.md) — end-to-end flow and participant roles
- [event-choreography.md](./event-choreography.md) — audit topic and causation DAG
- [failure-handling.md](./failure-handling.md) — reaper design and its non-supervisor properties
