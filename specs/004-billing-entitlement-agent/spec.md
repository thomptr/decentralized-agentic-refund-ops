# Feature Specification: Billing and Entitlement Agent

**Feature Branch**: `004-billing-entitlement-agent`

**Created**: 2026-06-09

**Status**: Draft

**Input**: User description: "Build the Billing and Entitlement Agent. This independent agent owns subscription, invoice, payment, entitlement, and product usage analysis. It exposes an A2A capability to analyze refund eligibility and publishes structured Kafka result events with a recommendation, evidence, confidence score, and policy references."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Analyze Refund Eligibility on a Peer Request (Priority: P1)

As the billing-and-entitlement function, when a peer agent asks me to analyze whether a refund is
warranted for a specific case, I want to evaluate that case against the billing facts I own —
subscription state, invoices, payments, entitlements, and product usage — and return a clear
eligibility recommendation, so that the requesting agent receives a billing judgment from the agent
that actually owns billing data rather than guessing at it.

**Why this priority**: This is the agent's reason to exist and the front door for every other
behavior. Until the agent can accept an analysis request and return a recommendation, none of the
downstream evidence, result-event, or audit behavior is reachable. This slice proves the Billing and
Entitlement Agent stands up as an independent domain agent that owns the refund-eligibility judgment.

**Independent Test**: Send the agent a refund-eligibility analysis request for a case whose billing
facts clearly warrant a refund and confirm it returns a recommendation to approve; send a request for
a case whose billing facts clearly do not warrant a refund and confirm it returns a recommendation to
deny — each correlated to the originating request.

**Acceptance Scenarios**:

1. **Given** a refund-eligibility analysis request correlated to a case whose billing facts support a
   refund, **When** the agent analyzes it, **Then** the agent returns a recommendation to approve the
   refund, correlated to the originating request.
2. **Given** a refund-eligibility analysis request for a case whose billing facts do not support a
   refund, **When** the agent analyzes it, **Then** the agent returns a recommendation to deny the
   refund, correlated to the originating request.
3. **Given** any analysis request the agent accepts, **When** analysis completes, **Then** the result
   is correlated to the originating request and is consumable by the requesting peer without any
   back-channel to this agent.

---

### User Story 2 - Publish a Structured Billing Result Event (Priority: P1)

As the billing-and-entitlement function, when I complete an analysis, I want to publish a structured
result event carrying my recommendation, the evidence behind it, a confidence score, and the policy
references I applied, so that any interested agent or reviewer receives a self-describing, auditable
billing verdict without having to ask me how I reached it.

**Why this priority**: A bare approve/deny verdict is not enough for a decentralized, auditable
system — the consuming agents and reviewers need the supporting evidence and confidence to act on and
to trust the verdict. This slice turns the analysis from User Story 1 into the structured, observable
artifact the demo depends on.

**Independent Test**: Drive one analysis end to end and confirm exactly one structured result event is
published for it, carrying the recommendation, a non-empty evidence set, a confidence score within its
defined range, the policy references applied, and a human-readable reasoning summary — all correlated
to the originating case/request.

**Acceptance Scenarios**:

1. **Given** a completed analysis, **When** the result is published, **Then** the result event
   contains a recommendation, a confidence score within its defined range, an evidence set, the policy
   references applied, and a reasoning summary, correlated to the originating case.
2. **Given** a completed analysis, **When** the result event is inspected, **Then** every evidence item
   names its source and what it shows, and the policy references identify the specific billing/refund
   rules the recommendation rests on.
3. **Given** a completed analysis, **When** the result is delivered, **Then** the structured verdict is
   both returned to the requesting peer (correlated to its request) and published as a billing result
   event observable on the shared event stream.

---

### User Story 3 - Ground Every Recommendation in Owned Billing & Entitlement Data (Priority: P1)

As the billing-and-entitlement function, I want every recommendation to be derived solely from the
billing facts I own — subscription, invoice, payment, entitlement, and product-usage data — and to
cite that data as evidence, so that the verdict is genuinely a billing judgment and the agent never
substitutes risk, fraud, or customer-relationship reasoning that belongs to other agents.

**Why this priority**: Strict domain ownership is a constitutional guardrail and the basis for trust
in the verdict. A billing agent whose recommendation cannot be traced to billing facts — or that
reaches into another domain — collapses the separation the decentralized demo is meant to prove. This
slice fixes what "owns billing" concretely means for every recommendation.

**Independent Test**: For a set of cases with differing billing facts (within refund window vs.
expired, paid vs. unpaid invoice, active vs. lapsed entitlement, light vs. heavy product usage),
confirm each recommendation changes in line with those facts and that every evidence item and policy
reference traces back to one of the owned billing/entitlement data domains — with no risk/fraud or
unrelated data used.

**Acceptance Scenarios**:

1. **Given** two cases identical except for one billing fact (e.g., one inside the refund window and
   one outside it), **When** each is analyzed, **Then** the recommendations differ in a way explained
   by that fact, and the evidence cites it.
2. **Given** any recommendation, **When** its inputs are traced, **Then** every evidence item and
   policy reference originates from the agent's owned billing/entitlement data (subscription, invoice,
   payment, entitlement, or product usage) and from its published refund policy — never from a risk,
   fraud, or other agent's domain.
3. **Given** a case, **When** the agent analyzes it, **Then** the agent reads only its own billing/
   entitlement data sources and makes no synchronous call to any other agent to obtain facts.

---

### User Story 4 - Handle Cases It Cannot Confidently Decide (Priority: P2)

As the billing-and-entitlement function, when a case is missing the billing data I need, is internally
contradictory, or otherwise cannot be confidently decided from the facts I own, I want to flag it for
human review (or report a failure) with a recorded reason instead of inventing an eligibility verdict,
so that uncertainty surfaces honestly rather than producing a false approve/deny.

**Why this priority**: A confident-sounding but unfounded verdict is worse than an honest "needs
review." This guardrail keeps the agent trustworthy and gives the requesting workflow a safe path when
billing facts are insufficient. It builds on User Stories 1–3, which establish the normal verdict path.

**Independent Test**: Send the agent a request for a case whose billing data is missing or
contradictory and confirm it does not emit a confident approve/deny, instead flagging the result as
requiring human review (or returning a failure result) with a recorded reason; confirm a well-formed
case still returns a normal recommendation.

**Acceptance Scenarios**:

1. **Given** a request for a case whose required billing facts are missing or unresolvable, **When** the
   agent analyzes it, **Then** the agent does not fabricate an eligibility verdict; it returns a result
   flagged as requiring human review with a recorded reason, or a failure result when it cannot analyze
   at all.
2. **Given** a case with contradictory billing facts, **When** the agent analyzes it, **Then** the
   recommendation is accompanied by a lowered/uncertain confidence and a human-review flag, with the
   conflict captured in the evidence and reasoning.
3. **Given** a request the agent cannot process (malformed or unanalyzable input), **When** it is
   received, **Then** the agent returns a failure result with a reason rather than a fabricated
   recommendation, and the failure is observable in the audit trail.

---

### User Story 5 - Idempotent, Repeatable Analysis (Priority: P2)

As a reviewer of the PoC, I want re-delivery of the same analysis request to produce the same
recommendation and no duplicate result events, so that the billing verdict is stable and the workflow
is safe to replay.

**Why this priority**: Idempotency is a constitutional requirement and is what makes the
event-driven, at-least-once delivery model safe. Without it, a redelivered request could emit
contradictory or duplicated billing verdicts. It builds on the verdict path from User Stories 1–2.

**Independent Test**: Send the same analysis request twice and confirm the agent produces one logical
result (the same recommendation, evidence, and confidence) and does not publish a second, duplicate or
contradictory result event; confirm the duplicate is recorded in the audit trail.

**Acceptance Scenarios**:

1. **Given** an analysis request the agent has already processed, **When** the identical request is
   delivered again, **Then** the agent does not perform a second independent analysis that could yield a
   different verdict and does not publish a duplicate result event.
2. **Given** a redelivered request, **When** it is handled, **Then** the duplication is recorded in the
   audit trail, and any consumer sees a single, consistent billing verdict for that case.
3. **Given** identical billing facts for a case, **When** the case is analyzed, **Then** the
   recommendation is deterministic — the same facts and the same policy yield the same verdict.

---

### User Story 6 - Audit Every Analysis (Priority: P2)

As a reviewer evaluating the PoC, I want every step the billing agent takes — request received,
analysis performed (with the evidence and policy references it used), result published, and any
failure or human-review flag — to leave an immutable, correlated audit trail, so I can reconstruct how
a billing verdict was reached without reading the agent's code.

**Why this priority**: Observability is a constitutional requirement and the primary evidence that the
billing verdict is accountable. It builds on the prior stories, which produce the steps being audited.

**Independent Test**: Drive an analysis end to end, then query the audit trail by the case's
correlation identifier and confirm the received request, the analysis decision (with evidence and
policy references), and the published result are all present, attributed to the billing agent, and in
causal order.

**Acceptance Scenarios**:

1. **Given** a completed analysis, **When** the audit trail is queried by the case's correlation
   identifier, **Then** every step the billing agent performed is returned with its outcome, the
   agent's identity, a timestamp, and the causal link to its triggering request.
2. **Given** a case flagged for human review or returned as a failure, **When** the audit trail is
   queried, **Then** the reason (missing data, contradiction, or unanalyzable input) is recoverable
   from the trail.

---

### User Story 7 - Stay an Independent Domain Agent (Priority: P3)

As a project reviewer guarding against hidden coupling, I want to confirm the billing agent only
performs the billing/entitlement analyses requested of it and never supervises, routes, or dispatches
work for other agents — nor calls another agent to do its analysis — so the system remains genuinely
decentralized rather than hub-and-spoke.

**Why this priority**: This is an acceptance guardrail rather than new capability. It can be verified
once the prior stories establish exactly what the agent does and does not do.

**Independent Test**: Inspect the agent's behavior across several analysis requests and confirm it only
ever responds to refund-eligibility analysis requests addressed to it, issues no task requests of its
own to other agents, and dispatches no work on behalf of anyone else.

**Acceptance Scenarios**:

1. **Given** the agent's full set of interactions, **When** they are inspected, **Then** each is a
   refund-eligibility analysis the agent performed in response to a request addressed to it; the agent
   originates no task requests to other agents and routes no work between them.
2. **Given** the running system, **When** task flow is traced, **Then** no other agent depends on the
   billing agent to dispatch or coordinate their work, and the billing agent obtains its billing facts
   only from its own data, not from peer calls.

---

### Edge Cases

- **Missing billing data**: When the case references a subscription, invoice, or customer the agent has
  no billing record for, the agent MUST NOT default to a confident verdict; it flags human review (or
  returns a failure) with a recorded reason (US4).
- **Contradictory facts**: When billing facts conflict (e.g., a paid invoice with a recorded full
  reversal, or an active entitlement on a cancelled subscription), the agent MUST lower confidence and
  flag human review rather than silently picking one side (US4).
- **Borderline within policy thresholds**: A case sitting exactly on a policy boundary (e.g., the last
  day of the refund window, or usage exactly at a threshold) MUST resolve to a defined, documented side
  of the boundary, recorded in the reasoning — never left undecided.
- **Duplicate / redelivered request**: An identical analysis request delivered more than once MUST
  yield a single logical verdict and no duplicate result event; the duplication is recorded (US5).
- **Unanalyzable / malformed request**: A request the agent cannot interpret MUST produce a failure
  result with a reason, not a fabricated recommendation (US4).
- **No applicable policy**: When no published refund policy rule applies to a case, the agent MUST take
  a defined default stance (flag for human review with that stated reason) rather than approving by
  omission.
- **Heavy product usage vs. refund**: Where product usage materially weakens a refund claim, that usage
  MUST appear as evidence influencing the recommendation, not be silently ignored.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The agent MUST be an independent domain agent dedicated solely to billing and entitlement
  analysis, exposing its own addressable A2A endpoint on the shared runtime and owning no
  customer-resolution or risk/fraud logic.
- **FR-002**: The agent MUST expose a single A2A capability to analyze refund eligibility, accepting an
  analysis request correlated to a specific case and returning a structured recommendation.
- **FR-003**: The agent MUST own and analyze billing facts across five data domains — subscription,
  invoice, payment, entitlement, and product usage — and MUST derive every recommendation solely from
  those owned facts and its published refund policy.
- **FR-004**: The agent MUST produce a refund-eligibility recommendation for each accepted request,
  drawn from a defined set of outcomes (at minimum: approve refund, deny refund, and a flag that the
  case requires human review).
- **FR-005**: Every recommendation MUST be accompanied by an evidence set in which each item names its
  source (which billing/entitlement fact) and what it shows, and by the policy references identifying
  the specific refund-policy rules the recommendation rests on.
- **FR-006**: Every recommendation MUST carry a confidence score within a defined range and a
  human-readable reasoning summary explaining how the evidence and policy led to the recommendation.
- **FR-007**: The agent MUST publish a structured billing result event for each completed analysis,
  carrying the recommendation, confidence score, evidence set, policy references, reasoning summary, and
  human-review flag, correlated to the originating case/request.
- **FR-008**: The structured analysis result MUST be both returned to the requesting peer correlated to
  its request (so the requester can consume it by correlation) and published as a billing result event
  observable on the shared event stream.
- **FR-009**: The agent MUST NOT access or rely on any data outside its owned billing/entitlement
  domains (e.g., risk/fraud signals, other agents' internal state); it MUST NOT make synchronous calls
  to other agents to obtain the facts behind its recommendation.
- **FR-010**: When required billing data is missing, unresolvable, or contradictory, the agent MUST NOT
  fabricate an eligibility verdict; it MUST flag the result as requiring human review with a recorded
  reason, or return a failure result when it cannot analyze the case at all.
- **FR-011**: When the agent cannot interpret or process a request (malformed/unanalyzable input), it
  MUST return a failure result carrying a reason rather than a fabricated recommendation.
- **FR-012**: The agent MUST apply a defined, auditable refund policy: the mapping from billing facts to
  a recommendation MUST be deterministic and reproducible, so identical facts under the same policy
  yield the same verdict.
- **FR-013**: Analysis MUST be idempotent by request identity: re-delivery of the same analysis request
  MUST NOT produce a second independent analysis or a duplicate result event; the agent MUST track
  processed request identities and record duplicates in the audit trail.
- **FR-014**: The agent MUST emit a structured audit event for each significant step — request received,
  analysis decision (including the evidence and policy references used), result published, and any
  failure or human-review flag — each carrying the agent identity, case/correlation identity, a
  causation link, a timestamp, and the outcome.
- **FR-015**: The audit trail MUST be queryable by the case's correlation identifier to reconstruct the
  full analysis — from request received to result published — in causal order.
- **FR-016**: The agent MUST NOT act as a supervisor, router, dispatcher, or orchestrator. It MUST only
  respond to refund-eligibility analysis requests addressed to it, originate no task requests to other
  agents, and dispatch no work on behalf of other agents.
- **FR-017**: The agent MUST build on the existing shared A2A runtime and event foundation — reusing the
  runtime's capability-advertisement/discovery mechanism, the task-request/result contracts, the event
  envelope, the audit subsystem, and the idempotency mechanism — rather than introducing a parallel
  transport or a second audit path.
- **FR-018**: The agent MUST advertise its refund-eligibility capability via the shared
  capability-discovery mechanism so requesting peers can address it directly, with no central router
  selecting it on a requester's behalf.
- **FR-019**: The published result event MUST conform to the project's established billing result
  contract and topic so existing consumers (e.g., the customer resolution agent) can consume the real
  agent's output without contract changes, superseding the prior mock/stub billing behavior.

### Key Entities *(include if feature involves data)*

- **Refund Eligibility Analysis Request**: The inbound A2A task request asking the agent to assess
  refund eligibility for a specific case, carrying the case/correlation identity and the order/charge
  context needed to locate the relevant billing facts. The trigger for an analysis.
- **Subscription**: The customer's plan state the agent owns — status (active, cancelled, lapsed),
  term, and start/renewal dates — used to judge eligibility.
- **Invoice**: A billed charge the agent owns — amount, currency, issue date, and paid/unpaid state —
  the subject of a refund claim.
- **Payment**: A recorded payment or reversal against an invoice the agent owns, used to confirm what
  was actually charged and whether any refund already occurred.
- **Entitlement**: What the customer is entitled to under their subscription/plan, used to judge whether
  the disputed charge corresponds to delivered value.
- **Product Usage**: The customer's recorded consumption of the product/service, used as a factor in
  whether a refund is warranted (e.g., substantial usage weakening the claim).
- **Refund Policy**: The named, published set of refund rules (e.g., refund-window, paid-invoice,
  entitlement-delivered, usage-threshold rules) the agent applies; the recommendation cites the specific
  rules as policy references.
- **Eligibility Recommendation**: The agent's verdict for a case — approve refund, deny refund, or
  requires human review — together with its confidence score, evidence set, policy references, and
  reasoning summary.
- **Billing Result Event**: The structured, published outcome of an analysis — the recommendation,
  confidence, evidence, policy references, reasoning, and human-review flag — correlated to the
  originating case and observable on the shared event stream.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of accepted refund-eligibility requests receive exactly one recommendation drawn from
  the defined outcome set (approve, deny, or requires human review), demonstrated by a test suite over
  varied cases.
- **SC-002**: 100% of completed analyses publish exactly one structured result event carrying a
  recommendation, a confidence score within its defined range, a non-empty evidence set, at least one
  policy reference, and a reasoning summary, each correlated to the originating case.
- **SC-003**: 100% of recommendations are traceable to the agent's owned billing/entitlement data and
  published policy, with no risk/fraud or other-domain data used and no synchronous peer call made to
  obtain facts, demonstrated by an isolation test.
- **SC-004**: Across a matrix of cases differing by a single billing fact (refund window, invoice paid
  state, entitlement state, product usage), each recommendation changes consistently with that fact, and
  the change is explained in the evidence, demonstrated by a parameterized test.
- **SC-005**: 100% of cases with missing, unresolvable, or contradictory billing data resolve to a
  human-review flag or a failure result with a recorded reason — never a confident fabricated verdict —
  demonstrated by deliberate-fault tests.
- **SC-006**: Re-delivering an identical analysis request produces the same recommendation and no
  duplicate result event in 100% of test runs, demonstrating idempotency.
- **SC-007**: A reviewer can reconstruct any case's full analysis — request received, decision with
  evidence and policy references, and published result — from the audit trail by correlation identifier
  in under 30 seconds using a single documented query.
- **SC-008**: A reviewer can confirm the agent originates no task requests to other agents and
  dispatches no work on behalf of others, demonstrated by inspecting its full set of interactions.
- **SC-009**: The existing customer resolution agent consumes the real billing agent's published result
  with no change to the billing result contract or topic, demonstrated by an end-to-end test exercising
  the prior feature against this agent.

## Assumptions

- **Builds on the `002-a2a-runtime-contract` runtime and `001-event-foundation`.** The agent is wrapped
  in the shared A2A runtime: it advertises its capability, is discovered by peers, and sends/receives
  task requests and results through the existing Kafka transport, reusing the event envelope, audit
  subsystem, idempotency tracker, and topic conventions as-is. This feature adds only the
  billing/entitlement domain logic on top.
- **Replaces the existing mock `billing-entitlement-agent`.** A demo stub already advertises the
  refund-eligibility capability and returns a fixed verdict. This feature replaces that stub with the
  real domain agent producing the project's established canonical billing result contract; the prior
  consumer (customer resolution agent) already accepts that contract, so the stub branch can be retired
  without contract changes.
- **Owned billing data is local, seeded fixtures.** Subscription, invoice, payment, entitlement, and
  product-usage data are represented by a local, in-process/seeded dataset owned by the agent
  (consistent with PoC scope). No real billing system, database, or external billing service is
  integrated; the data is illustrative but sufficient to exercise every policy rule.
- **Refund policy is a simple, illustrative PoC policy.** The refund-policy rules (refund window,
  paid-invoice, entitlement-delivered, usage-threshold, and similar) and their thresholds are
  demonstration values chosen to be auditable and to drive distinct outcomes — not production refund
  policy. Exact rules and thresholds are finalized in planning and recorded as named, citable references.
- **Analysis may use the project's standard reasoning approach.** Mapping billing facts to a
  recommendation is the agent's own domain judgment; whether it is purely rule-based or includes an LLM
  reasoning step consistent with the project's AI SDK constraints is finalized in planning and does not
  change the externally observable behavior specified here. Determinism for identical facts (FR-012) is
  required regardless of mechanism.
- **Confidence score is an illustrative, bounded measure.** Confidence is reported on a defined bounded
  scale; how it is computed is a planning detail. Its role here is to be present, within range, and
  lowered on uncertainty/contradiction.
- **One analysis capability in scope.** The agent owns the five billing data domains, but the only
  externally exposed A2A capability in this feature is refund-eligibility analysis. Exposing additional
  billing/entitlement query capabilities is out of scope for this feature.
- **Liveness and timeout handling are out of scope.** Detecting a requester that never consumes a
  result, or enforcing a response deadline, is deferred (consistent with the runtime feature). The agent
  responds when asked; it does not poll or chase requesters.
- **"Result event" is an emitted, correlated event**, not a synchronous reply or a real billing-system
  side effect (no actual money is moved). Producing the auditable recommendation and result event is in
  scope; executing a real refund is owned by a different part of the workflow and is out of scope.
- **Single local environment.** The agent targets local developer workstations using the foundation's
  local infrastructure; production hardening (auth, scaling, HA) is out of scope per the constitution's
  PoC Scope Discipline principle.
