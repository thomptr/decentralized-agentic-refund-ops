# Feature Specification: Customer Resolution Agent

**Feature Branch**: `003-customer-resolution-agent`

**Created**: 2026-06-09

**Status**: Draft

**Input**: User description: "Build the Customer Resolution Agent for the decentralized RefundOps demo. The agent receives customer support tickets, determines whether the request needs refund review, requests billing and risk analysis from peer agents using A2A, consumes their Kafka result events, and produces a final customer response decision. The agent must not directly inspect billing or fraud databases and must not act as a general supervisor for unrelated tasks."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Triage an Incoming Support Ticket (Priority: P1)

As the customer resolution function, when a customer support ticket arrives, I want the agent to
decide whether the request actually needs a refund review or can be answered directly, so that only
genuine refund cases consume the peer-analysis workflow and everything else gets a fast, direct
response.

**Why this priority**: Triage is the agent's front door. Until the agent can ingest a ticket and
classify it, none of the downstream delegation or decision behavior is reachable. This slice proves
the Customer Resolution Agent stands up as an independent domain agent that owns ticket intake and
the refund-vs-no-refund judgment.

**Independent Test**: Submit a ticket that clearly does not concern a refund (e.g., a "how do I
change my email" question) and confirm the agent produces a direct customer response with no peer
analysis requested; submit a ticket that clearly concerns a refund and confirm the agent records a
"refund review required" determination and proceeds to the delegation step.

**Acceptance Scenarios**:

1. **Given** a support ticket whose content does not involve a refund or charge dispute, **When**
   the agent triages it, **Then** the agent records a "no refund review needed" determination and
   produces a direct customer response without requesting any peer analysis.
2. **Given** a support ticket that requests a refund or disputes a charge, **When** the agent
   triages it, **Then** the agent records a "refund review required" determination and advances the
   ticket to the analysis-delegation step.
3. **Given** any triaged ticket, **When** triage completes, **Then** the triage determination and
   its rationale are recorded on the resolution case and emitted to the audit trail.

---

### User Story 2 - Delegate Billing and Risk Analysis to Peer Agents (Priority: P1)

As the customer resolution function, when a ticket requires refund review, I want the agent to
request a billing analysis from the billing peer and a risk analysis from the risk peer using the
shared A2A runtime, so that specialized judgments are made by the agents that own that domain data —
never by the resolution agent itself.

**Why this priority**: Decentralized delegation is the core hypothesis. The resolution agent cannot
reach a sound decision without billing eligibility and risk signals, and constitutionally it must
obtain them only by asking the owning peers. This slice proves the agent participates in
peer-to-peer A2A delegation as a requester.

**Independent Test**: Submit a refund-review ticket and confirm the agent issues two correlated A2A
task requests — one to the billing peer's endpoint and one to the risk peer's endpoint — each
carrying the ticket context needed for analysis, and confirm the agent never reads billing or fraud
data directly.

**Acceptance Scenarios**:

1. **Given** a ticket determined to require refund review, **When** the agent begins analysis,
   **Then** it submits a structured billing-analysis task request to the billing agent's endpoint
   and a structured risk-analysis task request to the risk agent's endpoint, each correlated to the
   originating ticket.
2. **Given** the two analysis requests, **When** they are inspected, **Then** each carries only the
   ticket/order context the peer needs to perform its analysis, and the resolution agent reads no
   billing or fraud data source itself.
3. **Given** a peer that rejects a request (e.g., the capability is unavailable), **When** the
   rejection is received, **Then** the agent records the rejection on the case and routes the ticket
   to human escalation rather than fabricating the missing analysis.

---

### User Story 3 - Produce a Final Customer Response Decision (Priority: P1)

As the customer resolution function, when the billing and risk analyses come back as Kafka result
events, I want the agent to consume them, correlate them to the originating ticket, and produce a
single final customer response decision, so that the customer receives one clear, accountable
outcome for their refund request.

**Why this priority**: This is the payoff of the workflow. Requesting analyses has no value unless
their results are consumed and resolved into a decision. Together with User Stories 1 and 2, this
completes the end-to-end refund-resolution loop the demo exists to show.

**Independent Test**: Submit a refund-review ticket, supply billing and risk result events for it,
and confirm the agent emits exactly one final customer response decision correlated to the ticket,
whose outcome is consistent with the analyses it received.

**Acceptance Scenarios**:

1. **Given** a ticket awaiting analysis, **When** both the billing-analysis result and the
   risk-analysis result for that ticket are received, **Then** the agent combines them into a single
   final customer response decision (approve refund, deny refund, or escalate to human review) and
   emits it correlated to the originating ticket.
2. **Given** a ticket awaiting analysis, **When** only one of the two results has arrived, **Then**
   the agent does not yet emit a final decision and keeps the case open pending the second result.
3. **Given** an accepted task whose analysis result indicates the peer could not complete the work
   (a failure result), **When** it is received, **Then** the agent treats the analysis as
   unavailable and resolves the case to human escalation, recording the reason.
4. **Given** a ticket for which a final decision has already been emitted, **When** a duplicate or
   late result for that ticket arrives, **Then** the agent does not emit a second, contradictory
   decision.

---

### User Story 4 - Audit the Full Resolution Workflow (Priority: P2)

As a reviewer evaluating the PoC, I want every step the resolution agent takes — ticket received,
triage determination, each analysis delegated, each result consumed, and the final decision — to
leave an immutable, correlated audit trail, so I can reconstruct how a customer's refund outcome was
reached without reading the agent's code.

**Why this priority**: Observability is a constitutional requirement and the primary evidence that
the decentralized workflow is accountable. It builds on Stories 1–3, which produce the transitions
being audited.

**Independent Test**: Drive a refund-review ticket end to end, then query the audit trail by the
ticket's correlation identifier and confirm intake, triage, both delegations, both consumed results,
and the final decision are all present, attributed to the resolution agent, and in causal order.

**Acceptance Scenarios**:

1. **Given** a resolved ticket, **When** the audit trail is queried by the ticket's correlation
   identifier, **Then** every step the resolution agent performed is returned with its outcome, the
   agent's identity, a timestamp, and the causal link to its triggering event.
2. **Given** a ticket escalated to human review, **When** the audit trail is queried, **Then** the
   reason for escalation (peer rejection, peer failure, elevated risk, or conflicting analyses) is
   recoverable from the trail.

---

### User Story 5 - Never Inspect Billing or Fraud Data Directly (Priority: P2)

As a project reviewer enforcing strict domain ownership, I want to confirm the resolution agent
obtains all billing and risk judgments exclusively from peer analysis results and never reads a
billing or fraud data source itself, so that domain isolation between the customer-resolution,
billing, and risk agents is genuinely preserved.

**Why this priority**: Strict domain ownership is a constitutional guardrail. A resolution agent
that peeked at billing or fraud data directly would collapse three independent agents into one and
invalidate the decentralization the demo is meant to prove.

**Independent Test**: Inspect the agent's inputs and behavior across a refund-review case and
confirm that every billing-eligibility and risk judgment used in the decision originated from a peer
analysis result event, with no billing or fraud data source accessed by the resolution agent.

**Acceptance Scenarios**:

1. **Given** the resolution agent processing any ticket, **When** its data access is examined,
   **Then** it accesses no billing database, payment ledger, or fraud/risk data source directly; all
   such information enters only as peer analysis results.
2. **Given** a final decision, **When** its inputs are traced, **Then** every billing or risk fact it
   relied on is attributable to a billing-analysis or risk-analysis result from the owning peer.

---

### User Story 6 - Stay a Domain Agent, Not a General Supervisor (Priority: P3)

As a project reviewer guarding against a disguised orchestrator, I want to confirm the resolution
agent only delegates the specific billing and risk analyses its own refund workflow needs and never
coordinates, routes, or supervises unrelated tasks on behalf of other agents, so the system remains
genuinely decentralized rather than hub-and-spoke.

**Why this priority**: This is an acceptance guardrail rather than new capability. It can be verified
once the prior stories establish exactly what the agent does and does not do.

**Independent Test**: Inspect the agent's delegations and confirm each one is a billing or risk
analysis tied to a refund ticket it is itself resolving, and that the agent issues no task requests
unrelated to its own refund cases and accepts no role in dispatching work between other agents.

**Acceptance Scenarios**:

1. **Given** the agent's set of delegations, **When** they are inspected, **Then** each is a billing
   or risk analysis request bound to a specific refund ticket the agent owns; the agent delegates
   nothing outside its own refund-resolution workflow.
2. **Given** the running system, **When** task flow is traced, **Then** the resolution agent never
   receives, queues, or dispatches tasks on behalf of other agents, and no other agent depends on it
   to route their work.

---

### Edge Cases

- **Ambiguous triage**: When a ticket's refund intent is unclear, the agent MUST choose a defined
  default (treat as refund review required) and record the ambiguity in its rationale, rather than
  silently dropping the ticket.
- **Duplicate ticket**: If the same ticket (identical ticket identity) is delivered more than once,
  the agent MUST treat it as a single resolution case, producing no duplicate delegations and no
  duplicate final decision; the duplication MUST be recorded in the audit trail.
- **Only one analysis returns**: If one of the two required analyses never arrives, the case remains
  open with no final decision; liveness/timeout detection is out of scope and this gap MUST be
  documented rather than worked around.
- **Conflicting analyses**: When billing indicates eligibility but risk is elevated (or vice versa),
  the agent MUST resolve to a defined outcome (escalate to human review) rather than guessing.
- **Peer failure or rejection**: If a peer returns a failure result or rejects the request, the
  required judgment is unavailable; the agent MUST escalate the case to human review and record the
  reason, never fabricate the missing analysis.
- **Late result after decision**: A billing or risk result that arrives after a final decision has
  been emitted MUST NOT cause a second or contradictory decision; it is recorded, not applied.
- **Non-refund ticket**: A ticket that does not require refund review MUST receive a direct response
  with no peer delegation.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The agent MUST be an independent domain agent dedicated solely to customer resolution,
  exposing its own addressable A2A endpoint on the shared runtime and owning no billing or risk
  logic.
- **FR-002**: The agent MUST accept incoming customer support tickets and, for each, determine
  whether the ticket requires a refund review or can be answered directly.
- **FR-003**: The agent MUST record every triage determination, its rationale, and the resulting
  path (direct response vs. refund review) on the resolution case and in the audit trail.
- **FR-004**: For any ticket determined to need refund review, the agent MUST request a billing
  analysis from the billing peer agent and a risk analysis from the risk peer agent, using the
  shared A2A task-request contract, each request correlated to the originating ticket.
- **FR-005**: The agent MUST NOT directly access any billing database, payment ledger, or fraud/risk
  data source; all billing-eligibility and risk information MUST enter the agent exclusively as peer
  analysis results.
- **FR-006**: The agent MUST consume billing-analysis and risk-analysis result events from Kafka and
  correlate each result back to the originating ticket's resolution case.
- **FR-007**: The agent MUST produce exactly one final customer response decision per resolved
  refund-review ticket, with an outcome of approve refund, deny refund, or escalate to human review,
  correlated to the originating ticket.
- **FR-008**: The agent MUST NOT emit a final decision for a refund-review ticket until all required
  analysis results for that ticket have been received, except where a peer failure or rejection
  forces an escalation outcome.
- **FR-009**: The agent MUST derive its final decision only from the consumed analysis results and
  the ticket content, applying a defined, auditable decision policy (e.g., approve when billing
  indicates eligibility and risk is acceptable; deny when billing indicates ineligibility; escalate
  to human review on elevated risk, conflicting analyses, peer failure, or peer rejection).
- **FR-010**: The agent MUST resolve every refund-review case to a defined outcome — a final
  decision or a human escalation — and MUST record the reason whenever the outcome is escalation.
- **FR-011**: Ticket processing MUST be idempotent by ticket identity. Re-delivery of the same
  ticket MUST NOT create duplicate analysis requests or a duplicate final decision; the agent MUST
  track processed ticket identities and record duplicates in the audit trail.
- **FR-012**: A late or duplicate analysis result arriving after a case has reached a final decision
  MUST NOT produce a second or contradictory decision; it MUST be recorded rather than applied.
- **FR-013**: The agent MUST emit a structured audit event for each significant step — ticket
  received, triage determination, each analysis delegated, each result consumed, and the final
  decision — each carrying the agent identity, ticket/correlation identity, a causation link, a
  timestamp, the outcome, and (for escalations) a reason.
- **FR-014**: The audit trail MUST be queryable by the ticket's correlation identifier to reconstruct
  the full resolution workflow from intake to final decision in causal order.
- **FR-015**: The agent MUST NOT act as a supervisor, router, dispatcher, or orchestrator for tasks
  unrelated to its own refund cases. Its only delegations MUST be billing and risk analyses bound to
  refund tickets it is itself resolving; it MUST NOT receive, queue, or dispatch work on behalf of
  other agents.
- **FR-016**: The agent MUST build on the existing shared A2A runtime and event foundation — reusing
  the runtime's task-request/result contracts, the event envelope, the audit subsystem, and the
  idempotency mechanism — rather than introducing a parallel transport or a second audit path.
- **FR-017**: The agent MUST address the billing and risk peers directly via their published
  endpoints discovered through the shared capability-discovery mechanism, with no central router
  selecting the target on its behalf.

### Key Entities

- **Customer Support Ticket**: The inbound request from a customer, carrying a unique ticket
  identity, the customer's message, and any order/charge context. The trigger for a resolution case.
- **Resolution Case**: The agent's working record for one ticket, tracking its triage determination,
  the analyses requested, the results received, and the final decision. One per ticket identity.
- **Triage Determination**: The agent's judgment of whether a ticket needs refund review, with a
  rationale and the chosen path (direct response vs. refund review).
- **Analysis Request**: A structured A2A task request the agent sends to a peer — a billing-analysis
  request to the billing agent or a risk-analysis request to the risk agent — correlated to a ticket.
- **Billing Analysis Result**: The billing peer's returned judgment about refund eligibility for a
  ticket, consumed as a result event. Owned by the billing agent; the resolution agent only reads it.
- **Risk Analysis Result**: The risk peer's returned judgment about fraud/risk for a ticket, consumed
  as a result event. Owned by the risk agent; the resolution agent only reads it.
- **Customer Response Decision**: The single final outcome for a ticket — approve refund, deny
  refund, or escalate to human review — correlated to the originating ticket and recorded in the
  audit trail.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of incoming tickets receive a triage determination, and tickets that do not
  concern a refund receive a direct response with zero peer analysis requests, demonstrated by a
  test suite covering refund and non-refund tickets.
- **SC-002**: For 100% of refund-review tickets, the agent issues exactly one billing-analysis
  request and exactly one risk-analysis request, each correlated to the originating ticket.
- **SC-003**: 100% of refund-review tickets resolve to exactly one final outcome (approve, deny, or
  escalate) — never zero and never multiple contradictory outcomes — across the test suite.
- **SC-004**: 100% of final decisions are traceable to the billing and risk analysis results that
  informed them, with no billing or fraud data source accessed directly by the agent, demonstrated
  by an isolation test.
- **SC-005**: Re-delivering an identical ticket produces no duplicate analysis requests and no
  second final decision in 100% of test runs, demonstrating idempotency.
- **SC-006**: A reviewer can reconstruct any ticket's full resolution workflow — intake, triage,
  both delegations, both results, and the final decision — from the audit trail by correlation
  identifier in under 30 seconds using a single documented query.
- **SC-007**: 100% of cases where a peer fails, rejects the request, or returns conflicting analyses
  resolve to a human-escalation outcome with a recorded reason, demonstrated by deliberate-fault
  tests.
- **SC-008**: A reviewer can confirm the agent issues no task requests outside its own refund-
  resolution workflow and dispatches no work on behalf of other agents, demonstrated by inspecting
  its full set of emitted requests.

## Assumptions

- **Builds on the `002-a2a-runtime-contract` runtime and `001-event-foundation`.** The agent is
  wrapped in the shared A2A runtime: it exposes its endpoint, discovers peers, and sends/receives
  task requests and results through the existing Kafka transport, reusing the event envelope,
  audit subsystem, idempotency tracker, and topic conventions as-is. This feature adds only the
  customer-resolution domain logic on top.
- **Billing and risk peer agents are assumed available as A2A capabilities.** This feature ships the
  Customer Resolution Agent only. The billing and risk agents are separate future features; for
  testing this feature, their analysis behavior is represented by stub/example peers (or recorded
  result events) that conform to the shared contracts. The resolution agent depends on their
  *published capabilities and result contracts*, not on their internal implementation.
- **Decision policy is a simple, illustrative PoC policy.** The mapping from billing eligibility and
  risk level to approve/deny/escalate is intentionally simple and auditable (e.g., approve when
  eligible and low risk; deny when ineligible; escalate on elevated risk, conflict, or missing
  analysis). Exact thresholds are demonstration values, not production refund policy.
- **Triage may use the project's standard reasoning approach.** Determining whether a ticket needs
  refund review is the agent's own domain judgment; the concrete mechanism (rule-based and/or an LLM
  reasoning step consistent with the project's AI SDK constraints) is finalized in planning and does
  not change the externally observable behavior specified here.
- **Both billing and risk analyses are required for a refund decision.** Every refund-review ticket
  requests both analyses; the agent waits for both before deciding, except when a peer
  failure/rejection forces an escalation. Conditional/partial-analysis flows are out of scope.
- **Liveness and timeout handling are out of scope.** Detecting a peer that never returns a result is
  deferred (consistent with the runtime feature); an unanswered case stays open and the gap is
  documented rather than covered by orchestration.
- **"Final customer response decision" is an emitted, correlated decision event**, not a synchronous
  reply or an actual customer-facing message channel. Delivering the decision to a real customer
  surface (email, portal) is out of scope; producing the auditable decision is in scope.
- **Single local environment.** The agent targets local developer workstations using the foundation's
  local infrastructure; production hardening (auth, scaling, HA) is out of scope per the
  constitution's PoC Scope Discipline principle.
