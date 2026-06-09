# Phase 1 Data Model: Decentralized Agent Event Foundation

**Feature**: 001-event-foundation
**Date**: 2026-06-08
**Modeling tool**: Pydantic v2

This document defines the entities, fields, validation rules, and relationships for the foundation
package. All models live in `src/agent_foundation/` and are importable by future business agents.

---

## 1. Entities

### 1.1 `EventEnvelope`

The single canonical wrapper carried by every event on every topic (including audit). Immutable
once published.

| Field | Type | Required | Validation | Notes |
|-------|------|----------|------------|-------|
| `event_id` | `UUID` | yes | RFC 4122 v4 | Unique across the system; key for idempotency and audit lookup. |
| `correlation_id` | `UUID` | yes | RFC 4122 v4 | Shared across one logical workflow. |
| `causation_id` | `UUID \| None` | conditional | If `event_type` ∉ root-event allow-list, MUST be non-null. | Pointer to the immediate cause event. |
| `agent_id` | `str` | yes | Matches `^[a-z][a-z0-9_.-]{1,62}$` | Stable identifier of producer. |
| `tenant_id` | `str` | yes | Matches `^[a-z][a-z0-9_-]{1,62}$` | Multi-tenancy boundary; PoC default `"poc"`. |
| `timestamp` | `datetime` | yes | tz-aware, serialized RFC3339 | Producer wall-clock; observability only — not used for ordering. |
| `event_type` | `str` | yes | Matches `^agent\.[a-z_]+\.v\d+$` | Identifies payload schema and version. |
| `schema_version` | `str` | yes | semver `MAJOR.MINOR.PATCH` | Mirrors the `vN` in `event_type` (MAJOR). |
| `payload` | `Mapping[str, Any]` | yes | Validated against payload model registered for `event_type`. | Type-specific body; A2A `Message` for inter-agent comms. |

**Validation rules**:
- The envelope is validated at publish time (producer-side) AND at consume time
  (consumer-side). Mismatches at consume time produce a rejection audit record.
- `model_config = ConfigDict(frozen=True, extra="forbid")` — no extra fields, no mutation after
  construction.
- `causation_id` may be `None` only when `event_type` is in `ROOT_EVENT_TYPES` (initially:
  `agent.workflow_start.v1`).

**State transitions**: None. The envelope is immutable. The lifecycle is `produced → validated →
published → consumed → (idempotently processed | duplicate skipped) → audited`.

---

### 1.2 `AgentIdentity`

A small typed wrapper used in CLI configuration and logging context. Not embedded in the envelope
itself (the envelope stores `agent_id` as a flat string), but used to construct it.

| Field | Type | Required | Validation |
|-------|------|----------|------------|
| `agent_id` | `str` | yes | Same regex as envelope `agent_id`. |
| `display_name` | `str` | yes | 1–80 chars. |
| `tenant_id` | `str` | yes | Same regex as envelope `tenant_id`. |

**Usage**: Bound into `structlog` context at process start; passed into `Publisher` / `Consumer`
constructors.

---

### 1.3 A2A Message Models (`a2a.py`)

Pydantic mirrors of the A2A spec's core types, used as the canonical `payload` shape for
inter-agent communication.

#### `A2APart`
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `type` | `Literal["text", "data", "file"]` | yes | A2A part discriminator. |
| `text` | `str \| None` | conditional | Required when `type == "text"`. |
| `data` | `Mapping[str, Any] \| None` | conditional | Required when `type == "data"`. |
| `file_uri` | `str \| None` | conditional | Required when `type == "file"`. |

#### `A2AMessage`
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `role` | `Literal["user", "agent"]` | yes | A2A role discriminator. |
| `parts` | `list[A2APart]` | yes | Non-empty. |
| `task_id` | `UUID \| None` | optional | A2A task linkage if applicable. |

#### `A2ATask`
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `task_id` | `UUID` | yes | Globally unique. |
| `status` | `Literal["submitted", "working", "completed", "failed", "canceled"]` | yes | A2A lifecycle. |
| `messages` | `list[A2AMessage]` | yes | Conversation transcript snapshot. |

These models are used **only** as payload shapes inside `EventEnvelope.payload`. They are never
sent as bare A2A-HTTP messages — the transport is always Kafka.

---

### 1.4 Payload registry (`payloads/__init__.py`)

A typed registry mapping `event_type` string → Pydantic model class.

| Entry | event_type | Payload model | Notes |
|-------|------------|---------------|-------|
| 1 | `agent.message.v1` | `A2AMessage` | Carries A2A messages between agents. |
| 2 | `agent.audit.v1` | `AuditPayload` | Audit-store record (see below). |
| 3 | `agent.sample.v1` | `SamplePayload` | Used by the smoke-test CLI; trivial body. |

Future business agents register additional entries; this feature ships only the three above.

---

### 1.5 `AuditPayload`

The body of an event published to `agent.audit.v1`. Carries enough context to reconstruct what
happened to the original event.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `original_envelope` | `EventEnvelope` | yes | Full copy of the audited envelope. |
| `outcome` | `Literal["accepted", "rejected", "duplicate_skipped"]` | yes | What happened. |
| `reason` | `str \| None` | conditional | Required when `outcome ∈ {"rejected"}`. |
| `recorded_at` | `datetime` | yes | tz-aware; when the audit row was written. |

The audit topic is keyed by `original_envelope.event_id` so log compaction retains the latest
record per event.

---

### 1.6 `SamplePayload`

Trivial payload used by the smoke-test CLI and integration tests.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `message` | `str` | yes | 1–200 chars; arbitrary text. |

---

## 2. Relationships

```text
EventEnvelope (1) ──── correlation_id ───► (N) EventEnvelope     [Correlation Group]
EventEnvelope (1) ──── causation_id ────► (0..1) EventEnvelope   [Causation Link]
EventEnvelope.payload ────────► A2AMessage | AuditPayload | SamplePayload  [Payload Registry]
AuditPayload.original_envelope ► EventEnvelope                    [Audit reference]
```

- A **Correlation Group** is the set of envelopes sharing a `correlation_id`. Reconstructed by
  consuming `agent.audit.v1` filtered on `original_envelope.correlation_id`.
- A **Causation Chain** is the ordered sequence within a Correlation Group where each event's
  `causation_id` points to the preceding event's `event_id`. Root events have `causation_id = None`.

---

## 3. Validation Rules (cross-entity)

| Rule | Where Enforced | Failure Mode |
|------|----------------|--------------|
| Envelope `event_type` MUST appear in the payload registry | Publisher AND Consumer | Publisher: raises `UnknownEventType`; Consumer: audit `rejected/unknown_schema_version` and skip. |
| Envelope `schema_version` MAJOR MUST match the `vN` suffix in `event_type` | Publisher AND Consumer | Same as above. |
| Envelope `payload` MUST validate against the registry-mapped model | Publisher AND Consumer | Publisher: raises `PayloadValidationError`; Consumer: audit `rejected/payload_invalid` and skip. |
| Non-root events MUST carry `causation_id` | Publisher AND Consumer | Publisher: raises `MissingCausation`; Consumer: audit `rejected/missing_causation` and skip. |
| Duplicate `event_id` arriving at an idempotent consumer | Consumer (`IdempotencyTracker`) | Audit `duplicate_skipped`, log `event.duplicate_skipped`, do NOT invoke user handler. |

---

## 4. Persistence Model

There is no separate database. Two Kafka topics persist all state required by this feature:

| Topic | Purpose | Retention | Compaction key |
|-------|---------|-----------|----------------|
| `agent.message.v1` | Inter-agent A2A messages. | time-based (7 days, default) | none |
| `agent.audit.v1` | Audit record for every event (accepted, rejected, duplicate). | compaction | `original_envelope.event_id` |
| `agent.processed.<consumer_name>.v1` | Per-consumer processed-event-id log used by `IdempotencyTracker` recovery. | compaction | `event_id` |
| `agent.sample.v1` | Smoke-test topic for the CLI utilities. | time-based (1 day) | none |

All topics are single-partition in this feature (see research R4).
