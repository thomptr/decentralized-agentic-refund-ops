# Contract: Topics (reuse — no new topics)

This feature introduces **no new topic**. It reuses the foundation/`002`/`003` topics as-is. Listed
here for completeness and traceability (FR-017, FR-019).

| Topic constant | Topic name | Role for this agent | Direction |
|----------------|------------|---------------------|-----------|
| `endpoint_topic("billing-entitlement-agent")` | `local.agent.billing-entitlement-agent.task.requested.v1` | the agent's addressable A2A endpoint (FR-001/FR-018) | **consume** |
| `TOPIC_AGENT_CARD` | `local.agent.agent-card.published.v1` | publishes its AgentCard for discovery (FR-018) | publish |
| `TOPIC_TASK_RESULT` | `local.agent.task.result.v1` | A2A `TaskResult` returned to the requester (FR-008 path 1) | publish (via runtime) |
| `TOPIC_BILLING_RESULT` | `local.billing.refund-analysis.completed.v1` | structured domain result event (FR-007, FR-008 path 2) | publish (via domain Publisher) |
| `TOPIC_AUDIT` | `local.audit.envelope.recorded.v1` | accepted/completed/failed/rejected/duplicate audit (FR-014) | publish (via runtime) |

All are already declared in `src/agent_foundation/transport/topics.py` (`_CANONICAL_TOPICS`,
`TOPIC_NAMES`) and `packages/contracts/topics.py`. The per-agent endpoint topic is created by the
runtime at `serve()` via `endpoint_topic_new_topic(agent_id)`.

## Registry status (already present — verified)

- `payloads/__init__.py:PAYLOAD_REGISTRY[TOPIC_BILLING_RESULT] = BillingRefundAnalysisCompletedPayload` ✅
- `transport/topics.py:TOPIC_NAMES[TOPIC_BILLING_RESULT] = TOPIC_BILLING_RESULT` ✅
- `transport/topics.py:_CANONICAL_TOPICS` includes `TOPIC_BILLING_RESULT` ✅

No registry edits are required to publish the result event. The agent calls
`publisher.publish(payload, event_type=TOPIC_BILLING_RESULT, correlation_id=case_id, causation_id=…)`.
