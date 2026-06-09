# Kafka Topic Contracts — A2A Runtime (delta over 001)

This document lists the **new** topics introduced by the runtime and the **reused** topics from
`001-event-foundation`. It follows the foundation's naming convention
(`{environment}.{domain}.{entity}.{action}.v{version}`, see
`specs/001-event-foundation/contracts/topics.md`). Any change here is a contract change.

## New topics

| Topic | Owner | Payload schema | Partitions | Retention | Key |
|-------|-------|----------------|------------|-----------|-----|
| `local.agent.<agent_id>.task.requested.v1` | the named agent (its endpoint) | `TaskRequest` ([task-request.schema.json](./task-request.schema.json)) | 1 | 7 days | `task_id` |
| `local.agent.task.result.v1` | shared (runtime) | `TaskResult` ([task-result.schema.json](./task-result.schema.json)) | 1 | 7 days | `task_id` |
| `local.agent.agent-card.published.v1` | shared (runtime discovery) | `AgentCard` ([agent-card.schema.json](./agent-card.schema.json)) | 1 | compacted (indefinite) | `agent_id` |

## Reused topics (unchanged ownership; extended usage)

| Topic | Reused for | Change |
|-------|-----------|--------|
| `local.audit.envelope.recorded.v1` | task-lifecycle audit (accepted/completed/failed/rejected) | Payload is the **extended** `AuditPayload` ([task-audit-payload.schema.json](./task-audit-payload.schema.json)) — adds optional `task_id`, adds `completed`/`failed` outcomes. No new topic; honors FR-014. |
| `local.system.processed-id.<agent_id>.recorded.v1` | task idempotency | Now also records processed `task_id`s (UUIDs) via the existing `IdempotencyTracker`. |

## Endpoint topic factory (dynamic)

The per-agent endpoint topic is the agent's A2A **address**. It is constructed at runtime and is
intentionally **not** in the static `event_type → topic` map (`TOPIC_NAMES`):

```python
# packages/contracts/topics.py
def endpoint_topic(agent_id: str) -> str:
    # entity = the agent being addressed; action = task requested of it
    return f"{AGENT_ENVIRONMENT}.agent.{agent_id}.task.requested.v1"

TOPIC_AGENT_CARD: str = topic_for("agent", "agent-card", "published")  # local.agent.agent-card.published.v1
TOPIC_TASK_RESULT: str = topic_for("agent", "task", "result")          # local.agent.task.result.v1
```

**Convention note (Principle V deviation, see plan Complexity Tracking)**: embedding `<agent_id>`
in the endpoint topic deviates from the convention's "never name a topic after a consumer." It is
justified because an A2A endpoint is, by definition, addressed to one specific agent — the same
rationale under which the foundation already permits the dynamic
`local.system.processed-id.<consumer_name>.recorded.v1` topic. The `<agent_id>` occupies the
`entity` segment (the agent is the thing a task is requested *of*), keeping the five-segment shape.

## Topic creation

`endpoint_topic(agent_id)` is created when an `AgentRuntime` starts (its `serve()` ensures its own
endpoint topic plus the shared result/card topics exist), reusing the foundation's
`create_topics()` / `AIOKafkaAdminClient` path with `extra_topics`. `TOPIC_AGENT_CARD` is created
compacted; `TOPIC_TASK_RESULT` and endpoint topics use 7-day time retention. Auto-create remains
disabled in `docker-compose.yml`.

New `NewTopic` definitions are added to `transport/topics.py`:

```python
TOPIC_AGENT_CARD  -> cleanup.policy=compact
TOPIC_TASK_RESULT -> retention.ms=7d
endpoint_topic(x) -> retention.ms=7d   # created per serving agent via extra_topics
```

## Out of scope (unchanged from 001)

- ACLs, authentication, encryption-in-transit.
- Cross-broker replication (single broker).
- Multi-partition routing (single partition by design).
