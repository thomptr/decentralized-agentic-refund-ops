# Phase 1 Data Model: Shared A2A Runtime Contract

**Feature**: 002-a2a-runtime-contract
**Date**: 2026-06-09
**Modeling tool**: Pydantic v2

This document defines the new entities, fields, validation rules, relationships, and state
transitions introduced by the runtime. It builds on `001-event-foundation/data-model.md`; the
`EventEnvelope`, `AgentIdentity`, `A2APart`, `A2AMessage`, and `A2ATask` models are reused unchanged.
New models live in `src/agent_foundation/runtime/` and `src/agent_foundation/payloads/task.py`.

---

## 1. New & Modified Entities

### 1.1 `Capability` (new — `runtime/agent_card.py`)

A single named task type an agent advertises. PoC-scoped subset of an A2A Agent Card "skill".

| Field | Type | Required | Validation | Notes |
|-------|------|----------|------------|-------|
| `id` | `str` | yes | `^[a-z][a-z0-9_.-]{1,62}$` | Stable capability identifier; matched against `TaskRequest.capability`. |
| `name` | `str` | yes | 1–80 chars | Human-readable label. |
| `description` | `str` | yes | 1–280 chars | What the capability does. |
| `tags` | `list[str]` | no | each 1–32 chars | Optional discovery hints. |

`model_config = ConfigDict(frozen=True, extra="forbid")`.

### 1.2 `AgentCard` (new — `runtime/agent_card.py`)

A2A Agent Card subset published to the discovery topic. Latest-published per `agent_id` wins.

| Field | Type | Required | Validation | Notes |
|-------|------|----------|------------|-------|
| `agent_id` | `str` | yes | same regex as envelope `agent_id` | Identity; discovery/compaction key. |
| `name` | `str` | yes | 1–80 chars | Display name. |
| `description` | `str` | yes | 1–280 chars | Agent purpose. |
| `version` | `str` | yes | semver `MAJOR.MINOR.PATCH` | Card version. |
| `endpoint_topic` | `str` | yes | non-empty | The agent's request topic (its address); see contracts/topics.md. |
| `capabilities` | `list[Capability]` | yes | non-empty, unique `id`s | What the agent can do. |

`model_config = ConfigDict(frozen=True, extra="forbid")`. Registered as payload for event_type
`agent.agent_card.v1`.

### 1.3 `TaskError` (new — `payloads/task.py`)

Structured error carried by `failed` and `rejected` results.

| Field | Type | Required | Validation | Notes |
|-------|------|----------|------------|-------|
| `category` | `Literal["validation", "unsupported_capability", "handler_error", "duplicate", "internal"]` | yes | — | Machine-readable failure class; distinguishes rejection (`validation`/`unsupported_capability`/`duplicate`) from failure (`handler_error`/`internal`). |
| `message` | `str` | yes | 1–500 chars | Human-readable detail. |

`model_config = ConfigDict(frozen=True, extra="forbid")`.

### 1.4 `TaskRequest` (new — `payloads/task.py`)

The structured instruction submitted to an agent's endpoint. Registered as payload for event_type
`agent.task_request.v1`.

| Field | Type | Required | Validation | Notes |
|-------|------|----------|------------|-------|
| `task_id` | `UUID` | yes | RFC 4122 v4 | Globally unique; basis for **task** idempotency (distinct from envelope `event_id`). |
| `capability` | `str` | yes | same regex as `Capability.id` | The requested capability id. |
| `requester_agent_id` | `str` | yes | envelope `agent_id` regex | Who is asking (for audit & result routing context). |
| `target_agent_id` | `str` | yes | envelope `agent_id` regex | The agent whose endpoint is addressed. |
| `input` | `A2AMessage` | yes | A2A validation (non-empty parts) | Typed task input; reuses `a2a.A2AMessage`. |

`model_config = ConfigDict(frozen=True, extra="forbid")`.

### 1.5 `TaskResult` (new — `payloads/task.py`)

The structured outcome returned for a task. Registered as payload for event_type
`agent.task_result.v1`.

| Field | Type | Required | Validation | Notes |
|-------|------|----------|------------|-------|
| `task_id` | `UUID` | yes | matches the request's `task_id` | Correlates result to request. |
| `status` | `Literal["completed", "failed", "rejected"]` | yes | see rules | Terminal/decision outcome surfaced to requester. |
| `performer_agent_id` | `str` | yes | envelope `agent_id` regex | The agent that produced the result. |
| `output` | `A2AMessage \| None` | conditional | required when `status == "completed"` | Typed success output. |
| `error` | `TaskError \| None` | conditional | required when `status ∈ {"failed","rejected"}` | Structured error. |

**Validation rules**:
- `status == "completed"` ⟹ `output` non-null AND `error` is null.
- `status ∈ {"failed","rejected"}` ⟹ `error` non-null AND `output` is null.
- `rejected` ⟹ `error.category ∈ {"validation","unsupported_capability","duplicate"}`.
- `failed` ⟹ `error.category ∈ {"handler_error","internal"}`.

`model_config = ConfigDict(frozen=True, extra="forbid")`.

### 1.6 `AuditPayload` (MODIFIED — `payloads/sample.py`)

Extended to carry task-lifecycle audit (see research R4). **Backward compatible**: new field is
optional; existing outcomes retained.

| Field | Type | Required | Change |
|-------|------|----------|--------|
| `original_envelope` | `EventEnvelope` | yes | unchanged |
| `outcome` | `Literal["accepted","rejected","duplicate_skipped","completed","failed"]` | yes | **added** `completed`, `failed` |
| `reason` | `str \| None` | conditional | required when `outcome == "rejected"` **or** `outcome == "failed"` |
| `recorded_at` | `datetime` | yes | unchanged |
| `task_id` | `UUID \| None` | no | **new** — set for task-lifecycle audit; null for envelope-level audit |

---

## 2. Payload Registry Additions (`payloads/__init__.py`)

| event_type | Payload model | Topic |
|------------|---------------|-------|
| `agent.task_request.v1` | `TaskRequest` | dynamic `endpoint_topic(agent_id)` (per-target) |
| `agent.task_result.v1` | `TaskResult` | `TOPIC_TASK_RESULT` |
| `agent.agent_card.v1` | `AgentCard` | `TOPIC_AGENT_CARD` (compacted) |
| `agent.audit.v1` | `AuditPayload` (extended) | `TOPIC_AUDIT` (existing, reused) |

The dynamic endpoint topic is **not** placed in the static `TOPIC_NAMES` map; the runtime/client
pass it via the new `Publisher.publish(topic=...)` override (research R5).

---

## 3. Relationships

```text
AgentCard (1) ──── capabilities ───► (N) Capability
AgentCard.agent_id ─── addresses ──► endpoint_topic(agent_id)         [the agent's A2A endpoint]
TaskRequest (1) ──── task_id ──────► (1) TaskResult                   [request/result correlation]
TaskRequest.capability ─── must match ──► Capability.id on target AgentCard
TaskRequest/TaskResult ── carried in ──► EventEnvelope.payload        [foundation transport]
TaskRequest envelope.event_id ◄── causation_id ── TaskResult envelope [causal link, reused]
Task lifecycle transition ── recorded as ──► AuditPayload (task_id set)  [reused audit topic]
```

- A **task** is identified by `task_id` and spans one `TaskRequest` and one `TaskResult` sharing the
  same `correlation_id` (inherited by the result from the request envelope).
- A task's **audit trail** is the set of `AuditPayload` records on the audit topic whose
  `task_id` equals that task's id, ordered by Kafka offset.

---

## 4. Task Lifecycle State Machine (`runtime/runtime.py`)

States and the **single** audit/result outcome each path produces (FR-009 invariant):

```text
                         ┌─────────────► REJECTED   (audit: rejected)        ─► TaskResult(rejected)
                         │               (validation / unsupported / duplicate; handler NOT run)
TaskRequest received ────┤
                         │
                         └─► ACCEPTED ──┬──► COMPLETED (audit: accepted, completed) ─► TaskResult(completed)
                            (audit:     │
                             accepted)  └──► FAILED    (audit: accepted, failed)    ─► TaskResult(failed)
                                             (handler raised / signalled failure)
```

**Invariants enforced by the runtime**:
1. Exactly one of {one `rejected`} **or** {one `accepted` + exactly one of `completed`|`failed`} is
   audited per `task_id` (FR-009).
2. Validation and capability checks run **before** `accepted` is emitted and before the handler runs
   (FR-005); a failure here yields `rejected`, never `accepted`.
3. A duplicate `task_id` (already processed) short-circuits to a `duplicate_skipped` audit; the
   handler is not re-run and no second terminal outcome or side effect is produced (FR-010).
4. `accepted` is non-terminal and never returned to the requester as a result status (research R8).

**Cross-references**: validation failure → `TaskError.category="validation"`; unknown capability →
`"unsupported_capability"`; duplicate → `"duplicate"`; handler exception → `"handler_error"`;
unexpected runtime error → `"internal"`.

---

## 5. Persistence Model

No new database. Topics (see contracts/topics.md for full configs):

| Topic | Purpose | Retention | Key |
|-------|---------|-----------|-----|
| `local.agent.<agent_id>.task.requested.v1` | Per-agent endpoint (request inbox). | time-based (7 days) | `task_id` |
| `local.agent.task.result.v1` | Shared result channel; requesters filter by `task_id`. | time-based (7 days) | `task_id` |
| `local.agent.agent-card.published.v1` | Capability discovery; latest card per agent. | compacted | `agent_id` |
| `local.audit.envelope.recorded.v1` | **Reused** for task-lifecycle audit (extended `AuditPayload`). | compacted | `original_envelope.event_id` |
| `local.system.processed-id.<agent_id>.recorded.v1` | **Reused** idempotency log, now also tracking processed `task_id`s. | compacted | id |

All topics are single-partition in this feature (foundation research R4).
