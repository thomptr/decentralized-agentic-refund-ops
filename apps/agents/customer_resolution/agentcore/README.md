# Customer Resolution Agent — AgentCore Run Guide

This document describes how to run the Customer Resolution Agent locally using the AWS AgentCore
CLI (`agentcore dev`) and the Kafka orchestration entrypoint.

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

> **Note**: `agentcore dev` must be run from the `apps/agents/customer_resolution` directory (the
> AgentCore project root containing `agentcore/agentcore.json`).

```bash
cd apps/agents/customer_resolution
agentcore validate       # validate agentcore.json before starting
agentcore dev            # build dev venv, start local A2A server, open inspector
```

`agentcore dev` will:
1. Build a local dev venv from `app/CustomerResolution/pyproject.toml`.
2. Start the local A2A server on port **8086** (configured via `agentcore/.env.local`).
3. Open the AgentCore inspector UI — invoke structured resolution requests there.

Useful flags:

```bash
agentcore dev -p 8086          # explicit port
agentcore dev --logs           # stream logs while running
```

### Sample invocation (inspector or terminal)

A non-refund ticket triages to a direct response with no peer analysis:

```bash
agentcore dev '{"ticket_id": "TKT-001", "customer_id": "CUS-001", "reason": "How do I reset my password?"}'
```

A refund ticket with peer findings supplied inline exercises the full decision matrix:

```bash
agentcore dev '{
  "ticket_id": "TKT-002",
  "customer_id": "CUS-002",
  "amount": 49.99,
  "currency": "USD",
  "reason": "I was double charged, please refund",
  "billing_result": {"recommendation": "approve_full_refund", "confidence": 0.9},
  "risk_result": {"recommendation": "low", "confidence": 0.1}
}'
```

Expected output (approve path):

```json
{
  "status": "completed",
  "outcome": "approve_refund",
  "customer_response": "We have reviewed your request and are pleased to approve your refund. ...",
  "rationale": "Eligible for refund; low risk"
}
```

> **Important**: `agentcore dev` is a **standalone demo/testing interface**. Unlike the Kafka
> entrypoint, it does **not** delegate to the billing/risk peers and does **not** publish the
> `resolution.decided` / `response.drafted` Kafka events. Peer findings (`billing_result` /
> `risk_result`) must be supplied in the payload; absent them, the deterministic decision engine
> escalates to a human (`escalate_human`, reason `missing_analysis`) — it never fabricates a
> billing or risk verdict (FR-005).

## Kafka orchestration entrypoint (the real collaboration path)

```bash
# Start the foundation Kafka broker first (from repo root):
docker compose up -d

# Then start the Customer Resolution Agent's orchestration loops:
demo-customer-resolution
# or directly:
python -m apps.agents.customer_resolution.main
```

This is the path used in the **three-agent demo** (Customer Resolution ↔ Billing Agent ↔ Risk
Agent). It consumes `support.ticket.created`, delegates `analyze_refund_eligibility` and
`assess_fraud_risk` TaskRequests to the peers, consumes their result events, and emits the final
`resolution.decided` and `response.drafted` events.

## AgentCore vs Kafka — which to use

| Mode | Command | Port | Delegates to peers / publishes Kafka? | Use when |
|------|---------|------|---------------------------------------|----------|
| **AgentCore local dev** | `agentcore dev` | 8086 | **No** | Local testing, inspector UI, decision-engine demo |
| **Kafka orchestration** | `demo-customer-resolution` | — (Kafka) | **Yes** | Three-agent demo, full peer collaboration |

> **Note on A2A transports**: `agentcore dev` speaks the standard `a2a-sdk` wire protocol
> (JSON-RPC `message/send` / `message/stream` over HTTP). This is **distinct** from this repo's
> internal A2A-over-Kafka runtime (feature 002). Both use the same `classify` + `decide` business
> logic — only the transport adapter differs.

## Environment variables

All environment variables are documented in `agentcore/.env.local`. Key overrides:

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` / `AGENTCORE_PORT` | `8086` | AgentCore dev server port |
| `AGENT_BROKER_URL` | `localhost:9092` | Kafka bootstrap server (Kafka entrypoint only) |
| `AGENT_ENVIRONMENT` | `local` | Topic prefix (`local.customer.resolution.decided.v1`) |
| `AUTH_MODE` | `none` | No auth for local dev — no AWS deployment required |

> Local dev runs entirely on the foundation's local Kafka + `agentcore dev`.
> `agentcore deploy` (CodeZip) is a **documented future target only** — it is not built for this PoC.
> The `aws-targets.json` contains a placeholder account/region.

## No new dependencies

All AgentCore and A2A libraries (`bedrock-agentcore[a2a]`, `a2a-sdk[all]`) were introduced by
feature 004 (Billing Entitlement Agent) and are already used by the billing and risk agents'
AgentCore packages. No new repo dependency was added by this agent.
