# Contract: Topic & Registry Deltas

This feature introduces **one** new topic and **one** new payload-registry entry. Everything else is
reused from `001-event-foundation` / `002-a2a-runtime-contract` (FR-016 — no parallel transport).

## New topic

| Constant (`packages/contracts/topics.py`) | Resolved name (local) | Factory |
|-------------------------------------------|-----------------------|---------|
| `TOPIC_RESOLUTION_DECIDED` **NEW** | `local.customer.resolution.decided.v1` | `topic_for("customer", "resolution", "decided")` |

Retention: time-retained (default 7 days), single partition (global order), like other domain event
topics. Not compacted — it is an event stream of decisions, not a keyed snapshot.

## New payload-registry entry

`agent_foundation/payloads/__init__.py` → `PAYLOAD_REGISTRY`:

```python
"local.customer.resolution.decided.v1": CustomerResponseDecisionPayload,
```

Registered exactly as `local.support.ticket.created.v1` already is, so `Publisher`/`Consumer`
validate the decision payload on send and receive.

## Reused topics (no change)

| Constant | Name | This agent's role |
|----------|------|-------------------|
| `support.ticket.created` event type | `local.support.ticket.created.v1` | **consume** — intake |
| `TOPIC_TASK_RESULT` | `local.agent.task.result.v1` | **consume** — analysis results |
| `endpoint_topic("billing-entitlement-agent")` | `local.agent.billing-entitlement-agent.task.requested.v1` | **produce** — billing request |
| `endpoint_topic("risk-fraud-agent")` | `local.agent.risk-fraud-agent.task.requested.v1` | **produce** — risk request |
| `endpoint_topic("customer-resolution-agent")` | `local.agent.customer-resolution-agent.task.requested.v1` | **own endpoint** (FR-001) |
| `TOPIC_AGENT_CARD` | `local.agent.agent-card.published.v1` | **produce** — own card / **read** — discovery |
| `TOPIC_AUDIT` | `local.audit.envelope.recorded.v1` | **produce** — audit trail |
| `processed_id_topic(<consumer>)` | `local.system.processed-id.<consumer>.recorded.v1` | idempotency (per consumer) |

## Topic creation

`TOPIC_RESOLUTION_DECIDED` is added to the canonical topic list created by
`agent_foundation.transport.topics.create_topics(...)` (or passed via `extra_topics`) so the demo
provisions it on startup alongside the existing topics.
