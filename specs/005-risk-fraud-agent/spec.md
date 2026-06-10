# Feature Specification: Risk and Fraud Agent

**Feature Branch**: `005-risk-fraud-agent`

**Created**: 2026-06-09

**Status**: Draft

**Input**: User description: "Create risk & fraud agent"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Assess Fraud Risk on a Peer Request (Priority: P1)

As the risk-and-fraud function, when a peer agent asks me to assess the fraud risk of a specific
refund case, I want to evaluate that case against the risk and fraud signals I own — account standing,
refund/dispute history, payment-instrument signals, behavioral/velocity anomalies, and known-fraud
indicators — and return a clear risk assessment, so that the requesting agent receives a fraud
judgment from the agent that actually owns risk signals rather than guessing at it.

**Why this priority**: This is the agent's reason to exist and the front door for every other
behavior. Until the agent can accept an assessment request and return a risk level, none of the
downstream evidence, result-event, or audit behavior is reachable. This slice proves the Risk and
Fraud Agent stands up as an independent domain agent that owns the fraud-risk judgment.

**Independent Test**: Send the agent a fraud-risk assessment request for a case whose risk signals
clearly indicate elevated/high fraud risk and confirm it returns an elevated/high risk level; send a
request for a case whose signals are clean and confirm it returns a low risk level — each correlated
to the originating request.

**Acceptance Scenarios**:

1. **Given** a fraud-risk assessment request correlated to a case whose signals indicate fraud risk,
   **When** the agent assesses it, **Then** the agent returns an elevated or high risk level,
   correlated to the originating request.
2. **Given** a fraud-risk assessment request for a case whose signals are clean, **When** the agent
   assesses it, **Then** the agent returns a low risk level, correlated to the originating request.
3. **Given** any assessment request the agent accepts, **When** assessment completes, **Then** the
   result is correlated to the originating request and is consumable by the requesting peer without any
   back-channel to this agent.

---

### User Story 2 - Publish a Structured Risk Result Event (Priority: P1)

As the risk-and-fraud function, when I complete an assessment, I want to publish a structured result
event carrying my risk level, the evidence behind it, a confidence score, the fraud-policy references I
applied, and a human-review flag, so that any interested agent or reviewer receives a self-describing,
auditable fraud verdict without having to ask me how I reached it.

**Why this priority**: A bare risk level is not enough for a decentralized, auditable system — the
consuming agents and reviewers need the supporting evidence and confidence to act on and to trust the
verdict. This slice turns the assessment from User Story 1 into the structured, observable artifact the
demo depends on.

**Independent Test**: Drive one assessment end to end and confirm exactly one structured result event
is published for it, carrying the risk level, a non-empty evidence set, a confidence score within its
defined range, the policy references applied, and a human-readable reasoning summary — all correlated
to the originating case/request.

**Acceptance Scenarios**:

1. **Given** a completed assessment, **When** the result is published, **Then** the result event
   contains a risk level, a confidence score within its defined range, an evidence set, the policy
   references applied, and a reasoning summary, correlated to the originating case.
2. **Given** a completed assessment, **When** the result event is inspected, **Then** every evidence
   item names its source and what it shows, and the policy references identify the specific fraud/risk
   rules the assessment rests on.
3. **Given** a completed assessment, **When** the result is delivered, **Then** the structured verdict
   is both returned to the requesting peer (correlated to its request) and published as a risk result
   event observable on the shared event stream.

---

### User Story 3 - Ground Every Assessment in Owned Risk & Fraud Signals (Priority: P1)

As the risk-and-fraud function, I want every risk level to be derived solely from the risk and fraud
signals I own — account standing, refund/dispute history, payment-instrument signals, behavioral/
velocity anomalies, and known-fraud indicators — and to cite that data as evidence, so that the verdict
is genuinely a fraud judgment and the agent never substitutes billing-eligibility or customer-
relationship reasoning that belongs to other agents.

**Why this priority**: Strict domain ownership is a constitutional guardrail and the basis for trust in
the verdict. A risk agent whose assessment cannot be traced to fraud signals — or that reaches into
another domain — collapses the separation the decentralized demo is meant to prove. This slice fixes
what "owns risk" concretely means for every assessment.

**Independent Test**: For a set of cases with differing risk signals (clean vs. prior chargebacks, low
vs. high refund velocity, matched vs. mismatched payment instrument, normal vs. anomalous behavior,
absent vs. present on a known-fraud list), confirm each risk level changes in line with those signals
and that every evidence item and policy reference traces back to one of the owned risk/fraud signal
domains — with no billing-eligibility or unrelated data used.

**Acceptance Scenarios**:

1. **Given** two cases identical except for one risk signal (e.g., one with a prior chargeback and one
   without), **When** each is assessed, **Then** the risk levels differ in a way explained by that
   signal, and the evidence cites it.
2. **Given** any assessment, **When** its inputs are traced, **Then** every evidence item and policy
   reference originates from the agent's owned risk/fraud signals and from its published fraud policy —
   never from billing, customer-resolution, or another agent's domain.
3. **Given** a case, **When** the agent assesses it, **Then** the agent reads only its own risk/fraud
   signal sources and makes no synchronous call to any other agent to obtain facts.

---

### User Story 4 - Handle Cases It Cannot Confidently Decide (Priority: P2)

As the risk-and-fraud function, when a case is missing the signals I need, is internally contradictory,
or otherwise cannot be confidently decided from the signals I own, I want to flag it for human review
(or report a failure) with a recorded reason instead of inventing a risk level, so that uncertainty
surfaces honestly rather than producing a false low/high verdict.

**Why this priority**: A confident-sounding but unfounded verdict is worse than an honest "needs
review" — and falsely clearing a fraudulent case, or falsely flagging a clean one, is exactly the
failure mode a fraud agent must avoid. This guardrail keeps the agent trustworthy and gives the
requesting workflow a safe path when signals are insufficient. It builds on User Stories 1–3, which
establish the normal verdict path.

**Independent Test**: Send the agent a request for a case whose risk signals are missing or
contradictory and confirm it does not emit a confident low/high level, instead flagging the result as
requiring human review (or returning a failure result) with a recorded reason; confirm a well-formed
case still returns a normal risk level.

**Acceptance Scenarios**:

1. **Given** a request for a case whose required risk signals are missing or unresolvable, **When** the
   agent assesses it, **Then** the agent does not fabricate a risk verdict; it returns a result flagged
   as requiring human review with a recorded reason, or a failure result when it cannot assess at all.
2. **Given** a case with contradictory signals, **When** the agent assesses it, **Then** the risk level
   is accompanied by a lowered/uncertain confidence and a human-review flag, with the conflict captured
   in the evidence and reasoning.
3. **Given** a request the agent cannot process (malformed or unanalyzable input), **When** it is
   received, **Then** the agent returns a failure result with a reason rather than a fabricated risk
   level, and the failure is observable in the audit trail.

---

### User Story 5 - Idempotent, Repeatable Assessment (Priority: P2)

As a reviewer of the PoC, I want re-delivery of the same assessment request to produce the same risk
level and no duplicate result events, so that the fraud verdict is stable and the workflow is safe to
replay.

**Why this priority**: Idempotency is a constitutional requirement and is what makes the event-driven,
at-least-once delivery model safe. Without it, a redelivered request could emit contradictory or
duplicated risk verdicts. It builds on the verdict path from User Stories 1–2.

**Independent Test**: Send the same assessment request twice and confirm the agent produces one logical
result (the same risk level, evidence, and confidence) and does not publish a second, duplicate or
contradictory result event; confirm the duplicate is recorded in the audit trail.

**Acceptance Scenarios**:

1. **Given** an assessment request the agent has already processed, **When** the identical request is
   delivered again, **Then** the agent does not perform a second independent assessment that could yield
   a different verdict and does not publish a duplicate result event.
2. **Given** a redelivered request, **When** it is handled, **Then** the duplication is recorded in the
   audit trail, and any consumer sees a single, consistent risk verdict for that case.
3. **Given** identical risk signals for a case, **When** the case is assessed, **Then** the risk level
   is deterministic — the same signals and the same policy yield the same verdict.

---

### User Story 6 - Audit Every Assessment (Priority: P2)

As a reviewer evaluating the PoC, I want every step the risk agent takes — request received, assessment
performed (with the evidence and policy references it used), result published, and any failure or
human-review flag — to leave an immutable, correlated audit trail, so I can reconstruct how a fraud
verdict was reached without reading the agent's code.

**Why this priority**: Observability is a constitutional requirement and the primary evidence that the
fraud verdict is accountable. It builds on the prior stories, which produce the steps being audited.

**Independent Test**: Drive an assessment end to end, then query the audit trail by the case's
correlation identifier and confirm the received request, the assessment decision (with evidence and
policy references), and the published result are all present, attributed to the risk agent, and in
causal order.

**Acceptance Scenarios**:

1. **Given** a completed assessment, **When** the audit trail is queried by the case's correlation
   identifier, **Then** every step the risk agent performed is returned with its outcome, the agent's
   identity, a timestamp, and the causal link to its triggering request.
2. **Given** a case flagged for human review or returned as a failure, **When** the audit trail is
   queried, **Then** the reason (missing signals, contradiction, or unanalyzable input) is recoverable
   from the trail.

---

### User Story 7 - Stay an Independent Domain Agent (Priority: P3)

As a project reviewer guarding against hidden coupling, I want to confirm the risk agent only performs
the fraud-risk assessments requested of it and never supervises, routes, or dispatches work for other
agents — nor calls another agent to do its assessment — so the system remains genuinely decentralized
rather than hub-and-spoke.

**Why this priority**: This is an acceptance guardrail rather than new capability. It can be verified
once the prior stories establish exactly what the agent does and does not do.

**Independent Test**: Inspect the agent's behavior across several assessment requests and confirm it
only ever responds to fraud-risk assessment requests addressed to it, issues no task requests of its
own to other agents, and dispatches no work on behalf of anyone else.

**Acceptance Scenarios**:

1. **Given** the agent's full set of interactions, **When** they are inspected, **Then** each is a
   fraud-risk assessment the agent performed in response to a request addressed to it; the agent
   originates no task requests to other agents and routes no work between them.
2. **Given** the running system, **When** task flow is traced, **Then** no other agent depends on the
   risk agent to dispatch or coordinate their work, and the risk agent obtains its risk signals only
   from its own data, not from peer calls.

---

### Edge Cases

- **Missing risk signals**: When the case references a customer, account, or order the agent has no risk
  record for, the agent MUST NOT default to a confident verdict (neither falsely clearing nor falsely
  flagging); it flags human review (or returns a failure) with a recorded reason (US4).
- **Contradictory signals**: When risk signals conflict (e.g., a long-tenured account in good standing
  paired with a sudden burst of high-velocity refund requests on a mismatched instrument), the agent
  MUST lower confidence and flag human review rather than silently picking one side (US4).
- **Borderline within policy thresholds**: A case sitting exactly on a policy boundary (e.g., a risk
  score exactly at the low/elevated or elevated/high threshold, or refund velocity exactly at a limit)
  MUST resolve to a defined, documented side of the boundary, recorded in the reasoning — never left
  undecided.
- **Duplicate / redelivered request**: An identical assessment request delivered more than once MUST
  yield a single logical verdict and no duplicate result event; the duplication is recorded (US5).
- **Unanalyzable / malformed request**: A request the agent cannot interpret MUST produce a failure
  result with a reason, not a fabricated risk level (US4).
- **No applicable policy**: When no published fraud-policy rule applies to a case, the agent MUST take a
  defined default stance (flag for human review with that stated reason) rather than clearing the case
  by omission.
- **Known-fraud indicator present**: When a case matches a known-fraud indicator (e.g., an entry on a
  blocklist), that indicator MUST appear as evidence driving the risk level upward, never be silently
  ignored.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The agent MUST be an independent domain agent dedicated solely to risk and fraud
  assessment, exposing its own addressable A2A endpoint on the shared runtime and owning no
  customer-resolution or billing-eligibility logic.
- **FR-002**: The agent MUST expose a single A2A capability to assess fraud risk, accepting an
  assessment request correlated to a specific case and returning a structured risk assessment.
- **FR-003**: The agent MUST own and analyze risk/fraud signals across its signal domains — account
  standing, refund/dispute history, payment-instrument signals, behavioral/velocity anomalies, and
  known-fraud indicators — and MUST derive every risk level solely from those owned signals and its
  published fraud policy.
- **FR-004**: The agent MUST produce a fraud-risk assessment for each accepted request, drawn from a
  defined set of risk levels (at minimum: low, elevated, and high) plus a flag that the case requires
  human review.
- **FR-005**: Every assessment MUST be accompanied by an evidence set in which each item names its
  source (which risk/fraud signal) and what it shows, and by the policy references identifying the
  specific fraud-policy rules the assessment rests on.
- **FR-006**: Every assessment MUST carry a confidence score within a defined range and a
  human-readable reasoning summary explaining how the evidence and policy led to the risk level.
- **FR-007**: The agent MUST publish a structured risk result event for each completed assessment,
  carrying the risk level, confidence score, evidence set, policy references, reasoning summary, and
  human-review flag, correlated to the originating case/request.
- **FR-008**: The structured assessment result MUST be both returned to the requesting peer correlated
  to its request (so the requester can consume it by correlation) and published as a risk result event
  observable on the shared event stream.
- **FR-009**: The agent MUST NOT access or rely on any data outside its owned risk/fraud signal domains
  (e.g., billing-eligibility facts, other agents' internal state); it MUST NOT make synchronous calls to
  other agents to obtain the facts behind its assessment.
- **FR-010**: When required risk signals are missing, unresolvable, or contradictory, the agent MUST NOT
  fabricate a risk verdict; it MUST flag the result as requiring human review with a recorded reason, or
  return a failure result when it cannot assess the case at all.
- **FR-011**: When the agent cannot interpret or process a request (malformed/unanalyzable input), it
  MUST return a failure result carrying a reason rather than a fabricated risk level.
- **FR-012**: The agent MUST apply a defined, auditable fraud policy: the mapping from risk signals to a
  risk level MUST be deterministic and reproducible, so identical signals under the same policy yield the
  same verdict.
- **FR-013**: Assessment MUST be idempotent by request identity: re-delivery of the same assessment
  request MUST NOT produce a second independent assessment or a duplicate result event; the agent MUST
  track processed request identities and record duplicates in the audit trail.
- **FR-014**: The agent MUST emit a structured audit event for each significant step — request received,
  assessment decision (including the evidence and policy references used), result published, and any
  failure or human-review flag — each carrying the agent identity, case/correlation identity, a causation
  link, a timestamp, and the outcome.
- **FR-015**: The audit trail MUST be queryable by the case's correlation identifier to reconstruct the
  full assessment — from request received to result published — in causal order.
- **FR-016**: The agent MUST NOT act as a supervisor, router, dispatcher, or orchestrator. It MUST only
  respond to fraud-risk assessment requests addressed to it, originate no task requests to other agents,
  and dispatch no work on behalf of other agents.
- **FR-017**: The agent MUST build on the existing shared A2A runtime and event foundation — reusing the
  runtime's capability-advertisement/discovery mechanism, the task-request/result contracts, the event
  envelope, the audit subsystem, and the idempotency mechanism — rather than introducing a parallel
  transport or a second audit path.
- **FR-018**: The agent MUST advertise its fraud-risk assessment capability via the shared
  capability-discovery mechanism so requesting peers can address it directly, with no central router
  selecting it on a requester's behalf.
- **FR-019**: The published result event MUST conform to the project's established risk result contract
  and topic so existing consumers (e.g., the customer resolution agent) can consume the real agent's
  output without contract changes, superseding the prior mock/stub risk behavior.

### Key Entities *(include if feature involves data)*

- **Fraud Risk Assessment Request**: The inbound A2A task request asking the agent to assess fraud risk
  for a specific case, carrying the case/correlation identity and the order/customer context needed to
  locate the relevant risk signals. The trigger for an assessment.
- **Account Standing**: The customer/account risk posture the agent owns — tenure, status, and standing
  flags — used to judge baseline risk.
- **Refund/Dispute History**: The customer's recorded history of prior refunds, disputes, and
  chargebacks the agent owns, used to judge repeat-abuse and velocity risk.
- **Payment-Instrument Signal**: Signals about the payment instrument the agent owns — e.g.,
  matched/mismatched billing details, instrument age, card-testing patterns — used to judge instrument
  risk.
- **Behavioral/Velocity Signal**: The customer's recent activity pattern the agent owns — request
  velocity and anomalies versus normal behavior — used to detect abuse bursts.
- **Known-Fraud Indicator**: A match against a maintained indicator/blocklist the agent owns (e.g.,
  flagged identifiers), used as a strong upward risk signal.
- **Fraud Policy**: The named, published set of fraud-risk rules (e.g., chargeback-history, refund-
  velocity, instrument-mismatch, known-indicator, account-standing rules) the agent applies; the
  assessment cites the specific rules as policy references.
- **Risk Assessment**: The agent's verdict for a case — a risk level (low, elevated, or high) and a
  requires-human-review flag — together with its confidence score, evidence set, policy references, and
  reasoning summary.
- **Risk Result Event**: The structured, published outcome of an assessment — the risk level, confidence,
  evidence, policy references, reasoning, and human-review flag — correlated to the originating case and
  observable on the shared event stream.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of accepted fraud-risk requests receive exactly one risk level drawn from the defined
  set (low, elevated, or high), with a human-review flag set as appropriate, demonstrated by a test suite
  over varied cases.
- **SC-002**: 100% of completed assessments publish exactly one structured result event carrying a risk
  level, a confidence score within its defined range, a non-empty evidence set, at least one policy
  reference, and a reasoning summary, each correlated to the originating case.
- **SC-003**: 100% of risk levels are traceable to the agent's owned risk/fraud signals and published
  policy, with no billing-eligibility or other-domain data used and no synchronous peer call made to
  obtain facts, demonstrated by an isolation test.
- **SC-004**: Across a matrix of cases differing by a single risk signal (chargeback history, refund
  velocity, instrument match, behavioral anomaly, known-fraud indicator), each risk level changes
  consistently with that signal, and the change is explained in the evidence, demonstrated by a
  parameterized test.
- **SC-005**: 100% of cases with missing, unresolvable, or contradictory risk signals resolve to a
  human-review flag or a failure result with a recorded reason — never a confident fabricated verdict —
  demonstrated by deliberate-fault tests.
- **SC-006**: Re-delivering an identical assessment request produces the same risk level and no duplicate
  result event in 100% of test runs, demonstrating idempotency.
- **SC-007**: A reviewer can reconstruct any case's full assessment — request received, decision with
  evidence and policy references, and published result — from the audit trail by correlation identifier
  in under 30 seconds using a single documented query.
- **SC-008**: A reviewer can confirm the agent originates no task requests to other agents and dispatches
  no work on behalf of others, demonstrated by inspecting its full set of interactions.
- **SC-009**: The existing customer resolution agent consumes the real risk agent's published result with
  no change to the risk result contract or topic, demonstrated by an end-to-end test exercising the prior
  feature against this agent.

## Assumptions

- **Builds on the `002-a2a-runtime-contract` runtime and `001-event-foundation`.** The agent is wrapped
  in the shared A2A runtime: it advertises its capability, is discovered by peers, and sends/receives
  task requests and results through the existing Kafka transport, reusing the event envelope, audit
  subsystem, idempotency tracker, and topic conventions as-is. This feature adds only the risk/fraud
  domain logic on top.
- **Replaces the existing mock `risk-fraud-agent`.** A demo stub already advertises the
  `assess_fraud_risk` capability and returns a fixed verdict (e.g., `{"risk": "low", "score": 0.1}`).
  This feature replaces that stub with the real domain agent producing the project's established canonical
  risk result contract (`RiskReviewCompletedPayload`: recommendation/level, confidence, evidence,
  policy references, reasoning summary, human-review flag); the prior consumer (customer resolution agent)
  already accepts that contract, so the stub branch can be retired without contract changes.
- **Risk level normalization stays compatible with the consumer.** The customer resolution agent
  normalizes risk results into `low | elevated | high` (with `requires_human_review` carried through).
  The real agent's risk level MUST map cleanly into that scheme so the decision policy is unchanged.
- **Owned risk data is local, seeded fixtures.** Account-standing, refund/dispute-history,
  payment-instrument, behavioral/velocity, and known-fraud-indicator data are represented by a local,
  in-process/seeded dataset owned by the agent (consistent with PoC scope). No real fraud system,
  database, or external risk service is integrated; the data is illustrative but sufficient to exercise
  every policy rule.
- **Fraud policy is a simple, illustrative PoC policy.** The fraud-policy rules (chargeback-history,
  refund-velocity, instrument-mismatch, known-indicator, account-standing, and similar) and their
  thresholds are demonstration values chosen to be auditable and to drive distinct outcomes — not
  production fraud policy. Exact rules and thresholds are finalized in planning and recorded as named,
  citable references.
- **Assessment may use the project's standard reasoning approach.** Mapping risk signals to a risk level
  is the agent's own domain judgment; whether it is purely rule-based or includes an LLM reasoning step
  consistent with the project's AI SDK constraints is finalized in planning and does not change the
  externally observable behavior specified here. Determinism for identical signals (FR-012) is required
  regardless of mechanism.
- **Confidence score is an illustrative, bounded measure.** Confidence is reported on a defined bounded
  scale; how it is computed is a planning detail. Its role here is to be present, within range, and
  lowered on uncertainty/contradiction.
- **One assessment capability in scope.** The agent owns the risk/fraud signal domains, but the only
  externally exposed A2A capability in this feature is fraud-risk assessment. Exposing additional
  risk/fraud query capabilities is out of scope for this feature.
- **Liveness and timeout handling are out of scope.** Detecting a requester that never consumes a
  result, or enforcing a response deadline, is deferred (consistent with the runtime feature). The agent
  responds when asked; it does not poll or chase requesters.
- **"Result event" is an emitted, correlated event**, not a synchronous reply or a real fraud-system side
  effect (no account is actually blocked or reported). Producing the auditable assessment and result
  event is in scope; taking a real anti-fraud action is owned by a different part of the workflow and is
  out of scope.
- **Single local environment.** The agent targets local developer workstations using the foundation's
  local infrastructure; production hardening (auth, scaling, HA) is out of scope per the constitution's
  PoC Scope Discipline principle.
