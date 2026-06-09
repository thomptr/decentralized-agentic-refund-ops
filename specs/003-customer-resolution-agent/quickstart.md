# Quickstart: Customer Resolution Agent

Runnable validation scenarios proving the feature end-to-end. Implementation details live in
`tasks.md`; contract details in `contracts/` and `data-model.md`.

## Prerequisites

- Python 3.12, `uv`, Docker (single-broker Kafka from the foundation).
- Repo synced: `uv sync --extra dev`.
- Start Kafka and verify:
  ```bash
  docker compose -f infra/local/docker-compose.yml up -d
  python -m agent_foundation health      # expect: broker reachable
  ```
- Topics provisioned (includes the new `local.customer.resolution.decided.v1`):
  ```bash
  agent-foundation create-topics         # or the project's documented topic-creation entrypoint
  ```

## Start the three demo agents

In separate terminals (all read `AGENT_BROKER_URL`, default `localhost:9092`):

```bash
demo-billing-entitlement      # billing peer (capability: analyze_refund_eligibility)
demo-risk-fraud               # risk peer    (capability: assess_fraud_risk)
demo-customer-resolution      # the agent under test
```

Confirm all three published cards (no router involved):

```bash
python -m apps.agents.discover            # lists 3 agents + capabilities
```

Observe events while testing:

```bash
python -m apps.api.dev_consume_events     # prints audit + decision envelopes
```

---

## Scenario 1 — Non-refund ticket → direct response (US1-1, SC-001)

Publish a ticket with no refund intent:

```bash
python -m apps.api.dev_publish_ticket --reason "How do I change my email address?"
```

**Expected**: a `local.customer.resolution.decided.v1` event with `outcome = direct_response`, **no**
`task.requested` events to billing/risk, `billing_summary`/`risk_summary` null. Audit trail shows
`ticket received` → `triage (no refund review)` → `decision`.

## Scenario 2 — Refund approved (US3-1)

With billing stub returning eligible and risk stub returning low:

```bash
python -m apps.api.dev_publish_ticket --reason "Please refund — I was charged twice for my subscription"
```

**Expected**: exactly **one** billing `task.requested` and **one** risk `task.requested` (SC-002),
both correlated to the ticket; a single decision with `outcome = approve_refund`, both summaries
populated. (See `contracts/decision-policy.md §D`.)

## Scenario 3 — Deny / escalate paths (FR-009, SC-007)

Drive each via the peer stubs' configured verdicts (e.g. billing ineligible → `deny_refund`; risk
high → `escalate_human` with `escalation_reason = elevated_risk`). The billing stub's `FAIL`
sentinel (text part `"FAIL"`) forces a peer failure → `escalate_human` with `escalation_reason =
peer_failure`. Each refund case resolves to exactly one outcome (SC-003).

## Scenario 4 — Idempotent re-delivery (FR-011, SC-005)

Publish the **same** ticket (same `ticket_id`/`correlation_id`) twice. **Expected**: no second pair
of `task.requested` events, no second decision; the duplicate appears in the audit trail as
`duplicate`.

## Scenario 5 — Only one analysis returns (US3-2, FR-008)

Stop the risk agent, publish a refund ticket. **Expected**: billing result consumed, **no** decision
emitted, case stays open (no timeout — documented gap). Bringing risk back and replaying its result
completes the decision.

## Scenario 6 — Late result after decision (US3-4, FR-012)

After a decision is emitted, replay one peer's result for the same `task_id`. **Expected**: it is
recorded in audit, **no** second/contradictory decision is emitted.

## Scenario 7 — Audit reconstruction (US4, SC-006)

Query the trail by the ticket's correlation id:

```bash
agent-foundation query-audit --correlation-id <CORRELATION_ID>
# or: agent_foundation.audit.store.query_by_correlation(bootstrap, correlation_id)
```

**Expected** (in causal order, attributed to `customer-resolution-agent`): ticket received → triage
→ billing delegated → risk delegated → billing result consumed → risk result consumed → final
decision (with escalation reason when applicable) — reconstructable in <30s via the single query.

## Scenario 8 — Domain isolation & no-supervisor guardrails (US5, US6, SC-004, SC-008)

- Inspect the agent's emitted `task.requested` events: every one is a billing or risk analysis bound
  to a refund ticket it owns — no requests outside its own workflow, no dispatching for other agents.
- Confirm (by code review + the isolation test) the agent imports/queries **no** billing, payment, or
  fraud/risk data store; all such facts enter only via `task.result` events.

---

## Automated validation

```bash
uv run pytest tests/unit/test_triage.py tests/unit/test_decision_policy.py \
              tests/unit/test_resolution_case.py tests/contract/test_resolution_schemas.py
uv run pytest -m integration tests/integration/test_customer_resolution.py
uv run mypy . && uv run ruff check .
```

The integration test drives Scenarios 1–7 through a `testcontainers` Kafka broker; the unit tests
cover the triage rules, the full decision truth table (`decision-policy.md §C`), and case
aggregation (completeness, idempotency, late result). `test_no_router` (existing) continues to pass,
confirming no supervisor/router was introduced.
