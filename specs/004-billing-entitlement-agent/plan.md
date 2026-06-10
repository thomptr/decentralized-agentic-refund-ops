# Implementation Plan: Billing and Entitlement Agent

**Branch**: `004-billing-entitlement-agent` | **Date**: 2026-06-09 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/004-billing-entitlement-agent/spec.md`

## Summary

Ship the **Billing and Entitlement Agent** — an independent domain agent that owns subscription,
invoice, payment, entitlement, refund-policy, and product-usage analysis — on top of the
`001-event-foundation` transport and the `002-a2a-runtime-contract` runtime. The agent advertises one
A2A capability, **`analyze_refund_eligibility`**, via the shared capability-discovery mechanism. On
each accepted task it **validates the structured task input**, loads the **billing facts it owns**
(seeded mock dataset across the five domains), **evaluates refund eligibility with a deterministic
rules engine** against a **named, citable refund policy**, and returns a structured recommendation
(approve / deny / requires-human-review) carrying a confidence score, an evidence set, the policy
references applied, and a reasoning summary.

The result is delivered on **two correlated paths** (FR-008): the runtime returns it to the
requesting peer as the A2A `TaskResult.output`, and the agent **publishes a
`BillingRefundAnalysisCompletedPayload` to `local.billing.refund-analysis.completed.v1`
(`TOPIC_BILLING_RESULT`)** so any consumer — notably the existing Customer Resolution Agent — sees a
self-describing billing verdict on the shared event stream. The runtime emits the **accepted /
completed / failed / rejected** task-lifecycle audit events automatically (FR-014), and dedups by
`task_id` so a redelivered request neither re-analyzes nor double-publishes (FR-013).

**This feature replaces the existing mock stub** at `apps/agents/billing_entitlement/main.py` (which
returns a fixed `{"eligible": true}` verdict) with the real domain agent. Crucially, the shared
contract and topic the stub's consumer expects **already exist and are already registered** in the
foundation (`TOPIC_BILLING_RESULT` in `transport/topics.py:TOPIC_NAMES`,
`BillingRefundAnalysisCompletedPayload` in `payloads/__init__.py:PAYLOAD_REGISTRY`, the topic in
`_CANONICAL_TOPICS`, and the consumer's `billing_result_handler` in the resolution agent). The agent
therefore **adds no new cross-cutting contract, no new topic, and no new dependency** — only its own
domain package. It makes **no synchronous peer call**, reads **no** risk/fraud/customer-workflow
state, and acts as **no** supervisor, router, or dispatcher.

## Technical Context

**Language/Version**: Python 3.12 (single version per constitution; matches `001`/`002`/`003`).

**Primary Dependencies** (all already present — **no new dependency**):
- `pydantic` v2 — domain fact models, the `analyze_refund_eligibility` input model, the
  `EligibilityRecommendation` domain model, reuse of `BillingRefundAnalysisCompletedPayload`.
- `aiokafka` — endpoint consumption, result/audit/card publishing, and the domain result event, all
  via the foundation `Publisher`/`AgentRuntime` (reused unchanged).
- `structlog` — structured per-step logging (Principle IV).
- `agent_foundation.runtime` — `AgentRuntime` (card + endpoint + lifecycle audit + task-id
  idempotency), `AgentCard`/`Capability` for discovery advertisement.
- `pytest`, `pytest-asyncio`, `testcontainers[kafka]` — unit/contract/integration tests.

**Reasoning approach**: **Deterministic rule-based** evaluation (no LLM / Bedrock / `boto3`). FR-012
mandates that identical facts under the same policy yield the same verdict; the constitution's
determinism and PoC-scope principles, plus consistency with the `003` decision engine, make a pure
rules engine the simplest mechanism that proves the hypothesis. An optional LLM reasoning step is
recorded as an explicitly deferred alternative (`research.md` R1).

**Storage**: Kafka only for transport/audit (reused). Billing facts are an **in-process, seeded
fixture dataset** the agent owns (PoC scope, spec Assumption); no database or external billing
service. Processed `task_id` dedup state is the runtime's existing compacted-topic `IdempotencyTracker`.

**Testing**: `pytest` + `pytest-asyncio`; `testcontainers` Kafka for integration. New unit tests for
the policy rules, the eligibility truth table, mock-data lookup, input validation, and confidence
scoring; a contract test for the `BillingRefundAnalysisCompletedPayload` round-trip + registry +
result-data-part shape; integration tests driving approve / deny / requires-human-review,
missing/contradictory data, malformed input → failed, idempotent re-delivery, domain isolation
(no peer call / no foreign data), and a `003`↔`004` end-to-end proving SC-009.

**Target Platform**: Local developer workstations (Docker single-broker Kafka from the foundation).
No remote deployment in scope; AWS Bedrock AgentCore remains a forward-compatible future target (the
`AgentCard` is the A2A discovery format AgentCore can serve).

**Project Type**: Single Python project. The shipped agent expands the existing single-file stub at
`apps/agents/billing_entitlement/` into a small domain package. The `agent_foundation` library and
`packages/contracts` are reused **unchanged**.

**Performance Goals**: PoC-scale. Task request → result + published event under ~1s p95 on a
developer laptop (one endpoint hop + handler evaluation, no peer round-trips). Throughput target:
≤50 analyses/sec, far below single-broker capacity.

**Constraints**: Local-only; single broker; single partition per topic (global order). No
auth/TLS/ACLs (deferred, Principle V). No liveness/timeout detection (spec Assumption). **No access
to any non-billing data and no synchronous call to any other agent** (FR-009, hard constitutional
guardrail). **No supervisor/router/dispatcher behavior** (FR-016).

**Scale/Scope**: 0 new shared contracts, 0 new topics, 0 new dependencies. 1 expanded agent package
(~6 modules + tests). Reuses all `001`/`002`/`003` topics and the `BillingRefundAnalysisCompletedPayload`
contract as-is. Runs as the billing peer in the three-agent demo (resolution + billing + risk).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Agent Autonomy | ✅ PASS | A single scoped responsibility (billing/entitlement refund-eligibility analysis). The agent **never calls a peer synchronously** and derives every fact from its **own owned data** (FR-003, FR-009); it makes no request to obtain facts. It advertises its capability through the shared discovery mechanism and responds only to requests addressed to its endpoint — it **originates no task requests and dispatches no work** (FR-016, US7). Domain isolation is strict: no risk/fraud/customer-workflow logic or state is read (FR-009). |
| II. Event-Driven Coordination | ✅ PASS | Every interaction is a Kafka event via the foundation transport: inbound `TaskRequest` on its endpoint topic, the A2A `TaskResult`, the domain `billing.refund-analysis.completed` event, the AgentCard, and audit. A2A supplies message structure; Kafka is the sole transport. The published result carries full context (recommendation, evidence, policy refs, confidence, reasoning, correlation) so consumers act with **no back-channel** (FR-007/FR-008). |
| III. Idempotency & Safety | ✅ PASS | Analysis is idempotent by **`task_id`**: the runtime's `IdempotencyTracker` skips a redelivered request **before the handler runs**, so no second analysis and **no duplicate domain result event** (FR-013); the duplicate is recorded as `duplicate_skipped` audit. The fact→verdict mapping is deterministic, so identical facts yield an identical verdict (FR-012). |
| IV. Observability-First | ✅ PASS | The runtime emits exactly one of `{rejected}` or `{accepted + one terminal (completed/failed)}` task-lifecycle audit events per request — carrying agent identity, task/correlation identity, causation link, timestamp, and outcome (FR-014). The handler logs request-received, the decision (with evidence and policy refs), the published result, and any human-review/failure reason via `structlog`. The trail is queryable by correlation id via the existing `query_by_correlation` (FR-015, SC-007). |
| V. PoC Scope Discipline | ✅ PASS | Reuses the entire `001`/`002` stack plus the **already-registered** `BillingRefundAnalysisCompletedPayload` contract and `TOPIC_BILLING_RESULT` topic — **no new dependency, no new transport, no second audit path, no new shared contract, no new topic** (FR-017, FR-019). The rules engine is the simplest deterministic mechanism that proves the verdict; mock fixtures and an illustrative policy are PoC-appropriate (spec Assumptions). LLM reasoning is deferred. **No Complexity Tracking violations.** |

**Re-check after Phase 1 design**: ✅ PASS — Phase 1 introduces no third-party dependency, no new
transport, and no second audit path. The agent publishes its domain result through the **same**
foundation `Publisher` and the **same** already-registered event type/topic that `003` uses to
consume billing results; the only additions are the agent's internal domain modules (facts, mock
data, policy, rules engine, service) and its tests. All five principles remain satisfied; Complexity
Tracking stays empty.

## Project Structure

### Documentation (this feature)

```text
specs/004-billing-entitlement-agent/
├── plan.md              # This file (/speckit-plan output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── analyze-refund-eligibility.input.schema.json  # A2A task-input data-part contract
│   ├── billing-result-contract.md                    # reuse of the existing published result
│   ├── refund-policy.md                              # named rules, thresholds, precedence, mapping
│   ├── mock-billing-data.md                          # seeded fixture shape + lookup contract
│   └── topics.md                                     # topic reuse (no new topics)
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
├── transport/topics.py       # TOPIC_BILLING_RESULT + TOPIC_NAMES (already registered) — REUSED
├── payloads/__init__.py      # PAYLOAD_REGISTRY already maps TOPIC_BILLING_RESULT → payload — REUSED
└── audit/store.py            # write_task_audit / query_by_correlation — REUSED

packages/contracts/           # REUSED UNCHANGED
├── topics.py                 # TOPIC_BILLING_RESULT, endpoint_topic — REUSED as-is
└── events/payloads.py        # BillingRefundAnalysisCompletedPayload, EvidenceItem — REUSED as-is

apps/agents/billing_entitlement/      # EXPANDED from the single-file stub into a domain package
├── __init__.py
├── main.py                   # entrypoint: identity/card, register handler, serve with a
│                             #   handler-owned domain Publisher for the result event (research R2)
├── models.py                 # domain models: BillingFacts (Subscription, Invoice, Payment,
│                             #   Entitlement, ProductUsage), RefundEligibilityRequest input,
│                             #   EligibilityRecommendation
├── mock_data.py              # seeded owned-fact dataset + lookup (FR-003; missing → human review)
├── policy.py                 # named, citable refund-policy rules + thresholds (FR-012, FR-005)
├── rules_engine.py           # deterministic facts × policy → recommendation/evidence/conf/reason
└── service.py                # validate input → load facts → evaluate → build result payload (pure)

apps/agents/
├── common.py                 # (reused) BROKER_URL; run_agent — see research R2 for the entrypoint
├── customer_resolution/      # (reused) the consumer proving SC-009 end-to-end
└── risk_fraud/main.py        # (reused stub) co-running peer in the demo

apps/api/
├── dev_publish_ticket.py     # (reused) drive an end-to-end refund case through 003 → 004
└── dev_consume_events.py     # (reused) observe billing result + audit events

apps/agents/billing_entitlement/tests/   # co-located, mirroring the 003 layout
├── __init__.py
├── conftest.py
├── test_input_validation.py     # structured-input acceptance/rejection (FR-002, FR-011)
├── test_mock_data.py            # lookup hits, misses → missing-data path (FR-003, FR-010)
├── test_refund_policy.py        # each named rule fires on its fact; borderline boundary side
├── test_rules_engine.py         # full approve/deny/human-review truth table; single-fact matrix
│                                #   (SC-004); confidence lowering on contradiction (FR-006)
├── test_result_contract.py      # BillingRefundAnalysisCompletedPayload round-trip + registry +
│                                #   A2A result data-part shape consumed by 003's normalizer
├── test_domain_isolation.py     # no foreign-domain field read; facts only from owned data (SC-003)
├── test_no_supervisor.py        # originates no TaskRequest; dispatches no work (SC-008, US7)
└── test_billing_agent_e2e.py    # A2A request→result + published event + audit; missing/contradictory
                                 #   → human review; malformed → failed; idempotent redelivery;
                                 #   003↔004 end-to-end (SC-009)
```

**Structure Decision**: Expand the existing stub at `apps/agents/billing_entitlement/` into a small
domain package (`models`, `mock_data`, `policy`, `rules_engine`, `service`, `main`) so the
deterministic domain logic is unit-testable in isolation from Kafka, mirroring the `003` package
shape. The `agent_foundation` library and `packages/contracts` are reused **unchanged** — this
feature adds **no** library code and **no** shared contract, honoring Principle V and FR-017/FR-019.
The agent publishes its domain result event through a **handler-owned `Publisher`** (the same
foundation class `003` uses), created in the agent's async entrypoint and captured by the handler
closure (see Architecture Decision and `research.md` R2), so the runtime stays reused as-is with no
signature change.

## Architecture Decision: Dual-Path Result Delivery from a Reused Runtime

FR-008 requires the verdict to be **both** returned to the requesting peer (correlated to its task)
**and** published as a billing result event on the shared stream. The reused `AgentRuntime` already
covers the first path: the registered handler returns an `A2AMessage`, which the runtime wraps as
`TaskResult.output` on `TOPIC_TASK_RESULT` (correlated by `task_id`) and audits as `completed`. The
runtime handler signature is `(TaskRequest) -> A2AMessage` and exposes neither a publisher nor the
request envelope, so the **second path is the only addition**.

Rather than change the runtime (which `001`/`002` keep generic), the billing agent **owns a domain
`Publisher`** for the second path — exactly the pattern the `003` resolution agent uses to emit its
domain events. The agent's async entrypoint opens `async with Publisher(identity, BROKER_URL)` and
registers a handler closure that captures it; inside the handler the agent publishes the
`BillingRefundAnalysisCompletedPayload` to `TOPIC_BILLING_RESULT` with **`correlation_id` taken from
the validated request input's `case_id`** (which the requester sets equal to the originating case's
correlation id, so the consumer's `billing_result_handler` — keyed by `envelope.correlation_id` —
matches it). The handler then returns the `A2AMessage` carrying the same `recommendation`,
`confidence`, `evidence`, `reasoning_summary`, and `requires_human_review`, so the consumer's
`normalize_billing_result` adapter resolves it on the A2A path too.

The consumer (`003`) is wired to **both** paths (`result_handler` on `TOPIC_TASK_RESULT` and
`billing_result_handler` on `TOPIC_BILLING_RESULT`); its per-slot `apply_result` and
`DECIDED`/terminal guards make the duplicate delivery idempotent (one decision per case). Idempotency
of the producer side is provided by the runtime's `task_id` dedup, which skips redelivered requests
**before** the handler runs, so the domain event is published at most once per logical request
(FR-013). See `research.md` R2/R3/R8.

## Complexity Tracking

> No Constitution Check violations. This feature adds no new dependency, no new transport, no new
> shared contract, and no new topic; it reuses the already-registered billing result contract/topic
> and the runtime as-is. The rules engine is the simplest deterministic mechanism that proves the
> verdict. Table intentionally empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |
