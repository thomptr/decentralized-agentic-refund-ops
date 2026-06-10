# Contract: Topics (REUSED — no new topic)

This feature introduces **no new Kafka topic**. It reuses topics already declared and registered by
the foundation (`001`) and the runtime (`002`), and the risk result topic already declared for the
`003` consumer.

## Topics the Risk and Fraud Agent uses

| Topic constant | Topic name | Role for this agent | Direction |
|----------------|-----------|---------------------|-----------|
| `endpoint_topic("risk-fraud-agent")` | `local.agent.risk-fraud-agent.task.requested.v1` | The agent's A2A endpoint — inbound `assess_fraud_risk` `TaskRequest`s | consume |
| `TOPIC_TASK_RESULT` | `local.agent.task.result.v1` | A2A `TaskResult.output` written by the runtime | produce (via runtime) |
| `TOPIC_RISK_RESULT` | `local.risk.review.completed.v1` | Domain risk result event (`RiskReviewCompletedPayload`) | produce (handler-owned `Publisher`) |
| `TOPIC_AGENT_CARD` | `local.agent.agent-card.published.v1` | Capability advertisement / discovery (FR-018) | produce (via runtime) |
| `TOPIC_AUDIT` | `local.audit.envelope.recorded.v1` | Task-lifecycle audit (FR-014) | produce (via runtime) |
| `processed_id_topic(...)` | `local.system.processed-id.*.recorded.v1` | Compacted idempotency state (FR-013) | runtime-internal |

All are already present in `src/agent_foundation/transport/topics.py`:
- `TOPIC_RISK_RESULT` is in `TOPIC_NAMES` and `_CANONICAL_TOPICS` (7-day retention, single partition).
- `RiskReviewCompletedPayload` is in `src/agent_foundation/payloads/__init__.py:PAYLOAD_REGISTRY`
  keyed by `TOPIC_RISK_RESULT`.
- The agent's endpoint topic is created on startup via `endpoint_topic_new_topic("risk-fraud-agent")`
  the same way the stub already does (no change to topic provisioning).

## Why no new topic / contract

The mock `risk-fraud-agent` stub already publishes nothing to the result topic, but the `003` consumer
already subscribes to `TOPIC_RISK_RESULT` and already knows `RiskReviewCompletedPayload`. Shipping the
real agent only **populates** that existing topic with a real verdict — satisfying FR-019 (conform to
the established risk result contract/topic so existing consumers consume unchanged) and FR-017 (reuse
the shared transport/audit/idempotency, no parallel path). Principle V: no new topic, no new contract,
no new dependency.
