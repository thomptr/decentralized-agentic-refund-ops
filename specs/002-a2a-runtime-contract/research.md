# Phase 0 Research: Shared A2A Runtime Contract for Independent Agents

**Feature**: 002-a2a-runtime-contract
**Date**: 2026-06-09

This document resolves the open technical questions raised by the spec and plan. Each entry records
the **Decision**, the **Rationale**, and the **Alternatives considered**. It builds directly on the
decisions recorded in `001-event-foundation/research.md` (especially R2: A2A-structure-over-Kafka).

---

## R1. How an "A2A endpoint" maps onto Kafka

**Background**: The A2A protocol describes an HTTP server per agent, reachable at a URL advertised
by its Agent Card. The user input says each agent "must expose its own A2A endpoint." The
constitution (Principle II) forbids direct agent-to-agent invocation and mandates Kafka as the sole
transport. Foundation research R2 already resolved that A2A supplies *message structure* while Kafka
is the *transport*.

**Decision**: An agent's A2A endpoint is realized as a **per-agent request topic**,
`local.agent.<agent_id>.task.requested.v1`, that only that agent consumes. A peer "calls the
endpoint" by publishing a `TaskRequest` event to that topic. This is the task-level analogue of the
foundation's per-consumer `processed-id` dynamic topics.

**Rationale**:
- Preserves Principle II strictly: there is no HTTP and no direct call; delegation is an event.
- Satisfies FR-001's "uniquely addressable" requirement — the topic name *is* the address.
- Keeps the door open to a future HTTP/AgentCore gateway that forwards HTTP A2A calls onto this
  topic without changing the message contract (see R6).

**Alternatives considered**:
- **Real HTTP A2A servers between agents** — violates Principle II (direct invocation).
- **One shared `task.requested` topic with a `target_agent_id` filter** — turns every agent into a
  reader of every task (a shared inbox), weakening endpoint independence and adding filtering cost.

---

## R2. Capability publication & discovery (Agent Cards)

**Background**: A2A uses **Agent Cards** for discovery and metadata; AWS Bedrock AgentCore can
serve/retrieve A2A Agent Cards for a deployed runtime. The spec requires capability publication
discoverable by peers **without a central registry** (FR-003).

**Decision**: Each agent publishes an `AgentCard` event to a **compacted, latest-wins** discovery
topic `local.agent.agent-card.published.v1`, keyed by `agent_id`. Peers discover capabilities by
consuming that topic from the earliest offset and keeping the latest card per `agent_id`. The
`AgentCard` schema is a PoC-scoped subset of the A2A Agent Card (identity, version, endpoint
reference, and a list of capabilities/skills).

**Rationale**:
- Compaction gives a "registry-like" current view **without** a central registry service — the
  topic is just the event log; no component answers lookups, so no central component is introduced
  (honors FR-011).
- Keying by `agent_id` means re-publishing a card supersedes the prior one (FR-013).
- Using the A2A Agent Card shape keeps the published metadata forward-compatible with what
  AgentCore would serve for a deployed runtime (R6).

**Alternatives considered**:
- **A central capability registry/service** — would be a central component the spec forbids.
- **A static config file of capabilities** — not discoverable at runtime; cannot reflect agents
  joining/leaving or changing capabilities (FR-013).

---

## R3. Asynchronous request→result correlation

**Background**: With no synchronous transport, a requester cannot block on a return value; the
result must come back as an event correlated to the request.

**Decision**: Results flow on a single shared topic `local.agent.task.result.v1` (time-retained,
single partition). A `TaskResult` event carries the `task_id`; its envelope shares the request's
`correlation_id` and sets `causation_id` to the request envelope's `event_id`. The `A2AClient`
submits a request, then consumes the result topic filtering for its `task_id` until the matching
result arrives (or a caller-supplied timeout elapses).

**Rationale**:
- Reuses the foundation's correlation/causation discipline (a reply is a new event whose causation
  points at the request) — identical to foundation research R2.
- A single result topic keeps global order and makes correlation a trivial `task_id` filter at PoC
  scale.

**Alternatives considered**:
- **Per-requester result topics** — multiplies dynamic topics with no PoC benefit.
- **Synchronous RPC** — violates Principle II.

---

## R4. Task-lifecycle audit model (accepted / completed / failed / rejected)

**Background**: FR-008 requires a Kafka audit event for each of four outcomes; FR-009 requires
exactly one of {rejected} OR {accepted + one terminal (completed|failed)} per task; FR-014 requires
reusing the existing audit subsystem rather than a parallel path.

**Decision**: Extend the existing `AuditPayload` (in `payloads/sample.py`) with an optional
`task_id: UUID | None` and broaden its `outcome` literal to
`["accepted", "rejected", "duplicate_skipped", "completed", "failed"]`. Task-lifecycle audit events
are written through the existing `audit/store.py` helper to the existing compacted audit topic
`local.audit.envelope.recorded.v1`. The `original_envelope` recorded is the **request** envelope
for `accepted`/`rejected`, and the **result** envelope for `completed`/`failed`.

**Rationale**:
- Directly satisfies FR-014 — one audit subsystem, one audit topic, no parallel path.
- Each audit event has a unique envelope `event_id`, so compaction-by-`event_id` retains every
  transition; "query a task's full lifecycle" is a filter on `payload.task_id`.
- Reuses `write_audit()`, structlog wiring, and the query helpers unchanged in spirit.

**Alternatives considered**:
- **Dedicated per-outcome topics** (`...agent-task.accepted/completed/failed.v1`, which the
  foundation's `topics.md` lists as *examples*) — rejected because it creates a parallel audit path
  (FR-014) and fragments lifecycle reconstruction across topics.
- **A brand-new `TaskAuditPayload` + new topic** — more surface for no gain; the extended
  `AuditPayload` already carries everything needed.

---

## R5. Publishing to dynamic endpoint topics with validation intact

**Background**: `Publisher.publish()` resolves the destination from a static `event_type → topic`
map (`TOPIC_NAMES`) and validates the payload against the registry. Endpoint topics are computed
per target agent, so the static map cannot resolve them. `publish_raw()` exists but skips payload
validation.

**Decision**: Add a backward-compatible optional parameter `topic: str | None = None` to
`Publisher.publish()`. When provided, it overrides registry-based topic resolution while keeping all
payload/envelope validation. The runtime and `A2AClient` pass the computed endpoint/result topic.

**Rationale**:
- Keeps contract validation on the hot path (the runtime must reject malformed requests *before*
  the handler runs — FR-005) while supporting dynamic routing.
- Smaller and safer than duplicating build/validate logic in the runtime (which would violate
  FR-014's "no parallel transport") or loosening `publish_raw`.

**Alternatives considered**:
- **Use `publish_raw` from the runtime** — loses payload validation; the runtime would have to
  re-implement it.
- **Register every dynamic endpoint topic in `TOPIC_NAMES`** — impossible; agent IDs are not known
  ahead of time.

---

## R6. Relationship to AWS Bedrock AgentCore (forward compatibility, not built here)

**Background**: The user notes AgentCore supports retrieving A2A Agent Cards for deployed runtimes,
and that A2A centers on independent servers/clients rather than a required supervisor.

**Decision**: Treat AgentCore as a **future deployment target**, not part of this feature. The
local PoC publishes the **same A2A `AgentCard` structure** that AgentCore would serve, and keeps the
runtime's request/result contract transport-agnostic at the message level. No AgentCore SDK,
deployment, or Bedrock call is added in this feature.

**Rationale**:
- Aligns with Principle V (build only what proves the hypothesis locally) while ensuring the Agent
  Card and task contracts are not re-modeled when a managed deployment is later introduced.
- A2A's "independent client/server, no required supervisor" model is exactly the decentralized
  property the spec mandates (FR-011); adopting its Agent Card keeps that property portable.

**Alternatives considered**:
- **Build the AgentCore deployment now** — out of PoC scope; the hypothesis is provable locally on
  Kafka, and remote deployment is explicitly deferred by the spec's Assumptions.

---

## R7. Task idempotency granularity

**Background**: The foundation's `Consumer` already deduplicates by envelope `event_id`. But a
re-submitted task carries a **new** envelope `event_id` while keeping the **same** `task_id`, so
event-id dedup alone does not satisfy FR-010.

**Decision**: The `AgentRuntime` maintains task-level idempotency keyed by `task_id`, reusing the
foundation's `IdempotencyTracker` (its keys are UUIDs; `task_id` is a UUID). A repeat `task_id`
short-circuits before the handler runs; the runtime emits a `duplicate_skipped` audit event and
does not produce a second result or re-execute side effects.

**Rationale**:
- Satisfies Principle III and FR-010 at the correct granularity (the *task*, not the transport
  envelope) while reusing existing machinery (FR-014).

**Alternatives considered**:
- **Rely on envelope `event_id` dedup** — fails for genuine re-submissions of the same task.
- **A new bespoke task-dedup store** — duplicates `IdempotencyTracker` for no benefit.

---

## R8. Rejection vs. failure surfaced to the requester

**Background**: FR-006 requires a structured result for every accepted task; FR-007 distinguishes a
**rejection** (refused before execution) from a **failure** (accepted handler did not succeed). The
requester must always receive one typed outcome.

**Decision**: `TaskResult.status` is `Literal["completed", "failed", "rejected"]`. The runtime
always returns exactly one `TaskResult` to the requester:
- `rejected` — validation/unsupported-capability failure; carries a `TaskError` with a category;
  the handler never ran. Audit: single `rejected`.
- `completed` — handler succeeded; carries an `output` A2A message. Audit: `accepted` then
  `completed`.
- `failed` — handler ran and errored; carries a `TaskError`. Audit: `accepted` then `failed`.

`accepted` is an audit-only, non-terminal signal and is **not** a result status. This preserves the
FR-007 distinction in a single response object and maps cleanly onto the FR-009 audit invariant.

**Rationale**:
- One response shape for the requester is simpler than two (a separate rejection envelope) and
  still keeps rejection and failure semantically distinct via `status` + `error.category`.

**Alternatives considered**:
- **No result on rejection (audit only)** — the requester would have to infer rejection by timeout,
  which is unobservable and brittle.
- **Separate `TaskRejection` message type** — extra contract surface for no PoC benefit.

---

## R9. Testing strategy

**Decision**: Mirror the foundation's fast/slow split.
- **Unit** (`tests/unit/`): validate `TaskRequest`/`TaskResult`/`TaskError`/`AgentCard` models and
  the runtime **state machine** (exactly-one-terminal invariant, rejection-vs-failure mapping,
  duplicate short-circuit) with the transport mocked/stubbed.
- **Contract** (`tests/contract/`): JSON-schema round-trip for the three new payloads against the
  schemas in `contracts/`, plus payload-registry conformance.
- **Integration** (`tests/integration/`, `-m integration`): bring up Kafka via `testcontainers`,
  run the echo agent, and drive accept→complete, accept→fail, and reject end-to-end; assert the
  exact audit-event sequence per task and that a re-submitted `task_id` does not re-execute.

**Rationale**: Real Kafka is required to prove the lifecycle/audit/idempotency invariants (Principle
III, FR-009, FR-010); pure-unit tests keep the state-machine logic fast and deterministic.

**Alternatives considered**:
- **Mock Kafka everywhere** — rejected for the same reason as foundation research R10: it masks
  broker ordering and offset semantics that the audit/idempotency guarantees depend on.

---

## Summary of resolved NEEDS CLARIFICATION

None remained from the spec or the plan's Technical Context. The spec's one deferred item — whether
"endpoint" means literal HTTP/A2A or an event-bus inbox — is resolved here in R1 (event-bus inbox)
against the constitution, consistent with `001-event-foundation` research R2. AgentCore is scoped
out as a forward-compatible future target (R6).
