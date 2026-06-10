# Billing Entitlement Agent — AgentCore Local Run

Run this agent locally with the **AWS AgentCore CLI** ([`aws/agentcore-cli`](https://github.com/aws/agentcore-cli),
the npm `@aws/agentcore` package — the successor to the Python starter toolkit).

The CLI treats the directory that contains this `agentcore/` folder as the **project
root**, so all `agentcore` commands below must be run from
`apps/agents/billing_entitlement/` — *not* the repo root. (Running from the repo root
is what produced `No agentcore project found. Run agentcore create to fix this.`)

## Layout

```
apps/agents/billing_entitlement/        <- project root (cd here)
  agentcore/
    agentcore.json        # project + A2A runtime config (real CLI schema)
    aws-targets.json       # deploy targets (account/region) — array form
    .env.local             # local env vars (gitignored)
  app/BillingEntitlement/
    main.py                # A2A entrypoint: serve_a2a(BillingEntitlementExecutor(), CARD)
    pyproject.toml         # dev-venv deps (bedrock-agentcore[a2a], a2a-sdk, pydantic, structlog)
```

`main.py` reuses the existing `service.analyze` pipeline unchanged; it only adapts
the I/O to AgentCore's A2A contract. The repo's `apps/`, `packages/`, and `src/`
trees are put on `sys.path` from source inside `main.py`, so the auto-created dev
venv only needs the third-party libraries above.

> **Note on "A2A":** AgentCore's A2A is the standard a2a-sdk wire protocol
> (JSON-RPC `message/send`), which is **not** the same as this repo's internal A2A
> runtime from feature 002. This entrypoint is for running the agent standalone via
> the CLI; internal peer delegation still uses the repo's own A2A/Kafka paths.

## Prerequisites

| Tool | Required |
|------|----------|
| Node.js | 20+ (the CLI is an npm package) |
| Python | 3.12+ |
| AWS AgentCore CLI | `npm install -g @aws/agentcore` |

```sh
agentcore --help        # confirm install; you should see: dev, deploy, create, invoke, ...
```

## Running locally

```sh
cd apps/agents/billing_entitlement

# (optional) sanity-check the config against your CLI version
agentcore validate

# build the dev venv, start the local A2A server, open the inspector
agentcore dev
```

`agentcore dev`:
- creates a Python venv from `app/BillingEntitlement/pyproject.toml` and installs deps,
- starts a local server that mimics the AgentCore Runtime and serves the A2A
  agent card + protocol endpoints,
- opens the agent inspector in your browser (use `-p <port>` to change the port,
  `--logs` for non-interactive log streaming).

### Invoke the local agent

Send the refund request as a structured data payload (also accepted as a JSON string):

```sh
agentcore dev '{"case_id":"00000000-0000-0000-0000-000000000002","ticket_id":"TKT-001","customer_id":"CUS-001","requested_refund_amount":49.99,"purchase_reference":"PR-APPROVE"}'
```

The agent returns a single data artifact: `{"recommendation": "...", "confidence": ...,
"evidence": [...], "reasoning_summary": "...", "requires_human_review": ...}`.

## Deploying (later)

`agentcore deploy` reads `agentcore.json` + `aws-targets.json`. Before deploying:
- set a real 12-digit `account` in `aws-targets.json`,
- vendor the monorepo packages into `codeLocation` (CodeZip only zips
  `app/BillingEntitlement/`; the `sys.path`-from-source trick used for local dev
  will not include them in the deployed artifact).

## Standalone path (no AgentCore CLI)

The hand-rolled FastAPI surface still works for quick local testing without the CLI:

```sh
pip install -e ".[http]"
python -m apps.agents.billing_entitlement.http_app   # or: demo-billing-entitlement-http
python -m apps.agents.billing_entitlement.dev_a2a_client   # GETs the card + POSTs sample tasks
```

## Kafka entrypoint (unchanged)

The domain agent that publishes result events for the full three-agent demo:

```sh
demo-billing-entitlement   # or: python -m apps.agents.billing_entitlement.main
```
