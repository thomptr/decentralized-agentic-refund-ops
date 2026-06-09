# Kafka Topic Contracts

This document is the canonical list of topics created by the foundation feature, their
ownership, schema, and retention policy. Any change to this list is a contract change.

| Topic | Owner | Payload schema | Partitions | Retention | Compaction key |
|-------|-------|----------------|------------|-----------|----------------|
| `local.agent.message.sent.v1` | shared | `A2AMessage` (see [a2a-message.schema.json](./a2a-message.schema.json)) | 1 | 7 days | — |
| `local.audit.envelope.recorded.v1` | foundation (audit subsystem) | `AuditPayload` (see [audit-payload.schema.json](./audit-payload.schema.json)) | 1 | compacted (indefinite) | `original_envelope.event_id` |
| `local.system.processed-id.<consumer_name>.recorded.v1` | foundation (idempotency subsystem) | `{ "event_id": "<uuid>" }` (intentionally minimal) | 1 | compacted (indefinite) | `event_id` |
| `local.system.sample.published.v1` | foundation (smoke-test CLI) | `SamplePayload` (see [sample-payload.schema.json](./sample-payload.schema.json)) | 1 | 1 day | — |

## Naming convention

`{environment}.{domain}.{entity}.{action}.v{version}` — all lowercase, dot-separated segments,
kebab-case for multi-word entity or action names.

| Segment | Description | Rules |
|---------|-------------|-------|
| `environment` | Deployment target | `local` for developer workstations; `staging`, `prod` etc. for other environments |
| `domain` | Business capability area | One of: `support`, `resolution`, `billing`, `risk`, `audit`, `system`, `agent` |
| `entity` | The thing being acted on | Noun phrase, kebab-case (e.g., `ticket`, `refund-review`, `envelope`, `processed-id`) |
| `action` | What happened to the entity | Past-tense verb (e.g., `created`, `requested`, `completed`, `recorded`, `published`) |
| `v{version}` | Breaking-change counter | MAJOR portion of the payload `schema_version`. A breaking change increments this suffix, leaving the old topic intact for cutover. |

**Rules**:
- Use lowercase only
- Use kebab-case for multi-word entity/action names (`refund-review`, `agent-task`)
- Topic names are **business-event oriented** — they describe what happened, not which agent consumes the event
- Never name a topic after a consumer (e.g., `billing-agent-output` is wrong)
- Add future agents by adding new domains or event types, not by changing existing topics

**Good examples** (aligned with project convention):
```
local.support.ticket.created.v1
local.resolution.refund-review.requested.v1
local.billing.refund-analysis.completed.v1
local.risk.review.completed.v1
local.audit.agent-task.accepted.v1
local.audit.agent-task.completed.v1
local.audit.agent-task.failed.v1
```

**Bad examples** (do not use these patterns):
```
local.billing-agent-output      # named after consumer, missing segments
local.customer-agent-input      # named after consumer, missing segments
local.agent-1-events            # named after consumer, missing segments
agent.audit.v1                  # missing environment prefix, missing entity/action
```

**Dynamic topics** (constructed at runtime):
- `local.system.processed-id.{consumer_name}.recorded.v1` — use `processed_id_topic(consumer_name: str) -> str` factory in `transport/topics.py` to generate this at runtime

## Implementation

Topic name constants are defined in `packages/contracts/topics.py`:

```python
# resolve_topic(environment, domain, entity, action, version="1") -> str
# Returns: f"{environment}.{domain}.{entity}.{action}.v{version}"

TOPIC_AUDIT   = resolve_topic("local", "audit",  "envelope",    "recorded")  # local.audit.envelope.recorded.v1
TOPIC_MESSAGE = resolve_topic("local", "agent",  "message",     "sent")      # local.agent.message.sent.v1
TOPIC_SAMPLE  = resolve_topic("local", "system", "sample",      "published") # local.system.sample.published.v1

def processed_id_topic(consumer_name: str) -> str:
    return f"local.system.processed-id.{consumer_name}.recorded.v1"
```

The `AGENT_ENVIRONMENT` environment variable (default `"local"`) controls the environment prefix,
so the same code works across environments by changing one env var.

## Topic creation

Topics are explicitly created by `create_topics()` in `src/agent_foundation/transport/topics.py`
using the aiokafka `AIOKafkaAdminClient`. This function is called by the `health` CLI command and
by integration test fixtures to ensure all topics exist before use.

`docker-compose.yml` sets `KAFKA_AUTO_CREATE_TOPICS_ENABLE=false` so topics are never
silently auto-created with wrong configs.

## Out of scope for this feature

- ACLs, authentication, encryption-in-transit (production-hardening per Principle V).
- Cross-broker replication (single broker by design).
- Multi-partition routing keys (single partition by design).
