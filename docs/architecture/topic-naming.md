# Topic Naming Conventions

## Naming rule

`{environment}.{domain}.{entity}.{action}.v{major}`

All lowercase, dot-separated. `{major}` mirrors the MAJOR component of the payload's `schema_version`. A breaking schema change increments the suffix and leaves the old topic intact for cutover.

| Segment | Description | Rules |
|---------|-------------|-------|
| `environment` | Deployment target | `local` for dev; `staging`, `prod` for other envs. Controlled by `AGENT_ENVIRONMENT` env var (default `"local"`). |
| `domain` | Business capability | `support`, `resolution`, `billing`, `risk`, `audit`, `system`, `agent` |
| `entity` | The thing acted on | Noun phrase, kebab-case (`ticket`, `envelope`, `processed-id`) |
| `action` | What happened | Past-tense verb (`created`, `recorded`, `published`, `sent`) |
| `v{major}` | Breaking-change counter | MAJOR of payload `schema_version` |

## Canonical topics

| Topic | Owner | Payload schema | Partitions | Retention | Compaction key |
|-------|-------|----------------|------------|-----------|----------------|
| `local.agent.message.sent.v1` | shared | `A2AMessage` | 1 | 7 days | — |
| `local.audit.envelope.recorded.v1` | foundation | `AuditPayload` | 1 | compacted | `original_envelope.event_id` |
| `local.system.processed-id.<consumer>.recorded.v1` | foundation | `{"event_id": "<uuid>"}` | 1 | compacted | `event_id` |
| `local.system.sample.published.v1` | foundation (CLI) | `SamplePayload` | 1 | 1 day | — |

Source: `specs/001-event-foundation/contracts/topics.md`.

## Per-consumer processed-event topic

Pattern: `{env}.system.processed-id.{consumer_name}.recorded.v1`

Generated at runtime by `processed_id_topic(consumer_name)` from `packages/contracts/topics.py`. Created lazily by `IdempotencyTracker` on first use with log-compaction so the broker retains only the latest record per `event_id`.

## Topic creation policy

- **Development**: `create_topics()` in `src/agent_foundation/transport/topics.py` is called by the `health` CLI command and by integration test fixtures. It creates all canonical topics with correct retention/compaction configs.
- **Integration tests**: use `testcontainers[kafka]` (real Kafka, not the local Redpanda stack). `create_topics()` is called in test fixtures to ensure correct configs before the first message.
- **Auto-create**: `docker-compose.yml` sets `enable_auto_create_topics=true` so the Redpanda broker creates topics on first use during local dev; `create_topics()` immediately updates configs.

## Out of scope

ACLs, authentication, encryption-in-transit (production-hardening per Principle V), cross-broker replication, multi-partition routing keys.

## How to register a new topic

1. Add a `topic_for(domain, entity, action)` constant to `packages/contracts/topics.py`.
2. Add the event type → topic mapping to `TOPIC_NAMES` in `src/agent_foundation/transport/topics.py`.
3. Add the event type → Pydantic model mapping to `PAYLOAD_REGISTRY` in `src/agent_foundation/payloads/__init__.py`.
4. Optionally add a `NewTopic` entry to `_CANONICAL_TOPICS` in `transport/topics.py` with the correct retention/compaction config.
