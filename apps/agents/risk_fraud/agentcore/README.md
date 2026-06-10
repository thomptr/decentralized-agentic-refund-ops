# Risk Fraud Agent — AgentCore Run Guide

This document describes how to run the Risk Fraud Agent locally using the AWS AgentCore CLI
(`agentcore dev`), the standalone HTTP A2A surface, and the Kafka peer entrypoint.

## Prerequisites

Install the AgentCore CLI:

```bash
pip install bedrock-agentcore
```

Verify with:

```bash
agentcore --version
```

## Running locally — launch the AgentCore UI / terminal UI

> **Note**: `agentcore dev` must be run from the `apps/agents/risk_fraud` directory (the AgentCore
> project root containing `agentcore/agentcore.json`).

```bash
cd apps/agents/risk_fraud
agentcore validate       # validate agentcore.json before starting
agentcore dev            # build dev venv, start local A2A server, open inspector
```

`agentcore dev` will:
1. Build a local dev venv from `app/RiskFraud/pyproject.toml`.
2. Start the local A2A server on port **8083** (configured via `agentcore/.env.local`).
3. Open the AgentCore inspector UI — invoke structured risk requests there.

Useful flags:

```bash
agentcore dev -p 8083          # explicit port
agentcore dev --logs           # stream logs while running
```

### Sample invocation (inspector or terminal)

```bash
agentcore dev '{"case_id": "11111111-1111-1111-1111-111111111111", "ticket_id": "TKT-001", "customer_id": "CUS-BLOCKLIST"}'
```

Expected output (blocklist customer):

```json
{
  "recommendation": "high",
  "confidence": 0.95,
  "requires_human_review": false,
  "evidence": [{"source": "known_fraud", ...}, {"source": "fraud_policy", ...}]
}
```

## Run local A2A mode separately

The agent has **two independent run paths** for local development:

### Path 1 — Kafka peer entrypoint (collaboration path)

```bash
# Start the foundation Kafka broker first (from repo root):
docker compose up -d

# Then start the Risk Agent's Kafka A2A endpoint:
demo-risk-fraud
# or directly:
python -m apps.agents.risk_fraud.main
```

This is the path used in the **three-agent demo** (Customer Resolution ↔ Risk Agent ↔ Billing Agent).
It processes inbound `assess_fraud_risk` TaskRequests from the event stream and publishes
`RiskReviewCompletedPayload` events to `local.risk.review.completed.v1`.

### Path 2 — Standalone HTTP A2A surface (port 8103)

```bash
demo-risk-fraud-http
# or:
python -m apps.agents.risk_fraud.http_app
```

Exposes:

| Endpoint | Description |
|----------|-------------|
| `GET /.well-known/agent.json` | Agent Card (same card as Kafka path) |
| `POST /a2a/tasks` | Accept and process an `assess_fraud_risk` task |
| `GET /ping` | Health check |

Test with the dev client:

```bash
python -m apps.agents.risk_fraud.dev_a2a_client
```

Or with curl:

```bash
curl http://localhost:8103/.well-known/agent.json
curl -X POST http://localhost:8103/a2a/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "00000000-0000-0000-0000-000000000001",
    "capability": "assess_fraud_risk",
    "input": {"parts": [{"type": "data", "data": {
      "case_id": "11111111-1111-1111-1111-111111111111",
      "ticket_id": "TKT-001",
      "customer_id": "CUS-CHARGEBACKS"
    }}]}
  }'
```

## AgentCore vs A2A — which to use

| Mode | Command | Port | Publishes Kafka event? | Use when |
|------|---------|------|------------------------|----------|
| **AgentCore local dev** | `agentcore dev` | 8083 | **No** | Local testing, inspector UI, demo |
| **HTTP A2A surface** | `demo-risk-fraud-http` | 8103 | **No** | Direct HTTP calls, 003 direct-call testing |
| **Kafka peer entrypoint** | `demo-risk-fraud` | — (Kafka) | **Yes** | Three-agent demo, peer-agent collaboration |

> **Important**: `agentcore dev` and the HTTP surface are **standalone demo/testing interfaces**.
> They do **not** publish the `risk.review.completed` Kafka event (that is the Kafka entrypoint's job,
> US2/T020). Use the Kafka peer entrypoint for the full event-driven three-agent collaboration.

> **Note on A2A transports**: `agentcore dev` speaks the standard `a2a-sdk` wire protocol
> (JSON-RPC `message/send` / `message/stream` over HTTP). This is **distinct** from this repo's
> internal A2A-over-Kafka runtime (feature 002). Both use the same `service.assess` business logic —
> only the transport adapter differs.

## Environment variables

All environment variables are documented in `agentcore/.env.local`. Key overrides:

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` / `AGENTCORE_PORT` | `8083` | AgentCore dev server port |
| `A2A_ENDPOINT_PORT` | `8103` | Standalone HTTP A2A surface port |
| `AGENT_BROKER_URL` | `localhost:9092` | Kafka bootstrap server |
| `AGENT_ENVIRONMENT` | `local` | Topic prefix (`local.risk.review.completed.v1`) |
| `AUTH_MODE` | `none` | No auth for local dev — no AWS deployment required |

> Local dev runs entirely on the foundation's local Kafka + `agentcore dev`/`http_app`.
> `agentcore deploy` (CodeZip) is a **documented future target only** — it is not built for this PoC.
> The `aws-targets.json` contains a placeholder account/region.

## No new dependencies

All AgentCore and HTTP libraries (`bedrock-agentcore[a2a]`, `a2a-sdk[all]`, `fastapi`, `uvicorn`)
were introduced by feature 004 (Billing Entitlement Agent) and are already declared in the
root `pyproject.toml`. No new repo dependency was added by this agent.
