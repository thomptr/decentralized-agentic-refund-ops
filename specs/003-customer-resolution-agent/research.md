# Phase 0 Research: Customer Resolution Agent

All NEEDS CLARIFICATION items from Technical Context are resolved below. Each decision is grounded in
the existing `001-event-foundation` / `002-a2a-runtime-contract` code, the spec's assumptions, and
the constitution (esp. Principle V, PoC Scope Discipline).

---

## R1 — Triage & decision reasoning mechanism

**Decision**: Use **deterministic, rule-based** triage and decision logic. No LLM / Bedrock /
`boto3` is added in this feature.

**Rationale**:
- The codebase currently has **zero** Bedrock/`boto3` usage; all demo agents are mock/deterministic.
  Introducing an AWS SDK + credentials + prompt-caching plumbing to classify a ticket would be a
  large, untestable-locally addition that does not move the PoC hypothesis (decentralized,
  event-driven, auditable coordination) — exactly the kind of premature complexity Principle V
  defers.
- The user directive for this plan explicitly requires "classify customer refund-related tickets"
  and "apply **deterministic** decision rules."
- The spec's edge-case table demands *defined, deterministic* behavior (ambiguous → default to
  refund review; conflict → escalate; missing analysis → keep open). Deterministic rules make every
  acceptance scenario (SC-001…SC-008) reproducible in a test suite, which an LLM step would
  undermine.
- The spec Assumption explicitly allows "rule-based **and/or** an LLM reasoning step" and states the
  mechanism "does not change the externally observable behavior specified here."

**Triage rule (refund vs direct response)**: classify the ticket's `reason` (and message text) by
keyword/intent against a refund-intent vocabulary (e.g. *refund, charged, charge, double-charged,
overcharge, dispute, money back, reimburse, cancel … and bill*). Match → "refund review required";
clear non-refund (e.g. "how do I change my email") → "direct response"; **ambiguous/empty → default
to refund review required** and record the ambiguity in the rationale (spec edge case).

**Alternatives considered**:
- *Bedrock LLM triage with prompt caching* (constitution Technology Constraints names Bedrock as the
  AI SDK) — **deferred**, not rejected forever. Recorded here so a later feature can swap the triage
  function for an LLM call behind the same interface (`triage.py:classify(ticket) -> Triage`) without
  changing any event contract or downstream behavior. The seam is intentionally preserved.

---

## R2 — Delegation model: how the agent sends the two analysis requests

**Decision**: Send each analysis request as an A2A **`TaskRequest`** published to the **peer's
endpoint topic** (`endpoint_topic(target_agent_id)`) via the foundation `Publisher.publish(...,
topic=...)` (the validated dynamic-topic hook added in 002). The agent does **not** await the result
inline; results return asynchronously on the shared result topic (R3).

**Rationale**:
- FR-004 requires the runtime's task-request contract; FR-016 forbids a parallel transport; FR-017
  requires addressing peers' published endpoints **directly** (no router). Publishing a `TaskRequest`
  to the peer's endpoint topic is exactly the runtime's peer-to-peer mechanism — the same one
  `A2AClient.submit()` uses internally for the request leg.
- Using the request leg **without** `A2AClient.submit()`'s built-in await is what lets the agent
  keep one case open across two independent results (FR-008) and tolerate late results (FR-012).
- Both requests share the case's `correlation_id`, with `causation_id` set to the triggering ticket
  event — preserving the causal chain for audit (FR-013/FR-014).

**Peer discovery**: resolve the billing and risk **target agent IDs / endpoints** at delegation time
via `agent_foundation.runtime.discovery.find_capable(capability_id)` over the compacted agent-card
topic (FR-017) — capabilities `analyze_refund_eligibility` (billing) and `assess_fraud_risk` (risk),
as published by the existing demo stubs. No central registry; no router selects the target.

**Alternatives considered**:
- *Two concurrent `A2AClient.submit()` calls under `asyncio.gather`* — **rejected**: each `submit`
  blocks on its own result and embeds result-handling inside the client, so "case open pending the
  second result," "late result after decision," and "exactly one decision" become awkward timeouts
  rather than first-class case state. It also couples the case lifetime to a live coroutine with no
  durability seam.
- *A new domain `refund.review.requested` event per delegation* — **rejected**: FR-016 says reuse the
  runtime's task-request/result contracts rather than introduce a parallel domain path. The existing
  `RefundReviewRequestedPayload` stays available for future use but is **not** the delegation channel
  here; the `TaskRequest` is.

---

## R3 — Result aggregation & correlation

**Decision**: Run a dedicated `Consumer` on the shared **`TOPIC_TASK_RESULT`** topic. Correlate each
incoming `TaskResult` to a case by **`task_id`** (the agent recorded the billing and risk `task_id`
on the case at delegation time). Store the result on the case; when **both** slots are filled — or a
failure/rejection forces an escalation — apply the decision policy and emit the final decision.

**Rationale**:
- FR-006 requires consuming analysis **result events from Kafka** and correlating them to the case;
  the runtime returns results as `TaskResult` on the shared result topic. Correlating by `task_id` is
  robust and exactly how the runtime guarantees request↔result identity.
- The envelope **`correlation_id`** is the **case key** and the audit query key (FR-014); `task_id`
  is the **result-to-slot** key. Using both avoids any dependence on a peer echoing domain fields.
- Completeness rule (FR-008): a final decision is emitted only when **both** required slots are
  resolved, except when a peer failure/rejection forces an immediate escalation (US3-3, edge case
  "peer failure or rejection").

**Result contract the agent reads**: the agent treats each peer result's `A2AMessage` data part as a
**billing analysis** / **risk analysis** payload conforming to the existing
`BillingRefundAnalysisCompletedPayload` / `RiskReviewCompletedPayload` shapes
(`recommendation`, `confidence`, `requires_human_review`, `evidence`, `reasoning_summary`). The demo
stubs currently emit simpler `{eligible, reason}` / `{risk, score}` data; the agent reads a small
**adapter** mapping both the rich contract and the stub shapes to its internal `BillingFinding` /
`RiskFinding` (see `contracts/analysis-result-contract.md`). This keeps the resolution agent coupled
only to the peers' *published result contract*, not their internals (US5-2).

**Alternatives considered**:
- *Correlate by `correlation_id` only* — **rejected**: a single case issues two requests sharing one
  `correlation_id`; `task_id` is needed to tell the billing result from the risk result.

---

## R4 — Deterministic decision policy

**Decision**: A pure function `decide(triage, billing, risk) -> Decision` producing one of
`approve_refund`, `deny_refund`, `escalate_human` (refund cases) or `direct_response` (non-refund
triage). Full truth table in `contracts/decision-policy.md`. Summary:

| Condition | Outcome |
|-----------|---------|
| Triage = non-refund | `direct_response` |
| Any required peer **failed/rejected** (or result unavailable at decision time) | `escalate_human` (reason: peer failure/rejection) |
| Either finding sets `requires_human_review` | `escalate_human` (reason: peer requested review) |
| Risk **elevated/high** | `escalate_human` (reason: elevated risk) |
| Billing **ineligible / recommends deny** | `deny_refund` |
| Billing **eligible / recommends approve** AND risk **acceptable/low** | `approve_refund` |
| Conflicting findings not covered above | `escalate_human` (reason: conflicting analyses) |

**Rationale**: FR-009 mandates a defined, auditable policy derived **only** from consumed results +
ticket content. Escalation precedence (failure → human-review flag → elevated risk → conflict)
guarantees every case resolves to exactly one outcome (SC-003, FR-010) and that all fault paths land
on human escalation with a recorded reason (SC-007). Thresholds are illustrative PoC values (spec
Assumption), centralized in `decision.py` constants so they are easy to read and adjust.

**Alternatives considered**: weighting `confidence` into a score — **deferred**; the spec's
illustrative policy is categorical, and a score adds tuning surface with no PoC benefit.

---

## R5 — Idempotency by ticket identity

**Decision**: Two layers. (a) **Domain idempotency by ticket identity**: the `CaseStore` is keyed by
`correlation_id` (one case per ticket). A re-delivered ticket finds an existing case → **no** second
delegation, **no** second decision; the duplicate is recorded in audit as `duplicate` (FR-011). (b)
**Event-level dedup**: each `Consumer` reuses the foundation `IdempotencyTracker` (keyed by envelope
`event_id`) so exact event re-delivery is skipped before the handler runs.

**Rationale**: FR-011 requires idempotency by **ticket identity**, which the per-correlation case is
the natural home for; the `IdempotencyTracker` (keyed by UUID `event_id`) handles transport-level
redelivery but not "same ticket, new event_id." Both together satisfy the constitution's Idempotency
& Safety principle and SC-005.

**Note on ticket-id vs correlation-id**: the demo publishes one `support.ticket.created` event whose
`correlation_id` is the case identity and whose payload `ticket_id` is the business key. The case is
keyed by `correlation_id`; the `ticket_id` is recorded for human-readable audit and as a secondary
guard if two distinct events carry the same `ticket_id` (treated as the same case).

---

## R6 — Resolution-case state durability

**Decision**: Keep `ResolutionCase` state in an **in-process store** (a dict keyed by
`correlation_id`) for this PoC. Persisting/replaying case state from a compacted Kafka topic is
**deferred** and documented as a known gap.

**Rationale**: The spec scopes this to a "single local environment," defers liveness/timeout, and
states an unanswered case simply "stays open." Constitution Principle V prefers the simpler approach
when both prove the hypothesis. The full **audit trail** (intake, triage, both delegations, both
results, decision) is already durable on the compacted audit topic and queryable by `correlation_id`,
so accountability (the constitutional requirement) does not depend on in-process state.

**Documented gap**: a process restart loses open (undecided) cases' in-memory state. Recovery would
require replaying `support.ticket.created` + `task.result` or persisting cases to a compacted
`customer.resolution.case` topic — recorded here as the future durability path, consistent with the
runtime feature's deferred-liveness stance.

**Alternatives considered**: compacted case-state topic now — **rejected** for PoC scope; adds a
topic and replay logic with no hypothesis benefit while audit already provides reconstruction.

---

## R7 — Endpoint exposure vs event-trigger (FR-001)

**Decision**: The agent **publishes its `AgentCard` and exposes a runtime endpoint** (so it is a
discoverable, addressable participant — FR-001) **and** is primarily **triggered by
`support.ticket.created` Kafka events**. The `AgentRuntime`, the intake consumer, and the result
consumer run concurrently in one process via `asyncio.gather`, sharing the `CaseStore`.

**Rationale**: FR-001 requires an addressable A2A endpoint; the spec's primary intake is a Kafka
ticket event, not an inbound A2A task. Running the runtime (for card/endpoint/discoverability)
alongside the two domain consumers satisfies both without making the agent a router. The endpoint can
host a nominal `customer_resolution` capability for manual/alternate triggering, but the ticket topic
is the demo's front door.

**Alternatives considered**: expose **only** an A2A capability and have a dev tool submit tasks —
**rejected**: the spec's intake is explicitly `support.ticket.created` events from Kafka (FR-002,
US1); a Kafka consumer is the faithful front door. Run **only** consumers and skip the card —
**rejected**: violates FR-001's addressable-endpoint requirement and weakens discoverability.

---

## R8 — Final decision as an emitted, correlated event

**Decision**: Emit the outcome as a new domain event **`customer.resolution.decided.v1`**
(`CustomerResponseDecisionPayload`) on its own topic, registered in the foundation `PAYLOAD_REGISTRY`
exactly as `support.ticket.created.v1` is. It carries the outcome, a customer-facing response draft,
the rationale, the contributing billing/risk findings (for traceability), and the escalation reason
when applicable.

**Rationale**: The spec Assumption states the "final customer response decision" is "an emitted,
correlated decision **event**, not a synchronous reply." Delivering to a real customer surface
(email/portal) is out of scope; producing the auditable, correlated decision event is in scope
(FR-007). A dedicated event keeps the decision queryable and consumable (e.g. by `dev_consume_events`)
distinct from the audit trail. This is the **only** new contract the feature introduces.

**Alternatives considered**: reuse the audit event as the decision channel — **rejected**: the audit
trail records *steps*; the decision is a *domain outcome* other consumers may act on, and conflating
them muddies both. Adding a separate `triage.determined` event — **rejected** as unnecessary; triage
is captured on the case and in the audit trail (FR-003/FR-013) without its own domain topic.
