# Feature Specification: Decentralized Workflow & Event Choreography

**Feature Branch**: `006-workflow-choreography`

**Created**: 2026-06-10

**Status**: Draft

**Input**: User description: "Decentralized Workflow & Event Choreography. Make the full system work end-to-end. Includes: Ticket → resolution → billing/risk → decision; Correlation across topics; Async result aggregation; Idempotent processing; Replay tests; Failure paths"

## Overview

The individual agents — customer resolution, billing entitlement, and risk/fraud — already exist and
work in isolation. This feature makes the **whole system run end-to-end**: a customer refund ticket
enters at one end and a final, fully-reasoned decision (approve, deny, or escalate) comes out the
other, produced entirely by autonomous agents coordinating through events with **no central
orchestrator**.

The work here is integration and choreography, not new domain logic. It connects the existing pieces
into a continuous, observable, replay-safe flow and proves the core hypothesis: that autonomous agents,
coordinated solely through events, can handle an end-to-end refund workflow while remaining auditable
and idempotent.

## Clarifications

### Session 2026-06-10

- Q: When billing says ineligible but risk flags high fraud, what is the final decision? → A: Deny the refund AND emit a separate risk/escalation flag for independent fraud follow-up (deny + risk flag).
- Q: How should the implementation prove there is no supervisor/orchestrator agent? → A: An automated architecture/structural test asserting no component directs or centrally dispatches all agents, PLUS the correlation-id audit trail showing the decision emerges purely from peer events.
- Q: Without a supervisor, what enforces a case's deadline when a peer opinion never arrives? → A: The Customer Resolution Agent runs its own per-case async wall-clock timer and self-resolves to escalate on expiry (resolution self-timer).
- Q: What default per-case deadline for collecting both peer opinions in the local demo? → A: 10 seconds.
- Q: How should "each agent owns only its domain" be enforced as a testable acceptance criterion? → A: Add a Success Criterion plus an automated structural test asserting no component reads or writes a domain it does not own (the resolution agent accesses no billing/fraud data store; it learns those facts only via peer opinion events) — mirroring the no-supervisor guard.
- Q: Must a case's full causal trace be reconstructable solely from the durable event/audit log, without reading any agent's in-memory state? → A: Yes — the recorded event/audit log is the single authoritative source of audit truth; the trace is derived only from recorded events (audit + domain result topics), never from in-process agent state.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A refund ticket becomes an automated decision (Priority: P1)

A customer submits a support ticket requesting a refund. The system triages the ticket, gathers a
billing-eligibility opinion and a fraud-risk opinion in parallel, combines them, and produces a single
final decision — approve the refund, deny it, or escalate to a human — together with a human-readable
explanation and a complete audit trail. No human touches the flow for a clean, low-risk, eligible case.

**Why this priority**: This is the headline capability — the end-to-end path that proves the PoC
hypothesis. Without it nothing else matters; with it alone the system already delivers demonstrable
value (a ticket in, a justified decision out).

**Independent Test**: Submit a single refund ticket for an eligible, low-risk customer and confirm a
terminal `approve_refund` decision is produced with an explanation and an audit trail linking back to
the original ticket — with no manual intervention.

**Acceptance Scenarios**:

1. **Given** a refund ticket for an eligible customer with no risk flags, **When** the ticket enters
   the system, **Then** a final `approve_refund` decision is produced with a customer-facing
   explanation and a full audit trail from ticket to decision.
2. **Given** a refund ticket for a customer who is ineligible per billing rules, **When** the ticket is
   processed, **Then** the final decision is `deny_refund` with the billing reason reflected in the
   explanation.
3. **Given** a non-refund support ticket (e.g., a general question), **When** the ticket enters the
   system, **Then** it is triaged to a direct response without invoking the billing or risk agents.

---

### User Story 2 - Correlated, async aggregation of independent opinions (Priority: P2)

For a refund case, the billing opinion and the risk opinion are produced independently and arrive at
different times and in any order. The resolution stage must wait for both opinions belonging to the
**same case**, combine them correctly, and never confuse opinions from one case with another — even
when many cases are in flight at once.

**Why this priority**: The async, correlated aggregation is what makes the choreography "decentralized"
rather than a disguised synchronous call chain. It is essential for correctness but builds on the P1
path already existing.

**Independent Test**: Run several refund cases concurrently, deliver their billing and risk results in
a deliberately shuffled order, and confirm each case's final decision combines exactly its own two
opinions and no others.

**Acceptance Scenarios**:

1. **Given** a refund case awaiting two opinions, **When** the risk result arrives before the billing
   result, **Then** the case still produces a correct decision once both are present (arrival order is
   irrelevant).
2. **Given** multiple refund cases in flight simultaneously, **When** their results interleave across
   the shared result stream, **Then** each decision is composed only of the opinions whose correlation
   matches that case.
3. **Given** a final decision has been produced, **When** its audit trail is inspected, **Then** both
   contributing opinions are linked to the decision and back to the originating ticket via a single
   shared correlation identifier.

---

### User Story 3 - Deterministic failure paths (Priority: P2)

Things go wrong: a peer agent is slow or never responds, an opinion request is rejected, or the two
opinions conflict (e.g., billing says eligible but risk is high). The workflow must always resolve a
case to a terminal state in a bounded, predictable way rather than hanging forever or producing an
unsafe decision.

**Why this priority**: A choreography that can stall or silently lose cases is not trustworthy. Bounded,
deterministic failure handling is required for the system to be considered "working end-to-end," but it
follows the happy path in sequence.

**Independent Test**: For each failure mode (no response within the deadline, rejected request, high-risk
opinion), drive a case through and confirm it reaches a deterministic terminal state — escalation to a
human or denial — with the reason recorded, and that no case remains open indefinitely.

**Acceptance Scenarios**:

1. **Given** a refund case where one peer opinion does not arrive within the configured deadline,
   **When** the deadline elapses, **Then** the case is resolved to `escalate_human` with a
   "missing opinion / timeout" reason, and is not left open.
2. **Given** a peer rejects or fails an opinion request, **When** the rejection/failure is observed,
   **Then** the case is resolved to a terminal state (escalate) with the failure reason recorded.
3. **Given** billing indicates eligible but risk indicates high fraud risk, **When** the opinions are
   combined, **Then** the case is resolved to `escalate_human` rather than auto-approved.
4. **Given** billing indicates ineligible AND risk indicates high fraud risk, **When** the opinions are
   combined, **Then** the case is resolved to `deny_refund` and a separate risk/escalation flag is
   emitted for independent fraud follow-up.

---

### User Story 4 - Idempotent, replay-safe processing (Priority: P3)

Because delivery is at-least-once, the same event may be delivered more than once, and an operator may
replay a recorded event stream to reproduce or debug a case. Re-processing identical events must produce
the identical decision and must not cause any duplicate side effects (no double opinions, no double
decisions).

**Why this priority**: Idempotency and replay are foundational guarantees that make the system safe and
debuggable, but they are validated on top of an already-working flow.

**Independent Test**: Process a recorded refund-case event stream once, capture the decision and the set
of emitted events; replay the same stream and confirm the decision is identical and no additional
side-effect events were produced.

**Acceptance Scenarios**:

1. **Given** a case has already been processed, **When** the exact same events are delivered again,
   **Then** the previously computed outcome is reused and no duplicate opinions or decisions are emitted.
2. **Given** a recorded end-to-end scenario, **When** it is replayed from the beginning, **Then** the
   final decision and explanation match the original run.
3. **Given** a duplicate opinion request (same task identity), **When** it is received, **Then** the
   stored result is returned without re-running the analysis.

---

### User Story 5 - Trace any case from a single identifier (Priority: P3)

An operator investigating a refund outcome can take one correlation identifier and reconstruct the entire
journey — ticket received, triage, both opinion requests, both opinions, aggregation, and final decision —
in order, without reading code.

**Why this priority**: Observability is required by the project's principles and is what lets stakeholders
believe the decision, but it is a cross-cutting confirmation rather than a standalone deliverable.

**Independent Test**: Take the correlation identifier of a completed case and retrieve, in causal order,
every step that contributed to its decision.

**Acceptance Scenarios**:

1. **Given** a completed refund case, **When** its correlation identifier is used to query the audit
   record, **Then** every step from ticket to decision is present and ordered by causation.
2. **Given** an escalated case, **When** its trail is inspected, **Then** the reason for escalation and
   the missing/failing contributor are identifiable from the trail alone.

---

### Edge Cases

- **Late opinion after timeout**: A peer opinion arrives *after* the case was already escalated for
  timeout. The late result MUST NOT silently flip or duplicate the already-terminal decision; it is
  recorded but ignored for decisioning.
- **Duplicate final decision attempt**: If aggregation is triggered twice for the same case, only one
  terminal decision is emitted.
- **Both opinions missing**: Neither peer responds before the deadline → escalate with a clear reason.
- **Out-of-order and interleaved results** across many concurrent cases → correct per-case attribution.
- **Replay of a partially-completed case**: Replaying a stream that ends mid-flight reproduces the same
  in-flight state, not a spurious decision.
- **Unknown / malformed ticket**: A ticket that cannot be triaged is routed to escalation rather than
  dropped.
- **Conflicting opinions**: Eligible-but-high-risk and ineligible-but-low-risk combinations resolve via
  an explicit, documented decision rule (see FR-010). Eligible+high-risk → escalate; ineligible+high-risk
  → deny **plus** a risk flag for separate fraud follow-up.

## Requirements *(mandatory)*

### Functional Requirements

**End-to-end flow**

- **FR-001**: The system MUST accept an incoming refund support ticket as the single entry point of the
  workflow and treat it as the root of a new refund case.
- **FR-002**: The system MUST triage each ticket and route refund-related tickets into the
  opinion-gathering flow while routing non-refund tickets directly to a response without invoking the
  billing or risk capabilities.
- **FR-003**: For a refund case, the system MUST request a billing-eligibility opinion and a fraud-risk
  opinion independently and concurrently, without either opinion depending on the other.
- **FR-004**: The system MUST produce exactly one terminal decision per refund case, with outcome one of
  `approve_refund`, `deny_refund`, or `escalate_human`, accompanied by a human-readable explanation.

**Correlation across topics**

- **FR-005**: Every event produced anywhere in a case's flow MUST carry the same correlation identifier
  as the originating ticket, so the entire case shares one correlation thread across all topics.
- **FR-006**: Every produced event MUST record its causation link to the immediate event that triggered
  it, enabling reconstruction of the causal chain from ticket to decision.
- **FR-007**: Each opinion result MUST be attributable to the specific opinion request (and therefore the
  specific case) that prompted it, so results can be matched to cases without ambiguity.

**Async result aggregation**

- **FR-008**: The resolution stage MUST hold a refund case open until both the billing and risk opinions
  for that case are received or the case's deadline elapses, regardless of the order in which opinions
  arrive.
- **FR-009**: The system MUST correctly attribute each incoming opinion to its case when many cases are
  in flight simultaneously, never combining opinions across cases.
- **FR-010**: The system MUST combine the two opinions into a final decision using this explicit
  decision rule, which defines the outcome for every combination of billing eligibility and risk level:
  - eligible + low/medium risk → `approve_refund`
  - eligible + high risk → `escalate_human`
  - ineligible + low/medium risk → `deny_refund`
  - ineligible + high risk → `deny_refund` **and** emit a separate risk/escalation flag (see FR-024)
  - any required opinion missing or failed → `escalate_human`
- **FR-024**: When the combination resolves to deny-with-high-risk (ineligible + high risk), the system
  MUST emit a distinct risk/escalation flag so fraud can be followed up independently of the refund
  outcome; this flag MUST NOT change the terminal `deny_refund` decision.

**Idempotent processing**

- **FR-011**: Re-delivery of an event already processed MUST NOT cause any duplicate side effect (no
  duplicate opinions, requests, or decisions); the prior outcome MUST be reused.
- **FR-012**: A repeated opinion request with the same task identity MUST return the previously computed
  result rather than re-running the analysis.
- **FR-013**: Aggregation MUST emit at most one terminal decision per case even if aggregation is
  triggered more than once.

**Replay**

- **FR-014**: The system MUST provide a means to replay a recorded end-to-end scenario from its events
  and MUST produce the identical final decision and explanation as the original run.
- **FR-015**: Replaying a recorded stream MUST NOT produce additional side-effect events beyond those of
  the original run.
- **FR-016**: The feature MUST include automated replay-based tests covering the happy path, the async
  aggregation/correlation behavior, and the defined failure paths.

**Failure paths**

- **FR-017**: Each refund case MUST have a bounded deadline (default 10 seconds) enforced by the Customer
  Resolution Agent itself via a per-case wall-clock timer; the agent MUST NOT depend on any external
  supervisor to time out. If both opinions are not received before the deadline elapses, the agent MUST
  self-resolve the case to a terminal `escalate_human` state with a timeout reason recorded.
- **FR-018**: A rejected or failed opinion request MUST resolve the case to a terminal state with the
  failure reason recorded, rather than leaving the case open.
- **FR-019**: An opinion that arrives after its case has already reached a terminal state MUST be
  recorded but MUST NOT alter or duplicate the terminal decision.
- **FR-020**: A ticket that cannot be triaged or is malformed MUST be routed to escalation rather than
  silently dropped.

**Decentralization & observability (constitutional)**

- **FR-021**: The choreography MUST emerge from agents reacting to events; the system MUST NOT introduce
  a central supervisor, router, or orchestrator that directs the agents. The absence of a supervisor
  MUST be proven by BOTH: (a) an automated architecture/structural test asserting that no component
  directs, commands, or centrally dispatches all three agents; and (b) the correlation-id audit trail
  demonstrating that the final decision emerges purely from peer events.
- **FR-022**: Every step of the workflow (ticket received, triage decision, each opinion request, each
  opinion, aggregation, final decision, and every failure/timeout) MUST emit a structured audit entry
  identifying the actor, the case, the action, and the outcome.
- **FR-023**: An operator MUST be able to reconstruct a case's full, causally-ordered journey from its
  correlation identifier alone, without inspecting code.
- **FR-025**: Each agent MUST act on only its own domain (customer resolution, billing, or risk); no
  agent may read or write another agent's domain data store or internal state. The resolution agent
  MUST learn billing-eligibility and fraud-risk facts solely via peer opinion events, never by reading a
  billing or fraud store directly. This domain isolation MUST be proven by an automated structural test
  (the same proof style as the no-supervisor guard in FR-021a).
- **FR-026**: The recorded event/audit log MUST be the single authoritative source of audit truth: a
  case's full causal journey (FR-023) MUST be reconstructable **solely** from recorded events (the audit
  trail plus domain result events), without reading any agent's in-memory or working state.

### Key Entities *(include if feature involves data)*

- **Refund Case**: The logical unit of work spanning a single ticket to its final decision. Identified by
  the shared correlation identifier; has a lifecycle state (e.g., triaging, awaiting opinions, decided,
  escalated) and a deadline.
- **Support Ticket**: The inbound customer request that roots a case; carries the refund reason and
  customer/order context.
- **Opinion Request**: A request for a domain opinion (billing eligibility or fraud risk) addressed to a
  peer capability, bearing a task identity used for result matching and idempotency.
- **Opinion Result**: A peer's structured answer (recommendation/level, evidence, confidence, reasons)
  linked back to its request and case.
- **Decision**: The single terminal outcome of a case (approve/deny/escalate) with explanation and the
  contributing opinions referenced.
- **Correlation Chain**: The set of events sharing one correlation identifier plus their causation links,
  forming the auditable journey of a case.
- **Replay Scenario**: A recorded, ordered set of events for a case (or set of cases) used to reproduce a
  run deterministically in tests.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A clean, eligible, low-risk refund ticket reaches a terminal `approve_refund` decision with
  zero manual intervention in 100% of runs.
- **SC-002**: Across a batch of at least 10 concurrent refund cases with opinions delivered in shuffled
  order, 100% of cases produce a decision composed of exactly their own two opinions (no cross-case
  contamination).
- **SC-003**: Replaying any recorded end-to-end scenario yields a final decision and explanation
  identical to the original run in 100% of cases, with zero additional side-effect events emitted.
- **SC-004**: 100% of cases reach a terminal state (decided or escalated); no case remains open
  indefinitely, and every case that misses its 10-second deadline is escalated within that deadline plus
  a small bounded grace period (target: under 2 seconds of grace).
- **SC-005**: For any completed case, an operator can reconstruct 100% of the workflow steps in causal
  order from a single correlation identifier, without reading code.
- **SC-006**: Re-delivering the complete event set for an already-decided case produces zero duplicate
  opinions, requests, or decisions.
- **SC-007**: Every defined failure path (opinion timeout, rejected/failed request, conflicting opinions,
  malformed ticket) resolves to its documented terminal outcome in 100% of test runs.
- **SC-008**: The end-to-end happy path completes — ticket to decision — within a demonstrable bounded
  time on a local single-broker setup (target: under 30 seconds per case in the reference demo).
- **SC-009**: The absence of a supervisor is demonstrably proven: an automated architecture/structural
  test passes (no component centrally dispatches all agents) AND a sample case's audit trail shows the
  decision emerging solely from peer events — both verifiable without code inspection for the audit part.
- **SC-010**: Domain isolation is demonstrably proven: an automated structural test passes showing no
  component reads or writes a domain it does not own (in particular, the resolution agent accesses no
  billing or fraud data store), in 100% of runs.
- **SC-011**: For any completed or escalated case, the full causal journey is reconstructed using **only**
  the recorded event/audit log (no in-process agent state) in 100% of runs.

## Assumptions

- **Reuse, not rebuild**: The existing customer-resolution, billing-entitlement, and risk-fraud agents
  and their existing topics are reused as-is. The resolution agent remains the peer that requests and
  aggregates opinions; it is a participant, not a supervisor. This feature wires and verifies the flow
  rather than re-implementing domain logic.
- **No new orchestrator**: Per the project constitution, the choreography is emergent. No central
  orchestrator/router agent is introduced; aggregation and decisioning remain inside the resolution
  agent's autonomous responsibility.
- **Ticket intake**: A lightweight intake mechanism (the existing developer ticket publisher and/or a
  thin entry point) is sufficient to root the workflow. A production-grade ticket ingestion API, CRM
  integration, and customer-facing delivery of the decision (email/callback) are out of scope for this
  PoC.
- **Aggregation policy**: A refund decision requires both the billing and risk opinions. A missing
  opinion (timeout/failure) escalates rather than deciding on partial information. This is the
  conservative default for refund safety.
- **Decision rule**: The combination rule is fixed in FR-010 — eligible+low/medium → approve;
  eligible+high → escalate; ineligible+low/medium → deny; ineligible+high → deny plus a risk flag;
  any missing/failed opinion → escalate. The risk-level thresholds reuse the existing risk agent's
  output bands.
- **Deadline**: Each case has a bounded, configurable deadline for collecting opinions, defaulting to
  **10 seconds**, enforced by the Customer Resolution Agent's own per-case timer (no external timeout
  authority).
- **Transport**: The default local event transport (in-memory/local single-broker as already used) is
  assumed; no new transport is introduced.
- **Scale**: Concurrency targets are demo-scale (tens of in-flight cases), consistent with PoC scope, not
  production load.

## Out of Scope

- Production ticket ingestion (HTTP API at scale, CRM webhooks, customer portal).
- Customer-facing delivery/actuation of the decision (sending the email, issuing the actual payment
  reversal to an external processor).
- Human escalation tooling (review queues, SLA tracking, routing UIs).
- Authentication, authorization, encryption, multi-broker/HA, and other production-hardening concerns.
- New domain logic inside the billing, risk, or resolution agents beyond what aggregation/choreography
  requires.

## Dependencies

- **001-event-foundation**: envelope schema, audit trail, idempotency (event-id) tracking, replay
  primitives.
- **002-a2a-runtime-contract**: A2A task-request/result contracts, AgentCard discovery, task-level
  idempotency.
- **003-customer-resolution-agent**: triage, opinion requesting, aggregation, and decision emission.
- **004-billing-entitlement-agent**: the billing-eligibility opinion capability.
- **005-risk-fraud-agent**: the fraud-risk opinion capability.
