# Quickstart: Billing and Entitlement Agent

Validation/run guide for the real billing agent. Implementation detail lives in
[`data-model.md`](./data-model.md), [`contracts/`](./contracts/), and (after `/speckit-tasks`)
`tasks.md`. Run commands from the repo root inside WSL/Linux.

## Prerequisites

- Local single-broker Kafka from `001-event-foundation` running (Docker).
- Python 3.12 env with project deps installed (`pydantic`, `aiokafka`, `structlog`, `pytest`,
  `pytest-asyncio`, `testcontainers[kafka]`). No new dependency for this feature.
- `AGENT_BROKER_URL` (default `localhost:9092`).

## Unit & contract tests (no broker)

```bash
pytest apps/agents/billing_entitlement/tests/test_input_validation.py \
       apps/agents/billing_entitlement/tests/test_mock_data.py \
       apps/agents/billing_entitlement/tests/test_refund_policy.py \
       apps/agents/billing_entitlement/tests/test_rules_engine.py \
       apps/agents/billing_entitlement/tests/test_result_contract.py \
       apps/agents/billing_entitlement/tests/test_domain_isolation.py \
       apps/agents/billing_entitlement/tests/test_no_supervisor.py -q
```

Proves: structured-input validation (FR-002/FR-011), fact lookup + missing-data path (FR-003/FR-010),
each named policy rule + borderline side (FR-012), the approve/deny/human-review truth table and
single-fact matrix (SC-001/SC-004), confidence lowering on contradiction (FR-006), the
`BillingRefundAnalysisCompletedPayload` round-trip + registry + A2A data-part shape (SC-002), domain
isolation (SC-003), and that the agent originates no task requests (SC-008).

## Run the agent locally

```bash
python -m apps.agents.billing_entitlement.main
```

Expect logs: `task.card_published`, `task.endpoint_serving` (endpoint
`local.agent.billing-entitlement-agent.task.requested.v1`).

## Scenario A — analyze a clearly-eligible case (US1/US2)

Drive a refund ticket through the full `003 → 004` flow (start the resolution + risk agents too), or
submit a task directly. Using the resolution path:

```bash
# terminal 1: billing agent (above)
# terminal 2: resolution agent
python -m apps.agents.customer_resolution.main
# terminal 3: risk stub
python -m apps.agents.risk_fraud.main
# terminal 4: publish a refund ticket whose purchase_reference maps to PR-APPROVE
python -m apps.api.dev_publish_ticket --reason "refund please" --amount 50 --reference PR-APPROVE
# terminal 5: observe events
python -m apps.api.dev_consume_events
```

**Expected**:
- Exactly **one** `local.billing.refund-analysis.completed.v1` event, correlated to the case, with
  `recommendation="approve"`, `confidence` in `[0,1]`, a **non-empty** `evidence` set each citing an
  owned fact / policy rule, `policy_references` (e.g. `RP-001`, `RP-002`, `RP-003`), and a
  `reasoning_summary` (SC-002).
- An A2A `TaskResult(status="completed")` on `local.agent.task.result.v1` carrying the same fields.
- Audit events `accepted` then `completed` for the task (FR-014).
- The resolution agent consumes the result and emits its `customer.resolution.decided` event — the
  **real** billing agent feeding the prior feature with **no contract change** (SC-009).

## Scenario B — deny by policy (US3 / SC-004)

Publish with `--reference PR-WINDOW-EXPIRED` (or `PR-UNPAID`, `PR-HEAVY-USAGE`). Expect
`recommendation="deny"` with evidence citing the decisive rule (`RP-001` / `RP-002` / `RP-004`) and
the differing fact — verifying the verdict tracks the single changed billing fact.

## Scenario C — missing / contradictory data → human review (US4 / SC-005)

- `--reference PR-UNKNOWN-XYZ` (no record) → `requires_human_review=True`, `confidence≈0.2`, reason
  "no billing record …". No confident verdict.
- `--reference PR-CONTRADICTION` → `requires_human_review=True`, `confidence≈0.3`, conflict captured
  in evidence/reasoning.

## Scenario D — malformed input → failure (US4 / FR-011)

Submit a task whose input `data` part omits `purchase_reference` (or send a non-`data` part). Expect
`TaskResult(status="failed", error.category="handler_error")` and a `failed` audit event — **no**
fabricated recommendation.

## Scenario E — idempotent re-delivery (US5 / SC-006)

Re-submit the **same** `task_id`. Expect: no second analysis, **no** duplicate
`billing.refund-analysis.completed` event, and a `duplicate_skipped` audit entry. The verdict for the
same facts is identical on every run (FR-012).

## Scenario F — audit reconstruction (US6 / SC-007)

```bash
python -m agent_foundation.cli query-task-audit --correlation-id <case-correlation-id>
# or query_by_correlation(BROKER_URL, correlation_id) from a REPL
```

Expect the ordered trail: request `accepted` → analysis `completed` (with the evidence/policy refs
recoverable from the result event correlated by the same id) → for fault cases, the `failed` /
human-review reason — all attributed to `billing-entitlement-agent`, in causal order, in under 30s.

## Integration suite (broker via testcontainers)

```bash
pytest apps/agents/billing_entitlement/tests/test_billing_agent_e2e.py -q
```

Covers Scenarios A–F end-to-end, including the `003 ↔ 004` round-trip (SC-009) and the dual-path
delivery dedup (research R8).
