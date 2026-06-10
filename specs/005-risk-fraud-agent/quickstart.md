# Quickstart: Risk and Fraud Agent

A validation/run guide proving the agent works end-to-end. Implementation detail lives in
[`plan.md`](./plan.md), [`data-model.md`](./data-model.md), and [`contracts/`](./contracts); the task
breakdown is produced by `/speckit-tasks`.

## Prerequisites

- Python 3.12, repo deps installed: `uv sync` (or `pip install -e ".[dev,http]"`).
- Local Kafka from the foundation (`infra/`): single broker on `localhost:9092`. The agent and tests
  create their topics on startup; `TOPIC_RISK_RESULT` already exists in `_CANONICAL_TOPICS`.
- For the AgentCore path only: Node 20+ and `npm install -g @aws/agentcore`.

## A. Unit / contract validation (no broker)

```sh
pytest apps/agents/risk_fraud/tests -q
```

Expected — these prove the deterministic core:
- `test_input_validation` — valid input parses; missing data part / bad types raise `ValueError`
  (FR-002/FR-011).
- `test_mock_data` — `load_signals` hits seeds and returns `None` on unknown `customer_id` (FR-003/FR-010).
- `test_fraud_policy` — each `FP-00x` rule fires on its signal; borderline resolves to the upper band.
- `test_scoring` — full `low/elevated/high` truth table; the **single-signal matrix** (SC-004) changes
  the level in the documented direction with the change cited in evidence; known-indicator forces
  `high`; contradiction lowers confidence and sets `requires_human_review` (FR-006/FR-010).
- `test_result_contract` — `RiskReviewCompletedPayload` round-trips, is in `PAYLOAD_REGISTRY`, and the
  A2A output data part matches the shape `003`'s `normalize_risk_result` consumes (SC-002/SC-009).
- `test_domain_isolation` — the verdict reads only owned signals; no billing/foreign field, no peer
  call (SC-003).
- `test_no_supervisor` — the agent originates no `TaskRequest` and dispatches no work (SC-008/US7).

## B. Three-agent event-driven demo (broker)

Run the three domain agents (each in its own shell) plus the dev driver:

```sh
demo-customer-resolution      # 003 consumer (unchanged)
demo-billing-entitlement      # 004 peer
demo-risk-fraud               # 005 — THIS agent (replaces the stub)
```

Drive a refund case and observe events (reuse the `apps/api` dev helpers):

```sh
python -m apps.api.dev_publish_ticket    # publishes a support.ticket.created refund case
python -m apps.api.dev_consume_events     # observe risk.review.completed + audit on the stream
```

Validate:
1. **US1/US3** — the risk agent receives the `assess_fraud_risk` `TaskRequest`, returns a risk level
   correlated to the request; a clean customer → `low`, a chargeback/velocity/blocklist customer →
   `elevated`/`high`.
2. **US2/FR-007/FR-008** — exactly one `RiskReviewCompletedPayload` is published on
   `local.risk.review.completed.v1` per assessment, carrying level, in-range confidence, a non-empty
   evidence set, ≥1 `fraud_policy` evidence item (policy reference), a reasoning summary, and the
   human-review flag — correlated to the case; the same verdict is also returned as the A2A
   `TaskResult` (dual path).
3. **US6/FR-014/FR-015/SC-007** — `query_by_correlation(case_id)` returns received → assessed →
   published (and any failure/human-review) in causal order, attributed to `risk-fraud-agent`.
4. **US5/FR-013/SC-006** — redelivering the identical `TaskRequest` (same `task_id`) yields one logical
   verdict and no duplicate result event; the duplicate is audited `duplicate_skipped`.
5. **SC-009** — the **unchanged** `003` agent consumes the real risk verdict and reaches a decision
   (elevated/high or `requires_human_review` → `escalate_human`); no edit to feature 003 was needed.

The `003`↔`005` end-to-end is automated in `test_risk_agent_e2e` (testcontainers Kafka), which also
covers missing/contradictory → human review and malformed → failed.

## C. AgentCore CLI local development (US: `agentcore dev` + inspector)

```sh
cd apps/agents/risk_fraud
agentcore validate          # optional: sanity-check config against your CLI version
agentcore dev               # build dev venv, start local A2A server, open the inspector UI
```

Invoke the local agent with a structured risk request (also accepted as a JSON string):

```sh
agentcore dev '{"case_id":"00000000-0000-0000-0000-000000000005","ticket_id":"TKT-005","customer_id":"CUS-BLOCKLIST","requested_refund_amount":49.99}'
```

Expected: a single data artifact `{"recommendation":"high","confidence":0.95,"evidence":[...],
"reasoning_summary":"...","requires_human_review":...,"policy_references":["FP-001"]}`. The AgentCore
path is standalone and does **not** publish the Kafka result event (that stays the `demo-risk-fraud`
entrypoint's job). The inspector shows the agent card advertising `assess_fraud_risk`.

CLI-free standalone path (FastAPI surface):

```sh
python -m apps.agents.risk_fraud.http_app        # serves GET /.well-known/agent.json + POST /a2a/tasks + GET /ping
python -m apps.agents.risk_fraud.dev_a2a_client   # GETs the card + POSTs sample tasks
```

## Success criteria mapping

| Criterion | Validated by |
|-----------|--------------|
| SC-001 every accepted request → one level + human-review flag | A (scoring) + B step 1 |
| SC-002 one structured result event, evidence + policy ref + confidence | B step 2 / `test_result_contract` |
| SC-003 traceable to owned signals, no foreign data / peer call | `test_domain_isolation` |
| SC-004 single-signal matrix | `test_scoring` |
| SC-005 missing/contradictory → human review or failure | `test_scoring` / `test_risk_agent_e2e` |
| SC-006 idempotent re-delivery | B step 4 / `test_risk_agent_e2e` |
| SC-007 audit reconstructable by correlation id | B step 3 |
| SC-008 no task origination / dispatch | `test_no_supervisor` |
| SC-009 `003` consumes unchanged | B step 5 / `test_risk_agent_e2e` |
| AgentCore local dev + inspector | C |
