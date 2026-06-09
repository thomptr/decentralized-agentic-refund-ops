# Implementation Plan: Shared A2A Runtime Contract for Independent Agents

**Branch**: `002-a2a-runtime-contract` | **Date**: 2026-06-09 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-a2a-runtime-contract/spec.md`

## Summary

Build a thin, reusable **agent runtime** on top of the `001-event-foundation` transport so that any
independent agent can: expose its own addressable A2A endpoint, publish an A2A **Agent Card**
describing its capabilities, accept structured **task requests**, return structured **task
results**, and emit a Kafka audit event for every task that is **accepted, completed, failed, or
rejected** — with no supervisor, central router, or orchestrator anywhere in the path.

The runtime reuses the foundation's `EventEnvelope`, `Publisher`, `Consumer`, idempotency tracker,
and audit module. It adds three new payload contracts (`AgentCard`, `TaskRequest`, `TaskResult`),
a per-agent endpoint topic, a shared result topic, a compacted card-discovery topic, and four
task-lifecycle audit outcomes carried through the existing audit topic. Task delegation is
peer-to-peer and asynchronous: a requester addresses a specific agent's endpoint topic and later
receives a correlated result event. The Agent Card structure is the A2A discovery format that AWS
Bedrock AgentCore can serve for a deployed runtime, keeping the local Kafka realization
forward-compatible with a future managed deployment. This feature ships the runtime plus a
non-domain **echo** example agent only — no refund-business logic.

## Technical Context

**Language/Version**: Python 3.12 (single version per constitution; matches `001-event-foundation`).

**Primary Dependencies** (all already present from the foundation — no new runtime deps):
- `pydantic` v2 — `AgentCard`, `TaskRequest`, `TaskResult`, `TaskError` models.
- `aiokafka` — endpoint/result/discovery topics via the existing `Publisher`/`Consumer`.
- `structlog` — task-lifecycle structured logging (Principle IV).
- `typer` — new CLI commands (`serve-echo`, `publish-card`, `discover`, `submit-task`,
  `query-task-audit`).
- `pytest`, `pytest-asyncio`, `testcontainers[kafka]` — unit/contract/integration tests.

**Storage**: Kafka only. Reuses the compacted audit topic for task-lifecycle audit; adds a
compacted card-discovery topic and time-retained endpoint/result topics. No external database.

**Testing**: `pytest` + `pytest-asyncio`; `testcontainers` for the integration suite. New unit
tests for the runtime state machine and contracts; contract tests for schema round-trips; an
integration test that drives accept→complete, accept→fail, and reject end-to-end through Kafka.

**Target Platform**: Local developer workstations (Docker-hosted single-broker Kafka from the
foundation). No remote deployment in scope; AWS Bedrock AgentCore is noted as a forward-compatible
future target, not built here.

**Project Type**: Single Python project — extends the existing `src/agent_foundation` package with
a new `runtime/` subpackage; the `packages/contracts` package gains the new topic factories.

**Performance Goals**: PoC-scale. Task request→result round-trip under 1s p95 on a developer
laptop (one extra Kafka hop beyond the foundation's publish/consume). Throughput target: 50
tasks/sec, well below single-broker capacity.

**Constraints**: Local-only; single broker; single partition per topic (global order); messages
fit default Kafka size limits. No auth/TLS/ACLs (deferred per Principle V). No liveness/timeout
detection of hung handlers (documented gap, per spec Assumptions).

**Scale/Scope**: ≤5 new topics (1 dynamic per-agent endpoint family + 1 result + 1 discovery,
reusing the audit topic), 3 new payload contracts, 1 example agent, ≤2 agents running concurrently
in the local demo.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Agent Autonomy | ✅ PASS | The runtime makes "no direct calls" structurally impossible — every interaction (request, result, card, audit) is a Kafka event. **No supervisor/router/orchestrator** is introduced; `A2AClient` addresses a peer's endpoint topic directly (FR-011). No business/domain logic ships, so domain isolation is untouched. |
| II. Event-Driven Coordination | ✅ PASS | Endpoints, results, capability cards, and audit all traverse Kafka via the foundation's `Publisher`/`Consumer`. A2A supplies the *message structure*; Kafka remains the sole transport. |
| III. Idempotency & Safety | ✅ PASS | Task requests are idempotent by `task_id`; the runtime tracks processed task IDs (reusing `IdempotencyTracker`) so re-delivery produces no duplicate work or duplicate side effects (FR-010). |
| IV. Observability-First | ✅ PASS | Every task emits structured logs and exactly one of {rejected} or {accepted + one terminal} audit events with task identity, agent identity, correlation/causation, timestamp, outcome, reason (FR-008/FR-009). |
| V. PoC Scope Discipline | ⚠ JUSTIFY | Per-agent dynamic endpoint topics deviate from the topic convention's "never name a topic after a consumer"; a shared result topic and an `AgentCard` subset are added. All justified in Complexity Tracking below; no new third-party dependency is introduced. |

**Re-check after Phase 1 design**: ✅ PASS — Phase 1 artifacts introduce no new deviations beyond
those recorded in Complexity Tracking. The only foundation change is a backward-compatible optional
`topic` override on `Publisher.publish` (Phase 1, research R5), which adds no new dependency and no
new transport.

## Project Structure

### Documentation (this feature)

```text
specs/002-a2a-runtime-contract/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (schemas + interface + topic deltas)
│   ├── agent-card.schema.json
│   ├── task-request.schema.json
│   ├── task-result.schema.json
│   ├── task-audit-payload.schema.json
│   ├── runtime-api.md
│   └── topics.md
├── checklists/
│   └── requirements.md  # Created by /speckit-specify
└── tasks.md             # Phase 2 output (created by /speckit-tasks)
```

### Source Code (repository root)

```text
src/agent_foundation/
├── a2a.py                 # (existing) A2APart, A2AMessage, A2ATask — reused as task I/O bodies
├── envelope.py            # (existing) EventEnvelope, AgentIdentity — reused unchanged
├── idempotency.py         # (existing) IdempotencyTracker — reused, keyed by task_id
├── logging.py             # (existing) + new task-lifecycle log event constants
├── payloads/
│   ├── __init__.py        # (modified) register agent.task_request.v1, agent.task_result.v1,
│   │                      #            agent.agent_card.v1; extend AuditPayload usage
│   ├── sample.py          # (modified) AuditPayload: add task_id, extend outcome enum
│   └── task.py            # (new) TaskRequest, TaskResult, TaskError, TaskStatus
├── runtime/               # (new) the A2A runtime contract
│   ├── __init__.py
│   ├── agent_card.py      # AgentCard, Capability (A2A AgentCard-aligned)
│   ├── runtime.py         # AgentRuntime: register handlers, serve endpoint, lifecycle + audit
│   ├── client.py          # A2AClient: submit a task to a peer endpoint, await correlated result
│   ├── discovery.py       # publish_card(), discover_agents() over the compacted card topic
│   └── errors.py          # TaskRejected, UnsupportedCapability, etc.
├── transport/
│   ├── publisher.py       # (modified) optional `topic` override on publish() — see research R5
│   ├── consumer.py        # (existing) reused by AgentRuntime to serve its endpoint
│   └── topics.py          # (modified) register card/result topics; expose endpoint factory
└── cli.py                 # (modified) serve-echo, publish-card, discover, submit-task,
                           #            query-task-audit commands

packages/contracts/
└── topics.py              # (modified) endpoint_topic(agent_id), TOPIC_AGENT_CARD,
                           #            TOPIC_TASK_RESULT factories

examples/
└── echo_agent.py          # (new) minimal non-domain agent that exercises the runtime

tests/
├── unit/
│   ├── test_task_contracts.py     # (new) TaskRequest/Result/Error + AgentCard validation
│   └── test_runtime_state.py      # (new) lifecycle state machine: exactly-one-terminal
├── contract/
│   └── test_runtime_schemas.py    # (new) JSON-schema round-trip for the new payloads
└── integration/
    └── test_runtime_a2a.py        # (new) accept→complete, accept→fail, reject end-to-end
```

**Structure Decision**: Single Python project, extending the existing `agent_foundation` package
with a `runtime/` subpackage rather than creating a new top-level package. This keeps the runtime
importable by future business-agent features exactly as the foundation is, honors Principle V (no
premature package split), and maximizes reuse of the foundation's transport, audit, and idempotency
code (FR-014). The example agent lives under a new `examples/` directory to keep clearly that it is
demonstration code, not part of the shipped library.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Per-agent **dynamic endpoint topics** (`local.agent.<agent_id>.task.requested.v1`) deviate from the topic convention's "never name a topic after a consumer" | FR-001 requires each agent to expose its **own uniquely addressable** endpoint; an addressable A2A endpoint maps to a per-agent inbox topic. The convention already permits dynamic, name-bearing topics (`local.system.processed-id.<consumer_name>...`), so this extends an accepted pattern. | A single shared `task.requested` topic that every agent reads and filters would make every agent consume every other agent's tasks (a shared inbox), weakening the "independent, uniquely addressable endpoint" property and adding per-message filtering overhead. |
| A shared **task result topic** (`local.agent.task.result.v1`) | The asynchronous model (Principle II forbids synchronous direct calls) requires results to flow back as events; a single result topic lets the `A2AClient` await a correlated result by `task_id`. | Per-requester result topics multiply dynamic topics with no PoC benefit; results are low-volume and a single-partition shared topic preserves global order and simple correlation. |
| Reusing the **audit topic** for task-lifecycle audit by extending `AuditPayload` (adding `task_id`, broadening `outcome` to include `completed`/`failed`) | FR-014 explicitly requires reusing the audit subsystem rather than introducing a second audit path; each lifecycle audit event has a unique envelope `event_id`, so compaction-by-`event_id` retains all transitions. | A separate per-outcome topic set (`...agent-task.accepted/completed/failed.v1`) would create a parallel audit path, contradicting FR-014 and fragmenting "query a task's full lifecycle." |
| Backward-compatible optional `topic` override on `Publisher.publish()` | The publisher resolves topics from a static `event_type → topic` registry, but endpoint topics are computed per target agent at call time. A validated send to a dynamic topic needs this hook. | Calling `publish_raw` (which skips payload validation) would bypass the contract validation the runtime must enforce; duplicating the build/validate logic in the runtime would violate DRY and FR-014's "no parallel transport." |
