# Feature Specification: Shared A2A Runtime Contract for Independent Agents

**Feature Branch**: `002-a2a-runtime-contract`

**Created**: 2026-06-09

**Status**: Draft

**Input**: User description: "Implement a shared A2A runtime contract for independent agents. Each agent must expose its own A2A endpoint, publish its capabilities, accept structured task requests, return structured task results, and emit Kafka audit events for all accepted, completed, failed, or rejected tasks. The system must not include a supervisor agent or centralized request router."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Stand Up an Independent Agent with Its Own Endpoint (Priority: P1)

As an agent author, I want to wrap my agent in the shared runtime so it exposes its own
addressable A2A endpoint and accepts structured task requests, without writing any transport,
validation, or audit plumbing myself.

**Why this priority**: Nothing else in the feature is reachable until an agent can be stood up and
addressed independently. This is the minimum slice that proves the runtime contract exists and is
reusable.

**Independent Test**: Register a minimal example agent against the runtime, address its endpoint
with a well-formed task request, and observe that the request is delivered to the agent's handler
and an "accepted" audit event is emitted — all without the author writing any transport code.

**Acceptance Scenarios**:

1. **Given** an agent registered with the shared runtime, **When** a peer addresses that agent's
   endpoint with a structured task request for a capability the agent declares, **Then** the
   runtime validates the request, hands it to the agent, and emits an "accepted" audit event
   carrying the task identity and the accepting agent's identity.
2. **Given** a registered agent, **When** a peer addresses its endpoint with a task request that
   violates the shared task-request contract, **Then** the runtime rejects the request before the
   agent's handler runs and emits a "rejected" audit event naming the validation failure.
3. **Given** a registered agent, **When** a peer submits a task request for a capability the agent
   does **not** declare, **Then** the runtime rejects the request with an "unsupported capability"
   reason and emits a "rejected" audit event.

---

### User Story 2 - Return a Structured Task Result (Priority: P1)

As an agent author, I want the runtime to return a structured result for every task my agent
accepts — whether the work succeeds or fails — so requesting peers always receive a typed,
predictable outcome and the lifecycle is fully audited.

**Why this priority**: An endpoint that accepts work but cannot return a typed result or signal
failure is not a usable contract. Paired with User Story 1, this completes the request→result loop
that every future business agent depends on.

**Independent Test**: Submit a task the example agent can satisfy and confirm a structured success
result is returned and a "completed" audit event is emitted; then submit a task whose handler
raises an error and confirm a structured failure result is returned and a "failed" audit event is
emitted.

**Acceptance Scenarios**:

1. **Given** an accepted task whose handler completes successfully, **When** the handler returns,
   **Then** the runtime returns a structured task result conforming to the shared result contract,
   correlated to the originating request, and emits a "completed" audit event.
2. **Given** an accepted task whose handler raises an error or signals failure, **When** the
   handler terminates, **Then** the runtime returns a structured failure result carrying an error
   category and message (distinct from a rejection) and emits a "failed" audit event.
3. **Given** any accepted task, **When** it reaches a terminal state, **Then** exactly one of a
   "completed" or "failed" audit event is emitted for it — never both and never neither.

---

### User Story 3 - Discover Peer Capabilities Without a Central Registry (Priority: P2)

As an agent author whose agent needs to delegate part of a workflow, I want to discover which
peers can perform which tasks by reading their published capabilities, so I can route a task
directly to a capable peer without consulting any supervisor or central router.

**Why this priority**: Decentralized delegation is the core hypothesis. Capability publication is
what makes peer-to-peer routing possible; it follows the request/result loop because delegation is
only meaningful once endpoints accept and answer tasks.

**Independent Test**: Start two example agents declaring different capabilities, read the published
capability descriptions, and confirm a requester can identify the correct peer for a given task
type purely from published capabilities — with no central routing component involved.

**Acceptance Scenarios**:

1. **Given** an agent that has started and joined the system, **When** it comes online, **Then**
   it publishes a machine-readable description of its identity and the capabilities it offers,
   discoverable by any peer.
2. **Given** an agent whose declared capabilities change, **When** it updates them, **Then** the
   latest published capability description supersedes the prior one for any peer that reads it.
3. **Given** a peer that needs a specific capability, **When** it inspects published capabilities,
   **Then** it can identify a capable agent and address that agent's endpoint directly, without
   any intermediary deciding the route.

---

### User Story 4 - Audit the Full Task Lifecycle End to End (Priority: P2)

As a reviewer evaluating the PoC, I want every task that any agent handles to leave an immutable
audit trail covering acceptance, rejection, completion, and failure, so I can reconstruct what
each autonomous agent did without reading its code.

**Why this priority**: Observability is a constitutional requirement and the primary evidence that
the decentralized model remains accountable. It builds on Stories 1–2, which produce the lifecycle
transitions being audited.

**Independent Test**: Drive a mix of accepted, rejected, completed, and failed tasks across the
example agents, then query the audit trail by task identity and confirm each task's full lifecycle
is recoverable with correct outcomes and reasons.

**Acceptance Scenarios**:

1. **Given** a set of tasks that were accepted, rejected, completed, or failed, **When** the audit
   trail is queried by a task identity, **Then** every lifecycle transition for that task is
   returned with its outcome, the responsible agent's identity, a timestamp, and (for rejections
   and failures) a reason.
2. **Given** a task that belongs to a larger workflow, **When** the audit trail is queried by the
   workflow's correlation identifier, **Then** the task's audit events are returned alongside the
   other events of that workflow in causal order.

---

### User Story 5 - Confirm There Is No Supervisor or Central Router (Priority: P3)

As a project reviewer, I want to verify that no supervisor agent, central router, or hidden
orchestrator exists in the runtime, so I can confirm the system genuinely demonstrates
decentralized coordination rather than a disguised hub-and-spoke design.

**Why this priority**: This is a guardrail/acceptance check rather than new capability. It can be
verified once the prior stories establish what the runtime does and does not contain.

**Independent Test**: Inspect the runtime deliverable and the running system; confirm that every
task is delivered directly from requester to the capable agent's endpoint, and that no component
receives, queues, or dispatches tasks on behalf of other agents.

**Acceptance Scenarios**:

1. **Given** the complete runtime deliverable, **When** a reviewer inspects its components,
   **Then** no component acts as a supervisor, router, dispatcher, or orchestrator that mediates
   task delegation between agents.
2. **Given** a task delegated from one agent to another, **When** the delegation path is traced,
   **Then** the requesting agent addresses the performing agent's endpoint directly, with no
   intermediary in the path.

---

### Edge Cases

- **Duplicate task request**: If the same task request (identical task identity) is delivered more
  than once, the runtime MUST treat it as a single logical task, producing no duplicate work or
  duplicate side effects, and the audit trail MUST record the duplication rather than emitting a
  second acceptance.
- **Result for an unknown or already-terminal task**: A result or status update referencing a task
  identity the runtime has no open record of (never accepted, or already completed/failed) MUST be
  rejected and recorded, not silently applied.
- **Unsupported capability**: A task request naming a capability the addressed agent does not
  declare MUST be rejected with an explicit reason; the agent's handler MUST NOT run.
- **Malformed capability publication**: A capability description that does not conform to the
  shared capability contract MUST be refused, leaving the prior valid description in effect.
- **Handler never terminates / agent stops mid-task**: Liveness detection (heartbeats, deadlines)
  is out of scope for this feature; a task whose handler neither completes nor fails produces no
  terminal audit event, and this limitation MUST be documented rather than worked around.
- **Competing providers for one capability**: When more than one agent declares the same
  capability, both are valid; the requester selects a target. No component arbitrates or
  load-balances between them (doing so would constitute a central router).
- **Audit emission failure**: If a lifecycle audit event cannot be emitted, the runtime MUST
  surface the failure rather than allowing a task transition to occur with no audit record.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The runtime MUST allow each agent to expose its own uniquely addressable A2A
  endpoint, such that a peer can direct a task request to a specific agent.
- **FR-002**: The runtime MUST provide a shared, reusable contract so that every agent uses
  identical structures for task requests, task results, capability descriptions, and audit events.
  No agent may define its own variant of these structures.
- **FR-003**: Each agent MUST publish a machine-readable description of its identity and the
  capabilities it offers, discoverable by peers without consulting any central registry, router,
  or supervisor.
- **FR-004**: An agent's endpoint MUST accept structured task requests that conform to the shared
  task-request contract, following the Agent2Agent (A2A) protocol's message conventions.
- **FR-005**: The runtime MUST validate every incoming task request against the shared contract
  and against the receiving agent's declared capabilities before the agent's handler runs. A
  request that fails validation or names an undeclared capability MUST be rejected without
  execution.
- **FR-006**: For every accepted task that runs to a terminal state, the runtime MUST return a
  structured task result conforming to the shared task-result contract, correlated to the
  originating request.
- **FR-007**: The runtime MUST distinguish a **rejection** (request refused before execution) from
  a **failure** (accepted task whose handler did not succeed). A failure result MUST carry a
  structured error with a category and a human-readable message.
- **FR-008**: The runtime MUST emit a Kafka audit event for each of the four task lifecycle
  outcomes — **accepted**, **completed**, **failed**, and **rejected**. Each audit event MUST
  carry the task identity, the responsible agent's identity, a correlation identifier, a causation
  identifier linking it to its triggering event, a timestamp, the outcome, and (for rejections and
  failures) a reason.
- **FR-009**: Each task MUST resolve to exactly one of the following audit patterns: a single
  "rejected" event, OR an "accepted" event followed by exactly one terminal event ("completed" or
  "failed"). The runtime MUST NOT produce contradictory or duplicate terminal outcomes for a task.
- **FR-010**: Task requests MUST be idempotent by task identity. Re-delivery of a request with the
  same task identity MUST NOT create a duplicate task or duplicate side effects; the runtime MUST
  track processed task identities and record duplicates in the audit trail.
- **FR-011**: The system MUST NOT include any supervisor agent, central request router, dispatcher,
  or orchestrator that mediates task delegation between agents. Task delegation MUST be
  peer-to-peer: the requesting agent addresses the performing agent's endpoint directly.
- **FR-012**: The audit trail MUST be queryable by task identity to retrieve a single task's full
  lifecycle, and by correlation identifier to place that task within its broader workflow.
- **FR-013**: An agent MUST publish its capabilities when it comes online and MUST be able to
  update them, with the latest published description superseding earlier ones for any reader.
- **FR-014**: The runtime MUST build on the existing event foundation — reusing its event
  envelope, audit subsystem, and idempotency mechanism — rather than introducing a parallel
  transport or a second audit path.
- **FR-015**: This feature MUST NOT ship any refund-domain (business) agent logic. The deliverable
  is the shared runtime contract plus a minimal, non-domain example agent (or agents) used solely
  to exercise and demonstrate the contract.
- **FR-016**: All documentation required for an agent author to wrap an agent in the runtime,
  publish its capabilities, accept a task, return a result, and inspect the resulting audit trail
  MUST be present in the repository.

### Key Entities

- **Agent Endpoint**: The uniquely addressable point at which a specific agent accepts task
  requests. Owned by exactly one agent; addressable by any peer.
- **Capability Description**: A machine-readable declaration of an agent's identity and the task
  types it can perform. Published by the agent and discoverable by peers; latest-published wins.
- **Capability**: A single named task type an agent advertises it can handle, including the shape
  of input it expects and output it returns.
- **Task Request**: A structured, A2A-aligned instruction submitted to an agent's endpoint,
  carrying a unique task identity, the requested capability, and typed input.
- **Task Result**: The structured outcome returned for an accepted task — either a success result
  with typed output or a failure result with a structured error — correlated to its request.
- **Task Lifecycle Outcome**: One of {accepted, completed, failed, rejected}, the discrete states
  a task may pass through. "Accepted" is non-terminal; "completed", "failed", and "rejected" are
  terminal.
- **Task Audit Event**: An immutable record of a single lifecycle transition, carrying task
  identity, agent identity, correlation/causation identifiers, timestamp, outcome, and reason.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An agent author can take a bare agent handler and expose it as an independently
  addressable endpoint with published capabilities by using only the shared runtime, writing zero
  transport, validation, or audit code, in under 15 minutes following the documentation.
- **SC-002**: 100% of task lifecycle transitions (accepted, completed, failed, rejected) emit
  exactly one corresponding audit event, demonstrated by a test suite that drives each outcome.
- **SC-003**: 100% of accepted tasks resolve to exactly one terminal outcome (completed or
  failed); no task in the test suite produces zero or multiple terminal outcomes.
- **SC-004**: 100% of task requests that are malformed or that name an undeclared capability are
  rejected before any handler runs, demonstrated by a deliberate-violation test suite.
- **SC-005**: Re-delivering an identical task request produces an identical outcome with no
  duplicate side effects in 100% of test runs, demonstrating idempotency.
- **SC-006**: A peer can discover a capable agent and successfully delegate a task to it using only
  published capabilities, with no central router in the path, demonstrated end to end.
- **SC-007**: A reviewer can reconstruct any task's full lifecycle from the audit trail by task
  identity in under 30 seconds using a single documented query.
- **SC-008**: A reviewer can confirm the deliverable contains zero supervisor, router, dispatcher,
  or orchestrator components; every delegation path goes directly from requester to performer.

## Assumptions

- **Transport is the existing event foundation.** Per the project constitution (agents communicate
  exclusively via Kafka, with no direct agent-to-agent invocation), an agent's "A2A endpoint" is
  realized as an addressable inbox on the shared event bus, and task delegation is asynchronous:
  a requester submits a task request and later receives a correlated task-result event. The A2A
  protocol governs the *message structure*; the event foundation governs the *transport*. The
  concrete realization is finalized in planning.
- **Builds directly on `001-event-foundation`.** The event envelope, audit topic, correlation/
  causation discipline, idempotency tracker, and topic-naming conventions are reused as-is; this
  feature adds the task-request, task-result, and capability contracts plus the per-agent endpoint
  and lifecycle-audit behavior on top of them.
- **No business agents.** Only the shared runtime and a minimal non-domain example agent (e.g., an
  echo or arithmetic agent) ship in this feature; refund-domain agents (customer resolution,
  billing, risk) are future features.
- **Capability discovery is publish/read, not query/respond.** Agents publish capability
  descriptions onto a shared, latest-wins discovery channel; peers read them. No central capability
  service answers lookups (that would be a central component).
- **Liveness and timeout handling are out of scope.** Detecting a crashed or hung agent mid-task
  (heartbeats, deadlines, automatic failure after timeout) is deferred; the feature documents this
  gap rather than adding orchestration to cover it.
- **Single local environment.** The runtime targets local developer workstations using the
  foundation's local infrastructure; production hardening (auth, scaling, HA) is out of scope per
  the constitution's PoC Scope Discipline principle.
- **"Result returned to the requester" means a correlated result event**, not a synchronous
  response, consistent with the asynchronous, event-driven coordination model above.
