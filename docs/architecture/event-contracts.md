# Event Contracts

Every inter-agent message in this system uses `EventEnvelope` as the canonical wrapper. An envelope is immutable once published — no field may change after it reaches Kafka.

## EventEnvelope field reference

| Field | Type | Required | Validation | Notes |
|-------|------|----------|------------|-------|
| `event_id` | `UUID` | yes | RFC 4122 v4 | Unique across the system; key for idempotency and audit lookup. |
| `correlation_id` | `UUID` | yes | RFC 4122 v4 | Shared across one logical workflow. |
| `causation_id` | `UUID \| None` | conditional | Required when `event_type` ∉ ROOT_EVENT_TYPES. | Pointer to the immediate cause event. |
| `agent_id` | `str` | yes | `^[a-z][a-z0-9_.-]{1,62}$` | Stable identifier of producer. |
| `tenant_id` | `str` | yes | `^[a-z][a-z0-9_-]{1,62}$` | Multi-tenancy boundary; PoC default `"poc"`. |
| `timestamp` | `datetime` | yes | tz-aware, serialized RFC 3339 | Producer wall-clock; observability only — not used for ordering. |
| `event_type` | `str` | yes | `^[a-z][a-z0-9_-]*(\.[a-z][a-z0-9_-]*)+\.v\d+$` | Identifies payload schema and version. |
| `schema_version` | `str` | yes | semver `MAJOR.MINOR.PATCH` | MAJOR mirrors the `vN` suffix in `event_type`. |
| `payload` | `dict[str, Any]` | yes | Validated against the payload model registered for `event_type`. | Type-specific body. |

Source: `src/agent_foundation/envelope.py` and `specs/001-event-foundation/data-model.md §1.1`.

## Root-event rule

`causation_id` may be `None` **only** when `event_type` ∈ `ROOT_EVENT_TYPES` (defined in `src/agent_foundation/envelope.py`). Root event types represent the start of a new workflow and therefore have no causal predecessor.

Current root types: `agent.sample.v1`, `agent.workflow_start.v1`, `{AGENT_ENVIRONMENT}.support.ticket.created.v1`.

## Payload registry

| `event_type` | Pydantic model | Notes |
|-------------|----------------|-------|
| `agent.message.v1` | `A2AMessage` | Carries A2A messages between agents. |
| `agent.audit.v1` | `AuditPayload` | Audit-store record written by the foundation. |
| `agent.sample.v1` | `SamplePayload` | Used by the smoke-test CLI. |
| `{env}.support.ticket.created.v1` | `SupportTicketCreatedPayload` | Dev/demo domain event. |

Business agents add entries to `src/agent_foundation/payloads/__init__.py`. Payload models live under `src/agent_foundation/payloads/` (foundation types) or `packages/contracts/events/payloads.py` (domain types).

## A2A payload conventions

`A2AMessage` and `A2APart` mirror the [A2A protocol](https://google.github.io/A2A/) specification. Key rules:

- `A2APart.type` is a discriminator: `"text"` requires `text`, `"data"` requires `data`, `"file"` requires `file_uri`.
- `A2AMessage.parts` must be non-empty.
- Transport is **always Kafka** — A2A-HTTP is never used directly.

See `src/agent_foundation/a2a.py` and `specs/001-event-foundation/contracts/a2a-message.schema.json`.

## Validation lifecycle

```
Publisher side:
  lookup(event_type)     → UnknownEventType if not in registry
  isinstance(payload)    → PayloadValidationError if wrong model type
  EventEnvelope(...)     → MissingCausation if non-root + causation_id=None
  producer.send_and_wait → Kafka delivery

Consumer side:
  EventEnvelope.model_validate_json(raw)  → audit rejected/invalid_envelope on failure
  IdempotencyTracker.is_duplicate(id)     → audit duplicate_skipped if seen before
  lookup(event_type)                      → audit rejected/unknown_schema_version
  model_cls.model_validate(payload)       → audit rejected/payload_invalid
  handler(envelope)                       → audit accepted
```

## Concrete JSON example

```json
{
  "event_id": "a1b2c3d4-...",
  "correlation_id": "e5f6a7b8-...",
  "causation_id": null,
  "agent_id": "cli.agent",
  "tenant_id": "poc",
  "timestamp": "2026-06-09T12:00:00Z",
  "event_type": "agent.sample.v1",
  "schema_version": "1.0.0",
  "payload": {"message": "hello from terminal B"}
}
```

## JSON schemas

All schemas live in `specs/001-event-foundation/contracts/`:

- `event-envelope.schema.json`
- `a2a-message.schema.json`
- `audit-payload.schema.json`
- `sample-payload.schema.json`
