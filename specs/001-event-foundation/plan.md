# Implementation Plan: Decentralized Agent Event Foundation

**Branch**: `001-event-foundation` | **Date**: 2026-06-08 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-event-foundation/spec.md`

## Summary

Establish the transport, contract, and audit foundation for a decentralized multi-agent refund
PoC. Deliverables: a `docker-compose` Kafka cluster (single broker, KRaft mode — no ZooKeeper),
a shared Python package of Pydantic v2 event envelopes and A2A-aligned message schemas, thin
async publisher/consumer helpers, an audit topic with replay-friendly semantics, and a smoke-test
CLI that round-trips a sample event end-to-end. No business agents are implemented in this
feature.

## Technical Context

**Language/Version**: Python 3.12 (single Python version across the project per constitution).

**Primary Dependencies**:
- `pydantic` v2 — shared event envelope + payload schemas.
- `aiokafka` — async Kafka producer/consumer for Python.
- `structlog` — structured logging required by Principle IV.
- `pytest`, `pytest-asyncio`, `testcontainers[kafka]` — test infrastructure.
- `typer` — minimal CLI for the smoke-test publish/consume utilities.

**Storage**: Kafka itself acts as the event store. A dedicated compacted topic
(`agent.audit.v1`) holds the canonical audit record. No external database in this feature.

**Testing**: `pytest` + `pytest-asyncio` for unit and async tests; `testcontainers` to bring up a
disposable Kafka in integration tests. Smoke test driven by `typer` CLI against the running
`docker-compose` stack.

**Target Platform**: Local developer workstations (Linux/macOS with Docker Desktop or compatible).
No remote deployment in scope.

**Project Type**: Single Python project — a shared `agent_foundation` library plus a thin CLI.

**Performance Goals**: PoC-scale only — publish/consume round-trip under 500ms p95 on a developer
laptop. Sustained throughput target: 100 events/sec (well below Kafka single-broker capacity).

**Constraints**: Local-only operation; single broker (no replication); KRaft mode; all messages
fit in default Kafka message size limits. No production hardening (auth, TLS, ACLs deferred).

**Scale/Scope**: One repository, ≤10 published topics, ≤5 schema types in this feature. No
business agents.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Agent Autonomy | ✅ PASS | This feature ships no agents; the foundation enforces "no direct calls" by exposing only event-bus interfaces. |
| II. Event-Driven Coordination | ✅ PASS | All inter-agent communication will go through Kafka; A2A message structures carried inside the event payload. |
| III. Idempotency & Safety | ✅ PASS | Envelope `event_id` is unique; foundation provides an idempotency helper that consumers can opt into. |
| IV. Observability-First | ✅ PASS | `structlog` wired from the first commit; every publish, consume, and rejection emits a structured record; all events also persisted to the `agent.audit.v1` topic. |
| V. PoC Scope Discipline | ⚠ JUSTIFY | Bringing in Kafka + `aiokafka` + `structlog` + `testcontainers` is heavier than the constitution's "in-memory default". Justified below — see Complexity Tracking. |

**Re-check after Phase 1 design**: ✅ PASS — no new deviations introduced by Phase 1 artifacts.

## Project Structure

### Documentation (this feature)

```text
specs/001-event-foundation/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (event schemas, A2A mapping)
└── tasks.md             # Phase 2 output (created by /speckit-tasks)
```

### Source Code (repository root)

```text
src/agent_foundation/
├── __init__.py
├── envelope.py          # EventEnvelope, AgentIdentity (Pydantic models)
├── a2a.py               # A2A-aligned message/part/task Pydantic schemas
├── payloads/            # Concrete payload schemas registered per event type
│   ├── __init__.py
│   └── sample.py        # SamplePayload used by the smoke-test event type
├── transport/
│   ├── __init__.py
│   ├── publisher.py     # Async Kafka publisher with envelope + schema validation
│   ├── consumer.py      # Async Kafka consumer with envelope validation + idempotency
│   └── topics.py        # Topic naming conventions + canonical topic list
├── audit/
│   ├── __init__.py
│   └── store.py         # Audit write helper + correlation query helper
├── idempotency.py       # Processed-event-id tracker (in-process + Kafka-backed)
├── logging.py           # structlog configuration shared across publishers/consumers
└── cli.py               # Typer CLI: publish-sample, consume-sample, query-audit, replay

tests/
├── unit/                # Pure unit tests (no Kafka)
├── integration/         # Kafka-backed via testcontainers
└── contract/            # Schema round-trip + A2A-mapping conformance tests

infra/
└── docker-compose.yml   # Single-broker Kafka (KRaft mode) + kafka-ui

pyproject.toml           # Project deps, package config, lint/test entry points
README.md                # Top-level quick-start pointing at quickstart.md
```

**Structure Decision**: Single Python project. The `src/agent_foundation` package will be
imported by future business-agent features; this feature delivers only the package, the CLI, the
docker-compose infrastructure, and the test suites. No `apps/` or `services/` split is justified
at PoC scale (Principle V).

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Kafka chosen over the constitution's "in-memory default" Event-Transport line | Constitution Principle II explicitly mandates "agents communicate exclusively via Kafka"; the Tech-Constraints "in-memory default" sentence pre-dates that principle and is treated as superseded by Principle II. User plan input also names Kafka explicitly. | An in-memory queue cannot demonstrate replay-friendly offsets, log-compacted audit, or partition-based ordering — all of which the spec requires (FR-009 through FR-012, SC-005, SC-006). Substituting an in-memory queue would invalidate the foundation's purpose. |
| `aiokafka` async client over `kafka-python` (sync) | The PoC will run many independent agents in a single process during local development; async I/O avoids one thread per consumer. | A sync client would force a thread-per-consumer model and complicate the smoke-test CLI. |
| `testcontainers[kafka]` as a dev dependency | Integration tests must hit a real broker to satisfy Principle III (idempotency cannot be proven against mocks) and SC-005 (replay determinism). | Mocking Kafka would mask broker-driven ordering and offset semantics, defeating the test. |
