# Contract: End-to-End Choreography Topology (006)

This is the **wiring contract** for the decentralized workflow. It introduces no new topics or payloads;
it pins down which existing topic carries which step, who emits and who consumes, and the
correlation/causation rules that make the flow auditable. Topic names resolve via
`packages/contracts/topics.py` with `AGENT_ENVIRONMENT` (default `local`).

## Participants (all existing, no new agent — FR-021, Principle I)
- **Dev intake** (`apps/api/dev_publish_ticket.py`) — publishes the root ticket. Not an agent/router.
- **Customer Resolution Agent** (`customer-resolution-agent`) — triage, delegation, aggregation,
  decision, **timeout reaper** (its own cases only).
- **Billing Entitlement Agent** (`billing-entitlement-agent`) — `analyze_refund_eligibility`.
- **Risk & Fraud Agent** (`risk-fraud-agent`) — `assess_fraud_risk`.

## Event flow (happy refund path)

| # | Topic (constant) | Emitter | Consumer(s) | correlation_id | causation_id |
|---|---|---|---|---|---|
| 1 | `local.support.ticket.created.v1` (`topic_for("support","ticket","created")`) | dev intake | resolution intake loop | **new case id** | `null` (root) |
| 2 | `local.resolution.customer-issue.classified.v1` (`TOPIC_ISSUE_CLASSIFIED`) | resolution | (observability) | case id | ticket event |
| 3 | `local.agent.billing-entitlement-agent.task.requested.v1` (`endpoint_topic(billing)`) | resolution | billing runtime | case id | ticket event |
| 3'| `local.agent.risk-fraud-agent.task.requested.v1` (`endpoint_topic(risk)`) | resolution | risk runtime | case id | ticket event |
| 4 | `local.resolution.refund-review.requested.v1` (`TOPIC_REFUND_REVIEW_REQUESTED`) | resolution | (observability) | case id | ticket event |
| 5 | `local.billing.refund-analysis.completed.v1` (`TOPIC_BILLING_RESULT`) | billing | resolution billing-results loop | case id | billing `task_id` |
| 5'| `local.risk.review.completed.v1` (`TOPIC_RISK_RESULT`) | risk | resolution risk-results loop | case id | risk `task_id` |
| 5"| `local.agent.task.result.v1` (`TOPIC_TASK_RESULT`) | billing & risk runtimes | resolution results loop | case id | respective `task_id` |
| 6 | `local.customer.resolution.decided.v1` (`TOPIC_RESOLUTION_DECIDED`) | resolution | (observability) | case id | the result/timeout that triggered decision |
| 7 | `local.resolution.customer-response.drafted.v1` (`TOPIC_RESPONSE_DRAFTED`) | resolution | (observability) | case id | the decided event |
| A | `local.audit.envelope.recorded.v1` (`TOPIC_AUDIT`) | every agent, every step | trace tool | case id | the audited event |

The decided + drafted events (and the classified/review-requested markers) are the **case lifecycle
events** the spec asks for; no separate lifecycle topic is added (Principle V).

## Correlation & causation rules (FR-005, FR-006, FR-007)
- The ticket's `correlation_id` is minted at intake and **propagated unchanged** to every downstream
  event for the case (envelope invariant; receivers never re-key).
- Every non-root event sets `causation_id` to the `event_id` (or `task_id`) of the event that triggered
  it, forming a single causation DAG per case.
- An opinion result is attributable to its case by **`task_id`** (A2A `TaskResult`) and by
  **`correlation_id`** (domain result events). `task_id = uuid5(correlation_id, capability)` is stable.

## Non-refund path
Steps 1–2 then a `direct_response` decision (step 6) + drafted (step 7); billing/risk are **not** invoked
(FR-002). Case closes.

## Decentralization invariants (FR-021, asserted in tests)
- No participant consumes another agent's endpoint topic to *direct* it; the only cross-agent messages
  are the resolution agent's A2A task requests (peer delegation) and the peers' own result publishes.
- The reaper, replay harness, and trace tool issue **no** task requests and **no** directives.
- Existing guards `apps/agents/customer_resolution/tests/test_no_supervisor.py` and
  `tests/integration/test_no_router.py` remain green.
