# Implementation Plan: Risk and Fraud Agent

**Branch**: `005-risk-fraud-agent` | **Date**: 2026-06-09 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/005-risk-fraud-agent/spec.md`

## Summary

Ship the **Risk and Fraud Agent** — an independent domain agent that owns refund-abuse, account-risk,
behavioral/velocity, prior-refund-history, payment-instrument, and known-fraud-indicator analysis —
on top of the `001-event-foundation` transport and the `002-a2a-runtime-contract` runtime. The agent
advertises one A2A capability, **`assess_fraud_risk`**, via the shared capability-discovery mechanism.
On each accepted task it **validates the structured task input**, loads the **risk/fraud signals it
owns** (seeded mock dataset across the five signal domains), **scores fraud risk with a deterministic
rule-based engine** against a **named, citable fraud policy**, and returns a structured assessment — a
risk level (`low` / `elevated` / `high`) plus a `requires_human_review` flag — carrying a confidence
score, an evidence set, the policy references applied, and a reasoning summary.

The result is delivered on **two correlated paths** (FR-008): the runtime returns it to the requesting
peer as the A2A `TaskResult.output`, and the agent **publishes a `RiskReviewCompletedPayload` to
`local.risk.review.completed.v1` (`TOPIC_RISK_RESULT`)** so any consumer — notably the existing
Customer Resolution Agent — sees a self-describing fraud verdict on the shared event stream. The
runtime emits the **accepted / completed / failed / rejected** task-lifecycle audit events
automatically (FR-014), and dedups by `task_id` so a redelivered request neither re-assesses nor
double-publishes (FR-013).

**This feature replaces the existing mock stub** at `apps/agents/risk_fraud/main.py` (which returns a
fixed `{"risk": "low", "score": 0.1}` verdict) with the real domain agent. Crucially, the shared
contract and topic the stub's consumer expects **already exist and are already registered** in the
foundation (`TOPIC_RISK_RESULT` in `transport/topics.py:TOPIC_NAMES` + `_CANONICAL_TOPICS`,
`RiskReviewCompletedPayload` in `payloads/__init__.py:PAYLOAD_REGISTRY`, and the consumer's
`normalize_risk_result` / `risk_result_handler` in the resolution agent). The agent therefore **adds
no new cross-cutting contract, no new topic, and no new dependency** — only its own domain package.
It makes **no synchronous peer call**, reads **no** billing/customer-workflow state, and acts as
**no** supervisor, router, or dispatcher.

**Capability-name note (resolved in planning)**: the feature request phrased the capability as
`assess_refund_risk`. The shipped capability id is **`assess_fraud_risk`** — the id the existing
Customer Resolution Agent discovers (`config.py:RISK_CAPABILITY_ID = "assess_fraud_risk"`, agent id
`risk-fraud-agent`) and the id the spec's FR-002 / Assumptions reference. Keeping it preserves SC-009
("consumer unchanged") with **zero edits to feature 003**; the `assess_refund_risk` phrasing is
treated as the descriptive intent of the same fraud-risk-assessment capability.

## Technical Context

**Language/Version**: Python 3.12 (single version per constitution; matches `001`/`002`/`003`/`004`).

**Primary Dependencies** (all already present — **no new dependency**):
- `pydantic` v2 — risk-signal fact models, the `assess_fraud_risk` input model, the `RiskAssessment`
  domain model, reuse of `RiskReviewCompletedPayload`.
- `aiokafka` — endpoint consumption, result/audit/card publishing, and the domain result event, all
  via the foundation `Publisher`/`AgentRuntime` (reused unchanged).
- `structlog` — structured per-step logging (Principle IV).
- `agent_foundation.runtime` — `AgentRuntime` (card + endpoint + lifecycle audit + task-id
  idempotency), `AgentCard`/`Capability` for discovery advertisement.
- `pytest`, `pytest-asyncio`, `testcontainers[kafka]` — unit/contract/integration tests.
- AgentCore local run (already in the repo for `004`): `bedrock-agentcore[a2a]`, `a2a-sdk[all]`,
  `fastapi`/`uvicorn` (the `[http]` optional extra) — used **only** by the AgentCore/HTTP entrypoints,
  not by the Kafka domain agent. No additions to the root project dependency set.

**Reasoning approach**: **Deterministic rule-based** scoring (no LLM / Bedrock / `boto3`). FR-012
mandates that identical signals under the same policy yield the same verdict; the constitution's
determinism and PoC-scope principles, plus consistency with the `003` decision engine and the `004`
billing rules engine, make a pure rules engine the simplest mechanism that proves the hypothesis. An
optional LLM reasoning step is recorded as an explicitly deferred alternative (`research.md` R1).

**Storage**: Kafka only for transport/audit (reused). Risk/fraud signals are an **in-process, seeded
fixture dataset** the agent owns (PoC scope, spec Assumption), keyed by `customer_id`; no database or
external risk service. Processed `task_id` dedup state is the runtime's existing compacted-topic
`IdempotencyTracker`.

**Testing**: `pytest` + `pytest-asyncio`; `testcontainers` Kafka for integration. New unit tests for
the policy rules, the risk-level truth table, the single-signal matrix (SC-004), mock-data lookup,
input validation, and confidence scoring; a contract test for the `RiskReviewCompletedPayload`
round-trip + registry + result-data-part shape; integration tests driving low / elevated / high,
missing/contradictory signals, malformed input → failed, idempotent re-delivery, domain isolation
(no peer call / no billing data read), and a `003`↔`005` end-to-end proving SC-009.

**Target Platform**: Local developer workstations (Docker single-broker Kafka from the foundation) for
the Kafka domain agent, plus **AWS AgentCore CLI local development** (`agentcore dev` + the AgentCore
inspector UI) for the standalone A2A entrypoint — mirroring the `004` AgentCore packaging. No remote
deployment in scope; `agentcore deploy` remains a forward-compatible future target.

**Project Type**: Single Python project. The shipped agent expands the existing single-file stub at
`apps/agents/risk_fraud/` into a small domain package plus an AgentCore app folder. The
`agent_foundation` library and `packages/contracts` are reused **unchanged**.

**Performance Goals**: PoC-scale. Task request → result + published event under ~1s p95 on a developer
laptop (one endpoint hop + handler evaluation, no peer round-trips). Throughput target: ≤50
assessments/sec, far below single-broker capacity.

**Constraints**: Local-only; single broker; single partition per topic (global order). No
auth/TLS/ACLs (deferred, Principle V). No liveness/timeout detection (spec Assumption). **No access to
any non-risk data and no synchronous call to any other agent** (FR-009, hard constitutional guardrail).
**No supervisor/router/dispatcher behavior** (FR-016).

**Scale/Scope**: 0 new shared contracts, 0 new topics, 0 new dependencies. 1 expanded agent package
(~7 modules + AgentCore app + tests). Reuses all `001`/`002`/`003`/`004` topics and the
`RiskReviewCompletedPayload` contract as-is. Runs as the risk peer in the three-agent demo
(resolution + billing + risk).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Agent Autonomy | ✅ PASS | A single scoped responsibility (risk/fraud assessment). The agent **never calls a peer synchronously** and derives every signal from its **own owned data** (FR-003, FR-009); it makes no request to obtain facts. It advertises its capability through the shared discovery mechanism and responds only to requests addressed to its endpoint — it **originates no task requests and dispatches no work** (FR-016, US7). Domain isolation is strict: no billing-eligibility or customer-workflow logic/state is read (FR-009). |
| II. Event-Driven Coordination | ✅ PASS | Every interaction is a Kafka event via the foundation transport: inbound `TaskRequest` on its endpoint topic, the A2A `TaskResult`, the domain `risk.review.completed` event, the AgentCard, and audit. A2A supplies message structure; Kafka is the sole transport. The published result carries full context (risk level, evidence, policy refs, confidence, reasoning, human-review flag, correlation) so consumers act with **no back-channel** (FR-007/FR-008). |
| III. Idempotency & Safety | ✅ PASS | Assessment is idempotent by **`task_id`**: the runtime's `IdempotencyTracker` skips a redelivered request **before the handler runs**, so no second assessment and **no duplicate domain result event** (FR-013); the duplicate is recorded as `duplicate_skipped` audit. The signals→verdict mapping is deterministic, so identical signals yield an identical verdict (FR-012). |
| IV. Observability-First | ✅ PASS | The runtime emits exactly one of `{rejected}` or `{accepted + one terminal (completed/failed)}` task-lifecycle audit events per request — carrying agent identity, task/correlation identity, causation link, timestamp, and outcome (FR-014). The handler logs request-received, the decision (with evidence and policy refs), the published result, and any human-review/failure reason via `structlog`. The trail is queryable by correlation id via the existing `query_by_correlation` (FR-015, SC-007). |
| V. PoC Scope Discipline | ✅ PASS | Reuses the entire `001`/`002` stack plus the **already-registered** `RiskReviewCompletedPayload` contract and `TOPIC_RISK_RESULT` topic — **no new dependency, no new transport, no second audit path, no new shared contract, no new topic** (FR-017, FR-019). The rules engine is the simplest deterministic mechanism that proves the verdict; mock fixtures and an illustrative policy are PoC-appropriate (spec Assumptions). The AgentCore/HTTP entrypoints reuse the libraries `004` already introduced. LLM reasoning is deferred. **No Complexity Tracking violations.** |

**Re-check after Phase 1 design**: ✅ PASS — Phase 1 introduces no third-party dependency, no new
transport, and no second audit path. The agent publishes its domain result through the **same**
foundation `Publisher` and the **same** already-registered event type/topic that `003` uses to consume
risk results; the only additions are the agent's internal domain modules (models, mock data, policy,
scoring engine, service) plus the AgentCore/HTTP shells and its tests. All five principles remain
satisfied; Complexity Tracking stays empty.

## Project Structure

### Documentation (this feature)

```text
specs/005-risk-fraud-agent/
├── plan.md              # This file (/speckit-plan output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── assess-fraud-risk.input.schema.json  # A2A task-input data-part contract
│   ├── risk-result-contract.md              # reuse of the existing published result
│   ├── fraud-policy.md                       # named rules, thresholds, precedence, scoring, mapping
│   ├── mock-risk-data.md                     # seeded fixture shape + lookup contract
│   └── topics.md                             # topic reuse (no new topics)
├── checklists/
│   └── requirements.md  # Created by /speckit-specify (if present)
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
src/agent_foundation/         # REUSED UNCHANGED (001 + 002)
├── runtime/runtime.py        # AgentRuntime — endpoint serve, accepted/completed/failed/rejected
│                             #   audit, task_id idempotency (FR-013/FR-014)
├── runtime/agent_card.py     # AgentCard, Capability — capability advertisement (FR-018)
├── runtime/discovery.py      # publish_card / find_capable — peers discover this agent (FR-018)
├── transport/publisher.py    # Publisher — validates + publishes the domain result event
├── transport/topics.py       # TOPIC_RISK_RESULT + TOPIC_NAMES (already registered) — REUSED
├── payloads/__init__.py      # PAYLOAD_REGISTRY already maps TOPIC_RISK_RESULT → payload — REUSED
└── audit/store.py            # write_task_audit / query_by_correlation — REUSED

packages/contracts/           # REUSED UNCHANGED
├── topics.py                 # TOPIC_RISK_RESULT, endpoint_topic — REUSED as-is
└── events/payloads.py        # RiskReviewCompletedPayload, EvidenceItem — REUSED as-is

apps/agents/risk_fraud/        # EXPANDED from the single-file stub into a domain package
├── __init__.py
├── identity.py               # shared identity + AgentCard (capability assess_fraud_risk) — FR-001/FR-018
├── models.py                 # domain models: RiskSignals (AccountStanding, RefundDisputeHistory,
│                             #   PaymentInstrumentSignal, BehavioralSignal, KnownFraudIndicator),
│                             #   RiskAssessmentRequest input, RiskAssessment, RiskLevel
├── mock_data.py              # seeded owned-signal dataset + lookup by customer_id (FR-003;
│                             #   miss → human review)
├── policy.py                 # named, citable fraud-policy rules + thresholds (FR-012, FR-005)
├── scoring.py                # deterministic signals × policy → level/evidence/conf/reason (rules engine)
├── service.py                # validate input → load signals → score → build outputs (pure)
├── main.py                   # Kafka A2A entrypoint: register handler, serve with a handler-owned
│                             #   domain Publisher for the result event (research R2) — REPLACES STUB
├── http_app.py               # FastAPI A2A surface for the standalone/local AgentCore HTTP path (R9)
├── dev_a2a_client.py         # dev helper: GET the card + POST sample tasks (R9)
├── agentcore/                # AWS AgentCore CLI project root config (mirrors 004) — R9
│   ├── agentcore.json        # project + A2A runtime config (entrypoint app/RiskFraud/main.py)
│   ├── aws-targets.json      # deploy targets (account/region) — array form
│   ├── .env.local            # local env vars (gitignored)
│   └── README.md             # agentcore dev / inspector run instructions
└── app/RiskFraud/            # AgentCore A2A code package (CodeZip codeLocation)
    ├── main.py               # serve_a2a(RiskFraudExecutor(), CARD) — grafts service.assess (R9)
    ├── pyproject.toml        # dev-venv deps (bedrock-agentcore[a2a], a2a-sdk, pydantic, structlog)
    └── README.md

apps/agents/
├── common.py                 # (reused) BROKER_URL; run_agent
├── customer_resolution/      # (reused, UNCHANGED) the consumer proving SC-009 end-to-end
└── billing_entitlement/      # (reused) co-running peer in the demo

apps/api/                     # (reused) drive a refund case through 003 → 004/005 and observe events

apps/agents/risk_fraud/tests/   # co-located, mirroring the 004 layout
├── __init__.py
├── conftest.py
├── test_input_validation.py     # structured-input acceptance/rejection (FR-002, FR-011)
├── test_mock_data.py            # lookup hits, misses → missing-data path (FR-003, FR-010)
├── test_fraud_policy.py         # each named rule fires on its signal; borderline boundary side
├── test_scoring.py              # full low/elevated/high truth table; single-signal matrix (SC-004);
│                                #   confidence lowering on contradiction (FR-006); known-indicator floor
├── test_result_contract.py      # RiskReviewCompletedPayload round-trip + registry + A2A result
│                                #   data-part shape consumed by 003's normalize_risk_result
├── test_domain_isolation.py     # no billing/foreign field read; signals only from owned data (SC-003)
├── test_no_supervisor.py        # originates no TaskRequest; dispatches no work (SC-008, US7)
├── test_http_entrypoint.py      # AgentCore/HTTP A2A surface: card + task + failed-on-bad-input (R9)
└── test_risk_agent_e2e.py       # A2A request→result + published event + audit; missing/contradictory
                                 #   → human review; malformed → failed; idempotent redelivery;
                                 #   003↔005 end-to-end (SC-009)
```

**Structure Decision**: Expand the existing stub at `apps/agents/risk_fraud/` into a small domain
package (`models`, `mock_data`, `policy`, `scoring`, `service`, `identity`, `main`) so the
deterministic domain logic is unit-testable in isolation from Kafka, mirroring the `004` package
shape. The AgentCore CLI footprint (`agentcore/` config + `app/RiskFraud/` code package + `http_app`
+ `dev_a2a_client`) mirrors `004` so the agent runs under `agentcore dev` and the AgentCore inspector
unchanged in shape. The `agent_foundation` library and `packages/contracts` are reused **unchanged** —
this feature adds **no** library code and **no** shared contract, honoring Principle V and
FR-017/FR-019. The agent publishes its domain result event through a **handler-owned `Publisher`** (the
same foundation class `003`/`004` use), created in the agent's async entrypoint and captured by the
handler closure (see Architecture Decision and `research.md` R2), so the runtime stays reused as-is
with no signature change.

## Architecture Decision: Dual-Path Result Delivery from a Reused Runtime

FR-008 requires the verdict to be **both** returned to the requesting peer (correlated to its task)
**and** published as a risk result event on the shared stream. The reused `AgentRuntime` already
covers the first path: the registered handler returns an `A2AMessage`, which the runtime wraps as
`TaskResult.output` on `TOPIC_TASK_RESULT` (correlated by `task_id`) and audits as `completed`. The
runtime handler signature is `(TaskRequest) -> A2AMessage` and exposes neither a publisher nor the
request envelope, so the **second path is the only addition**.

Rather than change the runtime (which `001`/`002` keep generic), the risk agent **owns a domain
`Publisher`** for the second path — exactly the pattern the `003`/`004` agents use to emit their
domain events. The agent's async entrypoint opens `async with Publisher(identity, BROKER_URL)` and
registers a handler closure that captures it; inside the handler the agent publishes the
`RiskReviewCompletedPayload` to `TOPIC_RISK_RESULT` with **`correlation_id` taken from the validated
request input's `case_id`** (which the requester sets equal to the originating case's correlation id,
so the consumer's `risk_result_handler` — keyed by `envelope.correlation_id` — matches it). The
handler then returns the `A2AMessage` carrying the same `recommendation` (the risk level string),
`confidence`, `evidence`, `reasoning_summary`, and `requires_human_review`, so the consumer's
`normalize_risk_result` adapter resolves it on the A2A path too.

The consumer (`003`) is wired to **both** paths (`result_handler` on `TOPIC_TASK_RESULT` and
`risk_result_handler` on `TOPIC_RISK_RESULT`); its per-slot `apply_result`, immediate
elevated/high-risk escalation, and `DECIDED`/terminal guards make the duplicate delivery idempotent
(one decision per case). Idempotency of the producer side is provided by the runtime's `task_id`
dedup, which skips redelivered requests **before** the handler runs, so the domain event is published
at most once per logical request (FR-013). See `research.md` R2/R3/R8.

## Architecture Decision: AgentCore CLI Local Development Parity

US/operational requirement: the agent must run under `agentcore dev` and be inspectable in the
AgentCore UI. This mirrors `004` exactly. AgentCore's `serve_a2a` speaks the standard `a2a-sdk` wire
protocol (JSON-RPC `message/send` / `message/stream`), which is **distinct** from this repo's internal
A2A-over-Kafka runtime (feature 002). The AgentCore entrypoint (`app/RiskFraud/main.py`) is therefore
a thin runtime shell that **reuses `service.assess` unchanged** and only adapts I/O to the AgentCore
A2A contract; the monorepo trees (`apps/`, `packages/`, `src/`) are put on `sys.path` from source so
the auto-created dev venv only needs the third-party A2A libraries. The Kafka entrypoint
(`main.py`) remains the agent used in the full three-agent event-driven demo and is the only path that
publishes the `risk.review.completed` event (the AgentCore path is standalone, US-2 publication stays
the Kafka entrypoint's job). See `research.md` R9.

## Complexity Tracking

> No Constitution Check violations. This feature adds no new dependency, no new transport, no new
> shared contract, and no new topic; it reuses the already-registered risk result contract/topic and
> the runtime as-is, and reuses the AgentCore/HTTP libraries `004` already introduced. The rules
> engine is the simplest deterministic mechanism that proves the verdict. Table intentionally empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |
