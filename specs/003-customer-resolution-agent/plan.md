# Implementation Plan: Customer Resolution Agent

**Branch**: `003-customer-resolution-agent` | **Date**: 2026-06-09 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/003-customer-resolution-agent/spec.md`

## Summary

Ship the **Customer Resolution Agent** — the first true domain agent in the decentralized
RefundOps demo — on top of the `001-event-foundation` transport and the `002-a2a-runtime-contract`
runtime. The agent **consumes `support.ticket.created` events from Kafka**, runs a deterministic
**triage** to decide refund-vs-direct-response, and for refund cases **delegates a billing analysis
and a risk analysis to peer agents via A2A task requests** (addressing each peer's endpoint topic
discovered through the shared capability-discovery mechanism — no router). It then **consumes the
two analysis results asynchronously from the shared task-result topic, correlates them to the
originating case, applies a deterministic decision policy, and emits exactly one final
`customer.resolution.decided` event** (approve refund / deny refund / escalate to human), keeping a
case open until both results arrive and never emitting a second or contradictory decision.

The agent owns **only**: ticket intake, triage, peer task requests for its own cases, result
aggregation for its own correlation IDs, final response drafting, and case closure. It reaches **no**
billing/subscription/payment/fraud/risk data store directly; every such fact enters exclusively as a
peer result. It is **not** a supervisor, router, dispatcher, or orchestrator.

The feature reuses the runtime's `EventEnvelope`, `Publisher`/`Consumer`, `IdempotencyTracker`,
audit subsystem, `TaskRequest`/`TaskResult` contracts, `AgentCard` discovery, and topic conventions
as-is. It adds only the customer-resolution domain logic, one new domain event contract
(`CustomerResponseDecisionPayload`), and its topic. Billing and risk peers remain the existing demo
stubs; this feature depends on their *published capabilities and result contracts*, not their
internals.

## Technical Context

**Language/Version**: Python 3.12 (single version per constitution; matches `001`/`002`).

**Primary Dependencies** (all already present — **no new dependency**):
- `pydantic` v2 — `CustomerResponseDecisionPayload`, `ResolutionCase`, triage/decision models.
- `aiokafka` — ticket-intake consumer, task-result consumer, request/decision publishers, via the
  existing `Publisher`/`Consumer`.
- `structlog` — structured per-step logging (Principle IV).
- `agent_foundation.runtime` — `AgentRuntime` (card + endpoint), `A2AClient`/`Publisher` for task
  requests, `discover.find_capable` for peer endpoint discovery.
- `pytest`, `pytest-asyncio`, `testcontainers[kafka]` — unit/contract/integration tests.

**Reasoning approach**: **Deterministic rule-based** triage and decision policy. No LLM / Bedrock /
`boto3` is introduced (the codebase currently has none, and the user directive plus the spec's
edge-case table require *deterministic* classification and decision rules). An LLM triage step is
recorded as an explicitly deferred alternative in `research.md` (R1).

**Storage**: Kafka only for transport/audit (reused). Resolution-case working state is an
**in-process store keyed by correlation_id** (PoC scope); durability across restart is a documented
gap (research R6), consistent with the runtime's "liveness/timeout out of scope" stance.

**Testing**: `pytest` + `pytest-asyncio`; `testcontainers` Kafka for integration. New unit tests for
triage rules, the decision-policy truth table, and case-aggregation state; a contract test for the
new decision payload round-trip; integration tests driving non-refund, approve, deny, escalate (risk
/ conflict / peer-failure), idempotent re-delivery, and late-result-after-decision end-to-end.

**Target Platform**: Local developer workstations (Docker single-broker Kafka from the foundation).
No remote deployment in scope; AWS Bedrock AgentCore remains a forward-compatible future target.

**Project Type**: Single Python project. The shipped agent lives under `apps/agents/customer_resolution/`
(expanding the existing stub into a domain package); the one new domain contract lives in
`packages/contracts/`. The `src/agent_foundation` library is reused **unchanged**.

**Performance Goals**: PoC-scale. Ticket → final decision under ~3s p95 on a developer laptop (two
A2A round-trips that proceed concurrently). Throughput target: ≤50 tickets/sec, far below
single-broker capacity.

**Constraints**: Local-only; single broker; single partition per topic (global order). No
auth/TLS/ACLs (deferred, Principle V). **No liveness/timeout detection** — a case with only one
result stays open (documented gap, spec Assumptions). No direct billing/payment/fraud/risk data
access (FR-005, hard constitutional guardrail).

**Scale/Scope**: 1 new domain event contract + 1 topic; 1 expanded agent package (~5 modules);
reuses all `001`/`002` topics. Three concurrent demo agents (resolution + billing + risk stub).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Agent Autonomy | ✅ PASS | The agent has a single scoped responsibility (customer resolution) and never calls a peer synchronously — every interaction (ticket intake, task request, result, decision, audit) is a Kafka event. It addresses billing/risk **endpoint topics directly** via discovery (FR-017); **no supervisor/router/orchestrator** is introduced or used (FR-015, US6). Domain isolation is preserved: it owns no billing/risk logic and reads no billing/fraud data store (FR-005, US5). |
| II. Event-Driven Coordination | ✅ PASS | Intake (`support.ticket.created`), delegation (`TaskRequest` to peer endpoint topics), results (shared `task.result` topic), the final `customer.resolution.decided` event, and audit all traverse Kafka via the foundation's `Publisher`/`Consumer`. A2A supplies message structure; Kafka is the sole transport. Each event carries full context (correlation/causation) for the receiver to act without back-channels. |
| III. Idempotency & Safety | ✅ PASS | Ticket processing is idempotent by **ticket identity** — a case is created once per `correlation_id`/`ticket_id`; re-delivery produces no duplicate task requests and no duplicate decision (FR-011), recorded as `duplicate` in the audit trail. Exactly one final decision per case; a late/duplicate result after the decision is **recorded, not applied** (FR-012). Event-level dedup reuses `IdempotencyTracker` on each consumer. |
| IV. Observability-First | ✅ PASS | Every significant step — ticket received, triage determination, each delegation, each result consumed, final decision, escalation reason — emits a structured log and an audit event carrying agent identity, ticket/correlation identity, causation link, timestamp, outcome, and (for escalations) reason (FR-013). The trail is queryable by `correlation_id` via the existing `query_by_correlation` (FR-014, SC-006). |
| V. PoC Scope Discipline | ✅ PASS | Reuses the entire `001`/`002` stack with **no new dependency** and **no new transport/audit path** (FR-016). Triage and decision are the *simplest* deterministic rules that prove the workflow; LLM reasoning is deferred. The single new contract (`CustomerResponseDecisionPayload`) and its topic are required to emit the auditable final decision (spec Assumption: the decision is an emitted, correlated event). In-process case state (vs. a compacted case topic) is the simpler choice; the durability gap is documented, not worked around. **No Complexity Tracking violations.** |

**Re-check after Phase 1 design**: ✅ PASS — Phase 1 introduces no new third-party dependency, no
new transport, and no second audit path. The only additions are one domain payload + its topic
(registered in the payload registry exactly as the foundation registers `support.ticket.created`),
and in-process domain state. All five principles remain satisfied; Complexity Tracking stays empty.

## Project Structure

### Documentation (this feature)

```text
specs/003-customer-resolution-agent/
├── plan.md              # This file (/speckit-plan output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── customer-response-decision.schema.json   # new domain event payload
│   ├── analysis-result-contract.md              # billing/risk result shape the agent consumes
│   ├── decision-policy.md                        # deterministic triage + decision truth tables
│   └── topics.md                                 # topic deltas for this feature
├── checklists/
│   └── requirements.md  # Created by /speckit-specify
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
src/agent_foundation/        # REUSED UNCHANGED (001 + 002)
├── envelope.py              # EventEnvelope, AgentIdentity
├── idempotency.py           # IdempotencyTracker (event-level dedup)
├── transport/
│   ├── publisher.py         # Publisher.publish(..., topic=...) — send TaskRequest + decision events
│   └── consumer.py          # Consumer — ticket-intake + task-result consumers
├── runtime/
│   ├── runtime.py           # AgentRuntime — publishes AgentCard, exposes endpoint (FR-001)
│   ├── client.py            # A2AClient — task-request send mechanism
│   ├── discovery.py         # find_capable() — discover billing/risk endpoints (FR-017)
│   └── agent_card.py        # AgentCard, Capability
├── payloads/
│   ├── __init__.py          # PAYLOAD_REGISTRY — register customer.resolution.decided.v1
│   └── task.py              # TaskRequest, TaskResult, TaskError
└── audit/store.py           # write_audit / write_task_audit / query_by_correlation (REUSED)

packages/contracts/
├── topics.py                # (modified) add TOPIC_RESOLUTION_DECIDED + ticket topic helper
└── events/
    └── payloads.py          # (modified) add CustomerResponseDecisionPayload; reuse Billing/Risk
                             #             analysis result payloads as the consumed result contract

apps/agents/customer_resolution/      # EXPANDED from stub into a domain package
├── __init__.py
├── main.py                  # entrypoint: build identity/card, wire consumers + runtime, run
├── triage.py                # deterministic triage rules (refund vs direct response) — FR-002/003
├── decision.py              # deterministic decision policy (approve/deny/escalate) — FR-009
├── case.py                  # ResolutionCase model + in-process CaseStore (keyed by correlation_id)
└── service.py               # ResolutionService: orchestrates intake→delegate→aggregate→decide

apps/agents/
├── common.py                # (reused) run_agent bootstrap; BROKER_URL
├── billing_entitlement/main.py   # (reused demo stub) — billing peer
└── risk_fraud/main.py            # (reused demo stub) — risk peer

apps/api/
├── dev_publish_ticket.py    # (reused) publish a support.ticket.created event to drive the demo
└── dev_consume_events.py    # (reused) observe audit + decision events

tests/
├── unit/
│   ├── test_triage.py             # (new) refund/non-refund/ambiguous classification
│   ├── test_decision_policy.py    # (new) full approve/deny/escalate truth table
│   └── test_resolution_case.py    # (new) aggregation, completeness, idempotency, late result
├── contract/
│   └── test_resolution_schemas.py # (new) CustomerResponseDecisionPayload round-trip + registry
└── integration/
    └── test_customer_resolution.py # (new) end-to-end: non-refund, approve, deny, escalate
                                     #        (risk/conflict/peer-failure), idempotent re-delivery,
                                     #        late-result-after-decision, audit-by-correlation
```

**Structure Decision**: Keep the shipped agent under `apps/agents/customer_resolution/`, expanding
the current single-file stub into a small domain package (`triage`, `decision`, `case`, `service`,
`main`) so the deterministic domain logic is unit-testable in isolation from Kafka. The
`agent_foundation` library is reused **unchanged** — this feature adds no library code, honoring
Principle V (no premature library growth) and FR-016 (reuse the runtime, no parallel path). The one
new cross-cutting contract (`CustomerResponseDecisionPayload`) lives in `packages/contracts` beside
the existing domain payloads, and is registered in the foundation `PAYLOAD_REGISTRY` exactly as
`support.ticket.created.v1` already is.

## Architecture Decision: Asynchronous Case Aggregation (not blocking submit)

The existing stub uses `A2AClient.submit()`, which **blocks** awaiting a single correlated
`TaskResult`. Spec 003 requires a different model (FR-006, FR-008, FR-012; US3 scenarios 2–4): the
agent sends **two** independent requests, **keeps the case open** until **both** results arrive as
Kafka events, and must tolerate **late/duplicate results after a decision**. A blocking
`gather(submit, submit)` cannot represent "case open pending the second result" as first-class
state, cannot record late-after-decision results, and ties up a task with no liveness story.

Therefore the agent is built as **three concurrent Kafka loops** sharing an in-process `CaseStore`:

1. **Intake loop** — `Consumer` on `support.ticket.created` → triage → create case (idempotent by
   ticket identity) → if refund: discover billing/risk endpoints and **publish two `TaskRequest`s**
   (recording each `task_id` on the case); if non-refund: emit a `direct_response` decision and close.
2. **Result loop** — `Consumer` on the shared `task.result` topic → map `task_id` → case → store the
   result → if **both** present (or a failure/rejection forces it) → apply the decision policy →
   **emit exactly one** `customer.resolution.decided` event → mark case decided. Results for an
   already-decided case are recorded in audit, not applied (FR-012).
3. **Runtime/card** — `AgentRuntime` publishes the agent's `AgentCard` and exposes its endpoint so
   the agent is a discoverable, addressable participant on the runtime (FR-001).

Correlation is by **`task_id`** (the agent knows each case's billing and risk `task_id`) and the
shared envelope **`correlation_id`** (used for the case key and audit queries). This matches the
runtime's existing correlation guarantees and keeps the agent a pure requester/aggregator with no
router behavior. See `research.md` R2/R3 and `data-model.md` for the case state machine.

## Complexity Tracking

> No Constitution Check violations. This feature adds no new dependency, no new transport, and no
> second audit path; triage and decision are the simplest deterministic rules that prove the
> workflow. Table intentionally empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |
