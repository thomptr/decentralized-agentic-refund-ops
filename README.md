# Decentralized Agentic Refund Operations

A proof-of-concept showing autonomous AI agents that coordinate to handle end-to-end
refund workflows — dispute intake, eligibility check, fraud review, and a final decision —
**without a central orchestrator, supervisor, or router**. Each agent is a peer that owns
its own data and decisions; they find each other and collaborate through the
**Agent-to-Agent (A2A)** contract, and the whole system is wired together by **Kafka** as
an event backbone and replayable audit log.

## Overview

Three peer agents collaborate on a refund case:

- **Customer-Resolution** owns the case: it takes in a support ticket, triages it, and — for
  refund disputes — asks the other two agents for their opinions, then decides.
- **Billing-Entitlement** answers "is this refund eligible per billing facts and policy?"
- **Risk-Fraud** answers "how risky/fraudulent does this refund look?"

No agent tells another what to do. Customer-Resolution delegates *capabilities* it discovers
at runtime; the peers reply with opinions; Customer-Resolution aggregates them into a
deterministic decision. Every step is an event on Kafka, so the entire case is auditable and
replayable.

```
support ticket ──▶ Customer-Resolution ──(A2A task)──▶ Billing-Entitlement ──▶ opinion ─┐
                          │                                                              │
                          └────────────(A2A task)──────▶ Risk-Fraud ──────────▶ opinion ─┤
                          │                                                              │
                          ▼                                                              │
                   final decision  ◀───────────── aggregate both opinions ◀─────────────┘
```

See [`docs/architecture/decentralized-workflow.md`](docs/architecture/decentralized-workflow.md)
for the full sequence and the non-refund path.

## How discovery and communication work (A2A + Kafka)

**A2A is the contract** the agents speak: an **Agent Card** advertising an agent's identity and
**capabilities**, plus a **TaskRequest → TaskResult** request/response for invoking a capability.
That contract is carried over two interchangeable transports.

### Discovery — no central registry

- **Over Kafka (local default):** each agent publishes its Agent Card once at startup (and
  re-announces periodically) to the **compacted** `agent.agent-card.published` topic, keyed by
  `agent_id` (latest-wins). Any agent reconstructs the live roster by replaying that topic —
  `discover_agents()` / `find_capable(capability_id)`. A restart or a late joiner gets the full
  picture with no registry service.
- **Over HTTP (AgentCore deployment):** an agent serves its card at `GET /.well-known/agent.json`.

### Agent-to-agent communication

- **Over Kafka (local default):** Customer-Resolution publishes a `TaskRequest` to the target
  agent's **endpoint topic** `agent.<agent-id>.task.requested`; the agent's runtime consumes it,
  runs the handler, and publishes a `TaskResult` to `agent.task.result`. Delegation is
  asynchronous (fire-and-forget + aggregate-on-result), so a slow peer never blocks the case.
- **Over HTTP (AgentCore deployment):** a `TaskRequest` is `POST`ed to `/a2a/tasks` and the
  `TaskResult` is the HTTP response.

### What Kafka provides

Kafka is the system's nervous system and **replayable system of record**:

- **Event backbone** — every interaction is an `EventEnvelope` (with `correlation_id` /
  `causation_id` for causal tracing) published to a topic named
  `<env>.<domain>.<entity>.<action>.v<n>` (the `<env>` prefix comes from `AGENT_ENVIRONMENT`,
  default `local`).
- **Choreography** — agents react to domain events rather than being called by a coordinator.
- **Audit & replay** — everything is mirrored to the audit topic, so a case can be traced
  (`trace_case`) or replayed deterministically.
- **Idempotency** — per-consumer compacted "processed-id" topics make every handler
  exactly-once in effect.

Details: [`docs/architecture/event-choreography.md`](docs/architecture/event-choreography.md),
[`event-contracts.md`](docs/architecture/event-contracts.md),
[`replay-and-idempotency.md`](docs/architecture/replay-and-idempotency.md),
[`no-supervisor-verification.md`](docs/architecture/no-supervisor-verification.md).

## Events on Kafka vs. messages over HTTP (A2A)

### Events published to Kafka

Topic names below omit the `<env>.` prefix (e.g. `local.`) and the `.v1` suffix.

| Topic | Purpose | Category |
|-------|---------|----------|
| `agent.agent-card.published` | Agent Cards for **discovery** (compacted, latest-wins per agent) | A2A / discovery |
| `agent.<agent-id>.task.requested` | A2A **TaskRequest** delivered to one agent's endpoint | A2A / transport |
| `agent.task.result` | A2A **TaskResult** returned by a performer | A2A / transport |
| `agent.message.sent` | A2A message channel | A2A / transport |
| `support.ticket.created` | Root intake event that starts a case (`causation_id=None`) | Domain / choreography |
| `resolution.customer-issue.classified` | Customer-Resolution's triage outcome | Domain / choreography |
| `resolution.refund-review.requested` | Customer-Resolution announces a refund review (delegation) | Domain / choreography |
| `billing.refund-analysis.completed` | Billing-Entitlement's eligibility opinion | Domain / choreography |
| `risk.review.completed` | Risk-Fraud's risk opinion | Domain / choreography |
| `customer.resolution.decided` | Customer-Resolution's final decision | Domain / choreography |
| `resolution.customer-response.drafted` | Drafted customer reply | Domain / choreography |
| `audit.envelope.recorded` | The audit trail — replayable system of record | Cross-cutting |
| `system.agent.heartbeat` | Periodic liveness signal (feature 009) | Cross-cutting |
| `audit.llm.invocation.completed` / `.failed` | Optional LLM reasoning audit events (feature 008) | Cross-cutting |
| `system.processed-id.<consumer>.recorded` | Per-consumer idempotency tracking (compacted) | Cross-cutting |
| `system.sample.published` | Sample/demo event (feature 001) | Cross-cutting |

### Messages sent over HTTP (A2A — AgentCore deployment)

When an agent is deployed in its AgentCore HTTP form (`demo-*-http` entry points), the same
A2A contract is exposed over HTTP instead of Kafka:

| Method & path | Message | Purpose |
|---------------|---------|---------|
| `GET /.well-known/agent.json` | Agent Card | Discovery (capabilities, identity) |
| `POST /a2a/tasks` | `TaskRequest` → `TaskResult` | Invoke a capability |
| `GET /ping` | — | Liveness health check |

> The **local demo runs entirely over Kafka**; the HTTP surface is the deployment shape for
> Amazon Bedrock AgentCore. The agents share one `identity.py` Agent Card across both transports.

## Running locally

Prerequisites: [`uv`](https://docs.astral.sh/uv/) and Docker.

```bash
# 1. Install dependencies (add extras as needed: ui, llm, observability)
uv sync --extra dev --extra ui

# 2. Start Kafka (Redpanda) — Kafka UI at http://localhost:8080
docker compose -f infra/local/docker-compose.yml up -d

# 3a. Start all three agents (Ctrl-C stops them)
bash infra/local/run-demo-agents.sh

# 3b. ...and the demo UI (separate terminal) — http://localhost:8200
uv run demo-ui
```

Or bring up the whole stack (broker + agents + UI) with one script:

```bash
bash scripts/start-local-system.sh --with-ui    # add --with-http for the HTTP A2A variant
bash scripts/stop-local-system.sh
```

Drive it from the CLI:

```bash
uv run agent-foundation discover                                  # list advertised agents
uv run agent-foundation discover --capability analyze_refund_eligibility
uv run agent-foundation submit-task \
  --target billing-entitlement-agent \
  --capability analyze_refund_eligibility --text "check this"
```

The easiest way to exercise a full refund case is the demo UI's **Demo trigger** (use the
**Scenario** dropdown to pick a ticket with seeded billing data so the rules engine actually
runs). See [`apps/demo_ui/demo-ui.md`](apps/demo_ui/demo-ui.md).

More: [`apps/agents/README.md`](apps/agents/README.md) (agent runner details) and
[`specs/001-event-foundation/quickstart.md`](specs/001-event-foundation/quickstart.md)
(foundation walkthrough).

## The agents and the demo UI

### Customer-Resolution agent — `resolve_customer_case`
The case owner and the only "coordinator" — but it coordinates by *delegating discovered
capabilities*, not by supervising. It consumes `support.ticket.created`, triages the ticket
(refund vs. non-refund; LLM-assisted, deterministic fallback), and for refund disputes delegates
to the Billing and Risk peers via A2A, aggregates both opinions, makes the final
`customer.resolution.decided` call (approve / deny / manual-review / escalate), and drafts the
customer response. Kafka-only (no HTTP surface).
Spec: [`specs/003-customer-resolution-agent/plan.md`](specs/003-customer-resolution-agent/plan.md).

### Billing-Entitlement agent — `analyze_refund_eligibility`
Answers refund eligibility from the billing/entitlement data it owns, using a deterministic
rules engine (refund window, paid/captured/not-reversed, heavy-usage gate, contradiction gate).
Publishes `billing.refund-analysis.completed`. The LLM only polishes the human-readable summary.
Spec: [`specs/004-billing-entitlement-agent/plan.md`](specs/004-billing-entitlement-agent/plan.md).

### Risk-Fraud agent — `assess_fraud_risk`
Scores fraud/risk for the refund from the risk signals it owns and publishes
`risk.review.completed`. Deterministic scoring; LLM assistive only.
Spec: [`specs/005-risk-fraud-agent/plan.md`](specs/005-risk-fraud-agent/plan.md).

All three share the A2A runtime/contract (Agent Card, capability handlers, TaskRequest/Result):
[`specs/002-a2a-runtime-contract/plan.md`](specs/002-a2a-runtime-contract/plan.md). The LLM
runtime is **assistive, never authoritative** (binding decisions stay in the deterministic
engines) and defaults to a stub provider:
[`specs/008-agent-llm-runtime/plan.md`](specs/008-agent-llm-runtime/plan.md).

### Demo UI
A **read-only** Streamlit observatory (the only write is the bounded Demo trigger). Four views:
**Roster** (live discovery + liveness), **Case timeline** (causal trace of one case),
**Audit stream** (cross-case event feed), and **Demo trigger** (start a case). See
[`apps/demo_ui/README.md`](apps/demo_ui/README.md) and the per-view guide
[`apps/demo_ui/demo-ui.md`](apps/demo_ui/demo-ui.md).

## Observability

OpenTelemetry-compatible spans (`event.consume`, `kafka.publish`, `a2a.task.send/receive`,
`llm.invoke`, and the engine spans `ticket.classify` / `policy.evaluate` / `case.decision`)
export to a self-hosted or cloud **LangFuse** backend, with PII redacted before export. Kafka
remains the replayable record. Toggle with `AGENT_OBSERVABILITY_ENABLED`; suppress noisy spans
with `AGENT_OBSERVABILITY_DISABLED_SPANS`.
Spec: [`specs/009-observability/plan.md`](specs/009-observability/plan.md).

## Repository map

| Path | What's there |
|------|--------------|
| `src/agent_foundation/` | Transport, A2A runtime, envelope/audit/idempotency, LLM runtime, observability |
| `apps/agents/` | The three peer agents ([README](apps/agents/README.md)) |
| `apps/demo_ui/` | Read-only Streamlit observatory ([README](apps/demo_ui/README.md) · [view guide](apps/demo_ui/demo-ui.md)) |
| `packages/contracts/` | Topic naming + canonical topic registry |
| `docs/architecture/` | Cross-cutting design docs ([index](docs/architecture/README.md)) |
| `specs/` | Per-feature specs, plans, and contracts (001–009) |
| `infra/local/` | Docker compose (Redpanda, LangFuse) + agent run scripts |
