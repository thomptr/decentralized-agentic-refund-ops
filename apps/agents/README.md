# Demo Agents

Three mock agents that exercise the A2A runtime contract. They contain **no refund-domain business logic** — every handler returns a fixed mock result. They exist solely to demonstrate the contract.

## Agents

| Agent | Entry point | Capability |
|-------|-------------|------------|
| `customer-resolution-agent` | `demo-customer-resolution` | `resolve_customer_case` |
| `billing-entitlement-agent` | `demo-billing-entitlement` | `analyze_refund_eligibility` |
| `risk-fraud-agent` | `demo-risk-fraud` | `assess_fraud_risk` |

## Prerequisites

Start the Kafka broker from the foundation:

```bash
docker compose -f infra/local/docker-compose.yml up -d
```

## Starting the agents

Start each in a separate terminal:

```bash
uv run demo-customer-resolution
uv run demo-billing-entitlement
uv run demo-risk-fraud
```

Or use `python -m`:

```bash
uv run python -m apps.agents.customer_resolution.main
uv run python -m apps.agents.billing_entitlement.main
uv run python -m apps.agents.risk_fraud.main
```

## Discovering agents

```bash
uv run python -m apps.agents.discover
```

Or via the CLI:

```bash
uv run agent-foundation discover
uv run agent-foundation discover --capability analyze_refund_eligibility
```

## Submitting a task

```bash
uv run agent-foundation submit-task \
  --target billing-entitlement-agent \
  --capability analyze_refund_eligibility \
  --text "check this"
```

## Triggering the FAIL sentinel

The billing agent raises when the input text part equals `"FAIL"`, producing
`TaskResult(status="failed", error.category="handler_error")`:

```bash
uv run agent-foundation submit-task \
  --target billing-entitlement-agent \
  --capability analyze_refund_eligibility \
  --text "FAIL"
```

## Cross-agent delegation (A2A)

`customer-resolution-agent` delegates to `billing-entitlement-agent` via `A2AClient`. The
delegation path is: **requester → performer endpoint topic directly** — no supervisor, no
central router (FR-011).

```bash
uv run agent-foundation submit-task \
  --target customer-resolution-agent \
  --capability resolve_customer_case \
  --text "resolve case 123"
```

## Querying the audit trail

```bash
uv run agent-foundation query-task-audit --task-id <uuid>
```

## No supervisor / no router

The three agents communicate **exclusively via Kafka**. There is no supervisor agent, central
router, dispatcher, or orchestrator:

- Each agent listens on its own **endpoint topic** (`local.agent.<agent_id>.task.requested.v1`).
- `A2AClient.submit()` publishes the `TaskRequest` **directly** to the target's endpoint topic
  and awaits the correlated `TaskResult` on the shared result topic.
- To verify: inspect `apps/agents/customer_resolution/main.py` — the only cross-agent call is
  `a2a_client.submit("billing-entitlement-agent", ...)`. No intermediate topic is in the path.
- Running `test_no_router.py` confirms this statically.
