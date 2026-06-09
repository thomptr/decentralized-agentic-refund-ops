---
description: "Task list for Customer Resolution Agent implementation"
---

# Tasks: Customer Resolution Agent

**Input**: Design documents from `/specs/003-customer-resolution-agent/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: INCLUDED — the plan's "Testing" section and quickstart.md "Automated validation" explicitly
require unit (triage, decision truth table, case aggregation), contract (decision payload round-trip),
and integration tests. Test tasks are therefore generated below.

**Organization**: Tasks are grouped by user story (US1–US6 from spec.md) for independent
implementation and testing.

## File-layout note

This task list follows the **package layout supplied in the `/speckit-tasks` request** (which
overrides the module names sketched in plan.md). The plan's concepts map onto the requested files as:

| plan.md concept | This package file (`apps/agents/customer_resolution/`) |
|-----------------|--------------------------------------------------------|
| `triage.py` (classify) | `ticket_classifier.py` |
| `decision.py` (decide + thresholds) | `decision_engine.py` |
| `decision.py` response templates | `response_drafter.py` |
| `case.py` models | `models.py` |
| `case.py` CaseStore | `state_store.py` |
| `service.py` orchestration | `agent.py` |
| `main.py` entrypoint | `main.py` |
| consumers (intake + result) | `event_handlers.py` |
| runtime/card/discovery/delegation | `a2a_handlers.py` |
| (new) | `config.py` |

Tests live in `apps/agents/customer_resolution/tests/` so the agent package is self-contained and
**runs independently** (acceptance criterion). The only edits **outside** the agent package are the
single new shared contract + its topic + registry entry (Phase 2), required because the agent's final
decision is an emitted, registered domain event (research R8, contracts/topics.md). All billing/risk
analysis enters **only** as peer `TaskResult` events — **no billing or risk business logic is
implemented in this package** (FR-005, acceptance criterion).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: User story the task belongs to (US1–US6)
- Each task includes an exact file path

## Path Conventions

- Agent package: `apps/agents/customer_resolution/`
- Agent tests: `apps/agents/customer_resolution/tests/`
- Shared contracts (reused/extended): `packages/contracts/`
- Foundation library (reused; one registry edit only): `src/agent_foundation/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project scaffolding for the agent package and its test suite.

- [X] T001 Create the agent package skeleton under `apps/agents/customer_resolution/`: ensure `__init__.py` exists and add empty, docstring-only module stubs `config.py`, `models.py`, `state_store.py`, `ticket_classifier.py`, `decision_engine.py`, `response_drafter.py`, `event_handlers.py`, `a2a_handlers.py`, `agent.py` (keep existing `main.py`)
- [X] T002 [P] Create the test package `apps/agents/customer_resolution/tests/__init__.py` and a `conftest.py` with shared fixtures (sample `SupportTicketCreatedPayload`, billing/risk `TaskResult` builders for completed/failed/rejected, an in-memory `CaseStore` fixture)
- [X] T003 [P] Register the  console-script entrypoint (→ `apps.agents.customer_resolution.main:run`) in `pyproject.toml` and confirm `ruff`/`mypy` config covers `apps/agents/customer_resolution/` (matches the existing `demo-billing-entitlement` / `demo-risk-fraud` pattern)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The one new shared contract + topic + registry entry, plus the agent's internal models,
config, case store, and process skeleton. Everything in Phases 3+ depends on these.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T004 Add ` (`approve_refund`/`deny_refund`/`escalate_human`/`direct_response`) and the `CustomerResponseDecisionPayload` model — with field validation that `escalation_reason` is non-null **iff** `outcome == escalate_human` (FR-010) — to `packages/contracts/events/payloads.py` (per data-model.md §7)
- [X] T005 [P] Add the  constant resolving to `local.customer.resolution.decided.v1` (via `topic_for("customer","resolution","decided")`) in `packages/contracts/topics.py` (per contracts/topics.md)
- [X] T006 Register `"local.customer.resolution.decided.v1": CustomerResponseDecisionPayload` in `PAYLOAD_REGISTRY` in `src/agent_foundation/payloads/__init__.py` so `Publisher`/`Consumer` validate it on send/receive (contracts/topics.md) — **only foundation edit in this feature**
- [X] T007 Add  to the canonical topic-creation list in `src/agent_foundation/transport/topics.py` so the demo provisions it on startup (contracts/topics.md "Topic creation")
- [X] T008 [P] Implement the internal domain models in `apps/agents/customer_resolution/models.py`: `Triage`, `BillingFinding`, `RiskFinding`, `AnalysisSlot`, `CaseStatus` (enum), and `ResolutionCase` (per data-model.md §2–§4), all Pydantic v2 with `frozen`/`extra="forbid"` where specified
- [X] T009 [P] Implement `: agent identity (`customer-resolution-agent`), peer capability ids (`analyze_refund_eligibility`, `assess_fraud_risk`), broker URL (reuse `apps/agents/common.py`), refund-intent vocabulary, and decision thresholds (`ELEVATED_RISK_THRESHOLD=0.5`, high=0.8) as named constants (research R1/R4)
- [X] T010 Implement the in-process ` in `apps/agents/customer_resolution/state_store.py`: `get_or_create(correlation_id, ...)` (idempotent — returns existing case on re-delivery), `get_by_task_id(task_id)`, and `save`/update helpers keyed by `correlation_id` (data-model.md §4, research R5/R6)
- [X] T011 Implement the agent process skeleton in `apps/agents/customer_resolution/agent.py` (the `ResolutionService` that holds the shared `CaseStore` and wires components) and `apps/agents/customer_resolution/main.py` (`run()` entrypoint that builds identity/card and starts the runtime + intake consumer + result consumer concurrently via `asyncio.gather`) — **importing the event foundation (Spec 001) transport/envelope/audit and the A2A runtime (Spec 002)**, no parallel transport (FR-016, research R7)

**Checkpoint**: Contract registered, topic provisioned, models/config/store/process skeleton in place — user stories can now begin.

---

## Phase 3: User Story 1 - Triage an Incoming Support Ticket (Priority: P1) 🎯 MVP

**Goal**: The agent ingests a `support.ticket.created` event, deterministically classifies it as
refund-review vs. direct-response, records the determination on the case, and for non-refund tickets
emits a single `direct_response` decision with **zero** peer requests.

**Independent Test**: Publish a non-refund ticket ("how do I change my email") → agent emits one
`customer.resolution.decided` with `outcome=direct_response`, no `task.requested` events; publish a
clear refund ticket → agent records `needs_refund_review=true` and advances to delegation.

### Tests for User Story 1

- [X] T012 [P] [US1] Unit test the triage rules in `apps/agents/customer_resolution/tests/test_ticket_classifier.py` — refund-signal hit, clear non-refund, and empty/ambiguous→default-to-review with ambiguity recorded (decision-policy.md §A)
- [X] T013 [P] [US1] Contract test `CustomerResponseDecisionPayload` round-trip + registry lookup + the `escalation_reason`-iff-escalate validation in `apps/agents/customer_resolution/tests/test_resolution_schemas.py` (data-model.md §7)
- [ ] T014 [P] [US1] Integration test "non-refund ticket → direct_response, no peer requests" in `apps/agents/customer_resolution/tests/test_customer_resolution.py` (quickstart Scenario 1, SC-001)

### Implementation for User Story 1

- [X] T015 [US1] Implement `classify(ticket) -> Triage` (pure, deterministic; matches refund vocabulary, sets `matched_signals`, defaults ambiguous→review with rationale) in `apps/agents/customer_resolution/ticket_classifier.py` (decision-policy.md §A, FR-002/FR-003)
- [X] T016 [US1] Implement the `direct_response` customer-message template (and outcome-keyed dispatch stub for the other outcomes) in `apps/agents/customer_resolution/response_drafter.py` (decision-policy.md §C "Customer response draft")
- [X] T017 [US1] Implement the `direct_response` branch of `decide(...)` in `apps/agents/customer_resolution/decision_engine.py` (row 1 of the truth table) producing a `CustomerResponseDecisionPayload` with null billing/risk summaries (decision-policy.md §C/§D)
- [X] T018 [US1] Implement the intake handler in `apps/agents/customer_resolution/event_handlers.py`: consume `support.ticket.created` with `IdempotencyTracker`, `get_or_create` the case, run triage, and for **non-refund** emit the `direct_response` decision to `TOPIC_RESOLUTION_DECIDED` and close the case (`CLOSED_DIRECT`) (FR-002, US1)
- [X] T019 [US1] Wire the intake `Consumer` into `agent.py`/`main.py` and run it under the process `asyncio.gather` (depends on T011)

**Checkpoint**: A non-refund ticket flows end-to-end to a direct-response decision with no peer calls — MVP demoable.

---

## Phase 4: User Story 2 - Delegate Billing and Risk Analysis to Peers (Priority: P1)

**Goal**: For a refund-review ticket the agent discovers the billing and risk peer endpoints and
publishes **exactly two** correlated A2A `TaskRequest`s (one per peer endpoint topic), recording each
`task_id` on the case — reading no billing/fraud data itself.

**Independent Test**: Publish a refund ticket → confirm exactly one billing and one risk
`task.requested` event, each correlated to the ticket, carrying only ticket/order context.

### Tests for User Story 2

- [ ] T020 [P] [US2] Integration test "refund ticket → two correlated `task.requested` events to billing & risk endpoints, case in AWAITING_ANALYSES" in `apps/agents/customer_resolution/tests/test_customer_resolution.py` (quickstart Scenario 2 request leg, SC-002)
- [ ] T021 [P] [US2] Unit test peer-rejection handling (rejected request → case slot `failed`, routes to escalation, never fabricated) in `apps/agents/customer_resolution/tests/test_state_store.py` (US2-3, SC-007)

### Implementation for User Story 2

- [X] T022 [US2] Implement the runtime/card setup in `apps/agents/customer_resolution/a2a_handlers.py`: build the `AgentCard` and start `AgentRuntime` exposing the agent's own addressable endpoint (FR-001, research R7) — imports the Spec 002 runtime
- [X] T023 [US2] Implement peer discovery in `a2a_handlers.py` via `agent_foundation.runtime.discovery.find_capable(...)` for `analyze_refund_eligibility` (billing) and `assess_fraud_risk` (risk), resolving target endpoints with no router (FR-017, research R2)
- [X] T024 [US2] Implement `delegate(case)` in `a2a_handlers.py`: build two `TaskRequest`s (ticket/order context only), publish each to `endpoint_topic(target)` with the case `correlation_id` and `causation_id`=ticket event id, and record each `task_id` on the case's billing/risk slot (FR-004/FR-016, data-model.md §5)
- [X] T025 [US2] Extend the intake handler in `event_handlers.py` so the **refund** branch calls `delegate(case)` and sets the case to `AWAITING_ANALYSES` (FR-004, US2)

**Checkpoint**: Refund tickets produce exactly two correlated peer requests; the agent is a discoverable A2A participant.

---

## Phase 5: User Story 3 - Produce a Final Customer Response Decision (Priority: P1)

**Goal**: The agent consumes billing/risk `TaskResult` events, correlates each by `task_id` to its
case slot, and once both slots are resolved (or a failure forces it) applies the deterministic policy
to emit **exactly one** final decision — tolerating late/duplicate results after a decision.

**Independent Test**: Supply billing+risk results for a refund ticket → exactly one decision whose
outcome matches the truth table; with only one result → no decision (case open); a late result after
decision → recorded, not applied.

### Tests for User Story 3

- [X] T026 [P] [US3] Unit test the full decision truth table (rows 1–7: direct/approve/deny/escalate for peer-failure, human-review flag, elevated risk, conflict) in `apps/agents/customer_resolution/tests/test_decision_engine.py` (decision-policy.md §C/§D, SC-003/SC-007)
- [X] T027 [P] [US3] Unit test case aggregation in `apps/agents/customer_resolution/tests/test_state_store.py`: completeness (`is_ready_to_decide` only when both slots received), one-slot-open stays open, failed-slot short-circuit, and late-result-after-decision recorded-not-applied (FR-008/FR-012)
- [X] T028 [P] [US3] Unit test the result-normalization adapter (canonical contract, demo-stub shape, and unparseable→`failed`/`unparseable_result`) in `apps/agents/customer_resolution/tests/test_adapters.py` (analysis-result-contract.md, decision-policy.md §B)
- [ ] T029 [P] [US3] Integration tests for approve / deny / escalate(elevated-risk, peer-failure, conflict), only-one-result (case stays open), and late-result-after-decision in `apps/agents/customer_resolution/tests/test_customer_resolution.py` (quickstart Scenarios 2,3,5,6; SC-003/SC-007)

### Implementation for User Story 3

- [X] T030 [US3] Implement the result-normalization adapter (`TaskResult` → `BillingFinding`/`RiskFinding`; `failed`/`rejected`/unparseable → slot `failed` with reason; never fabricate) in `apps/agents/customer_resolution/agent.py` (analysis-result-contract.md, decision-policy.md §B) — reads only published peer fields (FR-005)
- [X] T031 [US3] Implement the full `decide(triage, billing_slot, risk_slot) -> CustomerResponseDecisionPayload` truth table (escalation precedence rows 2–4 before deny/approve rows 5–6, residual row 7) in `apps/agents/customer_resolution/decision_engine.py` (decision-policy.md §C, FR-009/FR-010)
- [X] T032 [US3] Implement the approve/deny/escalate customer-message templates (with traceable billing/risk summaries) in `apps/agents/customer_resolution/response_drafter.py` (decision-policy.md §C, SC-004)
- [X] T033 [US3] Implement `is_ready_to_decide` + terminal transitions (`DECIDED`/`CLOSED_DIRECT`) on the case/`CaseStore` in `apps/agents/customer_resolution/state_store.py` (data-model.md §4 state machine, FR-008)
- [X] T034 [US3] Implement the result handler in `apps/agents/customer_resolution/event_handlers.py`: consume `TOPIC_TASK_RESULT` with `IdempotencyTracker`, map `task_id`→case slot, store the normalized finding, and when ready apply `decide(...)` and emit **exactly one** decision to `TOPIC_RESOLUTION_DECIDED`; for an already-`DECIDED` case, record the late/duplicate result without emitting again (FR-006/FR-007/FR-012, research R3)
- [X] T035 [US3] Wire the result `Consumer` into `agent.py`/`main.py` under the process `asyncio.gather`, sharing the `CaseStore` with the intake loop (research R3/R7)

**Checkpoint**: End-to-end refund resolution (approve/deny/escalate) works; exactly one decision per case; late results are inert.

---

## Phase 6: User Story 4 - Audit the Full Resolution Workflow (Priority: P2)

**Goal**: Every significant step leaves an immutable, correlated audit record reconstructable by
correlation id.

**Independent Test**: Drive a refund ticket end-to-end, query the audit trail by correlation id, and
confirm intake → triage → both delegations → both results → final decision appear, attributed to the
agent, in causal order (escalation reason present when applicable).

### Tests for User Story 4

- [ ] T036 [P] [US4] Integration test audit reconstruction via `query_by_correlation` (all steps present, attributed, causal order; escalation reason recoverable) in `apps/agents/customer_resolution/tests/test_customer_resolution.py` (quickstart Scenario 7, SC-006)

### Implementation for User Story 4

- [X] T037 [US4] Emit a structured audit event at each step (ticket received, triage determination, billing delegated, risk delegated, billing result consumed, risk result consumed, final decision, duplicate re-delivery) via `agent_foundation.audit.store.write_audit`/`write_task_audit` across `event_handlers.py` and `a2a_handlers.py`, each carrying agent identity, correlation/task id, causation link, timestamp, outcome (FR-013, data-model.md §8)
- [X] T038 [US4] Ensure the escalation `reason` (peer_failure/peer_rejection/peer_requested_review/elevated_risk/conflicting_analyses) is written to the audit trail on every escalation in `decision_engine.py`/`event_handlers.py` (FR-010/FR-013, SC-007)

**Checkpoint**: Any ticket's full workflow is reconstructable from the audit trail by correlation id.

---

## Phase 7: User Story 5 - Never Inspect Billing or Fraud Data Directly (Priority: P2)

**Goal**: Prove every billing/risk fact used in a decision originated from a peer `TaskResult` and the
agent accesses no billing/payment/fraud data source.

**Independent Test**: Inspect inputs across a refund case — every billing/risk fact traces to a peer
result; no billing/fraud datastore import or query exists in the package.

### Tests for User Story 5

- [X] T039 [P] [US5] Isolation test in `apps/agents/customer_resolution/tests/test_domain_isolation.py`: assert the package imports no billing/payment/fraud datastore module and that every finding used by `decide` originates from a consumed `TaskResult` (FR-005, SC-004)

### Implementation for User Story 5

- [X] T040 [US5] Audit the package for any direct billing/fraud data access and confirm the normalization adapter (T030) is the **only** ingress for billing/risk facts — unparseable/missing data yields `failed` (escalation), never a fabricated finding (FR-005, analysis-result-contract.md)

**Checkpoint**: Domain isolation is enforced and test-verified.

---

## Phase 8: User Story 6 - Stay a Domain Agent, Not a General Supervisor (Priority: P3)

**Goal**: Confirm the agent's only delegations are billing/risk analyses bound to its own refund
cases, and it neither routes nor dispatches work for other agents.

**Independent Test**: Inspect emitted `task.requested` events — each is a billing/risk analysis tied
to a refund ticket the agent owns; no unrelated requests; no dispatch on behalf of others.

### Tests for User Story 6

- [X] T041 [P] [US6] Guardrail test in `apps/agents/customer_resolution/tests/test_no_supervisor.py`: assert every emitted `TaskRequest` is a billing/risk capability bound to an owned refund case, the agent consumes no inbound task-dispatch requests on behalf of peers, and the existing `test_no_router` invariant still holds (FR-015, SC-008)

**Checkpoint**: No-supervisor / no-router guardrail is test-verified.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Validation, docs, and quality gates across all stories.

- [ ] T042 [P] Add a package `README`/module docstrings in `apps/agents/customer_resolution/` summarizing the three concurrent loops, the deterministic policy, and the in-process-state durability gap (research R6)
- [ ] T043 Run the quickstart scenarios 1–8 (`specs/003-customer-resolution-agent/quickstart.md`) against a local broker and confirm expected outcomes
- [ ] T044 Run the full quality gate: `uv run pytest apps/agents/customer_resolution/tests`, `uv run mypy .`, `uv run ruff check .` (quickstart "Automated validation")

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Foundational (Phase 2)**: Depends on Setup — **BLOCKS all user stories**. T004→T006 (payload before registry); T005→T007 (constant before topic-creation); T008/T009/T010 feed T011.
- **User Stories (Phase 3–8)**: All depend on Foundational. Priority order P1 (US1→US2→US3) → P2 (US4, US5) → P3 (US6). US2 and US3 build on US1's intake/case; US4/US5/US6 are verification layers over US1–US3.
- **Polish (Phase 9)**: Depends on all targeted stories.

### User Story Dependencies

- **US1 (P1)**: After Foundational. Independent MVP.
- **US2 (P1)**: After US1 (extends the intake handler's refund branch).
- **US3 (P1)**: After US2 (consumes results from the requests US2 issues).
- **US4 (P2)**: After US1–US3 (audits the steps they produce); test independently verifiable.
- **US5 (P2)**: After US3 (verifies the adapter is the only billing/risk ingress); largely independent.
- **US6 (P3)**: After US2 (inspects the delegations US2 emits).

### Within Each User Story

- Tests written first and expected to fail before implementation.
- Models/config/store (Phase 2) before handlers.
- Pure functions (`ticket_classifier`, `decision_engine`, adapter) before the consumers that call them.
- Consumer wiring (`agent.py`/`main.py`) last within a story.

---

## Parallel Opportunities

- **Phase 1**: T002 and T003 in parallel.
- **Phase 2**: T005 (topics) ∥ T008 (models) ∥ T009 (config) — different files; T004 before T006.
- **Within a story**, all `[P]` test tasks run in parallel (different test files), and pure-function
  implementations in distinct files can parallelize.
- **Across stories** (with capacity): once Phase 2 is done, US4/US5/US6 test scaffolding can be
  drafted in parallel with US3 implementation since they touch separate test files.

### Parallel Example: User Story 3 tests

```bash
# Different test files, no shared state — launch together:
Task: "Unit decision truth table in apps/agents/customer_resolution/tests/test_decision_engine.py"
Task: "Unit case aggregation in apps/agents/customer_resolution/tests/test_state_store.py"
Task: "Unit normalization adapter in apps/agents/customer_resolution/tests/test_adapters.py"
Task: "Integration approve/deny/escalate/late in apps/agents/customer_resolution/tests/test_customer_resolution.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1: Setup.
2. Phase 2: Foundational (contract + topic + registry + models/config/store/skeleton).
3. Phase 3: US1 — triage + non-refund direct response.
4. **STOP and VALIDATE**: quickstart Scenario 1 (non-refund → direct_response, no peer calls).

### Incremental Delivery

1. Setup + Foundational → agent process starts, card published.
2. US1 → triage + direct response (MVP, quickstart S1).
3. US2 → two correlated peer requests (quickstart S2 request leg).
4. US3 → full decision/approve/deny/escalate + late-result safety (quickstart S2,3,5,6) — **core loop complete**.
5. US4 → audit reconstruction (quickstart S7).
6. US5 → domain-isolation proof (quickstart S8a).
7. US6 → no-supervisor guardrail (quickstart S8b).

### Acceptance-criteria mapping (from the `/speckit-tasks` request)

- **Agent runs independently** → T011, T019, T035 (self-contained process + entrypoint; self-contained tests).
- **Imports shared contracts from Spec 001** → T011, T018, T034 (envelope/transport/audit/idempotency reuse).
- **Imports A2A runtime from Spec 002** → T022, T023, T024 (`AgentRuntime`, discovery, `TaskRequest`).
- **No billing/risk business logic here** → T030, T040, T039 (facts enter only via peer `TaskResult`; isolation test).

---

## Notes

- `[P]` = different files, no incomplete-task dependency.
- Every billing/risk fact enters via the adapter (T030) over consumed `TaskResult` events — the package
  contains **no** billing/risk domain logic and **no** billing/fraud datastore access (FR-005).
- In-process case state durability across restart is a **documented PoC gap** (research R6); the audit
  trail is the durable record.
- Commit after each task or logical group; stop at any checkpoint to validate a story independently.

---

## Phase 10: Publish Classification Event — `local.resolution.customer-issue.classified.v1` (extends US1/US4)

**Added by a follow-up `/speckit-tasks` request.** This section is **additive** to the feature above —
it introduces a **new domain event** the agent emits immediately after triage: a structured
classification of the incoming ticket (its `issue_type`, a `confidence`, and the downstream review
routing flags). It is distinct from `customer.resolution.decided.v1` (the final decision) and is **not**
part of the original spec/plan/data-model. Tasks continue the numbering (T045+) and reuse this file's
package layout (`ticket_classifier.py`, `event_handlers.py`, `models.py`, tests under
`apps/agents/customer_resolution/tests/`).

**Goal**: After classifying a `support.ticket.created` ticket, the agent publishes exactly one
`local.resolution.customer-issue.classified.v1` event carrying `case_id`, `ticket_id`, `customer_id`,
`issue_type`, `confidence`, `requires_billing_review`, `requires_risk_review`,
`requires_human_review`, and `reasoning_summary`.

**Independent Test**: Publish a ticket → observe a single classification event on
`local.resolution.customer-issue.classified.v1` whose `envelope.correlation_id` equals the ticket's
correlation id and whose `envelope.agent_id == "customer-resolution-agent"`; for a refund ticket the
`requires_billing_review`/`requires_risk_review` flags are `true`, for a non-refund ticket they are
`false`.

### Acceptance criteria → how each is met (from the `/speckit-tasks` request)

| Criterion | How it is satisfied | Verified by |
|-----------|---------------------|-------------|
| Event uses the **shared envelope** | Published via the shared `Publisher`, which wraps the payload in `EventEnvelope` (`src/agent_foundation/envelope.py`) — no parallel transport (FR-016) | T049, T053 |
| Event includes the **original correlation ID** | `publish(...)` is called with `correlation_id = ticket_envelope.correlation_id` (never a fresh UUID) | T050, T053 |
| Event includes **`producer_agent_id = "customer-resolution-agent"`** | The publishing `Publisher` is built from the agent's `AgentIdentity(agent_id="customer-resolution-agent")`, so `envelope.agent_id == "customer-resolution-agent"` | T050, T053 |

> **Non-root event**: `local.resolution.customer-issue.classified.v1` is not a root type, so the
> envelope's `causation_id` is **required** — set it to the inbound ticket's `event_id`, or
> `EventEnvelope` validation raises `MissingCausation` (`src/agent_foundation/envelope.py`). Producer
> identity is `envelope.agent_id` (set by `Publisher` from `AgentIdentity`), consistent with the rest
> of this feature.

### Foundational (contract + registry + topic — blocks the publish path and tests)

- [X] T045 [US1] Add `CustomerIssueClassifiedPayload` (Pydantic v2, `frozen`, `extra="forbid"`) to `packages/contracts/events/payloads.py` with fields `case_id: UUID` (the resolution-case identity = inbound envelope `correlation_id`), `ticket_id: str`, `customer_id: str`, `issue_type: str`, `confidence: Annotated[float, Field(ge=0.0, le=1.0)]`, `requires_billing_review: bool`, `requires_risk_review: bool`, `requires_human_review: bool`, `reasoning_summary: str`; add it to the module `__all__` (mirror the existing `BillingRefundAnalysisCompletedPayload` `confidence` style)
- [X] T046 [P] [US1] Add `TOPIC_ISSUE_CLASSIFIED = topic_for("resolution","customer-issue","classified")` (resolves to `local.resolution.customer-issue.classified.v1`) in `packages/contracts/topics.py`, beside `TOPIC_TASK_RESULT`
- [X] T047 [US1] Register `"local.resolution.customer-issue.classified.v1": CustomerIssueClassifiedPayload` in `PAYLOAD_REGISTRY` in `src/agent_foundation/payloads/__init__.py` so `Publisher`/`Consumer` validate it on send/receive (depends on T045, T046)
- [X] T048 [US1] Wire transport resolution + provisioning in `src/agent_foundation/transport/topics.py`: add the event-type→topic mapping to `TOPIC_NAMES` (key == value == `TOPIC_ISSUE_CLASSIFIED`, new-style convention) and append `NewTopic(name=TOPIC_ISSUE_CLASSIFIED, num_partitions=1, replication_factor=1, topic_configs={"retention.ms": str(_SEVEN_DAYS_MS)})` to `_CANONICAL_TOPICS` (event stream, not compacted) (depends on T046)

### Tests (write first — must FAIL before implementation)

- [X] T049 [P] [US1] Extend `apps/agents/customer_resolution/tests/test_resolution_schemas.py`: assert `CustomerIssueClassifiedPayload` round-trips, that `lookup("local.resolution.customer-issue.classified.v1")` returns it, that `TOPIC_NAMES` resolves the same key, and that a `confidence` outside `[0.0, 1.0]` raises `ValidationError`
- [X] T050 [P] [US1] Add `apps/agents/customer_resolution/tests/test_classification_event.py`: build the classification envelope (via T051) from a sample ticket envelope and assert `envelope.event_type == "local.resolution.customer-issue.classified.v1"`, `envelope.agent_id == "customer-resolution-agent"`, `envelope.correlation_id == ticket_envelope.correlation_id`, `envelope.causation_id == ticket_envelope.event_id`, and that every payload field is carried through (no Kafka — assert on the constructed `EventEnvelope`)

### Implementation

- [X] T051 [US1] Extend the `Triage` model in `apps/agents/customer_resolution/models.py` with `issue_type: str` and `confidence: float` (deterministically set by `classify(...)` from T015), and add a pure `build_issue_classified_payload(ticket, correlation_id, triage) -> CustomerIssueClassifiedPayload` in `apps/agents/customer_resolution/ticket_classifier.py` that maps `case_id = correlation_id`, `requires_billing_review`/`requires_risk_review = triage.needs_refund_review`, `requires_human_review = triage.ambiguous` (or a human-review signal), and `reasoning_summary = triage.rationale` (decision-policy.md §A) — no I/O, unit-testable
- [X] T052 [US1] In the intake handler in `apps/agents/customer_resolution/event_handlers.py`, after `classify(...)` and **before** the refund/direct-response branch, publish the classification event to `TOPIC_ISSUE_CLASSIFIED` via the shared `Publisher` with `correlation_id = ticket_envelope.correlation_id` and `causation_id = ticket_envelope.event_id` (producer identity already `customer-resolution-agent` from the process `AgentIdentity`); emit for **both** refund and non-refund tickets (extends T018)
- [ ] T053 [US1] Add an integration test in `apps/agents/customer_resolution/tests/test_customer_resolution.py` (or extend it): publish a `support.ticket.created` envelope, consume from `local.resolution.customer-issue.classified.v1`, and assert exactly one classification event with `envelope.agent_id == "customer-resolution-agent"`, `envelope.correlation_id` == the ticket's correlation id, `envelope.causation_id` == the ticket's `event_id`, and the routing flags consistent with refund vs non-refund (depends on T052)

### Audit (extends US4)

- [ ] T054 [US4] Add a "ticket classified" step to the audit emission in `apps/agents/customer_resolution/event_handlers.py` via `agent_foundation.audit.store.write_audit` (agent identity, correlation/causation, timestamp, outcome) so the classification is reconstructable by correlation id — extends the step list in T037 (FR-013)

**Checkpoint**: A ticket in → one well-formed classification event out (plus an audit record),
satisfying all three acceptance criteria.

### Phase 10 dependencies

- **Foundational T045–T048** block everything in this phase. T045 ∥ T046 (different files); T047
  needs T045+T046; T048 needs T046.
- **Tests T049/T050** (different files, [P]) are written first and must fail before T051–T053.
- **Impl**: T051 (pure builder + model field) → T052 (handler wiring, extends T018) → T053
  (integration). T052 also requires the Phase 2 process/`Publisher` from T011 and the intake handler
  from T018.
- **T054** (audit) follows T052 and folds into the US4 audit step list (T037).
- **Parallel**: T046 ∥ T045; T049 ∥ T050.

---

## Phase 11: Publish Refund Review Requested Event — `local.resolution.refund-review.requested.v1` (extends US2/US4)

**Added by a follow-up `/speckit-tasks` request.** This section is **additive** to the feature above —
it introduces a **new domain event** the agent emits immediately after it issues the two billing/risk
A2A `TaskRequest`s for a refund-review case: a structured, replayable announcement of *which* peer
reviews were requested and *which task ids* back them. It is distinct from
`customer.resolution.decided.v1` (the final decision) and `customer-issue.classified.v1` (the triage
classification), and is **not** part of the original spec/plan/data-model. Tasks continue the
numbering (T055+) and reuse this file's package layout (delegation in `a2a_handlers.py`, the intake
handler in `event_handlers.py`, contracts in `packages/contracts/`, tests under
`apps/agents/customer_resolution/tests/`).

**Important — this event is *additive*, not a delegation transport.** Research **R2** rejected using a
`refund.review.requested` event *as the delegation channel*; the two `TaskRequest`s remain the sole
delegation mechanism (FR-004/FR-016/FR-017). This event is published **after** those requests as an
auditable, replayable record — fully consistent with R2.

**"Accepted" has no wire handshake in the 002 runtime.** `TaskResult.status` is only
`completed|failed|rejected` and the agent uses the **async** delegation model (research R2 — it does
*not* call the blocking `A2AClient.submit()`). The well-defined "requests accepted" point is therefore
**after both `TaskRequest`s are successfully published** (the broker-acknowledged send). This event is
emitted at that point.

**Goal**: After `delegate(case)` (T024) publishes both the billing and risk `TaskRequest`s and records
their `task_id`s on the case, the agent publishes exactly one
`local.resolution.refund-review.requested.v1` event carrying `case_id`, `ticket_id`, `customer_id`,
`requested_reviews` (e.g. `["billing","risk"]`), `billing_task_id`, `risk_task_id`, and
`timeout_seconds`.

**Independent Test**: Drive a refund-review case → observe exactly two `task.requested` events
(billing + risk) followed by a single `local.resolution.refund-review.requested.v1` event whose
`envelope.correlation_id` equals the ticket's correlation id, `envelope.agent_id ==
"customer-resolution-agent"`, `requested_reviews == ["billing","risk"]`, and whose
`billing_task_id`/`risk_task_id` equal the two issued `TaskRequest.task_id`s; a non-refund ticket emits
**no** such event.

### Acceptance criteria → how each is met (from the `/speckit-tasks` request)

| Criterion | How it is satisfied | Verified by |
|-----------|---------------------|-------------|
| Event is **emitted after A2A task requests are accepted** | Emission happens in `delegate(case)` only **after both** `Publisher.publish(...)` calls for the billing and risk `TaskRequest`s have completed successfully (the "accepted" point in the async model); on a discovery/publish failure no announcement is emitted (the case escalates instead) | T058, T060, T061 |
| Event **records all requested peer reviews** | `requested_reviews` lists every delegated review and `billing_task_id`/`risk_task_id` carry the corresponding `task_id`s read back from the case slots; a `model_validator` rejects an empty/duplicate `requested_reviews` or a listed review with no matching task id | T056, T059, T060 |
| Event is **audit-friendly and replayable** | Registered in `PAYLOAD_REGISTRY` + provisioned on a durable (7-day retention) topic via the shared `Publisher`/`EventEnvelope` (no parallel transport, FR-016); a `write_audit` "refund review requested" step is emitted; re-delivery is idempotent (no second event) | T057, T058, T062, T063, T064 |

> **Non-root event**: `local.resolution.refund-review.requested.v1` is not a root type, so the
> envelope's `causation_id` is **required** — set it to the inbound ticket's `event_id` (the same
> causation used for the two `TaskRequest`s), or `EventEnvelope` validation raises `MissingCausation`
> (`src/agent_foundation/envelope.py`). Producer identity is `envelope.agent_id`, set by `Publisher`
> from the process `AgentIdentity(agent_id="customer-resolution-agent")`.

### Foundational (contract + registry + topic — blocks the publish path and tests)

- [X] T055 [US2] Repurpose the existing **unused / unregistered** `RefundReviewRequestedPayload` in `packages/contracts/events/payloads.py` to the aggregate shape (Pydantic v2, `frozen`, `extra="forbid"`): `case_id: UUID` (the resolution-case identity = inbound envelope `correlation_id`), `ticket_id: str`, `customer_id: str`, `requested_reviews: list[Literal["billing","risk"]]`, `billing_task_id: UUID`, `risk_task_id: UUID`, `timeout_seconds: int | None = None`, `requested_by_agent_id: str = "customer-resolution-agent"`, `requested_at: datetime`; remove the obsolete `review_type`/`amount`/`currency` fields and keep it in the module `__all__` (no consumer depends on the old per-review shape, so this is safe)
- [X] T056 [US2] Add a `model_validator(mode="after")` to `RefundReviewRequestedPayload` in `packages/contracts/events/payloads.py` requiring `requested_reviews` non-empty with no duplicates, `"billing" in requested_reviews` ⇒ `billing_task_id` set, and `"risk" in requested_reviews` ⇒ `risk_task_id` set — every requested review is traceable to a task id
- [X] T057 [P] [US2] Add `TOPIC_REFUND_REVIEW_REQUESTED = topic_for("resolution","refund-review","requested")` (resolves to `local.resolution.refund-review.requested.v1`) in `packages/contracts/topics.py`, beside `TOPIC_TASK_RESULT`
- [X] T058 [US2] Register `"local.resolution.refund-review.requested.v1": RefundReviewRequestedPayload` in `PAYLOAD_REGISTRY` in `src/agent_foundation/payloads/__init__.py` so `Publisher`/`Consumer` validate it on send/receive (depends on T055, T057)
- [X] T059 [US2] Wire transport resolution + provisioning in `src/agent_foundation/transport/topics.py`: add the event-type→topic mapping to `TOPIC_NAMES` (key == value == `TOPIC_REFUND_REVIEW_REQUESTED`, new-style convention) and append `NewTopic(name=TOPIC_REFUND_REVIEW_REQUESTED, num_partitions=1, replication_factor=1, topic_configs={"retention.ms": str(_SEVEN_DAYS_MS)})` to `_CANONICAL_TOPICS` (event stream, not compacted) (depends on T057)

### Tests (write first — must FAIL before implementation)

- [ ] T060 [P] [US2] Extend `apps/agents/customer_resolution/tests/test_resolution_schemas.py`: assert `RefundReviewRequestedPayload` round-trips, that `lookup("local.resolution.refund-review.requested.v1")` returns it, that `TOPIC_NAMES` resolves the same key, and that the T056 validator rejects an empty `requested_reviews`, a duplicate entry, and a `"billing"` entry with no `billing_task_id`
- [ ] T061 [P] [US2] Add `apps/agents/customer_resolution/tests/test_refund_review_requested.py`: build the announcement envelope (via T062) from a refund case whose billing/risk slots hold known `task_id`s, and assert `envelope.event_type == "local.resolution.refund-review.requested.v1"`, `envelope.agent_id == "customer-resolution-agent"`, `envelope.correlation_id == case.correlation_id`, `envelope.causation_id == ticket_envelope.event_id`, `payload.requested_reviews == ["billing","risk"]`, and `payload.billing_task_id`/`payload.risk_task_id` equal the slot task ids (no Kafka — assert on the constructed `EventEnvelope`)

### Implementation

- [X] T062 [US2] Add a pure `build_refund_review_requested(case, *, timeout_seconds) -> RefundReviewRequestedPayload` in `apps/agents/customer_resolution/a2a_handlers.py` that maps `case_id = case.correlation_id`, `ticket_id`/`customer_id` from `case.ticket`, `requested_reviews` from the delegated slots, `billing_task_id`/`risk_task_id` from `case.billing.task_id`/`case.risk.task_id`, and `timeout_seconds` from config — no I/O, unit-testable
- [X] T063 [US2] Source `timeout_seconds` from a single `DELEGATION_TIMEOUT_SECONDS` constant in `apps/agents/customer_resolution/config.py` (illustrative PoC value; aligns with the `A2AClient.submit` 30s default) so the announced timeout matches the requests' intended liveness window (extends T009)
- [X] T064 [US2] In `delegate(case)` in `apps/agents/customer_resolution/a2a_handlers.py` (T024), **after both** billing and risk `Publisher.publish(...)` calls succeed and the slot `task_id`s are recorded, publish the announcement to `TOPIC_REFUND_REVIEW_REQUESTED` via the shared `Publisher` with `correlation_id = ticket_envelope.correlation_id` and `causation_id = ticket_envelope.event_id` (producer identity already `customer-resolution-agent`); document the "accepted == both publishes succeeded" interpretation in a code comment; emit it **exactly once** per case and **not** when discovery/publish fails (extends T024)
- [X] T065 [US2] Make the announcement idempotent in `apps/agents/customer_resolution/event_handlers.py`/`a2a_handlers.py`: a re-delivered or duplicate ticket (case already past intake / already delegated) performs no second delegation and emits **no** second `refund-review.requested` event (reuse the `IdempotencyTracker` + case-status guard from T018/T025; FR-011/FR-012)
- [ ] T066 [P] [US2] Add an integration test in `apps/agents/customer_resolution/tests/test_refund_review_requested.py`: publish a refund `support.ticket.created`, consume from `local.resolution.refund-review.requested.v1`, and assert exactly one event ordered **after** the two `task.requested` events, with `envelope.agent_id`/`correlation_id`/`causation_id` and `requested_reviews`/task ids as expected; assert a non-refund ticket and a re-delivered ticket each yield no (additional) announcement (depends on T064/T065)

### Audit (extends US4)

- [ ] T067 [US4] Add a "refund review requested" step to the audit emission in `apps/agents/customer_resolution/a2a_handlers.py` via `agent_foundation.audit.store.write_audit` (agent identity, `correlation_id`, `causation_id = ticket event id`, timestamp, outcome) so the announcement is reconstructable by correlation id — extends the step list in T037 (FR-013/FR-014)

**Checkpoint**: Two `task.requested` events out, then exactly one `refund-review.requested` event (plus
an audit record) — satisfying all three acceptance criteria; replays never double-emit.

### Phase 11 dependencies

- **Foundational T055–T059** block everything in this phase. T055 → T056 (validator on the repurposed
  model); T055 ∥ T057 (different files); T058 needs T055+T057; T059 needs T057.
- **Tests T060/T061** (different files, [P]) are written first and must fail before T062–T066.
- **Impl**: T062 (pure builder) + T063 (config constant) → T064 (emit in `delegate`, extends T024) →
  T065 (idempotency) → T066 (integration). T064 also requires the Phase 2 process/`Publisher` (T011),
  the delegation path (T024), and the refund branch (T025).
- **T067** (audit) follows T064 and folds into the US4 audit step list (T037).
- **Parallel**: T055 ∥ T057; T060 ∥ T061; T066 is [P] with later polish only after T064/T065 land.

---

## Phase 12: A2A Task Request to the Risk Agent (hardens US2/US3/US5)

**Added by a follow-up `/speckit-tasks` request.** This section is **additive** to the feature above.
US2 (Phase 4, T023/T024) already discovers peers and emits a billing **and** a risk `TaskRequest`
generically. This phase **pins and hardens the risk leg** to the explicit delegation contract and the
four acceptance criteria from the request. It continues the numbering (T068+) and reuses this file's
package layout (`a2a_handlers.py`, `models.py`, `state_store.py`, `event_handlers.py`, tests under
`apps/agents/customer_resolution/tests/`).

**Delegation contract (reconciled with the Risk Agent's published AgentCard)**:

| Field | Value |
|-------|-------|
| `target_agent_id` | `risk-fraud-agent` |
| `capability` | `assess_fraud_risk` — the id the Risk Agent publishes in its card (`apps/agents/risk_fraud/main.py`). The request's `assess_refund_risk` was a mismatch and is **corrected here** so AgentCard validation (AC3) succeeds. |
| task input | `case_id`, `ticket_id`, `customer_id`, `requested_refund_amount`, `customer_message_summary` |

**Acceptance criteria → coverage**:

| AC | Statement | Tasks |
|----|-----------|-------|
| **AC1** | Customer Resolution Agent does not inspect fraud data directly | T068, T073, T079 (request carries only ticket context; isolation asserted) |
| **AC2** | A2A request includes an idempotency key | T071, T073, T076 (`TaskRequest.task_id` recorded on the case risk slot, reused on re-delivery) |
| **AC3** | Risk Agent capability is validated through the Agent Card | T070, T074 (fail-closed `find_capable("assess_fraud_risk")` before send) |
| **AC4** | Failure to reach the Risk Agent moves the case to a pending or escalated state | T069, T072, T075, T077 |

### Foundational (request contract + case state — blocks the risk-request path)

- [ ] T068 [US2] Add `RiskAnalysisRequestInput` (Pydantic v2, `frozen`, `extra="forbid"`) to `apps/agents/customer_resolution/models.py` with **exactly** `case_id: UUID`, `ticket_id: str`, `customer_id: str`, `requested_refund_amount: float`, `customer_message_summary: str`, and a pure `build_risk_request_input(ticket, correlation_id) -> RiskAnalysisRequestInput` mapping `case_id=correlation_id`, `requested_refund_amount=ticket.amount`, `customer_message_summary=ticket.reason` — no billing/fraud fields, so the request type itself enforces the AC1 boundary
- [ ] T069 [US3] Add a non-terminal `PENDING_RISK` status to `CaseStatus` in `apps/agents/customer_resolution/models.py` and represent it in the `state_store.py` transitions (distinct from `AWAITING_ANALYSES`: "risk request not sent — peer undiscoverable" vs. "request sent, awaiting result"), carrying a recorded `reason` (extends data-model.md §4)

### Capability validation through the Agent Card (AC3)

- [ ] T070 [US2] In `apps/agents/customer_resolution/a2a_handlers.py`, add `async validate_risk_capability(broker_url) -> AgentCard`: call `agent_foundation.runtime.discovery.find_capable("assess_fraud_risk", broker_url)`, select the `risk-fraud-agent` card, and **fail closed** by raising `RiskPeerUnavailable` if no published card declares `assess_fraud_risk`; the risk request is built/sent only after the card validates the capability (AC3, FR-017, research R2)

### Idempotency key on the A2A request (AC2)

- [ ] T071 [US2] Implement `async request_risk_analysis(case)` in `apps/agents/customer_resolution/a2a_handlers.py` (the risk-specific path that T024's `delegate` calls or is refactored into): compute the **idempotency key** = stable `task_id` (reuse `case.risk.task_id` if set, else mint and record it on the risk slot) so re-delivery reuses it; build the `TaskRequest(task_id=…, capability="assess_fraud_risk", requester_agent_id="customer-resolution-agent", target_agent_id="risk-fraud-agent", input=build_risk_request_input(...))`; publish to `endpoint_topic("risk-fraud-agent")` with `correlation_id=case.correlation_id` and `causation_id=<ticket event_id>` via the shared `Publisher` (AC2, FR-004/FR-011/FR-016, data-model.md §5)

### Failure to reach the Risk Agent → pending / escalated (AC4)

- [ ] T072 [US3] Wrap capability validation + publish in `request_risk_analysis` (`a2a_handlers.py`) with failure handling: on `RiskPeerUnavailable` (no capable card discovered) move the case to `PENDING_RISK` with reason `risk-capability-unavailable`; on a publish/delivery exception move it to `ESCALATE_HUMAN` with reason `risk-peer-unreachable`; in both branches return without raising to the intake loop and **never fabricate** a risk finding (AC4, US2-3/US3 edge "peer failure or rejection", FR-008/FR-010). Document that an *accepted-but-never-answered* request remains the out-of-scope liveness gap (research R6)

### Tests (write first — must FAIL before implementation)

- [ ] T073 [P] [US2] Unit test in `apps/agents/customer_resolution/tests/test_a2a_handlers.py`: `build_risk_request_input` produces exactly the five fields with correct mapping and no billing/fraud keys (AC1); the constructed risk `TaskRequest` targets `risk-fraud-agent`/`assess_fraud_risk` and its `task_id == case.risk.task_id` (AC2)
- [ ] T074 [P] [US2] Unit test capability validation in `apps/agents/customer_resolution/tests/test_a2a_handlers.py`: a discovery list containing a `risk-fraud-agent` card declaring `assess_fraud_risk` returns that card; an empty list or a card without the capability raises `RiskPeerUnavailable` (AC3)
- [ ] T075 [P] [US3] Unit test failure handling in `apps/agents/customer_resolution/tests/test_state_store.py`: `RiskPeerUnavailable` drives the case to `PENDING_RISK` with reason; a simulated publish exception drives it to `ESCALATE_HUMAN` with reason; no exception escapes and no risk finding is fabricated (AC4)
- [ ] T076 [P] [US2] Integration test in `apps/agents/customer_resolution/tests/test_customer_resolution.py`: with the `risk-fraud-agent` card published, drive a refund ticket → exactly one `task.requested` on `endpoint_topic("risk-fraud-agent")` with `capability="assess_fraud_risk"`, the five-field input, `requester_agent_id="customer-resolution-agent"`, and a non-null `task_id`; **re-deliver the same ticket** → no second risk request and an unchanged `case.risk.task_id` (AC2/AC3, SC-002/SC-005)
- [ ] T077 [P] [US3] Integration test "risk peer undiscoverable" in `apps/agents/customer_resolution/tests/test_customer_resolution.py`: with **no** `risk-fraud-agent` card published, drive a refund ticket → the case ends `PENDING_RISK` (or `ESCALATE_HUMAN`) with an audit record carrying the reason; assert **no** risk `TaskRequest` is emitted and no risk finding is fabricated (AC4, SC-007)

### Audit & isolation (extends US4 / US5)

- [ ] T078 [US4] Emit a risk-delegation audit step in `a2a_handlers.py`/`event_handlers.py` via `agent_foundation.audit.store.write_task_audit(publisher, ticket_envelope, outcome="accepted", task_id=<risk task_id>, reason=None)` on a successful send, and `outcome="rejected"`/`"failed"` with the AC4 reason on the pending/escalation branches — carrying the idempotency key into the trail (extends T037; AC2/AC4, FR-013, SC-006)
- [ ] T079 [US5] Extend the isolation test (`apps/agents/customer_resolution/tests/test_domain_isolation.py`, T039) to assert the risk `TaskRequest.input` data keys are a **subset** of the five permitted fields (fail if any billing/fraud key leaks) and that the risk path performs no fraud/billing datastore read (AC1, FR-005, SC-004)

**Checkpoint**: A refund ticket emits exactly one card-validated, idempotent risk `TaskRequest` to
`risk-fraud-agent`/`assess_fraud_risk` carrying only the five-field ticket context; an unreachable
risk peer leaves the case in a defined `PENDING_RISK`/`ESCALATE_HUMAN` state with a recorded reason —
all four acceptance criteria satisfied.

### Phase 12 dependencies

- **Foundational T068, T069** block the rest of the phase (request type + case status). T068 ∥ T069
  (both touch `models.py`; sequence if edited together).
- **T070 → T071 → T072** are sequential in `a2a_handlers.py` (validate → build/send → wrap with
  failure handling). They build on US2's T022–T024 (runtime/discovery/delegate already present).
- **Tests T073/T074 (a2a_handlers), T075 (state_store), T076/T077 (integration)** are `[P]` across
  different files and written before T070–T072.
- **T078** (audit) follows T072 and folds into the US4 step list (T037); **T079** extends the US5
  isolation test (T039).
- Reuses `001`/`002` transport, audit, idempotency, runtime, and discovery unchanged (FR-016,
  Principle V) — no new dependency, no second audit path.

---

## Phase 13: A2A Task Request to the Billing Agent (hardens US2/US3/US5)

**Added by a follow-up `/speckit-tasks` request.** This section is **additive** and is the **billing
counterpart** to Phase 12 (Risk). US2 (Phase 4, T023/T024) already discovers peers and emits a billing
**and** a risk `TaskRequest` generically; this phase **pins and hardens the billing leg** to the
explicit delegation contract and the four acceptance criteria from the request. It continues the
numbering (T080+) and reuses this file's package layout (`a2a_handlers.py`, `models.py`,
`event_handlers.py`, tests under `apps/agents/customer_resolution/tests/`).

**Delegation contract (reconciled with the Billing Agent's published AgentCard)**:

| Field | Value |
|-------|-------|
| `target_agent_id` | `billing-entitlement-agent` |
| `capability` | `analyze_refund_eligibility` — the id the Billing Agent publishes in its card (`apps/agents/billing_entitlement/main.py`) |
| task input | `case_id`, `ticket_id`, `customer_id`, `requested_refund_amount`, `purchase_reference`, `customer_message_summary`, `policy_context` |

**Acceptance criteria → coverage**:

| AC | Statement | Tasks |
|----|-----------|-------|
| **AC1** | Customer Resolution Agent does not inspect billing data directly | T080, T084, T086 (request carries only ticket context; isolation asserted) |
| **AC2** | A2A request includes an idempotency key | T081, T084 (`TaskRequest.task_id` recorded on the case billing slot, reused on re-delivery) |
| **AC3** | A2A audit events are emitted | T083, T085 (`write_task_audit` for the billing delegation carries the idempotency key + outcome) |
| **AC4** | Billing result is expected asynchronously through Kafka | T082, T085 (delegation only publishes; result consumed on `TOPIC_TASK_RESULT` by US3 T034 — never a blocking `submit()`) |

### Foundational (request contract — blocks the billing-request path)

- [ ] T080 [US2] Add `BillingAnalysisRequestInput` (Pydantic v2, `frozen`, `extra="forbid"`) to `apps/agents/customer_resolution/models.py` with **exactly** `case_id: UUID`, `ticket_id: str`, `customer_id: str`, `requested_refund_amount: float`, `purchase_reference: str`, `customer_message_summary: str`, `policy_context: str`, plus a pure `build_billing_request_input(ticket, correlation_id, triage) -> BillingAnalysisRequestInput` mapping `case_id=correlation_id`, `requested_refund_amount=ticket.amount`, `customer_message_summary=ticket.reason`, and deriving `purchase_reference`/`policy_context` from ticket/triage context only — no billing/fraud fields, so the request type itself enforces the AC1 boundary

### Idempotency key on the A2A request (AC2)

- [ ] T081 [US2] Implement `async request_billing_analysis(case)` in `apps/agents/customer_resolution/a2a_handlers.py` (the billing-specific path T024's `delegate` calls or is refactored into): compute the **idempotency key** = stable `task_id` (reuse `case.billing.task_id` if set, else `uuid5(case.correlation_id, "analyze_refund_eligibility")` and record it on the billing slot) so re-delivery reuses it; build `TaskRequest(task_id=…, capability="analyze_refund_eligibility", requester_agent_id="customer-resolution-agent", target_agent_id="billing-entitlement-agent", input=build_billing_request_input(...))`; publish to `endpoint_topic("billing-entitlement-agent")` with `correlation_id=case.correlation_id` and `causation_id=<ticket event_id>` via the shared `Publisher` (AC2, FR-004/FR-011/FR-016, data-model.md §5)

### Async Kafka result (AC4)

- [ ] T082 [US3] Confirm `request_billing_analysis` does **not** await the result inline (no `A2AClient.submit()` in the billing path); the billing `TaskResult` is consumed asynchronously on `TOPIC_TASK_RESULT` by the US3 result handler (T034) and correlated back to `case.billing` by `task_id` (AC4, research R2/R3, FR-006/FR-016)

### A2A audit events (AC3)

- [ ] T083 [US4] Emit a billing-delegation audit step in `a2a_handlers.py` via `agent_foundation.audit.store.write_task_audit(publisher, ticket_envelope, outcome="accepted", task_id=<billing task_id>, reason=None)` on a successful send (and `outcome="rejected"`/`"failed"` with reason on a discovery/publish failure that escalates), carrying the idempotency key into the trail (AC3, extends T037, FR-013, SC-006)

### Tests (write first — must FAIL before implementation)

- [ ] T084 [P] [US2] Unit test in `apps/agents/customer_resolution/tests/test_a2a_handlers.py`: `build_billing_request_input` produces exactly the seven fields with correct mapping and no billing/fraud keys (AC1); the constructed billing `TaskRequest` targets `billing-entitlement-agent`/`analyze_refund_eligibility`, its `task_id == case.billing.task_id`, and re-running `request_billing_analysis` for the same case reuses that `task_id` (AC2)
- [ ] T085 [P] [US2] Integration test in `apps/agents/customer_resolution/tests/test_customer_resolution.py`: with the `billing-entitlement-agent` card published, drive a refund ticket → exactly one `task.requested` on `endpoint_topic("billing-entitlement-agent")` with `capability="analyze_refund_eligibility"`, the seven-field input, and a non-null `task_id`; assert a billing-delegation **audit** event is written (AC3); inject a billing `TaskResult` on `TOPIC_TASK_RESULT` keyed by that `task_id` and assert it correlates back to `case.billing` (AC4); **re-deliver the same ticket** → no second billing request and unchanged `case.billing.task_id` (AC2, SC-002/SC-005)
- [ ] T086 [P] [US5] Extend the isolation test (`apps/agents/customer_resolution/tests/test_domain_isolation.py`, T039) to assert the billing `TaskRequest.input` data keys are a **subset** of the seven permitted fields (fail if any billing/fraud-derived key leaks) and that the billing path performs no billing/payment datastore read (AC1, FR-005, SC-004)

**Checkpoint**: A refund ticket emits exactly one idempotent, audited billing `TaskRequest` to
`billing-entitlement-agent`/`analyze_refund_eligibility` carrying only the seven-field ticket context;
the billing result is awaited asynchronously on `TOPIC_TASK_RESULT`; no direct billing inspection
occurs — all four acceptance criteria satisfied.

### Phase 13 dependencies

- **Foundational T080** (request type) blocks T081–T086.
- **T081 → T082 → T083** sequence in `a2a_handlers.py` (build/send → async-result guard → audit);
  they build on US2's T022–T024 (runtime/discovery/delegate already present).
- **Tests T084 (a2a_handlers), T085/T086 (integration/isolation)** are `[P]` across different files and
  written before T081–T083.
- Symmetric to Phase 12 (Risk); reuses `001`/`002` transport, audit, idempotency, runtime, and
  discovery unchanged (FR-016, Principle V) — no new dependency, no second audit path.

---

## Phase 14: Implement Pluggable Case State Store (`CaseStateStore` / `InMemoryCaseStateStore`) — refines Phase 2 (T008/T010)

**Added by a follow-up `/speckit-tasks` request.** This section **supersedes and generalizes** the
in-process case state from Phase 2: the concrete `CaseStore` (T010) becomes a concrete
`InMemoryCaseStateStore` behind an abstract `CaseStateStore` **interface**, and the `CaseStatus`
enum + `ResolutionCase` fields (T008, data-model §4) are **expanded** to the richer set requested here.
It reuses the package layout (`models.py`, `state_store.py`, `agent.py`, tests under
`apps/agents/customer_resolution/tests/`) and continues the numbering (T087+).

**Reconciliation with the existing design (data-model §4 / T008 / T010 / Phases 12–13)**:

- **Statuses** expand from the 4-state machine (`INTAKE`/`AWAITING_ANALYSES`/`DECIDED`/`CLOSED_DIRECT`)
  to the 9 requested states. Mapping: `INTAKE → received`; (new) `classified`; `AWAITING_ANALYSES →
  waiting_for_peer_reviews`; (new) `ready_for_decision`; `DECIDED → decided`; (new) `response_drafted`;
  `CLOSED_DIRECT → closed`; (new) `escalated`; (new) `failed`. All earlier references (T011/T018/T025/
  T033/T034/T064/T065) are migrated to the new names.
- **Phases 12–13 overlap**: Phase 12 added `PENDING_RISK` and uses the `ESCALATE_HUMAN` outcome name.
  Reconcile here: `ESCALATE_HUMAN` case status folds into `escalated`; `PENDING_RISK` (risk request not
  sent — peer undiscoverable) is kept as a documented **sub-state of** `waiting_for_peer_reviews`
  carrying its own `reason`. Both stay reachable in the transition map (T089). The Phase 12/13 risk &
  billing request paths (`a2a_handlers.py`) are migrated onto the store interface in T095.
- **Fields** expand the `ResolutionCase`: add `case_id`, `classification`, `billing_result`,
  `risk_result`, `pending_tasks`, `deadline_at`. `case_id` is the domain identity; `correlation_id` is
  the envelope/case key (in this PoC they coincide — `case_id == correlation_id` — but both are stored
  so the store can index by either, satisfying the result-correlation criterion). `billing_result`/
  `risk_result` hold the normalized `BillingFinding`/`RiskFinding` (data-model §3) and **replace** the
  `AnalysisSlot.finding`; `pending_tasks` (a `set[UUID]` of outstanding billing/risk `task_id`s)
  replaces per-slot `received` tracking — a case is `ready_for_decision` when `pending_tasks` is empty
  (or a result `failed`/`rejected` forces escalation).
- **Liveness stays a documented gap** (research R6 / spec Assumptions): `deadline_at` is *recorded*
  (from the Phase 11 `DELEGATION_TIMEOUT_SECONDS`, T063) but **not** actively enforced; no timer
  reaps overdue cases. T094 documents this.

**Goal**: A storage-agnostic `CaseStateStore` interface with an `InMemoryCaseStateStore` PoC
implementation that (a) can be swapped for a Postgres/DynamoDB backend without touching the agent,
(b) keeps state uncorrupted under duplicate events, and (c) resolves a case from a result event by
both `case_id` and `correlation_id` (and the result's `task_id`).

**Independent Test**: Construct an `InMemoryCaseStateStore`, drive it through
received → classified → waiting_for_peer_reviews → ready_for_decision → decided; re-apply the same
intake and the same peer result and confirm state is unchanged (no duplicate `pending_tasks` removal,
no illegal transition); look a case up by `case_id`, by `correlation_id`, and by a peer `task_id` and
get the same case.

### Acceptance criteria → how each is met (from the `/speckit-tasks` request)

| Criterion | How it is satisfied | Verified by |
|-----------|---------------------|-------------|
| **Store interface can later be replaced with Postgres or DynamoDB** | `CaseStateStore` is an abstract, **async**, storage-agnostic interface (`Protocol`/ABC) with no in-memory types in its signatures; `InMemoryCaseStateStore` is one implementation; the agent/service depends on the interface (constructor-injected), so a `PostgresCaseStateStore`/`DynamoDbCaseStateStore` drops in unchanged | T090, T095, T096 |
| **Duplicate events do not corrupt state** | Idempotent `get_or_create` (returns the existing case on re-delivery); a monotonic transition map rejects illegal/backward status changes; applying a `task_id` already absent from `pending_tasks` is a no-op; optimistic `version` guards concurrent `save` | T089, T093, T097 |
| **Result events are correlated by `case_id` and `correlation_id`** | The store maintains secondary indexes and exposes `get_by_case_id`, `get_by_correlation_id`, and `get_by_task_id`; result-apply resolves the case from the envelope `correlation_id` + the result `task_id` | T092, T098 |

> **Async-by-design**: the interface methods are `async` even though the in-memory impl needs no I/O,
> so a future Postgres/DynamoDB implementation satisfies the same signatures without a breaking change.

### Foundational (model + status + transition map — blocks the store and tests)

- [ ] T087 [US3] Expand `CaseStatus` in `apps/agents/customer_resolution/models.py` to the 9 states `received`, `classified`, `waiting_for_peer_reviews`, `ready_for_decision`, `decided`, `response_drafted`, `closed`, `escalated`, `failed` (str Enum); add a module docstring recording the mapping from the old 4-state set (T008) and the Phase 12 `PENDING_RISK`/`ESCALATE_HUMAN` overlap, so existing references can be migrated
- [ ] T088 [US3] Expand `ResolutionCase` in `apps/agents/customer_resolution/models.py` with the tracked fields: `case_id: UUID`, `ticket_id: str`, `correlation_id: UUID`, `classification: CustomerIssueClassifiedPayload | None` (or the `Triage` summary), `billing_result: BillingFinding | None`, `risk_result: RiskFinding | None`, `pending_tasks: set[UUID]`, `status: CaseStatus`, `created_at: datetime`, `updated_at: datetime`, `deadline_at: datetime | None`; mark it **mutable** (drop `frozen` for this aggregate; keep `extra="forbid"`) since the store updates it, and note that `billing_result`/`risk_result`/`pending_tasks` supersede `AnalysisSlot`
- [ ] T089 [US3] Add an allowed-transition map and `can_transition(from, to) -> bool` / `assert_transition(...)` in `apps/agents/customer_resolution/models.py` enforcing the monotonic state machine (e.g. `received → classified → waiting_for_peer_reviews → ready_for_decision → decided → response_drafted → closed`, with `escalated`/`failed` reachable from the active states and `closed`/`failed` terminal); reject illegal/backward transitions — this is the core guard for "duplicate events do not corrupt state"

### Interface + implementation

- [ ] T090 [US3] Define the abstract `CaseStateStore` interface in `apps/agents/customer_resolution/state_store.py` as a `typing.Protocol` (or `abc.ABC`) with **async, storage-agnostic** methods: `get_or_create(case_id, *, ticket_id, correlation_id, created_at) -> ResolutionCase`, `get(case_id) -> ResolutionCase | None`, `get_by_correlation_id(correlation_id) -> ResolutionCase | None`, `get_by_task_id(task_id) -> ResolutionCase | None`, `save(case, *, expected_version=None) -> ResolutionCase`, and `transition(case_id, to_status) -> ResolutionCase`; no in-memory/dict types in any signature, with a docstring stating Postgres/DynamoDB back-ends implement the same Protocol (acceptance criterion 1)
- [ ] T091 [US3] Implement `InMemoryCaseStateStore(CaseStateStore)` in `apps/agents/customer_resolution/state_store.py`: a primary `dict[UUID, ResolutionCase]` keyed by `case_id`, secondary index dicts `correlation_id → case_id` and `task_id → case_id`, an `asyncio.Lock` guarding all mutations, and a per-case integer `version` for optimistic concurrency (`save` raises on a stale `expected_version`) — this **replaces** the T010 `CaseStore`
- [ ] T092 [US3] Implement the correlation lookups + result application in `apps/agents/customer_resolution/state_store.py`: `get_by_correlation_id`/`get_by_task_id` resolve via the secondary indexes; add `add_pending_task(case_id, task_id)` (registers the index entry) and `apply_result(case_id, task_id, finding)` that stores `billing_result`/`risk_result`, removes `task_id` from `pending_tasks`, and sets `ready_for_decision` when `pending_tasks` is empty (acceptance criterion 3)
- [ ] T093 [US3] Implement the duplicate-safety guards in `apps/agents/customer_resolution/state_store.py`: `get_or_create` returns the existing case (no overwrite) on a duplicate `case_id`/`correlation_id`; `apply_result` for a `task_id` **not** in `pending_tasks` is a logged no-op (already applied); `transition`/`save` route through `assert_transition` (T089) so a duplicate/late event cannot drive an illegal state change (acceptance criterion 2)
- [ ] T094 [US3] Set `deadline_at` in `apps/agents/customer_resolution/state_store.py` when a case enters `waiting_for_peer_reviews` (`= updated_at + DELEGATION_TIMEOUT_SECONDS` from `config.py`, T063), and add a code comment that the deadline is **recorded but not enforced** (no reaper) — the documented liveness gap (research R6, spec Assumptions)

### Wiring

- [ ] T095 [US3] Update `ResolutionService` in `apps/agents/customer_resolution/agent.py` (and `main.py`, T011) to accept a `CaseStateStore` via its constructor (defaulting to `InMemoryCaseStateStore()`), and migrate the intake/result/delegation handlers (`event_handlers.py`, `a2a_handlers.py`; T018/T025/T034/T064/T065 and the Phase 12/13 risk & billing paths T071–T072/T081–T083) to use the interface methods and the new status names — so no handler imports the concrete store directly (acceptance criterion 1)

### Tests (write first — must FAIL before implementation)

- [ ] T096 [P] [US3] Interface-substitutability test in `apps/agents/customer_resolution/tests/test_state_store.py`: define a trivial second `CaseStateStore` implementation (or a `unittest.mock`-backed stub) and assert `ResolutionService` drives a case end-to-end against it unchanged, and that `InMemoryCaseStateStore` satisfies `isinstance(..., CaseStateStore)` / the Protocol (acceptance criterion 1)
- [ ] T097 [P] [US3] Duplicate-event test in `apps/agents/customer_resolution/tests/test_state_store.py`: a repeated `get_or_create` returns the same case with unchanged `version`/fields; applying the same peer result twice removes the `task_id` only once and never double-writes `billing_result`/`risk_result`; an illegal transition (e.g. `decided → waiting_for_peer_reviews`) raises (acceptance criterion 2)
- [ ] T098 [P] [US3] Correlation test in `apps/agents/customer_resolution/tests/test_state_store.py`: after `add_pending_task`, the case is retrievable by `get_by_case_id`, `get_by_correlation_id`, and `get_by_task_id` (all the same case), and `apply_result(case_id, task_id, ...)` correlates a result back to its case by both `case_id` and `correlation_id` (acceptance criterion 3)

**Checkpoint**: A pluggable, duplicate-safe, correlation-indexed case store backs the agent; swapping
in a DB implementation requires no change to handlers or service.

### Phase 14 dependencies

- **Foundational T087–T089** block the store. T087 (statuses) and T088 (fields) before T089 (transition
  map references both); all three precede T090–T095.
- **Interface/impl**: T090 (interface) → T091 (in-memory impl) → T092 (lookups/apply) → T093 (guards) →
  T094 (deadline). T095 (wiring) depends on T090–T093 and supersedes the T010/T011 store wiring.
- **Tests T096/T097/T098** are written first against the T090 interface and must fail before T091–T095;
  they are `[P]` only if kept as independent test functions with no shared mutable fixture.
- **Supersedes**: this phase replaces the concrete `CaseStore` of T010 and the `CaseStatus`/
  `ResolutionCase` of T008 — when implementing, treat T087–T095 as the authoritative case-state design.

---

## Phase 15: Consume Billing Result Events — `local.billing.refund-analysis.completed.v1` (hardens US3)

**Added by a follow-up `/speckit-tasks` request.** This section is **additive** to the feature above —
it pins and hardens the **billing-result-consumption leg** of US3 (Phase 5) to the explicit billing
**domain completion event** `local.billing.refund-analysis.completed.v1`, against the four acceptance
criteria from the request. It continues the numbering (T099+) and reuses this file's package layout
(`event_handlers.py`, `state_store.py`, `agent.py`, contracts in `packages/contracts/`, tests under
`apps/agents/customer_resolution/tests/`).

**Builds on the Phase 14 `CaseStateStore`.** This phase consumes results **into** the pluggable store
defined in Phase 14 (T090–T093): it uses the async `get_by_correlation_id`, `apply_result(case_id,
task_id, finding)`, the `ready_for_decision` status, the `pending_tasks` set, and the duplicate-safe
no-op guard (T093) — it does **not** add a parallel store or a second state machine.

**Reconciliation with US3 (Phase 5).** US3's result handler (T034) consumes the **generic** A2A
`TaskResult` on `TOPIC_TASK_RESULT` and correlates by `task_id`. This phase adds the **billing-domain**
ingress: the billing peer's `BillingRefundAnalysisCompletedPayload` published on
`local.billing.refund-analysis.completed.v1`, which carries a `ticket_id` but **no `task_id`**.
Correlation is therefore by the envelope **`correlation_id`** (`get_by_correlation_id`); the case's
recorded billing `task_id` (from the Phase 13 delegation, T081) is then the key passed to
`apply_result(...)` so the result clears the billing entry in `pending_tasks`. Both ingresses
**normalize into the same `BillingFinding`** (the T030 adapter) and feed the same decision path
(T031/T034) — one decision policy, one "exactly one decision per case" guarantee. **No billing business
logic is added here** — the payload is consumed, never produced (FR-005).

**Goal**: A dedicated `Consumer` on `local.billing.refund-analysis.completed.v1` attaches each billing
result to its matching open case via the Phase 14 store, logs-and-parks results with no matching case,
is idempotent under duplicate delivery, and lets a case reach `ready_for_decision` only when every
required result is present — never emitting a premature or second decision.

**Independent Test**: For an open refund case awaiting billing, publish a
`local.billing.refund-analysis.completed.v1` event whose `envelope.correlation_id` matches the case →
the billing result is applied and (risk still in `pending_tasks`) **no** decision is emitted; supply
risk too → the case reaches `ready_for_decision` and exactly one decision is emitted. Publish a billing
result for an **unknown** `correlation_id` → it is logged and parked/ignored, no case created, no
crash. Re-deliver an already-applied billing result → no second apply and no second decision.

### Acceptance criteria → how each is met (from the `/speckit-tasks` request)

| Criterion | How it is satisfied | Verified by |
|-----------|---------------------|-------------|
| **Result is attached to matching case state** | The handler resolves the case via `store.get_by_correlation_id(envelope.correlation_id)` (guard: payload `ticket_id`), normalizes `BillingRefundAnalysisCompletedPayload`→`BillingFinding` via the T030 adapter, and calls `store.apply_result(case_id, case.billing_task_id, finding)` which sets `billing_result` and clears the billing `task_id` from `pending_tasks` (AC1, reuses Phase 14 T092) | T102, T104, T108 |
| **Unknown case results are logged and ignored or parked** | `get_by_correlation_id` returns `None` ⇒ a structured `structlog` warning + the result is placed in a bounded `parked_results` buffer keyed by `correlation_id` (drained if the case later appears) — never creates a spurious case, never raises (AC2) | T105, T109, T111 |
| **Duplicate results are idempotent** | Two layers: the consumer's `IdempotencyTracker` (envelope `event_id`) skips exact re-delivery; the Phase 14 `apply_result` no-op guard (T093) makes a billing result whose `task_id` is already absent from `pending_tasks` (or a case already `decided`) a logged no-op — no second `billing_result` write, no second decision (FR-011/FR-012) (AC3) | T106, T110, T111 |
| **Case moves to ready_for_decision only when required results are present** | `apply_result` sets `ready_for_decision` **only** when `pending_tasks` becomes empty (Phase 14 T092); with risk still pending the case stays `waiting_for_peer_reviews` and the handler emits no decision; a `failed`/`rejected` billing result forces escalation instead (AC4, FR-008) | T107, T110, T111 |

> **Consumed, never produced.** `local.billing.refund-analysis.completed.v1` is registered in
> `PAYLOAD_REGISTRY` **only so the shared `Consumer` can validate/deserialize it on receive** — the
> resolution agent never publishes it (the billing peer does). Correlation uses the envelope
> `correlation_id` the billing peer carries forward from the originating ticket's causal chain; the
> payload `ticket_id` is a human-readable secondary guard (research R3, R5).

### Foundational (contract registration + topic provisioning — blocks the consume path and tests)

- [ ] T099 [US3] Add `TOPIC_BILLING_RESULT = topic_for("billing", "refund-analysis", "completed")` (resolves to `local.billing.refund-analysis.completed.v1`) in `packages/contracts/topics.py`, beside `TOPIC_TASK_RESULT`
- [ ] T100 [US3] Register `"local.billing.refund-analysis.completed.v1": BillingRefundAnalysisCompletedPayload` in `PAYLOAD_REGISTRY` in `src/agent_foundation/payloads/__init__.py` (import the **existing** model from `packages/contracts/events/payloads.py` — no new model) so the shared `Consumer` validates/deserializes it on receive (depends on T099)
- [ ] T101 [US3] Wire transport resolution + provisioning in `src/agent_foundation/transport/topics.py`: add the event-type→topic mapping to `TOPIC_NAMES` (key == value == `TOPIC_BILLING_RESULT`, new-style convention) and append `NewTopic(name=TOPIC_BILLING_RESULT, num_partitions=1, replication_factor=1, topic_configs={"retention.ms": str(_SEVEN_DAYS_MS)})` to `_CANONICAL_TOPICS` (event stream, not compacted) (depends on T099)

### Tests (write first — must FAIL before implementation)

- [ ] T102 [P] [US3] Unit test **attach/correlation** in `apps/agents/customer_resolution/tests/test_state_store.py`: a billing result whose envelope `correlation_id` matches an open case resolves via `get_by_correlation_id`, normalizes to `BillingFinding`, and `apply_result(case_id, billing_task_id, finding)` sets `billing_result` and removes the billing `task_id` from `pending_tasks`; a `ticket_id` mismatch on a matched correlation id is logged as a guard warning (AC1)
- [ ] T103 [P] [US3] Contract test in `apps/agents/customer_resolution/tests/test_resolution_schemas.py`: assert `BillingRefundAnalysisCompletedPayload` round-trips, that `lookup("local.billing.refund-analysis.completed.v1")` returns it, and that `TOPIC_NAMES` resolves the same key (T099/T100/T101)
- [ ] T104 [P] [US3] Unit test the **result-normalization** of the billing completion payload in `apps/agents/customer_resolution/tests/test_adapters.py`: `recommendation ∈ {approve,eligible,refund}` → `eligible=True`, `{deny,ineligible,reject}` → `eligible=False`, `requires_human_review` passthrough, and an unparseable/`failed` result → slot `failed`/`unparseable_result` (never fabricated) (AC1, analysis-result-contract.md, decision-policy.md §B)
- [ ] T105 [P] [US3] Unit test the **unknown-case** path in `apps/agents/customer_resolution/tests/test_state_store.py`: a billing result whose `correlation_id` matches no open case is parked in the bounded `parked_results` buffer and a structured warning is logged; no case is created and no exception escapes; if the case later appears, the parked result is drained and applied (AC2)
- [ ] T106 [P] [US3] Unit test **duplicate idempotency** in `apps/agents/customer_resolution/tests/test_state_store.py`: a second billing result for a `task_id` already absent from `pending_tasks` (and one for an already-`decided` case) is a logged no-op — `billing_result` is not overwritten, `pending_tasks` is unchanged, and no second decision is armed (AC3, reuses Phase 14 T093)
- [ ] T107 [P] [US3] Unit test the **readiness gate** in `apps/agents/customer_resolution/tests/test_state_store.py`: after a billing-only `apply_result` the case stays `waiting_for_peer_reviews` (risk still in `pending_tasks` ⇒ no decision); after the risk result clears `pending_tasks` the case becomes `ready_for_decision`; a `failed` billing result short-circuits to escalation (AC4, FR-008)
- [ ] T108 [P] [US3] Integration test in `apps/agents/customer_resolution/tests/test_customer_resolution.py`: for an open refund case, publish a billing result on `local.billing.refund-analysis.completed.v1` (matching `correlation_id`) → billing applied, **no** decision while risk pending; then supply risk → exactly one decision (AC1/AC4); publish a billing result for an **unknown** `correlation_id` → no decision, no crash, audit/log shows it parked (AC2); **re-deliver** the same billing result → no second decision (AC3)

### Implementation

- [ ] T109 [US3] Implement `attach_billing_result(envelope, payload) -> AttachOutcome` in `apps/agents/customer_resolution/state_store.py` (or `agent.py`): `await store.get_by_correlation_id(envelope.correlation_id)` (guard: compare payload `ticket_id` to `case.ticket_id`, log on mismatch), normalize via the T030 `BillingFinding` adapter, `await store.apply_result(case.case_id, case.billing_task_id, finding)`, and return an outcome enum (`attached` / `unknown_case` / `duplicate`) for the handler + audit to branch on (AC1, reuses Phase 14 T092/T093 and the T030 adapter)
- [ ] T110 [US3] Implement the bounded in-process `parked_results` buffer on the store in `apps/agents/customer_resolution/state_store.py`: park `unknown_case` billing results keyed by `correlation_id` with a structured `structlog` warning, cap its size (drop-oldest), and drain a parked result into the case when that `correlation_id` is later created (`get_or_create`) — never create a case from a parked result (AC2; in-process-state durability remains the documented gap, research R6)
- [ ] T111 [US3] Implement the billing-result `Consumer` handler in `apps/agents/customer_resolution/event_handlers.py`: subscribe to `TOPIC_BILLING_RESULT` with `IdempotencyTracker`, call `attach_billing_result(...)`, and **only** when the case status is `ready_for_decision` invoke the shared `decide(...)`/emit-decision path (T031/T034) to emit **exactly one** `customer.resolution.decided` event; for `unknown_case`/`duplicate` outcomes emit audit + log and return without deciding; wire this `Consumer` into `agent.py`/`main.py` under the process `asyncio.gather`, sharing the Phase 14 `CaseStateStore` with the intake and `TOPIC_TASK_RESULT` loops (AC1–AC4, research R3/R7)

### Audit (extends US4)

- [ ] T112 [US4] Emit a "billing result consumed" audit step in `apps/agents/customer_resolution/event_handlers.py` via `agent_foundation.audit.store.write_task_audit`/`write_audit` carrying agent identity, `correlation_id`, causation link, timestamp, and the attach outcome (`outcome="completed"` on attach, `"duplicate_skipped"` on a duplicate, `"rejected"`/`reason="unknown_case"` on a parked unknown-case result) so every billing-result disposition is reconstructable by correlation id (extends the step list in T037/T083; FR-013/FR-014, SC-006)

**Checkpoint**: Billing results delivered on `local.billing.refund-analysis.completed.v1` attach to the
matching case via the Phase 14 store, let a case reach `ready_for_decision` only when all required
results are present, are inert under duplicate delivery, and are safely parked/logged when no case
matches — all four acceptance criteria satisfied, with the decision still emitted exactly once via the
shared US3 policy.

### Phase 15 dependencies

- **Foundational T099–T101** block everything in this phase. T099 → T100 (register needs the constant)
  and T099 → T101 (provisioning needs the constant); T100 ∥ T101 (different files).
- **Builds on Phase 14**: the store interface (T090), `get_by_correlation_id`/`apply_result` (T092),
  the duplicate no-op guard (T093), and the `ready_for_decision`/`pending_tasks` model (T087/T088). The
  case's recorded billing `task_id` comes from the Phase 13 delegation (T081).
- **Tests T102–T108** (different files, `[P]`) are written first and must fail before T109–T111.
- **Impl**: T109 (attach/correlate) → T110 (parking, attaches to T109's `unknown_case` outcome) → T111
  (consumer wiring + decision emit). T111 also requires the Phase 2 process (T011), the T030 adapter,
  and the US3 decision path (T031/T034).
- **T112** (audit) follows T111 and folds into the US4 audit step list (T037).
- Reuses `001`/`002` transport, audit, idempotency, the Phase 14 store, and the existing
  `BillingRefundAnalysisCompletedPayload` contract unchanged (FR-016, Principle V) — no new dependency,
  no new model, no second audit path.

---

## Phase 16: Consume Risk Result Events — `local.risk.review.completed.v1` (hardens US3/US4)

**Added by a follow-up `/speckit-tasks` request.** This section is **additive** to the feature above —
it is the **risk counterpart to Phase 15** (billing): it pins and hardens the **risk-result-consumption
leg** of US3 (Phase 5) to the explicit risk **domain completion event**
`local.risk.review.completed.v1`, against the four acceptance criteria from the request. It continues
the numbering (T113+) and reuses this file's package layout (`event_handlers.py`, `state_store.py`,
`agent.py`, `decision_engine.py`, contracts in `packages/contracts/`, tests under
`apps/agents/customer_resolution/tests/`).

**Builds on the Phase 14 `CaseStateStore`.** This phase consumes results **into** the pluggable store
defined in Phase 14 (T090–T093): it uses the async `get_by_correlation_id`, `apply_result(case_id,
task_id, finding)`, the `ready_for_decision`/`escalated` statuses, the `pending_tasks` set, and the
duplicate-safe no-op guard (T093) — it does **not** add a parallel store or a second state machine. It
also reuses the bounded `parked_results` buffer from Phase 15 (T110) for unknown-case results.

**Reconciliation with US3 (Phase 5) and Phase 12.** US3's result handler (T034) consumes the **generic**
A2A `TaskResult` on `TOPIC_TASK_RESULT` correlated by `task_id`; Phase 12 hardened the risk **request**
leg. This phase adds the **risk-domain** ingress: the risk peer's `RiskReviewCompletedPayload` published
on `local.risk.review.completed.v1`, which carries a `ticket_id` but **no `task_id`**. Correlation is
therefore by the envelope **`correlation_id`** (`get_by_correlation_id`); the case's recorded risk
`task_id` (from the Phase 12 delegation, T071) is the key passed to `apply_result(...)` so the result
clears the risk entry in `pending_tasks`. Both ingresses **normalize into the same `RiskFinding`** (the
T030 adapter) and feed the same decision path (T031/T034) — one policy, one "exactly one decision per
case" guarantee. **No risk/fraud business logic is added here** — the payload is consumed, never
produced (FR-005). Where a single risk-result path is desired, this domain-event path **supersedes** the
`TaskResult` risk leg (T125 gates the T034 risk handling so a case's `risk_result` is not written twice).

**Goal**: A dedicated `Consumer` on `local.risk.review.completed.v1` attaches each risk result to its
matching open case via the Phase 14 store, logs-and-parks results with no matching case, is idempotent
under duplicate delivery, and lets a **high/elevated** risk verdict force an immediate `escalated`
decision (short-circuiting the billing wait) — never emitting a premature or second decision.

**Independent Test**: For an open refund case awaiting risk, publish a `local.risk.review.completed.v1`
event whose `envelope.correlation_id` matches the case → the risk result is applied; a `low`-risk
verdict with billing still pending emits **no** decision (case stays `waiting_for_peer_reviews`), while
a `high`-risk verdict emits exactly one `escalate_human` decision and moves the case to `escalated`
even before billing arrives. Publish a risk result for an **unknown** `correlation_id` → it is logged
and parked/ignored, no case created, no crash. Re-deliver an already-applied risk result → no second
apply and no second decision.

### Acceptance criteria → how each is met (from the `/speckit-tasks` request)

| Criterion | How it is satisfied | Verified by |
|-----------|---------------------|-------------|
| **Result is attached to matching case state** | The handler resolves the case via `store.get_by_correlation_id(envelope.correlation_id)` (guard: payload `ticket_id`), normalizes `RiskReviewCompletedPayload`→`RiskFinding` via the T030 adapter, and calls `store.apply_result(case_id, case.risk_task_id, finding)` which sets `risk_result` and clears the risk `task_id` from `pending_tasks` (AC1, reuses Phase 14 T092) | T116, T118, T123 |
| **Unknown case results are logged and ignored or parked** | `get_by_correlation_id` returns `None` ⇒ a structured `structlog` warning + the result is placed in the bounded `parked_results` buffer (Phase 15 T110) keyed by `correlation_id` (drained if the case later appears) — never creates a spurious case, never raises (AC2) | T119, T124, T122 |
| **Duplicate results are idempotent** | Two layers: the consumer's `IdempotencyTracker` (envelope `event_id`) skips exact re-delivery; the Phase 14 `apply_result` no-op guard (T093) makes a risk result whose `task_id` is already absent from `pending_tasks` (or a case already `decided`/`escalated`) a logged no-op — no second `risk_result` write, no second decision (FR-011/FR-012) (AC3) | T120, T125 |
| **High-risk result can force escalation** | After attach, the handler runs the shared `decide(...)` (decision-policy.md escalation precedence): `RiskFinding.level ∈ {elevated, high}` or `requires_human_review=True` ⇒ emit **exactly one** `escalate_human` decision (non-null `escalation_reason`) and `transition(case_id, escalated)` — short-circuiting the billing wait (AC4, FR-007/FR-010, research R4) | T121, T125, T122 |

> **Consumed, never produced.** `local.risk.review.completed.v1` is registered in `PAYLOAD_REGISTRY`
> **only so the shared `Consumer` can validate/deserialize it on receive** — the resolution agent never
> publishes it (the risk peer does). Correlation uses the envelope `correlation_id` the risk peer
> carries forward from the originating ticket's causal chain; the payload `ticket_id` is a
> human-readable secondary guard (research R3, R5). `RiskReviewCompletedPayload` already exists in
> `packages/contracts/events/payloads.py` — only registered here, no new model.

### Foundational (contract registration + topic provisioning — blocks the consume path and tests)

- [ ] T113 [US3] Add `TOPIC_RISK_RESULT = topic_for("risk", "review", "completed")` (resolves to `local.risk.review.completed.v1`) in `packages/contracts/topics.py`, beside `TOPIC_TASK_RESULT` / `TOPIC_BILLING_RESULT`
- [ ] T114 [US3] Register `"local.risk.review.completed.v1": RiskReviewCompletedPayload` in `PAYLOAD_REGISTRY` in `src/agent_foundation/payloads/__init__.py` (import the **existing** model from `packages/contracts/events/payloads.py` — no new model) so the shared `Consumer` validates/deserializes it on receive (depends on T113)
- [ ] T115 [US3] Wire transport resolution + provisioning in `src/agent_foundation/transport/topics.py`: add the event-type→topic mapping to `TOPIC_NAMES` (key == value == `TOPIC_RISK_RESULT`, new-style convention) and append `NewTopic(name=TOPIC_RISK_RESULT, num_partitions=1, replication_factor=1, topic_configs={"retention.ms": str(_SEVEN_DAYS_MS)})` to `_CANONICAL_TOPICS` (event stream, not compacted) (depends on T113)

### Tests (write first — must FAIL before implementation)

- [ ] T116 [P] [US3] Unit test **attach/correlation** in `apps/agents/customer_resolution/tests/test_state_store.py`: a risk result whose envelope `correlation_id` matches an open case resolves via `get_by_correlation_id`, normalizes to `RiskFinding`, and `apply_result(case_id, risk_task_id, finding)` sets `risk_result` and removes the risk `task_id` from `pending_tasks`; a `ticket_id` mismatch on a matched correlation id is logged as a guard warning (AC1)
- [ ] T117 [P] [US3] Contract test in `apps/agents/customer_resolution/tests/test_resolution_schemas.py`: assert `RiskReviewCompletedPayload` round-trips, that `lookup("local.risk.review.completed.v1")` returns it, and that `TOPIC_NAMES` resolves the same key (T113/T114/T115)
- [ ] T118 [P] [US3] Unit test the **result-normalization** of the risk completion payload in `apps/agents/customer_resolution/tests/test_adapters.py`: `recommendation`→`level` (low/elevated/high), `requires_human_review` passthrough, `confidence`/`score` carried, and an unparseable/out-of-vocabulary `recommendation` → slot `failed`/`unparseable_result` (never fabricated) (AC1, analysis-result-contract.md "Risk analysis data part", decision-policy.md §B)
- [ ] T119 [P] [US3] Unit test the **unknown-case** path in `apps/agents/customer_resolution/tests/test_state_store.py`: a risk result whose `correlation_id` matches no open case is parked in the bounded `parked_results` buffer (Phase 15 T110) and a structured warning is logged; no case is created and no exception escapes; if the case later appears, the parked result is drained and applied (AC2)
- [ ] T120 [P] [US3] Unit test **duplicate idempotency** in `apps/agents/customer_resolution/tests/test_state_store.py`: a second risk result for a `task_id` already absent from `pending_tasks` (and one for an already-`decided`/`escalated` case) is a logged no-op — `risk_result` is not overwritten, `pending_tasks` is unchanged, and no second decision is armed (AC3, reuses Phase 14 T093)
- [ ] T121 [P] [US4] Unit test **high-risk escalation** in `apps/agents/customer_resolution/tests/test_decision_engine.py`: `decide(...)` returns `escalate_human` (reason "elevated risk") for `RiskFinding.level ∈ {elevated, high}` and for `requires_human_review=True`, taking precedence over a pending/eligible billing result (AC4, decision-policy.md §C/§D escalation precedence, research R4)
- [ ] T122 [P] [US3] Integration test in `apps/agents/customer_resolution/tests/test_customer_resolution.py`: for an open refund case, publish a `low`-risk result on `local.risk.review.completed.v1` (matching `correlation_id`) → risk applied, **no** decision while billing pending (AC1); publish a `high`-risk result → exactly one `escalate_human` decision emitted, case `escalated`, even before billing arrives (AC4); publish a risk result for an **unknown** `correlation_id` → no decision, no crash, audit/log shows it parked (AC2); **re-deliver** the same risk result → no second decision (AC3)

### Implementation

- [ ] T123 [US3] Implement `attach_risk_result(envelope, payload) -> AttachOutcome` in `apps/agents/customer_resolution/state_store.py` (or `agent.py`): `await store.get_by_correlation_id(envelope.correlation_id)` (guard: compare payload `ticket_id` to `case.ticket_id`, log on mismatch), normalize via the T030 `RiskFinding` adapter, `await store.apply_result(case.case_id, case.risk_task_id, finding)`, and return an outcome enum (`attached` / `unknown_case` / `duplicate`) for the handler + audit to branch on (AC1, reuses Phase 14 T092/T093 and the T030 adapter)
- [ ] T124 [US3] Reuse the bounded in-process `parked_results` buffer (Phase 15 T110) for `unknown_case` risk results in `apps/agents/customer_resolution/state_store.py`: park keyed by `correlation_id` with a structured `structlog` warning, drained into the case when that `correlation_id` is later created (`get_or_create`) — never create a case from a parked result; if T110 does not yet exist, implement the shared buffer here (AC2; in-process-state durability remains the documented gap, research R6)
- [ ] T125 [US4] Implement the risk-result `Consumer` handler in `apps/agents/customer_resolution/event_handlers.py`: subscribe to `TOPIC_RISK_RESULT` with `IdempotencyTracker`, call `attach_risk_result(...)`, then run the shared `decide(...)` — if the risk finding **forces escalation** (`level ∈ {elevated, high}` or `requires_human_review`) emit **exactly one** `customer.resolution.decided` (`outcome=escalate_human`, non-null `escalation_reason`, `risk_summary`) and `transition(case_id, escalated)` even with billing still pending (AC4); otherwise emit a decision **only** when the case reached `ready_for_decision` (T031/T034); for `unknown_case`/`duplicate` outcomes emit audit + log and return without deciding; **gate the T034 `TaskResult` risk-slot handling** (skip risk-keyed `apply_result`) so `risk_result` is not written twice; wire this `Consumer` into `agent.py`/`main.py` under the process `asyncio.gather`, sharing the Phase 14 `CaseStateStore` with the intake, `TOPIC_TASK_RESULT`, and `TOPIC_BILLING_RESULT` loops (AC1–AC4, research R3/R7)

### Audit (extends US4)

- [ ] T126 [US4] Emit a "risk result consumed" audit step in `apps/agents/customer_resolution/event_handlers.py` via `agent_foundation.audit.store.write_task_audit`/`write_audit` carrying agent identity, `correlation_id`, causation link, timestamp, and the attach/decision outcome (`outcome="completed"` on attach, `"duplicate_skipped"` on a duplicate, `"rejected"`/`reason="unknown_case"` on a parked unknown-case result, and the escalation `reason` on a forced escalation) so every risk-result disposition is reconstructable by correlation id (extends the step list in T037/T112; FR-013/FR-014, SC-006/SC-007)

**Checkpoint**: Risk results delivered on `local.risk.review.completed.v1` attach to the matching case
via the Phase 14 store, force a single `escalated` decision on elevated/high risk (short-circuiting the
billing wait), are inert under duplicate delivery, and are safely parked/logged when no case matches —
all four acceptance criteria satisfied, with the decision still emitted exactly once via the shared US3
policy.

### Phase 16 dependencies

- **Foundational T113–T115** block everything in this phase. T113 → T114 (register needs the constant)
  and T113 → T115 (provisioning needs the constant); T114 ∥ T115 (different files).
- **Builds on Phase 14**: the store interface (T090), `get_by_correlation_id`/`apply_result` (T092),
  the duplicate no-op guard (T093), and the `ready_for_decision`/`escalated`/`pending_tasks` model
  (T087/T088/T089). The case's recorded risk `task_id` comes from the Phase 12 delegation (T071). The
  `parked_results` buffer comes from Phase 15 (T110).
- **Tests T116–T122** (different files, `[P]`) are written first and must fail before T123–T125.
- **Impl**: T123 (attach/correlate) → T124 (parking, attaches to T123's `unknown_case` outcome) → T125
  (consumer wiring + escalation/decision emit). T125 also requires the Phase 2 process (T011), the T030
  adapter, the US3 decision path (T031/T034), and the US4 escalation reason (T038).
- **T126** (audit) follows T125 and folds into the US4 audit step list (T037).
- Reuses `001`/`002` transport, audit, idempotency, the Phase 14 store, and the existing
  `RiskReviewCompletedPayload` contract unchanged (FR-016, Principle V) — no new dependency, no new
  model, no second audit path.

---

## Phase 17: Publish Customer Response Drafted Event — `local.resolution.customer-response.drafted.v1` (extends US3/US4)

**Added by a follow-up `/speckit-tasks` request.** This section is **additive** to the feature above —
it introduces a **new domain event** the agent emits immediately **after** it publishes the final
`customer.resolution.decided.v1` decision: a customer-delivery-candidate **draft** of the
customer-facing message, **linked to** that decision event, written in **safe customer-facing
language**, and carrying a **`requires_human_approval`** gate. It is distinct from
`customer.resolution.decided.v1` (the accountable internal decision) and is **not** part of the
original spec/plan/data-model. Tasks continue the numbering (T127+) and reuse this file's package
layout (`response_drafter.py`, `decision_engine.py`, `event_handlers.py`, `config.py`, contracts in
`packages/contracts/`, tests under `apps/agents/customer_resolution/tests/`).

**Reconciliation with the existing design — the draft is *not* a duplicate of the decision.** The
decision payload already carries `customer_response` (data-model §7, drafted by `response_drafter.py`
in T016/T032) as the **auditable record of what the customer would be told**, alongside internal-only
fields (`rationale`, `escalation_reason`, `billing_summary`, `risk_summary`). This phase re-emits
**only** that customer-facing text as a separate event on its own topic so a downstream
delivery/approval surface can consume it **without parsing decisions or seeing internal rationale**,
gated by `requires_human_approval`. This is consistent with the spec Assumption that *actually
delivering* the response to a customer channel is out of scope while *producing the auditable artifact*
is in scope. The Phase 14 state machine already anticipates this step: `decided → response_drafted →
closed` (T087); if Phase 14 is not yet implemented, the draft is emitted after the `DECIDED` terminal
state (data-model §4) with no status change.

**Emitted after every decision.** Every `customer.resolution.decided.v1` event — `direct_response`,
`approve_refund`, `deny_refund`, `escalate_human` — produces exactly one corresponding drafted event,
so every resolved ticket yields a single customer-facing artifact.

**Goal**: After the agent emits a `customer.resolution.decided.v1` event for a case, it publishes
exactly one `local.resolution.customer-response.drafted.v1` event carrying `case_id`, `ticket_id`,
`customer_id`, `decision_event_id` (the linked decision's `event_id`), `outcome`, `draft_response`
(safe customer-facing text only), `requires_human_approval`, `drafted_by_agent_id`, and `drafted_at`.

**Independent Test**: Drive an `escalate_human` (or `approve_refund`) case end-to-end → after the
decision, observe exactly one event on `local.resolution.customer-response.drafted.v1` whose
`envelope.causation_id` equals the decided event's `event_id`, whose `payload.decision_event_id`
equals it too, whose `requires_human_approval` is `true`, and whose `draft_response` contains **none**
of the decision's internal fields (`rationale`/`escalation_reason`/`billing_summary`/`risk_summary`);
drive a `deny_refund`/`direct_response` case → `requires_human_approval` is `false`; re-deliver a
ticket → no second drafted event.

### Acceptance criteria → how each is met (from the `/speckit-tasks` request)

| Criterion | How it is satisfied | Verified by |
|-----------|---------------------|-------------|
| **Drafted response is linked to decision event** | Dual linkage: the envelope's `causation_id` is set to the just-emitted `customer.resolution.decided.v1` event's `event_id`, **and** the payload carries `decision_event_id == <that event_id>` plus `case_id`/`correlation_id == <case correlation id>` — so the draft is traceable to its decision by both the causal chain and an explicit field (FR-014) | T132, T133, T139 |
| **Draft contains safe customer-facing language** | `draft_response` is built **solely** from the customer-facing template in `response_drafter.py` (the same text as `decision.customer_response`), which never concatenates the internal-only fields (`rationale`/`escalation_reason`/`billing_summary`/`risk_summary`); a source-level guard (T137) and a test (T134) assert no internal field content leaks into the draft | T134, T137, T139 |
| **Event includes `requires_human_approval`** | The payload has a required `requires_human_approval: bool` set by a deterministic, auditable policy in `config.py`/`decision_engine.py` (`escalate_human` ⇒ `True`; `approve_refund` ⇒ `True` (money movement); `deny_refund`/`direct_response` ⇒ `False`); a `model_validator` enforces `outcome == escalate_human ⇒ requires_human_approval is True` | T131, T132, T136 |

> **Non-root event**: `local.resolution.customer-response.drafted.v1` is not a root type, so the
> envelope's `causation_id` is **required** — set it to the **decision** event's `event_id` (which
> also satisfies the "linked to decision event" criterion), or `EventEnvelope` validation raises
> `MissingCausation` (`src/agent_foundation/envelope.py`). Producer identity is `envelope.agent_id`,
> set by `Publisher` from the process `AgentIdentity(agent_id="customer-resolution-agent")`.

### Foundational (contract + registry + topic — blocks the publish path and tests)

- [ ] T127 [US3] Add `CustomerResponseDraftedPayload` (Pydantic v2, `frozen`, `extra="forbid"`) to `packages/contracts/events/payloads.py` with fields `case_id: UUID` (the resolution-case identity = decision envelope `correlation_id`), `ticket_id: str`, `customer_id: str`, `decision_event_id: UUID` (the linked `customer.resolution.decided.v1` event's `event_id`), `outcome: ResolutionOutcome` (reuse the enum from `CustomerResponseDecisionPayload`, T004), `draft_response: str`, `requires_human_approval: bool`, `drafted_by_agent_id: str = "customer-resolution-agent"`, `drafted_at: datetime`; add a `model_validator(mode="after")` requiring `draft_response` non-empty and `outcome == escalate_human ⇒ requires_human_approval is True`; add it to the module `__all__`
- [ ] T128 [P] [US3] Add `TOPIC_RESPONSE_DRAFTED = topic_for("resolution","customer-response","drafted")` (resolves to `local.resolution.customer-response.drafted.v1`) in `packages/contracts/topics.py`, beside `TOPIC_RESOLUTION_DECIDED`
- [ ] T129 [US3] Register `"local.resolution.customer-response.drafted.v1": CustomerResponseDraftedPayload` in `PAYLOAD_REGISTRY` in `src/agent_foundation/payloads/__init__.py` so `Publisher`/`Consumer` validate it on send/receive (depends on T127, T128)
- [ ] T130 [US3] Wire transport resolution + provisioning in `src/agent_foundation/transport/topics.py`: add the event-type→topic mapping to `TOPIC_NAMES` (key == value == `TOPIC_RESPONSE_DRAFTED`, new-style convention) and append `NewTopic(name=TOPIC_RESPONSE_DRAFTED, num_partitions=1, replication_factor=1, topic_configs={"retention.ms": str(_SEVEN_DAYS_MS)})` to `_CANONICAL_TOPICS` (event stream, not compacted) (depends on T128)

### Human-approval policy + safe-language constraints (config)

- [ ] T131 [US3] Add the deterministic human-approval policy and safe-language constraint set to `apps/agents/customer_resolution/config.py`: `HUMAN_APPROVAL_OUTCOMES = {ResolutionOutcome.ESCALATE_HUMAN, ResolutionOutcome.APPROVE_REFUND}` (illustrative PoC policy — escalations need a human; approving a refund moves money so it is human-gated), and `INTERNAL_ONLY_DRAFT_FIELDS = ("rationale", "escalation_reason", "billing_summary", "risk_summary")` naming the decision fields that MUST NOT appear in a customer draft; document both as demonstration values, not production policy (extends T009)

### Tests (write first — must FAIL before implementation)

- [ ] T132 [P] [US3] Extend `apps/agents/customer_resolution/tests/test_resolution_schemas.py`: assert `CustomerResponseDraftedPayload` round-trips, that `lookup("local.resolution.customer-response.drafted.v1")` returns it, that `TOPIC_NAMES` resolves the same key, that an empty `draft_response` raises `ValidationError`, and that `outcome=escalate_human` with `requires_human_approval=False` raises `ValidationError` (T127/T128/T129/T130)
- [ ] T133 [P] [US3] Add `apps/agents/customer_resolution/tests/test_response_drafted.py`: build the drafted envelope (via T135) from a sample decided envelope + `CustomerResponseDecisionPayload` and assert `envelope.event_type == "local.resolution.customer-response.drafted.v1"`, `envelope.agent_id == "customer-resolution-agent"`, `envelope.correlation_id == decision_envelope.correlation_id`, `envelope.causation_id == decision_envelope.event_id`, `payload.decision_event_id == decision_envelope.event_id` (AC1), and that `payload.requires_human_approval` matches the T131 policy for each `ResolutionOutcome` (AC3) — no Kafka, assert on the constructed `EventEnvelope`
- [ ] T134 [P] [US3] Add a safe-language test in `apps/agents/customer_resolution/tests/test_response_drafted.py`: for a decision whose internal fields carry distinctive sentinel strings (e.g. `rationale="INTERNAL-RATIONALE"`, `escalation_reason="conflicting_analyses"`, `billing_summary="INTERNAL-BILLING"`, `risk_summary="INTERNAL-RISK"`), assert the built `draft_response` contains **none** of those substrings nor any `INTERNAL_ONLY_DRAFT_FIELDS` content, for every outcome (AC2)

### Implementation

- [ ] T135 [US3] Add a pure `build_response_drafted_payload(decision_payload, decision_envelope, *, requires_human_approval) -> CustomerResponseDraftedPayload` in `apps/agents/customer_resolution/response_drafter.py` mapping `case_id = decision_envelope.correlation_id`, `ticket_id`/`customer_id` from the decision payload, `decision_event_id = decision_envelope.event_id`, `outcome = decision_payload.outcome`, `draft_response = decision_payload.customer_response` (the already-template-built customer-facing text from T016/T032), and `drafted_at` from the caller — no I/O, unit-testable
- [ ] T136 [US3] Implement the deterministic `requires_human_approval(outcome: ResolutionOutcome) -> bool` in `apps/agents/customer_resolution/decision_engine.py` returning `outcome in config.HUMAN_APPROVAL_OUTCOMES` (T131); the result is passed into `build_response_drafted_payload` (FR-009 auditable policy)
- [ ] T137 [US3] Add a source-level safe-language guard in `apps/agents/customer_resolution/response_drafter.py`: ensure the customer-facing draft is built **only** from the outcome-keyed customer template (never concatenating `rationale`/`escalation_reason`/`billing_summary`/`risk_summary`), and add an internal assertion/`raise` if any `INTERNAL_ONLY_DRAFT_FIELDS` (T131) content is detected in the draft before it is published — fail closed rather than leak internal text (AC2)
- [ ] T138 [US3] In `apps/agents/customer_resolution/event_handlers.py`, **after** the `customer.resolution.decided.v1` event is published (the non-refund/direct branch in T018 **and** the refund decision branch in T034/T111/T125), publish exactly one `customer-response.drafted` event to `TOPIC_RESPONSE_DRAFTED` via the shared `Publisher` with `correlation_id = decision_envelope.correlation_id` and `causation_id = decision_envelope.event_id` (the linked decision event, AC1); compute `requires_human_approval` via T136; transition the case `decided → response_drafted` (Phase 14 T087, or no-op if Phase 14 not yet applied); emit **exactly once** per decision and **not** for an already-drafted/late-result path (reuse the case-status guard + `IdempotencyTracker`; FR-011/FR-012)
- [ ] T139 [P] [US3] Add an integration test in `apps/agents/customer_resolution/tests/test_customer_resolution.py`: drive `approve_refund`, `deny_refund`, `escalate_human`, and non-refund `direct_response` cases; after each, consume from `local.resolution.customer-response.drafted.v1` and assert exactly one event ordered **after** the matching `customer.resolution.decided.v1`, with `envelope.causation_id`/`payload.decision_event_id == decided event_id` (AC1), `requires_human_approval` `true` for escalate/approve and `false` for deny/direct (AC3), and `draft_response` carrying no internal-field content (AC2); a re-delivered ticket yields **no** second drafted event (FR-011/FR-012)

### Audit (extends US4)

- [ ] T140 [US4] Add a "customer response drafted" step to the audit emission in `apps/agents/customer_resolution/event_handlers.py` via `agent_foundation.audit.store.write_audit` (agent identity, `correlation_id`, `causation_id = decided event id`, timestamp, `outcome`, and the `requires_human_approval` flag in the reason/metadata) so the draft and its approval gate are reconstructable by correlation id — extends the step list in T037 (FR-013/FR-014, SC-006)

**Checkpoint**: Every `customer.resolution.decided.v1` event is followed by exactly one
`local.resolution.customer-response.drafted.v1` event linked to it by `causation_id`/`decision_event_id`,
carrying safe customer-facing language and a deterministic `requires_human_approval` gate (plus an audit
record) — all three acceptance criteria satisfied; replays never double-emit.

### Phase 17 dependencies

- **Foundational T127–T130** block everything in this phase. T127 ∥ T128 (different files); T129 needs
  T127+T128; T130 needs T128.
- **T131** (policy/constants) precedes T136/T137 and the tests that assert against it.
- **Tests T132/T133/T134** (T132 different file from T133/T134; all `[P]` as independent functions) are
  written first and must fail before T135–T139.
- **Impl**: T135 (pure builder) + T136 (approval policy) + T137 (safe-language guard) → T138 (emit after
  the decision, extends T018/T034/T111/T125) → T139 (integration). T138 also requires the Phase 2
  process/`Publisher` (T011), the decision-emit paths (T018/T034/T111/T125), and reuses the Phase 14
  `response_drafted` status (T087) when present.
- **T140** (audit) follows T138 and folds into the US4 audit step list (T037).
- Reuses `001`/`002` transport, audit, idempotency, and the existing `ResolutionOutcome`/
  `response_drafter` templates unchanged (FR-016, Principle V) — no new dependency, no second audit path.

---

## Phase 18: Implement the Deterministic Decision Engine (expands US3) ⭐ DECISION ENGINE

**Added by a follow-up `/speckit-tasks` request.** This section is **additive** and is the heart of
the agent: it **expands and supersedes** the minimal decision policy of US3 (Phase 5, `decide(...)`
T031) into the full deterministic decision engine requested here. It continues the numbering (T141+)
and reuses this file's package layout (`decision_engine.py`, `models.py`, `config.py`,
`response_drafter.py`, `event_handlers.py`, contracts in `packages/contracts/`, tests under
`apps/agents/customer_resolution/tests/`).

**Builds on Phase 14 (case model) and Phases 12/13/15/16 (peer results).** The engine is a **pure
function over the Phase 14 `ResolutionCase` fields** (`classification`, `billing_result`,
`risk_result`, `pending_tasks`, `deadline_at`) plus two new inputs (`policy_context`,
`timeout_status`). It reads **only** normalized peer findings (the T030 adapter output) and the
triage classification — it issues **no** query to any billing/fraud datastore and **fabricates no
finding** (FR-005, US5). Both the billing (Phase 15, T111) and risk (Phase 16) result-consume paths
funnel into this single engine; its output is the emitted `customer.resolution.decided` event (T004),
expanded with the requested decision metadata.

**Reconciliation with the existing design** (the engine is one policy, not a second one):

| Requested element | Existing design | Reconciliation in this phase |
|-------------------|-----------------|------------------------------|
| inputs `classification`, `billing_result`, `risk_result` | Phase 14 `ResolutionCase` fields (T088) | Engine consumes the case fields directly; no new ingress. |
| input `policy_context` | (none) | **NEW** `PolicyContext` input model (T144) — illustrative PoC policy knobs (refund caps, partial-credit fraction), defaulted from `config.py`. |
| input `timeout_status` | Phase 14 `deadline_at` (recorded, not enforced, T094) + `pending_tasks` | **NEW** `TimeoutStatus` derived (pure) from `pending_tasks`/`deadline_at` (T144); "missing result" ⇒ escalate. Liveness reaper stays the documented gap (research R6). |
| outcomes `approve_refund`, `deny_refund`, `escalate_to_human` | `ResolutionOutcome` (T004) — note existing name is `escalate_human` | Keep the canonical enum value `escalate_human`; the request's `escalate_to_human` is the **same** value (naming note recorded in T141). |
| outcome `offer_partial_credit`, `request_more_information` | (none) | **NEW** enum members (T141) + schema-contract enum update. |
| outputs `confidence`, `reasoning_summary`, `customer_response_strategy`, `evidence` | `CustomerResponseDecisionPayload` has `rationale`, `customer_response`, `billing_summary`/`risk_summary` (T004) | Expand the payload (T145): `reasoning_summary` ≡ the existing `rationale` (renamed-with-alias); **add** `confidence`, `customer_response_strategy`, and a structured `evidence` list that **subsumes** `billing_summary`/`risk_summary`. |
| risk levels `low` / `medium` / `high` | `RiskFinding.level ∈ {low, elevated, high}` (T007) | Treat `elevated ≡ medium` in the engine; documented in T143. |
| billing `partial eligibility` | `BillingFinding.eligible: bool` (T007) | Expand `BillingFinding` to a 3+1-valued `eligibility` (T142) so "partial" is representable. |

**Goal**: A single pure, deterministic, total function
`decide(classification, billing_result, risk_result, policy_context, timeout_status) ->
CustomerResponseDecisionPayload` that maps the inputs to exactly one of five outcomes, attaches a
`confidence`, a `reasoning_summary`, a `customer_response_strategy`, and an `evidence` list citing the
peer findings — with **no** I/O, **no** datastore access, and **no** fabricated facts.

**Independent Test**: Call `decide(...)` directly (no Kafka) across the full truth table and confirm
each input combination yields the specified outcome, that re-running identical inputs yields an
identical decision (modulo `decided_at`), that a missing/`None` billing or risk result yields
`escalate_human(missing_analysis)` (never approve/deny/partial), and that every approve/deny/partial
decision's `evidence` cites both peer findings' `task_id`s.

### Decision rules (ordered; first match wins — escalation precedence guarantees one total outcome)

> Evaluated top-down in `decide(...)`. Rows 1–3 are the **escalation guards** (run before the
> categorical rows so a low-confidence or incomplete case never silently approves). Rows 4–7 are the
> categorical mapping of the request's example rules. Row 8 is the defined residual default
> (totality — FR-010). `risk medium ≡ RiskFinding.level "elevated"`.

| # | Condition | `outcome` | `escalation_reason` |
|---|-----------|-----------|---------------------|
| 1 | `timeout_status.any_missing` **or** `billing_result is None` **or** `risk_result is None` (a required analysis is missing/timed out) | `escalate_human` | `missing_analysis` (or `analysis_timeout`) |
| 2 | `billing_result.failed` / `risk_result.failed` **or** either `requires_human_review` | `escalate_human` | `peer_failure` / `peer_requested_review` |
| 3 | `confidence < CONFIDENCE_THRESHOLD` (from `compute_confidence`, T147) | `escalate_human` | `low_confidence` |
| 4 | `billing.eligibility == eligible` **and** `risk.level == low` | `approve_refund` | — |
| 5 | `billing.eligibility == ineligible` **and** `risk.level in {elevated(=medium), high}` | `deny_refund` | — |
| 6 | `billing.eligibility == partial` **and** `risk.level in {low, elevated(=medium)}` | `offer_partial_credit` | — |
| 7 | `billing.eligibility == indeterminate` (peer inconclusive / needs more info) and no higher row fired | `request_more_information` | — |
| 8 | anything else (residual conflict, e.g. eligible+high risk, ineligible+low risk) | `escalate_human` | `conflicting_analyses` |

Notes: Row 1 directly implements the request's "Escalate if billing or risk result is missing"; Row 3
implements "Escalate if confidence is below threshold"; Rows 4/5/6 implement the approve / deny /
partial-credit example rules; Row 7 introduces `request_more_information` for the inconclusive case;
Row 8 keeps the function total. **No row reads or invents a billing/risk fact** — all conditions are
over the normalized findings already on the case (acceptance criterion: "Agent does not invent billing
or risk facts").

### Acceptance criteria → how each is met (from the `/speckit-tasks` request)

| Criterion | How it is satisfied | Verified by |
|-----------|---------------------|-------------|
| **Decision engine is deterministic** | `decide(...)` and `compute_confidence(...)` are **pure** (no I/O, no clock except the injected `decided_at`, no randomness); all thresholds are named constants in `config.py`; the truth table is evaluated in a fixed order | T148, T152, T153 |
| **Decision logic is unit tested** | Full truth-table unit tests over all 5 outcomes + every escalation reason, a determinism (idempotence) test, and a `compute_confidence` boundary test | T152, T153, T156 |
| **Agent does not invent billing or risk facts** | The engine consumes only the T030-normalized findings; a missing/`None`/`failed`/unparseable result escalates (rows 1–2), never a fabricated approve/deny/partial; the engine imports no billing/fraud datastore | T148, T154, T159 |
| **Final decision cites peer agent outputs** | Every approve/deny/partial decision carries an `evidence` list referencing both findings' `task_id`, `performer_agent_id`, recommendation/summary, and confidence; `billing_summary`/`risk_summary` are derived from the same findings | T149, T155 |

### Foundational (contract + model + config expansion — blocks the engine and tests)

- [ ] T141 [US3] Expand `ResolutionOutcome` in `packages/contracts/events/payloads.py` (T004) with `offer_partial_credit` and `request_more_information`; add a docstring noting the request's `escalate_to_human` is the canonical `escalate_human` value (no rename) and that `direct_response` (Phase 5 / non-refund) is unchanged; update the enum in `specs/003-customer-resolution-agent/contracts/customer-response-decision.schema.json` to the 6-value set
- [ ] T142 [US3] Expand `BillingFinding` in `apps/agents/customer_resolution/models.py` (T007) to represent partial eligibility: replace `eligible: bool` with `eligibility: Literal["eligible","partial","ineligible","indeterminate"]` plus `confidence: float | None = None`; keep a back-compat `@property eligible -> bool` (`== "eligible"`) so Phase 5/15 references and the T030 adapter migrate cleanly; update the T030/T104 adapter to set `partial` (e.g. stub `{"eligible": "partial"}` / `recommendation == partial_refund`) and `indeterminate` (inconclusive/needs-more-info recommendation)
- [ ] T143 [US3] Document and enforce the risk-band reconciliation in `apps/agents/customer_resolution/models.py`/`config.py`: `RiskFinding.level ∈ {low, elevated, high}` with the engine treating `elevated` as the request's `medium`; add a `RISK_MEDIUM = "elevated"` alias constant and a comment mapping the request's low/medium/high vocabulary to the existing enum (no schema change)
- [ ] T144 [US3] Add the two new engine inputs to `apps/agents/customer_resolution/models.py`: a `PolicyContext` model (frozen, `extra="forbid"`: e.g. `max_auto_refund_amount: float`, `partial_credit_fraction: float`, defaulted from `config.py`) and a `TimeoutStatus` model (`any_missing: bool`, `missing_reviews: list[Literal["billing","risk"]]`, `deadline_exceeded: bool`); implement a pure `build_timeout_status(case, *, now) -> TimeoutStatus` derived from `case.pending_tasks` and `case.deadline_at` (Phase 14 T088/T094) — status only, no reaper (liveness gap stays documented, research R6)
- [ ] T145 [US3] Expand `CustomerResponseDecisionPayload` in `packages/contracts/events/payloads.py` (T004) with `confidence: Annotated[float, Field(ge=0.0, le=1.0)]`, `customer_response_strategy: str`, and `evidence: list[DecisionEvidence]`; add a `DecisionEvidence` model (`source: Literal["billing","risk","classification"]`, `task_id: UUID | None`, `performer_agent_id: str | None`, `summary: str`, `confidence: float | None`); treat the existing `rationale` as `reasoning_summary` (add a `reasoning_summary` alias/field); update `specs/003-customer-resolution-agent/contracts/customer-response-decision.schema.json` (new fields + `evidence` items) and confirm the `PAYLOAD_REGISTRY` entry (T004) still resolves
- [ ] T146 [US3] Add the engine's named constants to `apps/agents/customer_resolution/config.py` (T009): `CONFIDENCE_THRESHOLD = 0.6` (illustrative), `PARTIAL_CREDIT_FRACTION`, `MAX_AUTO_REFUND_AMOUNT`, and the risk-band thresholds reused from T009 — all PoC values with a comment that they are demonstration, not production, policy (research R4)

### Engine implementation (pure, deterministic)

- [ ] T147 [US3] Implement the pure `compute_confidence(classification, billing_result, risk_result) -> float` in `apps/agents/customer_resolution/decision_engine.py`: a deterministic combination (e.g. the minimum of the available `classification.confidence`, `billing_result.confidence`, `risk_result.confidence|score`-derived certainty), bounded to `[0.0, 1.0]`, returning a low value when an input confidence is absent — no randomness, no I/O (acceptance: deterministic)
- [ ] T148 [US3] Implement the pure, total `decide(classification, billing_result, risk_result, policy_context, timeout_status, *, decided_at) -> CustomerResponseDecisionPayload` in `apps/agents/customer_resolution/decision_engine.py` evaluating the ordered truth table above (rows 1–8), calling `compute_confidence` (T147) and `build_evidence` (T149); **supersedes** the Phase 5 `decide` (T031), absorbing its `direct_response` row (non-refund classification ⇒ `direct_response`) so there is exactly one engine; no datastore access, no fabricated findings (FR-005/FR-009/FR-010)
- [ ] T149 [US3] Implement the pure `build_evidence(classification, billing_result, risk_result) -> list[DecisionEvidence]` in `apps/agents/customer_resolution/decision_engine.py`: one entry per **present** finding citing its `task_id`, `performer_agent_id`, recommendation/`summary`, and `confidence`, plus a classification entry — drawing **only** from the inputs (no field not present on a finding) so the decision provably cites peer outputs and invents nothing (acceptance: cites peer outputs / no invented facts; SC-004)
- [ ] T150 [US3] Implement the per-outcome `customer_response_strategy` + customer-message templates for all five outcomes in `apps/agents/customer_resolution/response_drafter.py` (extends T016/T032): e.g. `confirm_and_process_refund` (approve), `explain_denial` (deny), `offer_partial_and_confirm` (partial), `request_details` (request-more-info), `handoff_to_specialist` (escalate); strategy + drafted `customer_response` are set deterministically from the outcome

### Wiring (one decision path)

- [ ] T151 [US3] Update the decision-emit path in `apps/agents/customer_resolution/event_handlers.py`/`agent.py` (T034/T111 and the Phase 16 risk-consume path) so that when a case is `ready_for_decision` it builds `policy_context` (from `config.py`/`PolicyContext`) and `timeout_status` (via `build_timeout_status`, T144) and calls the expanded `decide(...)` (T148) with `case.classification`/`case.billing_result`/`case.risk_result`, then emits the single resulting `CustomerResponseDecisionPayload` (now carrying `confidence`/`customer_response_strategy`/`evidence`) to `TOPIC_RESOLUTION_DECIDED` — still **exactly one** decision per case (FR-007/FR-012), late results inert (Phase 14 T093)

### Tests (write first — must FAIL before implementation)

- [ ] T152 [P] [US3] Expand the truth-table unit test in `apps/agents/customer_resolution/tests/test_decision_engine.py` (T026) to cover **all five** outcomes and every escalation reason: approve (eligible+low), deny (ineligible+medium/high), partial (partial+low/medium), request-more-info (indeterminate), and escalate for `missing_analysis`/`analysis_timeout` (row 1), `peer_failure`/`peer_requested_review` (row 2), `low_confidence` (row 3), and `conflicting_analyses` (row 8) — one assertion per truth-table row (decision rules above; SC-003/SC-007)
- [ ] T153 [P] [US3] Determinism test in `apps/agents/customer_resolution/tests/test_decision_engine.py`: call `decide(...)` twice with identical inputs and a fixed `decided_at` and assert the two `CustomerResponseDecisionPayload`s are equal (outcome, confidence, strategy, evidence, summaries) — proving no hidden state/randomness (acceptance: deterministic)
- [ ] T154 [P] [US3] "No invented facts" test in `apps/agents/customer_resolution/tests/test_decision_engine.py`: with `billing_result=None`, with `risk_result=None`, and with a `failed` finding, assert the outcome is `escalate_human` with reason `missing_analysis`/`peer_failure` — **never** approve/deny/partial — and that `evidence` contains no entry for the absent finding (acceptance: no invented facts; FR-005/FR-008)
- [ ] T155 [P] [US3] "Cites peer outputs" test in `apps/agents/customer_resolution/tests/test_decision_engine.py`: for approve/deny/partial decisions assert `evidence` includes one entry per present finding with the finding's `task_id`/`performer_agent_id`/`summary`/`confidence`, and that `billing_summary`/`risk_summary` are derived from those findings — assert no evidence field holds a value absent from the inputs (acceptance: cites peer outputs; SC-004)
- [ ] T156 [P] [US3] `compute_confidence` unit test in `apps/agents/customer_resolution/tests/test_decision_engine.py`: bounded to `[0.0,1.0]`, returns low when an input confidence is missing, monotonic in the inputs, and the `CONFIDENCE_THRESHOLD` boundary (just-below ⇒ escalate via row 3, at/above ⇒ proceeds) behaves as specified
- [ ] T157 [P] [US3] Adapter test extension in `apps/agents/customer_resolution/tests/test_adapters.py` (T104): the T030 adapter maps a `partial_refund`/`{"eligible":"partial"}` billing result to `BillingFinding.eligibility == "partial"` and an inconclusive/needs-more-info result to `"indeterminate"` (feeds rows 6/7)
- [ ] T158 [P] [US3] Integration tests in `apps/agents/customer_resolution/tests/test_customer_resolution.py`: drive end-to-end (a) partial-eligible + low risk → one `offer_partial_credit` decision with both summaries; (b) indeterminate billing → one `request_more_information` decision; (c) low-confidence inputs → one `escalate_human(low_confidence)`; (d) a refund case whose risk result never arrives (or `timeout_status.any_missing`) → `escalate_human(missing_analysis)` — each exactly one decision (SC-003/SC-007)

### Audit & isolation (extends US4 / US5)

- [ ] T159 [US4] Extend the "final decision" audit step in `apps/agents/customer_resolution/event_handlers.py` (T037) to record the decision `outcome`, `confidence`, `customer_response_strategy`, `escalation_reason`, and the `evidence` `task_id`s, so the full deterministic rationale is reconstructable by correlation id (FR-013/FR-014, SC-006); the US5 isolation test (T039/T079/T086) continues to assert the engine module imports no billing/fraud datastore (acceptance: no invented facts; FR-005)

**Checkpoint**: A single pure, deterministic decision engine maps `(classification, billing_result,
risk_result, policy_context, timeout_status)` to exactly one of five outcomes with a confidence, a
reasoning summary, a customer-response strategy, and peer-citing evidence — unit-tested across the full
truth table, escalating (never fabricating) when a required analysis is missing or confidence is low,
and emitted exactly once per case.

### Phase 18 dependencies

- **Foundational T141–T146** block the engine. T141 (outcomes) + T145 (payload fields) edit
  `payloads.py` + the schema contract (sequence if edited together); T142/T143/T144 edit `models.py`;
  T146 edits `config.py`. All precede T147–T151.
- **Engine**: T147 (`compute_confidence`) and T149 (`build_evidence`) feed T148 (`decide`); T150
  (strategies/templates) is `[P]` with T147–T149 (different file). T148 **supersedes** the Phase 5
  `decide` (T031) — treat T148 as the authoritative decision policy.
- **Wiring**: T151 depends on T148 and the Phase 14 store (T092 `ready_for_decision`) + the Phase
  15/16 consume paths (T111 and the risk handler); it replaces the inline `decide` call in T034/T111.
- **Tests T152–T158** (mostly the same `test_decision_engine.py`, plus `test_adapters.py`,
  `test_customer_resolution.py`) are written first and must fail before T147–T151; `[P]` only where in
  distinct files or independent test functions.
- **Supersedes**: this phase replaces the minimal `decide`/outcome set of Phase 5 (T031, and the
  4-value `ResolutionOutcome` of T004) — when implementing, treat T141–T151 as the authoritative
  decision-engine design.
- Reuses `001`/`002` transport, audit, idempotency, the Phase 14 store, and the existing decision
  event/topic (T004–T007) — no new dependency, no new transport, no second decision policy
  (FR-009/FR-016, Principle V).

---

## Phase 19: Architecture Documentation (Cross-Cutting)

**Purpose**: Produce the four architecture documents requested for this feature, so a reviewer can
understand the agent, its case lifecycle, its refund logic, and its safety guardrails **without
reading the code**. These are prose/diagram deliverables — there are no code tests; "validation"
means each doc renders (Markdown + Mermaid), its facts match the authoritative artifacts verbatim
(topic names, capability ids, enum values, FR/SC references), and its cross-links resolve.

**Document → story map**:

| Document | Primary stories | Authoritative sources |
|----------|-----------------|-----------------------|
| `docs/architecture/customer-resolution-agent.md` | US1 + US2 + US3 (FR-001/004/016/017) | `plan.md` Summary + Architecture Decision; `research.md` R2/R3/R7/R8 |
| `docs/architecture/customer-resolution-state-machine.md` | US3 (FR-008/011/012) | `data-model.md` §4; `research.md` R3/R5/R6; Phase 14 (`state_store.py`) |
| `docs/architecture/refund-decision-rules.md` | US1 + US3 (FR-002/003/009/010) | `contracts/decision-policy.md`; **Phase 18** truth table (authoritative); `research.md` R1/R4 |
| `docs/architecture/customer-response-safety.md` | US5 + US6 + US4 (FR-005/011/012/013/014/015) | `spec.md` US4/US5/US6 + Edge Cases; `plan.md` Constitution Check; `data-model.md` §8 |

**⚠️ Authoritative-source note**: where `data-model.md` (4 outcomes) and Phase 18 (5 outcomes:
`approve_refund`, `deny_refund`, `offer_partial_credit`/partial, `request_more_information`,
`escalate_human`, plus `direct_response` for non-refund) disagree, the **Phase 18 decision engine
(T141–T151) is authoritative**. The decision-rules doc must document the Phase 18 engine and note the
data-model §7 payload as the base contract that Phase 18 (T145) expanded.

### Setup & shared terminology

- [ ] T160 Create the `docs/architecture/` directory and author `docs/architecture/README.md` as an index linking the four feature docs (one-line description each) and back to `specs/003-customer-resolution-agent/` (spec, plan, research, data-model, contracts); include a "Documentation conventions" note (heading style, Mermaid for diagrams, citation format referencing spec FR-/SC- ids and the source artifact)
- [ ] T161 Add an "Authoritative sources & terminology" section to `docs/architecture/README.md` pinning the canonical facts all four docs must reproduce identically (from `data-model.md` §Topic deltas + Phase 18): agent id `customer-resolution-agent`; peer capabilities `analyze_refund_eligibility` (billing) / `assess_fraud_risk` (risk); the decision event `local.customer.resolution.decided.v1` on `TOPIC_RESOLUTION_DECIDED` and its `CustomerResponseDecisionPayload` (incl. Phase 18 `confidence`/`customer_response_strategy`/`evidence`); consumed topics (`support.ticket.created`, `TOPIC_TASK_RESULT`) and produced topics (peer `endpoint_topic(...)`, `TOPIC_AUDIT`, `TOPIC_AGENT_CARD`, `TOPIC_RESOLUTION_DECIDED`); the authoritative `ResolutionOutcome` value set (Phase 18); the `CaseStatus` values; and the three concurrent loops (intake / result / runtime)

**Checkpoint**: Shared terminology fixed — the four documents can be authored in parallel.

### Document 1 — Agent architecture (US1/US2/US3)

- [ ] T162 [US2] Author `docs/architecture/customer-resolution-agent.md`: agent responsibilities and hard boundaries (FR-001 addressable endpoint/card, FR-005 no direct data, FR-015 not a supervisor/router); the three concurrent loops (intake, result, runtime) over a shared `CaseStateStore` (Phase 14); A2A delegation by publishing a `TaskRequest` to each peer's `endpoint_topic(...)`; peer discovery via `find_capable(...)` (FR-017); reused `001`/`002` foundation components (envelope, Publisher/Consumer, IdempotencyTracker, audit, runtime); and the consumed/produced topic map — sourced from `plan.md` Summary + "Architecture Decision: Asynchronous Case Aggregation" and `research.md` R2/R3/R7/R8
- [ ] T163 [US2] Add a Mermaid sequence/flow diagram to `docs/architecture/customer-resolution-agent.md`: `support.ticket.created` → triage → two correlated `TaskRequest`s to billing/risk endpoints → `task.result` consumption → single `customer.resolution.decided` event; verify it renders
- [ ] T164 [US2] Cross-link `docs/architecture/customer-resolution-agent.md` to spec US1/US2/US3 + FR-001/004/016/017, the relevant package files (`agent.py`, `event_handlers.py`, `a2a_handlers.py`), and the other three architecture docs; verify all links resolve

### Document 2 — Case state machine (US3)

- [ ] T165 [P] [US3] Author `docs/architecture/customer-resolution-state-machine.md`: the `CaseStatus` states (`INTAKE`, `AWAITING_ANALYSES`, `DECIDED`, `CLOSED_DIRECT`), the `AnalysisSlot` model (`task_id`/`finding`/`failed`/`received`), the `is_ready_to_decide`/`ready_for_decision` completeness rule (both slots received; any `failed` slot short-circuits to escalation), idempotency via `CaseStore.get_or_create`, and the exactly-one-decision / late-result-recorded-not-applied guarantees — sourced from `data-model.md` §4, `research.md` R3/R5/R6, and Phase 14 (`state_store.py`, T092)
- [ ] T166 [P] [US3] Add a Mermaid `stateDiagram-v2` to `docs/architecture/customer-resolution-state-machine.md` reproducing the `data-model.md` §4 transitions: non-refund → `CLOSED_DIRECT`; refund → `AWAITING_ANALYSES`; both slots → `DECIDED`; failed/rejected slot → `DECIDED(escalate_human)`; one-slot self-loop ("stay open", FR-008); duplicate-re-delivery no-op (FR-011); verify it renders
- [ ] T167 [P] [US3] Add a transition table to `docs/architecture/customer-resolution-state-machine.md` mapping each transition → triggering event → guard → emitted audit step → spec ref (FR-008/011/012, US3-2/3/4); cross-link to the agent + decision-rules docs and `data-model.md` §4/§8; verify all links resolve

### Document 3 — Refund decision rules (US1/US3)

- [ ] T168 [P] [US1] Author `docs/architecture/refund-decision-rules.md`: (a) Triage section — the refund-intent vocabulary, clear-non-refund path, and ambiguous/empty → default-to-refund-review rule with rationale recording (from `contracts/decision-policy.md §A`, `research.md` R1, `ticket_classifier.py`); (b) Peer-result normalization — mapping billing/risk `TaskResult` to findings and `failed`/`rejected` → no finding (from `decision-policy.md §B`, the Phase 15/16 adapters)
- [ ] T169 [P] [US1] Add the **authoritative Phase 18** ordered decision truth table (all five refund outcomes + `direct_response`, escalation precedence, `confidence`/`evidence`) and a worked-examples table to `docs/architecture/refund-decision-rules.md`, sourced from Phase 18 (T148 truth table) with `contracts/decision-policy.md §C/§D` noted as the base policy it supersedes; tag each row with its spec ref (FR-009/010, SC-003/007)
- [ ] T170 [P] [US1] Add a Mermaid flowchart to `docs/architecture/refund-decision-rules.md` showing triage → (`direct_response` | delegate) and the ordered decision guards mapping to each `ResolutionOutcome`; cross-link to the agent + state-machine docs, spec FR-002/003/009/010, and `data-model.md` §2/§3/§7; verify it renders and links resolve

### Document 4 — Customer-response safety & guardrails (US5/US6/US4)

- [ ] T171 [P] [US5] Author `docs/architecture/customer-response-safety.md`: domain isolation (no billing/payment/fraud datastore access; all such facts enter only via `task.result`, FR-005, US5); no-supervisor / no-router posture (delegations bound only to own refund cases, FR-015, US6); idempotency by ticket identity + event-level dedup (FR-011, `research.md` R5); exactly-one-decision and late-result-recorded-not-applied (FR-012); fault-to-escalation policy with recorded reason (SC-007); and audit/observability by `correlation_id` (FR-013/014, US4) — sourced from `spec.md` US4/US5/US6 + Edge Cases, `plan.md` Constitution Check, and `data-model.md` §8
- [ ] T172 [P] [US5] Add a guardrails table to `docs/architecture/customer-response-safety.md` mapping each guardrail → enforcing mechanism → spec FR/SC → validating test (e.g. `test_no_router`, the US5 isolation test T039/T079/T086, idempotent re-delivery); cross-link to the agent + state-machine docs and `.specify/memory/constitution.md`; verify all links resolve

### Polish

- [ ] T173 [P] Update `docs/architecture/README.md` so all four documents are reachable from the index, and add a pointer to `docs/architecture/` from the repo-root docs entry point if one exists
- [ ] T174 [P] Run a terminology/consistency pass across all four docs: topic names, capability ids, the authoritative `ResolutionOutcome` values, the `CaseStatus` values, and the event name `local.customer.resolution.decided.v1` must match `data-model.md`/Phase 18 exactly
- [ ] T175 Verify every Mermaid diagram renders and every cross-document and spec/artifact link resolves across all four docs plus `README.md`

**Checkpoint**: All four architecture documents exist, render, are internally consistent, and let a
reviewer reconstruct the agent's design, lifecycle, refund logic, and guardrails from docs alone.

### Phase 19 dependencies

- **T160–T161 (setup/terminology)** block T162–T172 — the shared terminology must be fixed before the
  docs cite it.
- After T161, the four documents are **different files** and can be authored fully in parallel: Doc 1
  (T162–T164), Doc 2 (T165–T167), Doc 3 (T168–T170), Doc 4 (T171–T172). Tasks **within** one document
  touch the same file and are sequential (author → diagram → cross-link).
- **T173–T175 (polish)** depend on all four documents being complete; T175 runs last.
- This phase is documentation-only — it adds no dependency, no code, and no transport; it documents
  the design produced by Phases 1–18 (Principle IV: Observability/accountability).

---

## Phase 20: Implement Case Closure — `local.resolution.case.closed.v1` / `local.resolution.case.escalated.v1` (completes US3/US4) 🏁 TERMINAL STEP

**Added by a follow-up `/speckit-tasks` request.** This section is **additive** and implements the
**terminal close-out of a resolution case**: after the agent has decided (Phase 18) and drafted the
customer response (Phase 17), this phase emits exactly **one** terminal lifecycle event per case —
either `local.resolution.case.closed.v1` (clean resolution) or `local.resolution.case.escalated.v1`
(routed to a human) — and moves the case to its terminal state. It continues the numbering (T176+) and
reuses this file's package layout (`event_handlers.py`, `state_store.py`, `decision_engine.py`,
`response_drafter.py`, `config.py`, contracts in `packages/contracts/`, tests under
`apps/agents/customer_resolution/tests/`).

**Close vs. escalate (from the `/speckit-tasks` request):**

- **Close** (`local.resolution.case.closed.v1`) when **all** hold: the **decision is final** (a
  `customer.resolution.decided.v1` event was emitted, Phase 18 T148/T151), the **response is drafted**
  (a `customer.resolution.customer-response.drafted.v1` event was emitted, Phase 17 T138), and **human
  review is not required** (`requires_human_approval == False` (Phase 17 T136) **and** `outcome !=
  escalate_human`).
- **Escalate** (`local.resolution.case.escalated.v1`) when **any** trigger fires: **human review
  required**, **peer result timeout**, **low confidence**, **policy conflict**, or **high risk**.

**Reconciliation with the existing design — this phase consumes prior outputs, it does not re-decide.**
The five escalation triggers are **already computed** upstream; this phase **maps** them onto the
closure event, it does not recompute policy:

| Closure escalation trigger (request) | Already produced by | Mapped from |
|--------------------------------------|---------------------|-------------|
| **human review required** | Phase 18 decision / Phase 17 gate | `outcome == escalate_human` with `escalation_reason == peer_requested_review`, **or** `requires_human_approval == True` (Phase 17 T131/T136 — incl. `approve_refund` money-movement gate), **or** a `peer_failure`/`peer_rejection` escalation (a human must handle the missing analysis) |
| **peer result timeout** | Phase 18 `timeout_status` (T144) / Phase 14 `deadline_at` (T094) | `escalation_reason ∈ {missing_analysis, analysis_timeout}` |
| **low confidence** | Phase 18 row 3 (T146 `CONFIDENCE_THRESHOLD`, T147 `compute_confidence`) | `escalation_reason == low_confidence` |
| **policy conflict** | Phase 18 row 8 (T148) | `escalation_reason == conflicting_analyses` |
| **high risk** | Phase 18 rows / Phase 16 risk consume (T125) | `escalation_reason == elevated_risk`, i.e. `RiskFinding.level ∈ {elevated(=medium), high}` |

So `case.escalated.v1` is emitted whenever the decision's `outcome == escalate_human` (its
`escalation_reason` carried through, folded into the five request buckets above) **or** the decision
carries a human-approval gate; `case.closed.v1` is emitted for every other terminal outcome
(`approve_refund` only when not human-gated, `deny_refund`, `offer_partial_credit`,
`request_more_information`, `direct_response`). Exactly one of the two fires per case — **never both,
never neither** — preserving the "exactly one terminal outcome per case" invariant (SC-003, FR-007).

**Case state machine.** This phase realizes the terminal edges of the Phase 14 machine (T087/T089):
`response_drafted → closed` and `response_drafted → escalated` (and, when no draft step ran — e.g. a
pre-Phase-17 escalation — `decided → escalated`). `closed` and `escalated` are **terminal**; a
late/duplicate result or re-delivered ticket on a terminal case is recorded, never re-closed
(FR-012, reuses Phase 14 T093 + the `IdempotencyTracker`).

> **Liveness note.** "Peer result timeout" closure uses the **recorded-but-not-enforced** `deadline_at`
> + `timeout_status` (Phase 14 T094 / Phase 18 T144): when a decision was forced with
> `escalation_reason ∈ {missing_analysis, analysis_timeout}`, this phase maps it to a
> `peer_result_timeout` escalation. No background reaper is added — an *accepted-but-never-answered*
> case with no forced decision stays open, the documented gap (research R6, spec Assumptions).

**Goal**: After a case is decided (and its response drafted), the agent publishes exactly one terminal
event — `local.resolution.case.closed.v1` carrying `case_id`, `ticket_id`, `customer_id`, `outcome`,
`customer_response`, `resolution_summary`, `prior_decision_event_id`, `closed_at`; or
`local.resolution.case.escalated.v1` carrying `case_id`, `ticket_id`, `customer_id`,
`escalation_reason`, `escalation_detail`, `customer_response`, `prior_decision_event_id`,
`escalated_at` — and transitions the case to `closed` or `escalated`.

**Independent Test**: Drive a `deny_refund` (eligible-not-required, low-risk, confident) case
end-to-end → after the decided + drafted events, observe exactly one `local.resolution.case.closed.v1`
whose `envelope.correlation_id` is the case id and **no** escalated event; drive a `high`-risk case →
observe exactly one `local.resolution.case.escalated.v1` with `escalation_reason == high_risk` and
**no** closed event; drive `approve_refund` (human-approval-gated) → `case.escalated.v1` with
`escalation_reason == human_review_required`; re-deliver any ticket → no second terminal event.

### Acceptance criteria → how each is met (from the `/speckit-tasks` request)

| Criterion | How it is satisfied | Verified by |
|-----------|---------------------|-------------|
| **Closes only when decision final, response drafted, and no human review** | `close_or_escalate(case, decision)` (T181) returns `CLOSE` only when a decided event id and a drafted event id are recorded on the case (Phase 17/18) **and** `decision.outcome != escalate_human` **and** `decision.requires_human_approval is False`; otherwise `ESCALATE` | T184, T186, T181 |
| **Publishes `local.resolution.case.closed.v1` on close** | The handler builds `ResolutionCaseClosedPayload` (T188) and publishes it via the shared `Publisher` to `TOPIC_CASE_CLOSED`, then `transition(case_id, closed)` (FR-007/FR-016) | T183, T186, T190 |
| **Escalates on human review / peer timeout / low confidence / policy conflict / high risk** | `escalation_trigger_for(decision) -> CaseEscalationReason` (T182) maps the decision's `outcome`/`escalation_reason`/`requires_human_approval` onto the five request buckets; the handler publishes `ResolutionCaseEscalatedPayload` (T189) with that reason | T185, T187, T182 |
| **Publishes `local.resolution.case.escalated.v1` on escalate** | The handler builds and publishes the escalated payload to `TOPIC_CASE_ESCALATED`, then `transition(case_id, escalated)` (FR-010/FR-016), recording the reason for audit (SC-007) | T183, T187, T190 |
| **Exactly one terminal event per case** | `close_or_escalate` returns exactly one disposition; the handler is guarded by the case terminal-status check (Phase 14 T093) + the consumer `IdempotencyTracker`, so a duplicate/late trigger emits no second terminal event (FR-012/SC-003) | T191, T187, T186 |

> **Non-root events**: neither `local.resolution.case.closed.v1` nor
> `local.resolution.case.escalated.v1` is a root type, so the envelope's `causation_id` is **required**
> — set it to the **decided** event's `event_id` (the action that makes the case terminal), or
> `EventEnvelope` validation raises `MissingCausation` (`src/agent_foundation/envelope.py`). Producer
> identity is `envelope.agent_id`, set by `Publisher` from the process
> `AgentIdentity(agent_id="customer-resolution-agent")`; `correlation_id` is the case's
> `correlation_id`.

### Foundational (contracts + registry + topics — block the publish path and tests)

- [ ] T176 [US3] Add a `CaseEscalationReason` str-Enum to `packages/contracts/events/payloads.py` with **exactly** the five request buckets `human_review_required`, `peer_result_timeout`, `low_confidence`, `policy_conflict`, `high_risk`; add a docstring table mapping the Phase 18 `escalation_reason` values (`peer_requested_review`/`peer_failure`/`peer_rejection` → `human_review_required`; `missing_analysis`/`analysis_timeout` → `peer_result_timeout`; `low_confidence` → `low_confidence`; `conflicting_analyses` → `policy_conflict`; `elevated_risk` → `high_risk`) and the Phase 17 `requires_human_approval` gate (→ `human_review_required`); add to the module `__all__`
- [ ] T177 [US3] Add `ResolutionCaseClosedPayload` (Pydantic v2, `frozen`, `extra="forbid"`) to `packages/contracts/events/payloads.py` with fields `case_id: UUID` (= case `correlation_id`), `ticket_id: str`, `customer_id: str`, `outcome: ResolutionOutcome` (reuse T004/T141 enum; the non-escalation outcomes), `customer_response: str` (the drafted customer-facing text from Phase 17), `resolution_summary: str`, `prior_decision_event_id: UUID` (the `customer.resolution.decided.v1` `event_id`), `closed_by_agent_id: str = "customer-resolution-agent"`, `closed_at: datetime`; add a `model_validator(mode="after")` requiring `outcome != ResolutionOutcome.ESCALATE_HUMAN` and `customer_response` non-empty; add to `__all__`
- [ ] T178 [US3] Add `ResolutionCaseEscalatedPayload` (Pydantic v2, `frozen`, `extra="forbid"`) to `packages/contracts/events/payloads.py` with fields `case_id: UUID` (= case `correlation_id`), `ticket_id: str`, `customer_id: str`, `escalation_reason: CaseEscalationReason`, `escalation_detail: str` (human-readable; names the underlying Phase 18 reason / failed peer), `customer_response: str | None = None` (the interim "forwarded to a specialist" draft when present), `prior_decision_event_id: UUID`, `escalated_by_agent_id: str = "customer-resolution-agent"`, `escalated_at: datetime`; add a `model_validator(mode="after")` requiring `escalation_detail` non-empty; add to `__all__`
- [ ] T179 [P] [US3] Add `TOPIC_CASE_CLOSED = topic_for("resolution","case","closed")` (resolves to `local.resolution.case.closed.v1`) and `TOPIC_CASE_ESCALATED = topic_for("resolution","case","escalated")` (resolves to `local.resolution.case.escalated.v1`) in `packages/contracts/topics.py`, beside `TOPIC_RESOLUTION_DECIDED` / `TOPIC_RESPONSE_DRAFTED`
- [ ] T180 [US3] Register `"local.resolution.case.closed.v1": ResolutionCaseClosedPayload` and `"local.resolution.case.escalated.v1": ResolutionCaseEscalatedPayload` in `PAYLOAD_REGISTRY` in `src/agent_foundation/payloads/__init__.py` so `Publisher`/`Consumer` validate them on send/receive (depends on T177, T178, T179), and wire transport resolution + provisioning in `src/agent_foundation/transport/topics.py`: add both event-type→topic mappings to `TOPIC_NAMES` (key == value == `TOPIC_CASE_CLOSED` / `TOPIC_CASE_ESCALATED`) and append a `NewTopic(name=…, num_partitions=1, replication_factor=1, topic_configs={"retention.ms": str(_SEVEN_DAYS_MS)})` for each to `_CANONICAL_TOPICS` (event streams, not compacted)

### Closure policy (pure — maps the decision onto close/escalate)

- [ ] T181 [US3] Implement the pure `close_or_escalate(case, decision) -> ClosureDisposition` in `apps/agents/customer_resolution/decision_engine.py` (or a new `closure.py`): return `CLOSE` **iff** the case has a recorded decided-event id **and** a recorded drafted-event id (Phase 17/18), `decision.outcome != ResolutionOutcome.ESCALATE_HUMAN`, and `decision.requires_human_approval is False`; otherwise `ESCALATE`. `ClosureDisposition` is a small frozen result (`action: Literal["close","escalate"]`, `escalation_reason: CaseEscalationReason | None`, `detail: str`). No I/O — pure over the case + decision payload (acceptance: closes only when final + drafted + no human review)
- [ ] T182 [US3] Implement the pure `escalation_trigger_for(decision) -> tuple[CaseEscalationReason, str]` in the same module, mapping the decision onto the five request buckets per the reconciliation table: `requires_human_approval` or `escalation_reason ∈ {peer_requested_review, peer_failure, peer_rejection}` → `human_review_required`; `∈ {missing_analysis, analysis_timeout}` → `peer_result_timeout`; `== low_confidence` → `low_confidence`; `== conflicting_analyses` → `policy_conflict`; `== elevated_risk` → `high_risk`; the second tuple element is the human-readable `escalation_detail` (names the underlying reason). Total over the Phase 18 reason set, with a defined default (`human_review_required`) so it never raises (FR-010)

### Tests (write first — must FAIL before implementation)

- [ ] T183 [P] [US3] Extend `apps/agents/customer_resolution/tests/test_resolution_schemas.py`: assert both `ResolutionCaseClosedPayload` and `ResolutionCaseEscalatedPayload` round-trip, that `lookup("local.resolution.case.closed.v1")` / `lookup("local.resolution.case.escalated.v1")` return them, that `TOPIC_NAMES` resolves both keys, that a `ResolutionCaseClosedPayload` with `outcome=escalate_human` or empty `customer_response` raises `ValidationError`, and that a `ResolutionCaseEscalatedPayload` with empty `escalation_detail` raises (T176–T180)
- [ ] T184 [P] [US3] Add `apps/agents/customer_resolution/tests/test_case_closure.py`: unit-test `close_or_escalate(case, decision)` returns `CLOSE` for a decided+drafted case whose decision is `deny_refund`/`offer_partial_credit`/`request_more_information`/`direct_response` with `requires_human_approval=False`; returns `ESCALATE` when the drafted-event id is missing, when `requires_human_approval=True` (incl. gated `approve_refund`), and when `outcome==escalate_human` (acceptance: close conditions)
- [ ] T185 [P] [US3] In `apps/agents/customer_resolution/tests/test_case_closure.py`, table-test `escalation_trigger_for(decision)` maps **each** Phase 18 escalation reason to the correct `CaseEscalationReason`: `peer_requested_review`/`peer_failure`/`peer_rejection` & the `requires_human_approval` gate → `human_review_required`; `missing_analysis`/`analysis_timeout` → `peer_result_timeout`; `low_confidence` → `low_confidence`; `conflicting_analyses` → `policy_conflict`; `elevated_risk` → `high_risk` (acceptance: escalates on the five triggers; SC-007)
- [ ] T186 [P] [US3] Integration test the **close** path in `apps/agents/customer_resolution/tests/test_customer_resolution.py`: drive a `deny_refund` refund case end-to-end and assert exactly one `local.resolution.case.closed.v1` event ordered **after** the `customer.resolution.decided.v1` + `customer-response.drafted.v1` events, with `envelope.correlation_id`/`causation_id` = the case correlation id / decided `event_id`, `outcome=deny_refund`, the drafted `customer_response`, and the case in terminal status `closed`; assert **no** escalated event (SC-003)
- [ ] T187 [P] [US3] Integration test the **escalate** paths in `apps/agents/customer_resolution/tests/test_customer_resolution.py`: drive (a) a `high`-risk case → `case.escalated.v1` with `escalation_reason=high_risk`; (b) a human-approval-gated `approve_refund` → `escalation_reason=human_review_required`; (c) a missing/timed-out analysis → `escalation_reason=peer_result_timeout`; (d) a low-confidence case → `escalation_reason=low_confidence`; (e) a conflicting-analyses case → `escalation_reason=policy_conflict`; each emits exactly one `local.resolution.case.escalated.v1` and **no** closed event, case terminal `escalated` (SC-003/SC-007)

### Implementation

- [ ] T188 [US3] Add the pure `build_case_closed_payload(case, decision, decided_envelope, *, closed_at) -> ResolutionCaseClosedPayload` in `apps/agents/customer_resolution/response_drafter.py` (or `closure.py`): map `case_id = case.correlation_id`, `ticket_id`/`customer_id` from `case.ticket`, `outcome`/`customer_response` from the decision payload, `prior_decision_event_id = decided_envelope.event_id`, and `resolution_summary` from a per-outcome closure template (e.g. "refund denied — billing ineligible", "partial credit offered") — no I/O, unit-testable
- [ ] T189 [US3] Add the pure `build_case_escalated_payload(case, decision, decided_envelope, *, escalated_at) -> ResolutionCaseEscalatedPayload` in the same module: map `case_id`/`ticket_id`/`customer_id`, `(escalation_reason, escalation_detail) = escalation_trigger_for(decision)` (T182), `customer_response = decision.customer_response` (the interim handoff draft) if present, and `prior_decision_event_id = decided_envelope.event_id` — no I/O, unit-testable
- [ ] T190 [US3] In `apps/agents/customer_resolution/event_handlers.py`, **after** the Phase 17 drafted event is published (T138), call `close_or_escalate(case, decision)` (T181) and publish exactly one terminal event via the shared `Publisher`: on `CLOSE` → `ResolutionCaseClosedPayload` (T188) to `TOPIC_CASE_CLOSED` then `transition(case_id, closed)`; on `ESCALATE` → `ResolutionCaseEscalatedPayload` (T189) to `TOPIC_CASE_ESCALATED` then `transition(case_id, escalated)`; both with `correlation_id = decided_envelope.correlation_id` and `causation_id = decided_envelope.event_id`; emit **exactly once** per case (Phase 14 T087/T089 terminal transitions; FR-007/FR-010/FR-016)
- [ ] T191 [US3] Make closure idempotent in `apps/agents/customer_resolution/event_handlers.py`/`state_store.py`: a case already in terminal `closed`/`escalated` (Phase 14 T093 guard) or a re-delivered/late trigger (consumer `IdempotencyTracker`) emits **no** second terminal event and performs no second transition; record the duplicate disposition instead (FR-011/FR-012, SC-003)

### Wiring & Observability

- [ ] T192 [US3] Update `apps/api/dev_consume_events.py` to also subscribe to and pretty-print `local.resolution.case.closed.v1` and `local.resolution.case.escalated.v1` envelopes (and confirm the closure `Publisher`/topics are wired through `agent.py`/`main.py`, T011/T095) so the demo shows each case's terminal disposition (quickstart "Observe events"); emit a `structlog` line (`case_closed`/`case_escalated` with `correlation_id`, `outcome`/`escalation_reason`) at each terminal transition (Principle IV, FR-013)

### Audit (extends US4)

- [ ] T193 [US4] Emit a terminal "case closed" / "case escalated" audit step in `apps/agents/customer_resolution/event_handlers.py` via `agent_foundation.audit.store.write_audit` carrying agent identity, `correlation_id`, `causation_id = decided event id`, timestamp, the terminal `outcome` (closed) or `escalation_reason` (escalated), and a `duplicate_skipped` outcome on a guarded re-trigger — so the case's final disposition and (for escalations) its reason are reconstructable by correlation id (extends the step list in T037/T140/T159; FR-013/FR-014, SC-006/SC-007)

**Checkpoint**: Every decided-and-drafted case terminates with exactly one
`local.resolution.case.closed.v1` (clean resolution, no human review) **or**
`local.resolution.case.escalated.v1` (human review required / peer result timeout / low confidence /
policy conflict / high risk), the case reaches its terminal `closed`/`escalated` state, an audit record
captures the disposition, and replays never double-emit — completing the customer-resolution lifecycle.

### Phase 20 dependencies

- **Foundational T176–T180** block everything in this phase. T176 (reason enum) → T178 (uses it);
  T177 ∥ T178 (same file `payloads.py` — sequence if edited together); T179 (topics) ∥ payload work;
  T180 needs T177+T178+T179.
- **Policy T181/T182** are pure and depend on the Phase 18 decision payload (`outcome`,
  `escalation_reason`, `requires_human_approval` — T141/T145/T136) and the Phase 17 drafted-event id
  recorded on the case (T138); they precede T188–T190.
- **Tests T183 (schemas), T184/T185 (`test_case_closure.py`), T186/T187 (integration)** are written
  first (different files, `[P]`) and must fail before T188–T191.
- **Impl**: T188 + T189 (pure builders, `[P]`) → T190 (emit after the drafted event, extends T138) →
  T191 (idempotency). T190 also requires the Phase 2 process/`Publisher` (T011), the decision-emit
  paths (T148/T151), the drafted-event step (T138), and the Phase 14 terminal transitions (T087/T089).
- **T192** (dev tooling/logging) follows T190; **T193** (audit) follows T190 and folds into the US4
  audit step list (T037/T140/T159).
- **Completes the lifecycle**: `decided` (Phase 18) → `response_drafted` (Phase 17) →
  `closed`/`escalated` (this phase). Reuses `001`/`002` transport, audit, idempotency, the Phase 14
  store, and the existing decision/draft events unchanged (FR-016, Principle V) — no new dependency, no
  second decision policy, no second audit path.

---

## Phase 21: End-to-End Local Workflow Test — full happy-path with three live agents (verifies US1–US6)

**Added by a follow-up `/speckit-tasks` request.** This section is **additive** and **test-centric**: it
adds a single, runnable, **local** end-to-end integration test that drives the **entire**
customer-resolution workflow through the **three real agents** (`customer-resolution` + the existing
`billing-entitlement` and `risk-fraud` demo stubs) against **one local broker**, with **no injected
results and no supervisor**. It is the capstone proof that the per-leg phases above compose into the
demo's headline scenario. It adds **no** new contract, topic, or transport; it continues the numbering
(**T194+**, after the highest existing id T193) and reuses this file's package layout; the test lives
under `apps/agents/customer_resolution/tests/`.

**Scenario under test** (the exact chain from the request, mapped to the phases that build each step):

```text
support.ticket.created
  → ticket classified as refund_request   (Phase 10 classification event; requires_billing/risk_review=true)
  → billing A2A task requested            (Phase 4/13 TaskRequest → billing endpoint_topic)
  → risk A2A task requested               (Phase 4/12 TaskRequest → risk endpoint_topic)
  → billing result consumed               (US3 / T034 generic TaskResult on TOPIC_TASK_RESULT)
  → risk result consumed                  (US3 / T034 generic TaskResult on TOPIC_TASK_RESULT)
  → decision produced                     (Phase 18 engine T148/T151 → customer.resolution.decided)
  → customer response drafted             (Phase 17 customer-response.drafted.v1 event, T138)
  → case closed                           (Phase 14 status: decided → response_drafted → closed)
```

**Result ingress used by this test (reconciliation with Phases 15/16).** The live demo stubs
(`apps/agents/billing_entitlement/main.py`, `apps/agents/risk_fraud/main.py`) reply through the **002
runtime's generic `TaskResult` mechanism on `TOPIC_TASK_RESULT`** — and each already **echoes the
originating `task_id`** in its result data part. That generic path (US3 / **T034**) is therefore the
ingress this E2E exercises; it does **not** drive the Phase 15/16 billing/risk **domain-completion**
events (`local.billing.refund-analysis.completed.v1` / `local.risk.review.completed.v1`), whose own
integration tests (T108/T122) cover that variant. This keeps the E2E a *true* end-to-end run (the peers
actually compute and return results) rather than an injected-result harness.

**Reconciliation with Phases 17/18 (decision, draft, evidence, closed).**
- *"decision produced"* uses the Phase 18 single decision engine (`decide`, T148/T151) emitting one
  `customer.resolution.decided.v1`; if Phase 18 is not yet implemented the Phase 5 `decide` (T031)
  applies — either way exactly one decision (FR-007).
- *"customer response drafted"* maps to the Phase 17 `local.resolution.customer-response.drafted.v1`
  event (T138). The test also accepts the decision payload's own `customer_response` field as the draft
  when Phase 17 is not yet present.
- *"case closed"* is the Phase 14 terminal `closed` status reached via `decided → response_drafted →
  closed` (T087/T089); T194 ensures the final `→ closed` transition runs on the happy path.
- **AC4 ("A2A task IDs appear in final decision evidence")** maps directly onto the Phase 18 structured
  `evidence: list[DecisionEvidence]` (T145/T149), where each `DecisionEvidence.task_id` cites the
  billing/risk task. T195 guarantees the issued task ids reach the decision evidence regardless of which
  decision design is in place (Phase 18 `evidence`, else the `billing_summary`/`risk_summary` fields).

### Acceptance criteria → how each is met (from the `/speckit-tasks` request)

| Criterion | How it is satisfied | Verified by |
|-----------|---------------------|-------------|
| **Test runs locally** | One `@pytest.mark.integration` test on the established **module-scoped `testcontainers` Kafka** fixture (`tests/integration/conftest.py` pattern) and the `AgentRuntime.serve(stop_event)` lifecycle — no remote infra, no external services; runnable with a single `uv run pytest -m integration …` command | T196, T202, T203 |
| **No supervisor agent is used** | Exactly **three** agent cards are discovered (resolution + billing + risk), each `TaskRequest` is published **directly** to a peer `endpoint_topic(...)` (no shared/intermediary routing topic), and the `test_no_router` `FORBIDDEN_NAMES` AST invariant (dispatcher/router/orchestrator/supervisor) still holds across `apps/agents/**` | T199 |
| **Kafka events preserve same correlation ID** | Every envelope in the chain — `support.ticket.created`, the classification event, both `task.requested`, both `TaskResult`s, the refund-review-requested announcement, the final `customer.resolution.decided`, and the `customer-response.drafted` event — carries the **same `correlation_id`** as the originating ticket envelope | T201 |
| **A2A task IDs appear in final decision evidence** | The two issued `TaskRequest.task_id`s (recorded on `case.billing.task_id`/`case.risk.task_id`) appear in the emitted decision's `evidence` (Phase 18 `DecisionEvidence.task_id`, T149) — or its `billing_summary`/`risk_summary` (T195 fallback) — **and** in the correlated audit trail (`query_by_correlation`) | T200 |

### Implementation enablers (make "case closed" and AC4 truthfully verifiable)

- [ ] T194 [US3] Drive the happy path to the Phase 14 terminal `closed` status: after the decision is emitted and the response is drafted (Phase 17 T138, or the decision's `customer_response`), run `decided → response_drafted → closed` via `state_store.transition(...)` (using `assert_transition`, T089) in `apps/agents/customer_resolution/event_handlers.py`/`agent.py`, so a fully-resolved refund case ends terminal `closed` (scenario "case closed"; reconciles Phase 14 T087/T089 and Phase 17 T138, and the Phase 20 closure emit T190)
- [ ] T195 [US3] Guarantee the originating A2A task ids reach the **final decision evidence**: confirm Phase 18 `build_evidence` (T149) emits a `DecisionEvidence` with `task_id == case.billing.task_id` and one with `task_id == case.risk.task_id`; if the structured `evidence` list is not present (Phase 18 not applied), instead include `case.billing.task_id` in `billing_summary` and `case.risk.task_id` in `risk_summary` in `apps/agents/customer_resolution/response_drafter.py`/`decision_engine.py` (kept null for `direct_response`) — so every billing/risk fact in the decision is traceable to its A2A task (AC4, US5-2, SC-004)

### Test harness + shared evidence fixture (build the harness first)

- [ ] T196 [US3] Add the E2E harness to `apps/agents/customer_resolution/tests/conftest.py`: a module-scoped `local_broker` fixture reusing the `testcontainers` `KafkaContainer("confluentinc/cp-kafka:7.6.0")` pattern from `tests/integration/conftest.py`; a `running_agents` fixture that provisions the topics and starts all **three** agents in-process (resolution + `billing_entitlement` + `risk_fraud`) via their `AgentRuntime.serve(stop_event)` under `asyncio` against `local_broker` (set `AGENT_BROKER_URL`), tearing them down via the stop event; and an `event_recorder` consumer capturing every `EventEnvelope` on the ticket, classification, both peers' `endpoint_topic(...)`, `TOPIC_TASK_RESULT`, refund-review-requested, decision, and response-drafted topics (mark the module `@pytest.mark.integration`)
- [ ] T197 [US3] Add the **package-scoped `e2e_evidence` fixture** to `apps/agents/customer_resolution/tests/conftest.py`: with `running_agents` up, publish one refund `support.ticket.created` (reason e.g. "Please refund — I was charged twice for my subscription") via the shared `Publisher`, then await (bounded timeout) the terminal `customer.resolution.decided` event and the case reaching `closed`; return an `EvidenceBundle` dataclass exposing the captured envelopes (ticket, classification, billing & risk `task.requested`, billing & risk `TaskResult`, refund-review-requested, decision, response-drafted), the issued billing/risk `task_id`s, the final `CaseStatus`, and the audit records from `query_by_correlation(ticket.correlation_id)` — so the AC tests assert against one real run

### End-to-end assertions (the scenario + the four acceptance criteria)

- [ ] T198 [P] [US3] Add `apps/agents/customer_resolution/tests/test_e2e_local_workflow.py::test_full_happy_path_step_order`: assert the nine scenario steps occurred in causal order against `e2e_evidence` — a classification event with `requires_billing_review` and `requires_risk_review` both `true` (classified as a refund request), exactly **one** billing and **one** risk `task.requested`, both `TaskResult`s consumed, exactly **one** `customer.resolution.decided` with `outcome == approve_refund` and a non-empty `customer_response` plus a `customer-response.drafted` event (response drafted), and final `CaseStatus == closed` (full scenario; SC-001/SC-002/SC-003)
- [ ] T199 [P] [US6] Add `apps/agents/customer_resolution/tests/test_e2e_no_supervisor.py`: assert **AC "no supervisor"** — card discovery (`find_capable`) returns exactly the three agent ids (`customer-resolution-agent`, `billing-entitlement-agent`, `risk-fraud-agent`) with no router/supervisor capability; both `task.requested` events in `e2e_evidence` were observed on the peers' `endpoint_topic(...)` (never a shared intermediary/result topic); and the `FORBIDDEN_NAMES` AST invariant from `tests/integration/test_no_router.py` still holds across `apps/agents/**` (reuse its helper) (AC2, FR-015/FR-017, SC-008)
- [ ] T200 [P] [US3] Add `apps/agents/customer_resolution/tests/test_e2e_decision_evidence.py`: assert **AC "task ids in final decision evidence"** against `e2e_evidence` — the billing `task_id` and the risk `task_id` (equal to the `task_id`s on the two captured `task.requested` envelopes) each appear in the decision's `evidence` (`DecisionEvidence.task_id`, Phase 18) or, fallback, in `decision.billing_summary`/`decision.risk_summary` (T195), **and** both appear in the correlated audit trail (`query_by_correlation`) for the billing/risk delegation steps (AC4, SC-004/SC-006)
- [ ] T201 [P] [US3] Add `apps/agents/customer_resolution/tests/test_e2e_local_workflow.py::test_correlation_id_preserved`: assert **AC "same correlation id"** — every captured envelope (`ticket`, classification, both `task.requested`, both `TaskResult`, refund-review-requested, decision, response-drafted) has `envelope.correlation_id == ticket.correlation_id` (AC3, FR-006/FR-014)

### Local-run registration & validation

- [ ] T202 [US3] Register the E2E in the quickstart and test config: add a **"Scenario 9 — full happy-path E2E (three live agents, local)"** entry to `specs/003-customer-resolution-agent/quickstart.md` "Automated validation" with the single command `uv run pytest -m integration apps/agents/customer_resolution/tests/test_e2e_local_workflow.py apps/agents/customer_resolution/tests/test_e2e_decision_evidence.py apps/agents/customer_resolution/tests/test_e2e_no_supervisor.py`, and ensure the `integration` marker is declared in `pyproject.toml`/`pytest.ini` (AC1)
- [ ] T203 [US3] Run the E2E locally against a `testcontainers` broker and confirm all four acceptance criteria pass (runs locally; no supervisor; correlation id preserved end-to-end; A2A task ids present in the final decision evidence); fold the run into the Phase 9 polish gate (T043/T044)

**Checkpoint**: One local `pytest -m integration` run drives `support.ticket.created` through three live
agents to a single `approve_refund` decision and a `closed` case — proving the full decentralized
happy-path with **no supervisor**, a **preserved correlation id** end-to-end, and the **A2A task ids
present in the final decision's evidence**.

### Phase 21 dependencies

- **Builds on the whole feature**: US1 intake/triage (Phase 3) + classification (Phase 10) + US2
  delegation (Phase 4, hardened by Phases 12/13) + US3 result consumption (Phase 5, T034) + the decision
  engine (Phase 18, or Phase 5 T031) + Phase 14 case store/statuses (`response_drafted`/`closed`) +
  Phase 17 draft event + the Phase 20 closure emit (T190) + US4 audit (Phase 6) must be implemented;
  this phase adds no new contract, topic, or transport.
- **Enablers first**: T194 (closed transition) and T195 (task-id evidence) precede the assertions; they
  touch different files and may proceed in parallel.
- **Harness before assertions**: T196 (broker + 3 live agents + recorder) → T197 (`e2e_evidence`
  fixture, one real run) → T198/T199/T200/T201 (assertions, `[P]` across separate test files sharing the
  module/package-scoped `e2e_evidence` fixture).
- **T202/T203** (docs + local validation) follow the assertions.
- Reuses `001`/`002` transport, audit, idempotency, runtime, discovery, and the existing demo stubs
  unchanged (FR-016, Principle V) — **no new dependency, no new model, no second audit path, no
  supervisor**.

---

## Phase 22: Structured Response Drafter — `subject` / `body` / `response_type` + tone & fact whitelist (refines Phase 17 / hardens US3/US5)

**Added by a follow-up `/speckit-tasks` request: "Implement response drafter."** This section is
**additive** and **refines** the response drafter built in Phase 17 (and the templates in
T016/T032/T150). Phase 17 produces a single flat `draft_response` string gated by
`requires_human_approval`; this phase decomposes drafting into the explicit, testable contract the
request specifies and adds a **positive allow-list** of customer-safe facts plus **fraud-scoring
suppression**. It reuses this file's package layout (`response_drafter.py`, `config.py`,
`event_handlers.py`, tests under `apps/agents/customer_resolution/tests/`) and the existing
`ResolutionOutcome`/human-approval policy — **no new dependency, no new transport, no second audit
path** (FR-016, Principle V).

**Requested contract**:

| | Fields |
|---|---|
| **Inputs** (python) | `ticket_summary`, `decision`, `allowed_facts`, `tone_config` |
| **Outputs** (python) | `subject`, `body`, `response_type`, `requires_human_approval` |

**Reconciliation with Phase 17 — the structured draft is the *source* of the flat draft, not a
duplicate.** `draft_structured_response(...)` becomes the single place customer-facing text is built;
the Phase 17 `build_response_drafted_payload` (T135) and the decision payload's `customer_response`
(T016/T032/T150) are refactored to render from it (`customer_response = subject + body`), so the
existing `customer.resolution.decided.v1` and `customer-response.drafted.v1` events keep their wire
shape. `requires_human_approval` is **not** re-derived here — it reuses the deterministic policy in
`config.HUMAN_APPROVAL_OUTCOMES` / `requires_human_approval(outcome)` (Phase 17 T131/T136) so there is
one auditable rule (escalate ⇒ human review).

**The `allowed_facts` whitelist is the positive complement to Phase 17's negative guard.** Phase 17's
`INTERNAL_ONLY_DRAFT_FIELDS` (T131) blocks `rationale`/`escalation_reason`/`billing_summary`/
`risk_summary` from leaking; this phase additionally enforces that the draft is composed **only** from
an explicit `AllowedFacts` set built from the ticket, the billing finding, the risk finding, and
policy/decision context — and that this set **excludes all fraud-scoring detail** (risk score,
confidence, risk level, fraud evidence, risk reasoning). Fraud suppression is therefore guaranteed by
construction (the whitelist omits those fields), by the builder (it never reads them), and by a
fail-closed output guard.

**Goal**: A pure `draft_structured_response(ticket_summary, decision, allowed_facts, tone_config) ->
ResponseDraft` returning `subject`, `body`, `response_type`, and `requires_human_approval`, where
`body`/`subject` are rendered solely from `allowed_facts` + `tone_config`, `response_type` is keyed to
the outcome, escalations require human review, and no fraud-scoring detail can reach the customer.

**Independent Test**: Call `draft_structured_response` with each `ResolutionOutcome` and a fixed
`tone_config` over an `allowed_facts` built from a billing finding (eligible) and a risk finding
carrying a high score + fraud evidence; assert (1) `subject`/`body` are non-empty and contain only
whitelisted facts, (2) none of the risk score/confidence/evidence/reasoning values appear in
`subject` or `body`, (3) `response_type` matches the outcome and `requires_human_approval` is `True`
only for `escalate_human` (and `approve_refund` per the Phase 17 policy), (4) `ResponseDraft` is a
frozen, structured model.

### Acceptance criteria → how each is met (from the `/speckit-tasks` request)

| Criterion | How it is satisfied | Verified by |
|-----------|---------------------|-------------|
| **Draft uses only known facts (ticket, billing, risk, policy)** | `body`/`subject` are rendered strictly from the `AllowedFacts` set produced by `build_allowed_facts(...)`; a guard raises if drafting references any field outside it | T206, T208, T211, T213 |
| **Draft does not expose fraud-scoring details** | `AllowedFacts` omits every risk score/confidence/level/evidence/reasoning field by type (T206); `build_allowed_facts` never reads them (T211); a fail-closed output scan rejects any `FRAUD_SCORING_FIELDS` content (T213) | T206, T209, T211, T213 |
| **Human review required for escalated cases** | `requires_human_approval` reuses the deterministic Phase 17 policy (`escalate_human ⇒ True`); a `model_validator` on `ResponseDraft` enforces it | T207, T210, T212 |
| **Draft is structured and testable** | Output is the frozen Pydantic `ResponseDraft(subject, body, response_type, requires_human_approval)`; the drafter is a pure, I/O-free function unit-tested per outcome | T207, T210, T212 |

### Foundational (models + config — block the drafter and its tests)

- [ ] T204 [P] [US3] Define a `ResponseType` enum (`refund_confirmation`, `refund_denial`, `escalation_acknowledgement`, `direct_answer`) and the outcome→type mapping in `apps/agents/customer_resolution/response_drafter.py` (keyed to `ResolutionOutcome`: approve→confirmation, deny→denial, escalate→acknowledgement, direct→answer)
- [ ] T205 [P] [US3] Define a frozen `ToneConfig` Pydantic model (`brand_name`, `greeting`, `signoff`, `formality: Literal["formal","friendly"]`, `apologetic: bool`) in `apps/agents/customer_resolution/response_drafter.py`, and add a `DEFAULT_TONE` instance to `apps/agents/customer_resolution/config.py` documented as illustrative PoC wording (extends T009/T131)
- [ ] T206 [P] [US5] Define a frozen `AllowedFacts` model (whitelist only: `refund_amount`, `currency`, `order_reference`, `billing_outcome_summary`, `eligibility: bool | None`) in `apps/agents/customer_resolution/response_drafter.py`, and add `CUSTOMER_SAFE_FACT_KEYS` + `FRAUD_SCORING_FIELDS = ("score", "confidence", "risk_level", "evidence", "reasoning_summary")` to `apps/agents/customer_resolution/config.py`; the model MUST contain no risk score/confidence/level/evidence/reasoning field (fraud suppression by construction, AC2)
- [ ] T207 [US3] Define the frozen `ResponseDraft` output model (`subject: str`, `body: str`, `response_type: ResponseType`, `requires_human_approval: bool`, `extra="forbid"`) in `apps/agents/customer_resolution/response_drafter.py` with a `model_validator(mode="after")` requiring non-empty `subject`/`body` and re-asserting the Phase 17 rule `outcome-derived escalate ⇒ requires_human_approval is True` (depends on T204)

### Tests (write first — must FAIL before implementation)

- [ ] T208 [P] [US5] Unit-test `build_allowed_facts` in `apps/agents/customer_resolution/tests/test_response_drafter.py`: given a billing finding (eligible + summary) and a risk finding carrying a score/confidence/evidence, the returned `AllowedFacts` contains only `CUSTOMER_SAFE_FACT_KEYS` and **none** of the `FRAUD_SCORING_FIELDS` (AC1/AC2)
- [ ] T209 [P] [US5] Leak-scan unit test in `apps/agents/customer_resolution/tests/test_response_drafter.py`: for every `ResolutionOutcome`, the rendered `subject`+`body` contain none of the risk finding's score/confidence/evidence/reasoning values nor any `FRAUD_SCORING_FIELDS`-named content (AC2)
- [ ] T210 [P] [US3] Structure/typing unit test in `apps/agents/customer_resolution/tests/test_response_drafter.py`: `draft_structured_response` returns a frozen `ResponseDraft` with non-empty `subject`/`body`; `response_type` matches the outcome mapping (T204); `requires_human_approval` is `True` only for outcomes in `HUMAN_APPROVAL_OUTCOMES` (Phase 17 T131) and `False` otherwise (AC3/AC4)

### Implementation

- [ ] T211 [US5] Implement `build_allowed_facts(ticket_summary, decision, billing_finding, risk_finding) -> AllowedFacts` in `apps/agents/customer_resolution/response_drafter.py`: read only the ticket amount/currency/order reference, the billing eligibility + sanitized billing summary, and policy/decision context; deliberately read **no** `RiskFinding` score/level/evidence/reasoning (AC1/AC2) (depends on T206)
- [ ] T212 [US3] Implement the pure `draft_structured_response(ticket_summary, decision, allowed_facts, tone_config) -> ResponseDraft` in `apps/agents/customer_resolution/response_drafter.py`: per-outcome `subject`/`body` templates rendered solely from `allowed_facts` + `tone_config`; set `response_type` from the T204 mapping and `requires_human_approval` via the Phase 17 `requires_human_approval(outcome)` policy (T136) — no I/O, unit-testable (depends on T204, T205, T207, T211)
- [ ] T213 [US5] Extend the Phase 17 safe-language guard (T137) in `apps/agents/customer_resolution/response_drafter.py` to (a) render the draft **only** from `AllowedFacts` keys and raise if any out-of-whitelist field is referenced, and (b) fail closed (raise) if any `FRAUD_SCORING_FIELDS` content is detected in the final `subject`/`body` before return (AC1/AC2) (depends on T212)

### Integration (back-compat with Phase 17 / decision payload)

- [ ] T214 [US3] Refactor the flat-text producers to source from the structured drafter: in `apps/agents/customer_resolution/response_drafter.py`, build `customer_response`/`draft_response` as `f"{draft.subject}\n\n{draft.body}"` from `draft_structured_response(...)` so `build_response_drafted_payload` (T135) and `decision.customer_response` (T016/T032/T150) keep their existing wire shape; do **not** alter the `customer.resolution.decided.v1` / `customer-response.drafted.v1` contracts (depends on T212)
- [ ] T215 [US4] Extend the "customer response drafted" audit step (T140) in `apps/agents/customer_resolution/event_handlers.py` to record the draft's `response_type` and the `AllowedFacts` keys used, so the structured draft and its fact provenance are reconstructable by `correlation_id` (FR-013/FR-014, SC-006) (depends on T214)

### Polish

- [ ] T216 [P] [US3] Run the drafter suite + static checks green: `uv run pytest apps/agents/customer_resolution/tests/test_response_drafter.py && uv run mypy apps/agents/customer_resolution && uv run ruff check apps/agents/customer_resolution`
- [ ] T217 [P] Add a "structured response drafter" note to `specs/003-customer-resolution-agent/quickstart.md` covering the outcome→`response_type` mapping, the `tone_config` knobs, the `allowed_facts` whitelist, and the fraud-suppression guarantee

**Checkpoint**: The response drafter exposes the requested `draft_structured_response(ticket_summary,
decision, allowed_facts, tone_config) -> ResponseDraft(subject, body, response_type,
requires_human_approval)` contract; drafts are built only from whitelisted facts, expose no
fraud-scoring detail, require human review for escalations, and are fully unit-tested — while the
Phase 17 draft event and the decision payload keep their existing shapes.

### Phase 22 dependencies

- **Foundational T204–T207** block the rest of the phase. T204 ∥ T205 ∥ T206 (independent symbols);
  T207 needs T204.
- **Tests T208/T209/T210** (same test file, independent functions — `[P]`) are written first and must
  fail before T211–T214.
- **Impl**: T211 (allow-list builder) → T212 (structured drafter) → T213 (whitelist + fraud-suppression
  guard) → T214 (back-compat wiring into Phase 17/decision text). T212 also reuses the Phase 17 approval
  policy (T131/T136) and the existing per-outcome templates (T016/T032/T150).
- **T215** (audit) follows T214 and extends the Phase 17 audit step (T140).
- **Refines, does not replace, Phase 17**: the `customer-response.drafted.v1` event (T127–T139) and the
  `customer.resolution.decided.v1` decision payload are unchanged; only the **construction** of the
  customer-facing text is restructured. Reuses `001`/`002` transport, audit, idempotency, runtime, and
  `ResolutionOutcome` unchanged (FR-016, Principle V) — **no new dependency, no new transport, no second
  audit path**.

---

## Phase 23: Publish Resolution Decision Event — `local.resolution.customer-resolution.decided.v1` (completes US3/US4)

**Added by a follow-up `/speckit-tasks` request.** This section is **additive** to the feature above —
it pins the agent's **final decision emission** to the explicit, `resolution.*`-namespaced domain event
`local.resolution.customer-resolution.decided.v1` with the requested payload, against the three
acceptance criteria from the request. It continues the numbering (T218+) and reuses this file's package
layout (`decision_engine.py`, `response_drafter.py`, `event_handlers.py`, `models.py`, contracts in
`packages/contracts/`, tests under `apps/agents/customer_resolution/tests/`).

**Reconciliation — this supersedes the base decision event (Phase 2/US1/US3).** The base feature emits
`CustomerResponseDecisionPayload` on `TOPIC_RESOLUTION_DECIDED` (`local.customer.resolution.decided.v1`,
T004–T007), published from the intake handler (direct_response, T017/T018) and the result handler
(approve/deny/escalate, T034). This phase makes **`local.resolution.customer-resolution.decided.v1`**
the **authoritative** emitted decision — aligning it with the `local.resolution.*` namespace used by
Phase 10 (`customer-issue.classified`), Phase 11 (`refund-review.requested`), Phase 17
(`customer-response.drafted`), and Phase 20 (`case.closed`/`case.escalated`) — and migrates the two base
emit sites onto it. Field mapping from the base payload: `outcome → decision` (same four values:
`approve_refund`/`deny_refund`/`escalate_human`/`direct_response`), `rationale → reasoning_summary`,
`billing_summary → billing_recommendation`, `risk_summary → risk_recommendation`; the base
`customer_response` drafted message is **dropped from the wire** (the customer-facing message lives in the
Phase 17 `customer-response.drafted.v1` event) to satisfy AC3 (minimize sensitive raw content); and
`confidence`, `requires_human_review`, and `evidence` (peer task-id / result-event-id references, AC2)
are **added**. When implementing, treat T204–T230 as the authoritative decision-event design; the base
`CustomerResponseDecisionPayload` / `TOPIC_RESOLUTION_DECIDED` and the T017/T034 emit are retired in
favor of it.

**Builds on the deterministic decision engine (Phase 18) and the existing path.** The decision *outcome*
is produced by the deterministic `decide(triage, billing_slot, risk_slot)` policy (Phase 18 decision
engine; US3 T031; decision-policy.md §C) and emitted **exactly once** per case under the Phase 14 store's
terminal-state / duplicate guards (T093), the late-result-after-decision rule (FR-012, T034), and the
Phase 16 forced-escalation path (T125). This phase changes only the **emitted contract and topic**, not
the policy or the "exactly one decision per case" guarantee (SC-003). This decision event is the upstream
cause of the Phase 17 `customer-response.drafted.v1` and Phase 20 `case.closed`/`case.escalated` events,
which follow it.

**Goal**: For every resolved case, the agent publishes exactly one
`local.resolution.customer-resolution.decided.v1` event carrying `case_id`, `ticket_id`, `customer_id`,
`decision`, `confidence`, `billing_recommendation`, `risk_recommendation`, `evidence` (the peer
`task_id`s and source result `event_id`s), `reasoning_summary`, and `requires_human_review` — on a
durable, registered topic, with raw customer content minimized.

**Independent Test**: Drive a refund case to approve/deny/escalate and a non-refund case to
direct_response → consume from `local.resolution.customer-resolution.decided.v1`: exactly one event per
case, `envelope.correlation_id == case.correlation_id`, `envelope.agent_id == "customer-resolution-agent"`;
for refund decisions `evidence.billing_task_id`/`evidence.risk_task_id` equal the issued `TaskRequest`
ids and `evidence.billing_result_event_id`/`evidence.risk_result_event_id` equal the consumed result
envelopes' ids; for direct_response the recommendation fields and evidence peer references are null; no
field contains the raw ticket `reason` text; re-consuming the topic from offset 0 replays the decision
intact.

### Acceptance criteria → how each is met (from the `/speckit-tasks` request)

| Criterion | How it is satisfied | Verified by |
|-----------|---------------------|-------------|
| **Decision event is replayable** | Published via the shared `Publisher`/`EventEnvelope` (no parallel transport, FR-016) on a **durable, non-compacted** topic provisioned with 7-day retention and registered in `PAYLOAD_REGISTRY`; the payload is self-contained (carries `case_id`, the decision, and all evidence references) so a consumer can rebuild the outcome from the event alone; emitted exactly once per case (terminal-state guard) so a replay yields no contradictory second decision | T220, T221, T222, T229 |
| **Decision includes references to peer task IDs / result event IDs** | `evidence: DecisionEvidence` carries `billing_task_id`/`risk_task_id` (the issued `TaskRequest` ids recorded on the case slots) and `billing_result_event_id`/`risk_result_event_id` (the consumed result envelopes' `event_id`s, newly recorded on the case at result time); a `model_validator` requires both task ids **and** both result event ids for `approve_refund`/`deny_refund` (every billing/risk fact traceable to a peer task + result event) | T218, T219, T223, T225, T229 |
| **Sensitive raw customer content is minimized** | The payload carries only minimized **summaries** (`billing_recommendation`, `risk_recommendation`, `reasoning_summary` derived from the normalized findings — never `ticket.reason` or the raw customer message) and the `customer_id` identifier; the drafted customer-facing message is kept out of this event (it is the Phase 17 `customer-response.drafted.v1` payload); a minimization helper (length-bounded, redacting) produces the summary fields and a test asserts the raw ticket text never leaks | T226, T227, T225, T229 |

> **Non-root event**: `local.resolution.customer-resolution.decided.v1` is not a root type, so the
> envelope's `causation_id` is **required** — set it to the **decisive triggering event**: for a refund
> decision, the `event_id` of the result envelope that completed the case (cleared the last
> `pending_tasks` entry or forced escalation, Phase 16 T125); for `direct_response`, the inbound ticket's
> `event_id`. Otherwise `EventEnvelope` validation raises `MissingCausation`
> (`src/agent_foundation/envelope.py`). Producer identity is `envelope.agent_id`, set by `Publisher`
> from the process `AgentIdentity(agent_id="customer-resolution-agent")`.

### Foundational (contract + validator + topic + registry + provisioning — blocks the publish path and tests)

- [ ] T218 [US3] Add `ResolutionDecision` (str Enum: `approve_refund`/`deny_refund`/`escalate_human`/`direct_response`), `DecisionEvidence` (Pydantic v2, `frozen`, `extra="forbid"`: `billing_task_id: UUID | None = None`, `risk_task_id: UUID | None = None`, `billing_result_event_id: UUID | None = None`, `risk_result_event_id: UUID | None = None`, `notes: list[str] = []`), and `CustomerResolutionDecidedPayload` (Pydantic v2, `frozen`, `extra="forbid"`: `case_id: UUID`, `ticket_id: str`, `customer_id: str`, `decision: ResolutionDecision`, `confidence: Annotated[float, Field(ge=0.0, le=1.0)]`, `billing_recommendation: str | None = None`, `risk_recommendation: str | None = None`, `evidence: DecisionEvidence`, `reasoning_summary: str`, `requires_human_review: bool`) to `packages/contracts/events/payloads.py`; add all three to the module `__all__` (mirror the existing payload style)
- [ ] T219 [US3] Add a `model_validator(mode="after")` to `CustomerResolutionDecidedPayload` in `packages/contracts/events/payloads.py`: `requires_human_review` is `True` **iff** `decision == escalate_human` (FR-010); for `direct_response`, `billing_recommendation`/`risk_recommendation` are `None` and `evidence` carries **no** peer task/result ids (no peers consulted, SC-001); for `approve_refund`/`deny_refund`, `evidence.billing_task_id`, `evidence.risk_task_id`, `evidence.billing_result_event_id`, and `evidence.risk_result_event_id` are all non-null (every billing/risk fact traceable to a peer task + result event, AC2/SC-004)
- [ ] T220 [P] [US3] Add `TOPIC_RESOLUTION_DECISION = topic_for("resolution", "customer-resolution", "decided")` (resolves to `local.resolution.customer-resolution.decided.v1`) in `packages/contracts/topics.py`, beside the other `resolution.*` topics; add a docstring noting it **supersedes** the base `TOPIC_RESOLUTION_DECIDED` (`local.customer.resolution.decided.v1`, T005) as the authoritative emitted decision topic
- [ ] T221 [US3] Register `"local.resolution.customer-resolution.decided.v1": CustomerResolutionDecidedPayload` in `PAYLOAD_REGISTRY` in `src/agent_foundation/payloads/__init__.py` so `Publisher`/`Consumer` validate it on send/receive; remove the superseded `local.customer.resolution.decided.v1` entry (T006) (depends on T218, T220)
- [ ] T222 [US3] Wire transport resolution + provisioning in `src/agent_foundation/transport/topics.py`: add the event-type→topic mapping to `TOPIC_NAMES` (key == value == `TOPIC_RESOLUTION_DECISION`, new-style convention) and append `NewTopic(name=TOPIC_RESOLUTION_DECISION, num_partitions=1, replication_factor=1, topic_configs={"retention.ms": str(_SEVEN_DAYS_MS)})` to `_CANONICAL_TOPICS` (durable event stream, **not** compacted — replayable, AC1); drop the superseded `TOPIC_RESOLUTION_DECIDED` mapping/provisioning (T007) (depends on T220)

### Case state (record source result event ids — blocks AC2 evidence)

- [ ] T223 [US3] Extend `ResolutionCase` in `apps/agents/customer_resolution/models.py` (Phase 14 T088) with `billing_result_event_id: UUID | None = None` and `risk_result_event_id: UUID | None = None`, and record the **source result envelope `event_id`** on the case at result time in every result-apply path: the generic `TaskResult` handler (US3 T034), `attach_billing_result` (Phase 15 T109), `attach_risk_result` (Phase 16 T123), and the store's `apply_result` (Phase 14 T092) — so the decision builder can reference each consumed peer result event (AC2)

### Tests (write first — must FAIL before implementation)

- [ ] T224 [P] [US3] Extend `apps/agents/customer_resolution/tests/test_resolution_schemas.py`: assert `CustomerResolutionDecidedPayload` round-trips, that `lookup("local.resolution.customer-resolution.decided.v1")` returns it, that `TOPIC_NAMES` resolves the same key, that a `confidence` outside `[0.0, 1.0]` raises `ValidationError`, and that the T219 validator rejects (a) `escalate_human` with `requires_human_review=False`, (b) `direct_response` carrying a peer `task_id`, and (c) `approve_refund`/`deny_refund` missing any of the four `evidence` task/result-event ids
- [ ] T225 [P] [US3] Add `apps/agents/customer_resolution/tests/test_resolution_decided.py`: build the decision envelope (via T226) for approve / deny / escalate / direct_response from sample cases and assert `envelope.event_type == "local.resolution.customer-resolution.decided.v1"`, `envelope.agent_id == "customer-resolution-agent"`, `envelope.correlation_id == case.correlation_id`, `envelope.causation_id == <decisive triggering event id>` (decisive result `event_id` for refund; ticket `event_id` for direct_response), `evidence.billing_task_id`/`risk_task_id` equal the case slot `task_id`s and `evidence.billing_result_event_id`/`risk_result_event_id` equal the recorded result event ids (AC2), and that **no** payload field contains the raw `ticket.reason` substring or customer message (AC3) — assert on the constructed `EventEnvelope`, no Kafka

### Implementation

- [ ] T226 [US3] Add a pure `build_resolution_decided_payload(case, outcome, *, reasoning_summary, confidence) -> CustomerResolutionDecidedPayload` in `apps/agents/customer_resolution/decision_engine.py`: map `case_id = case.correlation_id`, `ticket_id`/`customer_id` from `case.ticket`, `decision` from the Phase 18 decision-engine outcome (decision-policy.md §C), `confidence` **deterministically** derived from the present `BillingFinding`/`RiskFinding` confidences (e.g. `min` of available; a fixed constant for `direct_response`), `billing_recommendation`/`risk_recommendation` from the **normalized findings' minimized summaries** (decision-policy.md §B — never `ticket.reason`), `evidence = DecisionEvidence(billing_task_id=case.billing.task_id, risk_task_id=case.risk.task_id, billing_result_event_id=case.billing_result_event_id, risk_result_event_id=case.risk_result_event_id)` (all null for `direct_response`), and `requires_human_review = (decision == escalate_human)` — no I/O, unit-testable
- [ ] T227 [US3] Add a minimization helper in `apps/agents/customer_resolution/response_drafter.py` (length-bounded summarize/redact, max length from `config.py`, T009) that produces `billing_recommendation`/`risk_recommendation`/`reasoning_summary` from the finding summaries and the decision rationale, guaranteeing the wire payload carries **no** raw customer message / `ticket.reason` / PII content — only `customer_id` as an identifier (AC3, FR-005-adjacent); the drafted customer-facing message stays in the Phase 17 `customer-response.drafted.v1` event and is **not** placed on this decision event
- [ ] T228 [US3] Migrate the decision emit to `TOPIC_RESOLUTION_DECISION`: in the result handlers (`apps/agents/customer_resolution/event_handlers.py`, US3 T034 / Phase 15 T111 / Phase 16 T125) and the intake direct_response branch (US1 T018), build the payload via T226 and publish **exactly one** `CustomerResolutionDecidedPayload` to `TOPIC_RESOLUTION_DECISION` via the shared `Publisher` with `correlation_id = case.correlation_id` and `causation_id = <decisive triggering event id>` (refund: the completing result envelope `event_id`; direct_response: the ticket `event_id`); a late/duplicate result for an already-decided case is recorded, **not** re-emitted (FR-012, reuse the T034/T093 terminal-state guard); **remove** the superseded `CustomerResponseDecisionPayload`/`TOPIC_RESOLUTION_DECIDED` emit (T017/T034). Publish this decision event **before** the Phase 17 drafted event (T138) and the Phase 20 closure events so they can cite it as cause
- [ ] T229 [P] [US3] Integration test in `apps/agents/customer_resolution/tests/test_customer_resolution.py`: drive approve / deny / escalate / direct_response → consume from `local.resolution.customer-resolution.decided.v1` and assert exactly one decision per case with the expected `decision` and `requires_human_review`; `evidence` task ids equal the issued `TaskRequest` ids and `evidence` result-event ids equal the consumed result envelopes' ids (AC2); the event contains no raw `ticket.reason` text (AC3); replay a peer result **after** the decision → no second/contradictory decision (FR-012); re-consume the decision topic **from offset 0** → the decision replays intact (durable retention, AC1)

### Audit (extends US4)

- [ ] T230 [US4] Update the "final decision" audit step in `apps/agents/customer_resolution/event_handlers.py` (T037/T038) to record the new event type `local.resolution.customer-resolution.decided.v1`, the `decision` outcome, the escalation reason when applicable, and the peer `task_id`/`result_event_id` references via `agent_foundation.audit.store.write_audit` (agent identity, `correlation_id`, causation link, timestamp) so the decision and its evidence are reconstructable by correlation id (FR-013/FR-014, SC-006)

**Checkpoint**: Every resolved case emits exactly one `local.resolution.customer-resolution.decided.v1`
event on a durable, registered topic — replayable, carrying peer `task_id`/`result_event_id` references
in `evidence`, and minimized of raw customer content — superseding the base decision event; replays
never double-decide.

### Phase 23 dependencies

- **Foundational T204–T222** block everything in this phase. T218 → T219 (validator on the new model);
  T218 ∥ T220 (different files); T221 needs T218+T220; T222 needs T220.
- **Case state T223** (records the source result `event_id`) blocks the AC2 evidence in T226; it extends
  the Phase 14 store (T092), the US3 result handler (T034), and the Phase 15/16 attach paths (T109/T123).
- **Tests T224/T225** (different files, `[P]`) are written first and must fail before T212–T229.
- **Impl**: T226 (pure builder) + T227 (minimization helper) → T228 (emit migration, supersedes
  T017/T034) → T229 (integration). T228 also requires the Phase 2 process/`Publisher` (T011), the
  Phase 18 decision engine / US3 decision path (T031/T034), and the direct_response branch (T018), and
  must precede the Phase 17 drafted emit (T138) and the Phase 20 closure emits.
- **T230** (audit) follows T228 and folds into the US4 audit step list (T037/T038).
- **Supersedes**: this phase retires the base `CustomerResponseDecisionPayload` / `TOPIC_RESOLUTION_DECIDED`
  decision event (T004–T007 contract/topic, T017/T034 emit) — when implementing, treat T204–T230 as the
  authoritative decision-event design.
- Reuses `001`/`002` transport, audit, idempotency, the Phase 14 store, and the deterministic decision
  policy (Phase 18 / US3) unchanged (FR-016, Principle V) — no new dependency, no second audit path.
