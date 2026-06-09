# Feature Specification: Decentralized Agent Event Foundation

**Feature Branch**: `001-event-foundation`

**Created**: 2026-06-08

**Status**: Draft

**Input**: User description: "Create the foundation for a proof-of-concept decentralized multi-agent system. The agents will communicate using the Agent2Agent protocol. The system must use structured event contracts for all inter-agent work and audit records. It must support local development with Kafka-compatible infrastructure using docker compose, shared Pydantic schemas, correlation IDs, causation IDs, timestamps, agent identity, and event replay-friendly design. This spec should not implement business agents yet."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Stand Up the Local Event Backbone (Priority: P1)

As a PoC developer, I want to launch the full local event infrastructure with a single command so I
can begin building and testing agents without depending on remote services or shared cloud
environments.

**Why this priority**: Without a reliable local backbone, no agent work can be developed, tested,
or demonstrated. Every downstream story depends on this being trivially reproducible.

**Independent Test**: Run the documented start-up command on a clean developer machine; observe
that the event broker and supporting services come online, accept connections, and expose an
inspectable health signal within a reasonable warm-up window.

**Acceptance Scenarios**:

1. **Given** a fresh checkout of the repository on a machine with the standard local container
   runtime installed, **When** the developer runs the documented start-up command, **Then** the
   event broker and any required companion services reach a ready state and report healthy.
2. **Given** the backbone is running, **When** the developer runs the documented stop command,
   **Then** all services shut down cleanly with no orphaned state that would block a subsequent
   start-up.
3. **Given** the backbone is running, **When** the developer queries the documented health/status
   endpoint or command, **Then** they receive a clear pass/fail indication for each component.

---

### User Story 2 - Publish and Consume a Structured Agent Event (Priority: P1)

As an agent author, I want to publish a structured event onto the bus from one process and consume
it from another so I can confirm the contract layer round-trips correctly and the transport is
wired end-to-end.

**Why this priority**: This proves the event-contract layer and transport are functional together.
Until this works, no business agent can be implemented.

**Independent Test**: Use a provided publisher utility to emit a sample event of the canonical
type; use a provided consumer utility to read it back. Validate that all required envelope fields
(identity, correlation, causation, timestamp) survive the round trip and that schema validation
catches a deliberately malformed payload.

**Acceptance Scenarios**:

1. **Given** the backbone is running and the shared schema package is installed, **When** a
   publisher utility emits a well-formed sample event, **Then** the consumer utility receives that
   exact event with every envelope field preserved.
2. **Given** the backbone is running, **When** a publisher attempts to emit an event whose payload
   violates the published schema, **Then** the publish call fails with a clear validation error
   before the event leaves the publisher.
3. **Given** the backbone is running, **When** a consumer receives an event whose envelope is
   missing a required identity, correlation, causation, or timestamp field, **Then** the consumer
   rejects the event and emits an audit record describing the rejection.

---

### User Story 3 - Trace a Logical Workflow via Correlation and Causation (Priority: P2)

As an operator investigating a workflow, I want every event in a logical chain to carry a stable
correlation identifier and a causation identifier pointing to its parent, so I can reconstruct
the full sequence of events that resulted from a single triggering action.

**Why this priority**: Auditability is a constitutional requirement (Principle IV). Without
correlation/causation discipline, the system cannot prove the hypothesis that decentralized agents
remain traceable.

**Independent Test**: Emit a chain of three events where each subsequent event names the previous
as its cause. Query the audit store by the shared correlation ID and verify the full chain is
recoverable in order, and that each event's causation pointer matches its true predecessor.

**Acceptance Scenarios**:

1. **Given** an initial event with a fresh correlation ID and no causation ID, **When** a
   downstream utility emits a follow-up event marking the first as its cause, **Then** both events
   share the same correlation ID and the second event's causation ID equals the first event's ID.
2. **Given** a chain of three events sharing a correlation ID, **When** the audit store is queried
   by that correlation ID, **Then** all three events are returned in their causal order.

---

### User Story 4 - Replay an Event Stream from a Known Point (Priority: P2)

As a PoC developer validating an agent's behavior, I want to replay a historical sequence of
events from a chosen starting point, so I can reproduce past scenarios deterministically without
re-creating upstream conditions.

**Why this priority**: Replay is the primary mechanism by which the team will demonstrate the
PoC's auditability and idempotency claims. Without it, regression testing of agent decisions is
impractical.

**Independent Test**: Publish a known sequence of events. Use the replay utility to re-deliver
events from a chosen offset to a fresh consumer; verify the consumer receives the expected subset
in the original order and that idempotent processing produces the same outcome as the original
run.

**Acceptance Scenarios**:

1. **Given** a stream containing a known sequence of events, **When** a developer requests replay
   from the earliest available offset, **Then** all events are re-delivered to the consumer in
   their original order with no duplicates or omissions.
2. **Given** a stream containing a known sequence of events, **When** a developer requests replay
   from a specified mid-stream offset, **Then** only events at or after that offset are delivered,
   in original order.
3. **Given** an idempotent consumer that has already processed a stream, **When** the same stream
   is replayed in full, **Then** the consumer's final state is identical to its state after the
   original run.

---

### User Story 5 - Inspect the Canonical Audit Record (Priority: P3)

As a reviewer evaluating the PoC, I want every event published on the bus to also be captured as
an immutable audit record with full envelope context, so I can demonstrate compliance with the
observability principle without inspecting agent code.

**Why this priority**: Audit visibility is required by the constitution but is not a prerequisite
for the publish/consume loop. It can land after the core contract layer is proven.

**Independent Test**: Publish a varied set of events. Query the audit record store and confirm
each published event appears exactly once with its full envelope intact, ordered by timestamp.

**Acceptance Scenarios**:

1. **Given** a sequence of events has been published, **When** the audit store is queried over the
   relevant time window, **Then** each published event appears exactly once with its full envelope
   preserved.
2. **Given** an event was rejected for schema or envelope reasons, **When** the audit store is
   queried for rejection records, **Then** the rejection is recorded with the reason and the
   offending event reference.

---

### Edge Cases

- **Broker unavailable at startup**: A publisher invoked before the broker is healthy MUST fail
  with a clear, actionable error rather than silently buffering or losing events.
- **Schema version drift**: If a consumer encounters an event whose schema version it does not
  recognise, it MUST refuse to process the event and emit an audit record naming the unknown
  version, rather than guessing.
- **Missing causation in a non-root event**: A downstream event that omits its causation ID MUST
  be rejected by the consumer; only root events (those initiating a new workflow) are permitted to
  omit causation.
- **Clock skew across producers**: Event ordering MUST rely on broker-assigned offsets or sequence
  numbers, not solely on producer-supplied timestamps, so that minor clock drift does not corrupt
  causal reconstruction.
- **Duplicate event IDs**: If two events with identical IDs appear on the bus, consumers MUST
  treat them as a single logical event (idempotent processing) and the audit store MUST record
  the duplication.
- **Replay against a live consumer**: Replay MUST be safe to perform against a consumer that is
  also processing live traffic, with no requirement for the consumer to be paused.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide a single documented command that starts a complete local
  event-backbone environment, including the event broker and any companion services required for
  event production, consumption, and audit storage.
- **FR-002**: The system MUST provide a single documented command that shuts down the local
  environment cleanly, leaving no state that would prevent a subsequent clean start-up.
- **FR-003**: The system MUST expose a health-check mechanism (command or endpoint) that reports a
  clear pass/fail signal for each backbone component.
- **FR-004**: The system MUST define a shared, versioned event envelope contract used by every
  inter-agent message and every audit record. The envelope MUST include, at minimum: a unique
  event identifier, a correlation identifier, a causation identifier (nullable for root events),
  an event-creation timestamp, the publishing agent's identity, the event type, and a schema
  version.
- **FR-005**: The system MUST provide a shared schema package that agent authors can depend on to
  produce and validate events against the canonical envelope and any registered payload schemas.
- **FR-006**: The system MUST follow the Agent2Agent (A2A) protocol for the wire-level contract of
  inter-agent messages. Where the A2A protocol leaves choices open, the project MUST document its
  selected conventions in a single referenced location.
- **FR-007**: Publishers MUST validate every outgoing event against its registered schema before
  publication. A failed validation MUST prevent the event from being placed on the bus.
- **FR-008**: Consumers MUST validate every incoming event against its registered schema and the
  envelope contract. A failed validation MUST result in the event being skipped and a rejection
  audit record being emitted.
- **FR-009**: The system MUST persist every successfully published event to an inspectable audit
  store, preserving the full envelope and payload.
- **FR-010**: The audit store MUST be queryable by correlation identifier to retrieve all events
  belonging to a single logical workflow.
- **FR-011**: The system MUST support replay of events from a chosen starting offset to a target
  consumer without requiring the rest of the system to be paused.
- **FR-012**: Consumers built on the provided foundation MUST be able to declare themselves
  idempotent and have the foundation track processed event IDs on their behalf, skipping
  duplicates automatically.
- **FR-013**: The system MUST provide minimal publisher and consumer utilities used for testing
  the contract and transport layers. These utilities are explicitly NOT business agents; their
  sole purpose is to exercise the foundation.
- **FR-014**: All documentation required for a new developer to bring the system up, publish a
  test event, consume it, and inspect the audit record MUST be present in the repository.
- **FR-015**: The system MUST NOT ship any domain-specific (refund-business) agent logic in this
  feature. The foundation is the deliverable.

### Key Entities

- **Event Envelope**: The shared structure carried by every event. Fields include: event ID,
  correlation ID, causation ID (nullable), timestamp, agent identity, event type, and schema
  version. Treated as immutable once published.
- **Event Payload**: The type-specific structured body that accompanies the envelope. Each
  registered event type has exactly one payload schema per schema version.
- **Agent Identity**: The stable identifier of the agent (or utility) that produced an event.
  Captured in the envelope so audit records can attribute every action.
- **Correlation Group**: The logical set of events sharing a single correlation ID, representing
  one end-to-end workflow.
- **Causation Link**: The directional pointer from an event to its immediate causing event. Root
  events have no causation link.
- **Audit Record**: A persistent, queryable representation of a published or rejected event,
  including its full envelope and outcome (accepted/rejected with reason).
- **Topic / Stream**: The logical channel on which a category of events is published. Topic naming
  and ownership conventions are part of the foundation.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A new developer, starting from a fresh repository clone on a supported workstation,
  can bring the full local event backbone to a healthy state in under 5 minutes following only the
  provided documentation.
- **SC-002**: A developer can publish a sample event from one terminal and observe it consumed in
  another terminal in under 1 minute of work, with no code changes required beyond the provided
  utilities.
- **SC-003**: For any chosen correlation identifier, a developer can retrieve the complete ordered
  chain of related events from the audit store in under 30 seconds, using a single documented
  query.
- **SC-004**: 100% of events that violate either the envelope contract or their payload schema are
  rejected before reaching downstream consumers, as demonstrated by a deliberate-violation test
  suite.
- **SC-005**: A consumer that has processed a stream once and is replayed against the same stream
  arrives at an identical final state in 100% of test runs, demonstrating idempotency.
- **SC-006**: Replay of a stream from a chosen offset delivers exactly the expected subset of
  events in original order in 100% of test runs.
- **SC-007**: Zero domain-specific refund agents exist in the foundation deliverable; a reviewer
  can verify the deliverable contains only transport, contract, audit, and test-utility code.

## Assumptions

- The PoC will run on developer workstations and lightweight shared environments only; production
  hardening (HA, multi-AZ, IAM-grade auth) is explicitly out of scope per the constitution's PoC
  Scope Discipline principle.
- Developers have a working local container runtime available; the project will not ship
  installation guidance for that runtime itself.
- The Agent2Agent (A2A) protocol's wire contract is stable enough to adopt directly; project-level
  conventions will be documented for any optional fields the protocol leaves to implementers.
- A single schema-version field on the envelope is sufficient for the PoC; multi-schema-version
  coexistence within a topic is not required to be demonstrated, only safely rejected.
- The audit store may be co-located with the event broker (e.g., a dedicated topic, log-compacted
  stream, or simple persistent store) provided it satisfies the queryability requirements.
- Replay semantics are scoped to consumer-driven re-read from a chosen offset; broker-level
  time-travel beyond standard retention is not required.
- Local development is the only target environment for this foundation feature; remote/staging
  deployment is a future concern.
