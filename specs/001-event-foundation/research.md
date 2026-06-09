# Phase 0 Research: Decentralized Agent Event Foundation

**Feature**: 001-event-foundation
**Date**: 2026-06-08

This document resolves the open technical questions raised by the spec and plan. Each entry
records the **Decision** taken, the **Rationale**, and the **Alternatives considered**.

---

## R1. Kafka deployment topology for local development

**Decision**: Single Kafka broker running in **KRaft mode** (no ZooKeeper), packaged via
`docker-compose`, plus `kafka-ui` for visual inspection during development.

**Rationale**:
- KRaft removes the ZooKeeper container entirely — one fewer service to launch, configure, and
  fail. KRaft is GA in current Kafka releases and is now the default mode upstream.
- A single broker satisfies all PoC requirements: ordered partitions, offset replay, log
  compaction for the audit topic. Replication is irrelevant locally.
- `kafka-ui` gives reviewers a zero-code way to inspect topics, partitions, and audit records,
  satisfying the spec's "audit visibility" requirement (FR-009, FR-010).

**Alternatives considered**:
- **Confluent Platform Docker images** — heavier, license-encumbered, includes services we will
  never use.
- **Redpanda** — Kafka-API-compatible and simpler, but adds an unfamiliar product to debug; the
  user input names "Kafka cluster" explicitly.
- **In-memory queue** — rejected at the Constitution Check stage (see plan.md Complexity
  Tracking); cannot satisfy replay or offset-based ordering requirements.

---

## R2. How A2A protocol maps onto Kafka transport

**Background**: The Agent2Agent (A2A) protocol defines a JSON message structure (Task, Message,
Part) intended to run over HTTP+JSON-RPC. The user mandate is "agents communicate using the A2A
protocol", but Principle II mandates Kafka as the transport. These can coexist.

**Decision**: Adopt A2A's **message-structure semantics** (Task, Message, Part, Role) inside the
event payload, but use Kafka — not HTTP — as the transport. Specifically:
- The `EventEnvelope` is our transport-level wrapper carrying routing, identity, correlation, and
  audit metadata. It is NOT part of A2A.
- The `payload` field of the envelope carries an A2A `Message` object (Pydantic-modeled) for
  agent-to-agent communication, or a domain-specific payload for system events (e.g., audit
  records).
- Request/response semantics that A2A normally expresses via JSON-RPC are expressed via
  correlation-ID + causation-ID chains across Kafka topics — i.e., a reply is a new event whose
  causation-ID points to the request event.

**Rationale**:
- A2A's value is its **payload shape** (typed messages, multi-part content) and its forward
  compatibility with the broader A2A ecosystem. None of that requires HTTP.
- Carrying A2A message structures inside Kafka events keeps the door open to expose an HTTP A2A
  gateway later (forwarding HTTP A2A calls onto Kafka and back) without re-modeling messages.
- This preserves Principle II strictly (Kafka is the sole inter-agent transport) while honoring
  the user mandate to "follow A2A".

**Alternatives considered**:
- **Run A2A as HTTP between agents, use Kafka only for audit events** — violates Principle II
  (would introduce direct agent-to-agent HTTP calls).
- **Invent a custom message structure ignoring A2A** — violates the user mandate; loses
  interoperability with future A2A clients.

---

## R3. Event envelope field set

**Decision**: The canonical envelope, as user-specified, contains:

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `event_id` | UUID v4 | yes | Globally unique; basis for idempotency. |
| `correlation_id` | UUID v4 | yes | Shared across one logical workflow. |
| `causation_id` | UUID v4 \| null | conditional | Required on every non-root event; null only for workflow-initiating events. |
| `agent_id` | string | yes | Stable identity of the publishing agent or utility. |
| `tenant_id` | string | yes | Multi-tenancy boundary; placeholder value `"poc"` acceptable for now. |
| `timestamp` | RFC3339 string | yes | Producer-side wall-clock for observability; **not** used for ordering. |
| `event_type` | string | yes | e.g., `agent.message.v1`, `agent.audit.v1`. |
| `schema_version` | string (semver) | yes | Carried on the envelope, mirrored in `event_type` suffix. |
| `payload` | object | yes | Type-specific Pydantic model (A2A `Message` for inter-agent comms). |

**Rationale**: This exactly matches the user-provided field list with two minimal additions
(`event_type`, `schema_version`) that the spec already requires (FR-004). The envelope is closed
for additions in this feature — extensions go in `payload`.

**Alternatives considered**:
- **Drop `tenant_id`** — rejected because retrofitting a tenancy field later would invalidate every
  audit record produced before the change.
- **Embed correlation/causation in payload** — rejected because operators querying the audit store
  must be able to filter without payload deserialization.

---

## R4. Topic naming and partitioning

**Decision**:
- Topic naming convention: `agent.<purpose>.v<major>`, e.g., `agent.message.v1`, `agent.audit.v1`.
- All topics in this feature are single-partition. Multi-partition routing is deferred until a
  business agent actually requires per-key ordering.
- The audit topic `agent.audit.v1` is configured with **log compaction** keyed by `event_id` so
  the audit record for any given event is always retrievable; non-audit topics use
  time-based retention (default 7 days locally).

**Rationale**:
- Single partition guarantees global order on each topic — sufficient for the PoC and removes a
  whole category of "why are my events out of order?" debugging.
- Compaction on the audit topic provides a near-permanent record without unbounded growth.
- Major-version suffix in the topic name lets a future schema-breaking change run side-by-side
  with the old version during cutover, in line with the spec's edge-case handling for schema
  drift.

**Alternatives considered**:
- **Per-tenant topics** — premature; one tenant in the PoC.
- **Multi-partition topics keyed by correlation_id** — would prevent global order on `agent.audit.v1`,
  defeating the simple "query by correlation, get the chain" requirement.

---

## R5. Idempotency mechanism for consumers

**Decision**: Provide an `IdempotencyTracker` helper in the foundation that:
1. Records processed `event_id`s in a per-consumer in-process LRU cache (fast path).
2. Optionally persists processed IDs to a dedicated Kafka topic `agent.processed.<consumer_name>.v1`
   for crash-recovery (slow path) — the consumer rebuilds its LRU on restart by reading this topic
   from the earliest offset.
3. Decorates the consumer's `handle()` method so that re-delivery of an already-processed event_id
   short-circuits before user code runs.

**Rationale**:
- The constitution mandates idempotency for every refund operation (Principle III); the foundation
  must make it trivially correct rather than leave each agent to implement it.
- Kafka-backed persistence keeps the foundation self-contained (no Redis/Postgres dependency) and
  preserves replay correctness across restarts.

**Alternatives considered**:
- **Rely on Kafka's exactly-once semantics (idempotent producer + transactions)** — overkill for
  the PoC and would complicate the consumer API surface; consumer-side dedup is simpler and
  explicit.
- **Require each agent to roll its own** — violates Principle V (forces every business agent to
  re-solve the same problem).

---

## R6. Replay semantics

**Decision**: Replay is implemented as a consumer-side capability: the smoke-test CLI exposes
`replay --topic <name> --from-offset <offset> --consumer-group <group>` which creates a fresh
consumer group at the chosen offset and runs the standard consume loop. No special "replay mode"
exists on the broker side; we are simply consuming the existing log.

**Rationale**:
- This is the simplest semantic that satisfies SC-005 and SC-006 and stays within native Kafka
  capabilities (offset seeking is a standard consumer operation).
- Because consumers are idempotent (R5), replaying against an already-warm consumer is safe by
  construction — satisfying the edge case "replay must be safe against a live consumer".

**Alternatives considered**:
- **Custom replay topic** that copies historical events into a new topic — adds infrastructure
  with no semantic gain.

---

## R7. Audit store implementation

**Decision**: Every successful publish path also writes the same envelope (with `event_type =
agent.audit.v1`) to the compacted `agent.audit.v1` topic. Rejection events (schema validation
failure, envelope-field missing) are written to `agent.audit.v1` with an `outcome: "rejected"`
field in payload and a `reason` describing why.

The "query by correlation_id" requirement (FR-010) is served by a CLI command
`query-audit --correlation <id>` that consumes `agent.audit.v1` from the earliest offset, filters
in-process, and prints results sorted by Kafka offset (true causal order).

**Rationale**:
- Co-locating the audit record with the rest of Kafka avoids a separate database (Principle V).
- Compaction guarantees the audit record for any given `event_id` is recoverable indefinitely.
- Linear scan via CLI is acceptable for PoC scale; a real index can be added later if any business
  use case demands it.

**Alternatives considered**:
- **Postgres / SQLite audit table** — adds a service or file dependency without proving anything
  the spec requires.
- **kSQL / ksqlDB materialized view** — overkill for a PoC; reviewers wouldn't gain anything from
  a SQL interface they don't already get from the CLI.

---

## R8. Structured logging configuration

**Decision**: `structlog` configured at process startup with:
- JSON output to stdout (one log line per event = one JSON object).
- Bound context: `agent_id`, `event_id`, `correlation_id`, `causation_id` injected per log call by
  the foundation's publisher/consumer helpers.
- Log events mandated by Principle IV: `event.received`, `event.published`, `event.rejected`,
  `event.duplicate_skipped`, `consumer.error`.

**Rationale**: structlog gives us key-value structured records without writing a custom logger;
JSON to stdout flows directly into any container log aggregator a reviewer chooses to point at it.

**Alternatives considered**:
- **`logging` stdlib with a custom JSONFormatter** — works but requires more boilerplate per
  module to bind contextual fields.
- **OpenTelemetry** — desirable long-term, but the value is in distributed tracing across
  services; the PoC has only local processes. Deferred to a later feature.

---

## R9. Schema-version drift handling

**Decision**: Consumers maintain a registry mapping `event_type` → Pydantic model class. On
receipt, the consumer looks up the registered model for the exact `event_type` string (which
includes the `vN` suffix). If no model is registered for the version on the wire:
- The event is **not** processed.
- An audit record with `outcome: "rejected"`, `reason: "unknown_schema_version"`, and the offending
  envelope is written to `agent.audit.v1`.
- A structured log line `event.rejected.unknown_schema_version` is emitted.

**Rationale**: Directly implements the spec's "schema version drift" edge case. The consumer never
guesses; it surfaces the problem.

**Alternatives considered**:
- **Schema Registry (Confluent / Apicurio)** — adds a service; the typed-Pydantic registry is
  enough for the PoC and gives developers the same compile-time safety inside Python.

---

## R10. Testing strategy

**Decision**:
- **Unit tests** (`tests/unit/`): Pure-Python validation of envelope/payload Pydantic models, the
  `IdempotencyTracker`, and the audit query helper. No Kafka.
- **Contract tests** (`tests/contract/`): Round-trip a sample event through model →
  serialize → deserialize → model and assert byte-stable JSON.
- **Integration tests** (`tests/integration/`): Spin up Kafka via `testcontainers[kafka]`, publish
  via the foundation's publisher, consume via the foundation's consumer, assert envelope fields
  survive and rejection paths fire correctly. Replay determinism is verified here.

All test layers run on `pytest` with `pytest-asyncio` for the integration suite. The CI entry point
in `pyproject.toml` runs unit + contract by default; integration is opt-in via `pytest -m integration`.

**Rationale**: This mirrors the spec's user-story / acceptance-scenario structure and gives a
clear fast/slow split. Real Kafka in integration tests is non-negotiable for proving Principle III
and SC-005.

**Alternatives considered**:
- **Mock Kafka everywhere** — rejected (see Complexity Tracking).

---

## Summary of resolved NEEDS CLARIFICATION

None remained after the plan's Technical Context; all decisions above were derived from the spec,
the constitution, and the user-provided plan input. Where the constitution contained an internal
inconsistency (Tech-Constraints "in-memory default" vs. Principle II "exclusively via Kafka"),
Principle II is treated as authoritative — see plan.md's Complexity Tracking.
