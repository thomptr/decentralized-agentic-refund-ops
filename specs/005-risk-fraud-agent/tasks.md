---
description: "Task list for Risk and Fraud Agent implementation"
---

# Tasks: Risk and Fraud Agent

**Input**: Design documents from `/specs/005-risk-fraud-agent/`

**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

**Tests**: Included. The feature spec and plan explicitly request a unit/contract/integration suite
(plan.md "Testing"; quickstart.md §A) and tie each Success Criterion to a named test, so test tasks
are first-class here and are written before the implementation they cover.

**Organization**: Tasks are grouped by user story (US1–US7 from spec.md) so each story can be
implemented and tested independently. Reused foundation/runtime/contract code (`001`/`002`/`003`/`004`)
is **not** re-created — tasks only add the agent-internal domain package and its AgentCore/HTTP shells.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which story the task serves (US1–US7, or **AC** = the AgentCore CLI operational story in Phase 10); omitted for Setup / Foundational / Polish
- Every task names an exact file path

## Path Conventions

Single Python project. Agent package: `apps/agents/risk_fraud/`. Co-located tests:
`apps/agents/risk_fraud/tests/`. Reused (unchanged): `src/agent_foundation/`, `packages/contracts/`,
`apps/agents/customer_resolution/`. Layout mirrors the shipped `apps/agents/billing_entitlement/` (004).

## Highlighted scope — A2A contract test suite (this `/speckit-tasks` run's focus)

This run adds a dedicated **A2A protocol-boundary contract suite** in the new file
`apps/agents/risk_fraud/tests/test_a2a_contract.py` (**Phase 12**, tasks **T042–T049**). It pins the
agent's externally observable A2A contract at the runtime boundary — capability advertisement,
capability routing/rejection, task lifecycle (`completed` / `failed` / `rejected` /
`duplicate_skipped`), result-contract conformance, and idempotency — **independently** of the full
`003`↔`005` flow that `test_risk_agent_e2e` (T039) covers. The seven requested scenarios map
one-to-one to **T043–T049** (T042 is the shared harness). Broker-dependent scenarios are marked
`integration` (testcontainers Kafka) and carry unit-level handler-direct stand-ins for CI, mirroring
the skip-plus-stand-in pattern in `apps/agents/billing_entitlement/tests/test_billing_agent_e2e.py`.

| # | Requested scenario | Task | Story | Asserted at |
|---|--------------------|------|-------|-------------|
| 1 | Agent Card exposes `assess_refund_risk` | **T043** | US1 | card advertises `assess_fraud_risk` (FR-018) |
| 2 | unknown capability is rejected | **T044** | US1 | runtime `rejected`, handler never runs (FR-016/FR-018) |
| 3 | invalid task input is rejected | **T045** | US4 | `TaskResult(status="failed")` + reason (FR-011) |
| 4 | valid task succeeds | **T046** | US1 | `TaskResult(status="completed")`, correlated by `task_id` (FR-002/FR-008) |
| 5 | result includes risk score and evidence | **T047** | US2 | data part: `confidence`/`score` in range + non-empty evidence (FR-005/FR-006) |
| 6 | Kafka `risk.review.completed` event is published | **T048** | US2 | one `RiskReviewCompletedPayload` on `TOPIC_RISK_RESULT` (FR-007/FR-008) |
| 7 | duplicate idempotency key does not reprocess | **T049** | US5 | redelivered `task_id` → one verdict, no 2nd event, `duplicate_skipped` (FR-013) |

**Capability-name reconciliation**: the request phrases scenario 1 as *"Agent Card exposes
`assess_refund_risk`"*. The shipped/discovered capability id is **`assess_fraud_risk`** (plan.md
§Capability-name note; the id `003` already discovers). **T043** therefore asserts the card advertises
`assess_fraud_risk` and treats `assess_refund_risk` as the descriptive intent of the same capability —
zero edits to feature 003 (SC-009).

## Highlighted scope — A2A capability handler `assess_fraud_risk` (a prior `/speckit-tasks` run's focus)

This run implements the **A2A capability handler** for the agent's one capability. The shipped id is
**`assess_fraud_risk`** (agent `risk-fraud-agent`); the request's `assess_refund_risk` phrasing is the
descriptive intent of the same fraud-risk-assessment capability — keeping `assess_fraud_risk` preserves
the **unchanged** 003 consumer and SC-009 (plan §Capability-name note; research R0). The handler is
already decomposed across the user-story phases below; the requested flow maps onto existing tasks:

| Flow step | Realized by |
|-----------|-------------|
| Validate request | `RiskAssessmentRequest` model **T009**; `service.assess` validation (raises `ValueError`) **T016** |
| Load risk profile | `mock_data.load_signals(customer_id)` **T011**, invoked in `service.assess` **T016** |
| Detect refund abuse | `scoring.assess_signals` FP-002 chargeback / FP-003 velocity **T015** |
| Analyze behavioral signals | `scoring.assess_signals` FP-004 instrument / FP-005 standing / FP-006 anomaly **T015** |
| Calculate risk score | additive score → threshold mapping (borderline → upper band) **T015** |
| Generate recommendation | `RiskAssessment` (`risk_level` + `requires_human_review` + confidence + evidence) **T015** |
| Return `A2ATaskResult` | handler returns `A2AMessage`; reused runtime wraps it as `TaskResult.output` **T017** |
| Publish `risk.review.completed` event | handler-owned `Publisher` → `TOPIC_RISK_RESULT` **T019/T020** |

**Acceptance criteria** (this run) → tasks:

1. **Valid A2A task succeeds** — US1 verdict path **T015–T017**; proven end-to-end in **T039**.
2. **Invalid task fails safely** — US4 uncertainty/failure paths **T023–T026** (signal-miss / contradiction
   → `requires_human_review` with reason; malformed input → structured `TaskResult(status="failed")`,
   no fabricated verdict), plus validation tests **T008/T024** (FR-010/FR-011).
3. **Kafka event published after completion** — US2 result-event mapping + publish **T018–T020**
   (exactly one `RiskReviewCompletedPayload` on `local.risk.review.completed.v1`, correlated to the case).
4. **A2A audit events emitted** — US6 **T029/T030** plus the **reused runtime's** automatic
   `accepted`/`completed`/`failed`/`rejected`/`duplicate_skipped` task-lifecycle audit (FR-014); the
   trail is reconstructed by correlation id in the e2e **T039** (no second audit path).

No new shared contract/topic/dependency is added — the agent reuses `RiskReviewCompletedPayload` /
`TOPIC_RISK_RESULT` and the runtime's idempotency + audit as-is (FR-017/FR-019; Principle V).

## Highlighted scope — AgentCore CLI project files (a prior `/speckit-tasks` run's focus)

This run adds the **AgentCore CLI project files** so the Risk Agent runs under `agentcore dev`, is
invocable from the AgentCore inspector UI, and delegates to the **same internal risk services**
(`service.assess`) the A2A/Kafka path uses. The work is the focal operational story in **Phase 10**
(tasks **T032–T038**), with acceptance criteria and an independent test stated inline there.

**Filename reconciliation**: the request listed example files `agentcore.yaml`, `requirements.txt`,
`README.md` under `apps/agents/risk_fraud/`. The repo's established convention (feature 004,
`apps/agents/billing_entitlement/`) and plan.md R9 instead use `agentcore/agentcore.json` +
`app/RiskFraud/pyproject.toml`. These tasks follow the **authoritative plan/004 convention** so
`agentcore dev` behaves identically to the working billing agent; the requested acceptance criteria are
fully met by that layout.

## Highlighted scope — Requested scoring unit tests (this run's focus)

This run pins the **scoring-engine unit tests** to the user-requested scenarios. Each maps to a
`poc-fraud-policy` rule/gate (`contracts/fraud-policy.md`) and an existing test task; the bulk land in
the US1 scoring test **T014** (truth table + single-signal matrix) and the US4 uncertainty test
**T023**. Two scenarios add **new** coverage (VIP/enterprise human-review, the score cap) plus the
offset case — folded into T014/T023/T025 below.

| Requested scenario | Policy / gate | Expected verdict | Task |
|--------------------|---------------|------------------|------|
| known good customer => low risk | all FP-002…FP-006 silent (`CUS-CLEAN`) | `low` (conf 0.9) | T014 |
| new account + high amount => medium/high risk | FP-005 (`tenure_days < 30`, `status != good`) | `elevated`/`high` | T014 |
| multiple recent refunds => medium/high risk | FP-003 refund-velocity (≥3 elevated, ≥5 high) | `elevated`/`high` | T013, T014 |
| prior chargeback => high / manual_review | FP-002 chargeback-history (1 elevated, ≥2 high) | `elevated`/`high` | T013, T014 |
| IP/device mismatch => elevated risk | FP-004 instrument-mismatch / card-testing | `elevated`/`high` | T013, T014 |
| missing profile => request_more_information | data-completeness gate (lookup miss) | `requires_human_review` (conf 0.2) | T023 |
| VIP/enterprise profile => manual_review | FP-005 standing tier → human-review path | `requires_human_review` | T023, T025 |
| known good customer offsets minor risk | FP-005 long-tenure `good` baseline `0.0` | stays `low` | T014 |
| score capped at 100 | additive score capped at `1.0` (engine units) | `high`, score == `1.0` | T013, T014 |

> **Units note**: the engine scores on a `0.0..1.0` scale (capped at `1.0`), not `0..100`. The "score
> capped at 100" scenario is implemented as the `1.0` cap assertion in T013/T014. A `0..100`
> presentation would be a display concern only and does not change the verdict.

## Highlighted scope — risk recommendation engine: action vocabulary (this run's input)

On top of the design's `risk_level` (`low`/`elevated`/`high`) + `requires_human_review` flag, the engine
derives an internal, **non-customer-facing** `recommended_action` per the requested rules. The published
`recommendation` **wire** field stays `risk_level.value` for the **unchanged** 003 consumer (SC-009 / R5);
`recommended_action` lives only in the domain `RiskAssessment` and is surfaced in evidence/reasoning,
never on the wire. Realized by **T006** (model field + enum), **T015** (derivation), asserted in **T014**
(mapping + acceptance) and the **T014a** no-customer-facing-language guard.

| Input condition | `risk_level` | `requires_human_review` | `recommended_action` |
|-----------------|--------------|--------------------------|----------------------|
| low risk (clean signals) | `low` | `False` | `approve_risk_clearance` |
| medium / elevated risk | `elevated` | `False` (unless a gate fires) | `allow_with_caution` |
| high risk | `high` | `False` (unless a gate fires) | `deny_or_escalate` |
| unknown / missing profile | n/a (review) | `True` | `request_more_information` or `manual_review` |
| prior chargeback present | `elevated`/`high` | `True` unless already `high` | `manual_review` or `deny_or_escalate` |
| VIP / enterprise customer | computed level | `True` | `manual_review` |

**Acceptance criteria (this run)** → tasks: (1) recommendation **includes confidence** — `RiskAssessment.confidence` (T006), set per-path in T015, asserted in T014; (2) recommendation **includes evidence** — non-empty `RiskAssessment.evidence` (T006), one item per fired rule (T015), asserted in T014; (3) recommendation **contains no customer-facing language** — `recommended_action` from the operational enum and `reasoning_summary`/evidence operational-only, guarded by **T014a**.

## Highlighted scope — A2A input model

The requesting peer (003) sends a `data` part validated by this agent (FR-002). The input model
`RiskAssessmentRequest` (alias for the requested `RefundRiskAssessmentRequest`) is defined in
`apps/agents/risk_fraud/models.py` and pinned by
`contracts/assess-fraud-risk.input.schema.json`:

| Field | Type | Rules |
|-------|------|-------|
| `case_id` | `UUID` | **required** — reject if missing; becomes the publish `correlation_id` |
| `ticket_id` | `str` | **required, non-empty** — reject if missing/blank |
| `customer_id` | `str` | **required, non-empty** — reject if missing/blank; primary signal-lookup key |
| `requested_refund_amount` | `Decimal \| None` | optional, `>= 0` when present |
| `customer_message_summary` | `str \| None` | optional context only; never overrides owned signals |
| `account_age_days` | `int \| None` | optional, `>= 0` when present (corroborates account-standing tenure) |
| `metadata` | `dict \| None` | optional passthrough context |

`model_config = ConfigDict(extra="ignore")` so the wire shape can evolve and **raw sensitive customer
text is not required** — only the structured fields above are. Validation failure → `ValueError`,
which the reused runtime turns into a structured A2A `TaskResult(status="failed")` (FR-011) plus a
`rejected`/`failed` audit event — never a fabricated verdict. Acceptance criteria for this model:
missing `case_id`/`ticket_id`/`customer_id` is rejected; invalid input returns a structured A2A error;
no raw sensitive customer text is required. Covered by **T009** (model), **T011** (validation), and the
TDD test **T008**.

---


## Highlighted scope — Idempotency behavior (this run's input)

This run sharpens **User Story 5** (Phase 7) into an explicit, independently testable idempotency
increment. It adds **no new contract, topic, or dependency**: idempotency is provided by the **reused
runtime's `task_id` `IdempotencyTracker`** (`src/agent_foundation/runtime/runtime.py:240-253` dedup +
`:307-311` mark-processed) plus this agent's **deterministic** signals→verdict mapping (FR-012). New
work is tasks **T081–T084** (folded into Phase 7); existing US5 tasks **T027** (determinism) / **T028**
(dedup reuse), the e2e **T039**, and the Phase-12 contract scenario **T049** are reused, not duplicated.

**Rules** (this run) → mechanism → tasks:

| Rule | Meaning here | Mechanism | Realized in | Tested in |
|------|--------------|-----------|-------------|-----------|
| **Same idempotency key returns same result** | The `task_id` is the idempotency key. A redelivered key never yields a second, possibly different verdict; and because `assess_signals` is deterministic (no clock/random), the logical result for that key is stable. | Runtime `tracker.is_duplicate(task_id)` short-circuit **before** the handler + deterministic scoring (T015). | T028, T083 | T027, T081, T049 |
| **Same `task_id` does not publish duplicate risk result events** | A redelivered `task_id` must NOT emit a second `RiskReviewCompletedPayload` on `local.risk.review.completed.v1`. | The domain publish (T020) lives **inside** the handler closure, which the runtime invokes **only after** the dedup check — so a duplicate `task_id` is skipped before any publish. | T083 | T081, T049 |
| **Repeated task with same `case_id` is safe** | A *distinct* `task_id` re-issued for the same `case_id` (a workflow retry) cannot corrupt the case: the verdict is identical (determinism) and the 003 consumer applies it at most once per case. | Deterministic verdict + `correlation_id=case_id` on the published event (T020/T030) + the 003 consumer's per-case `apply_result`/escalation/`DECIDED` guards (research R8). | T084 | T082, T039 |

**Acceptance criteria** (this run):

1. **Duplicate A2A requests do not duplicate side effects** — a redelivered `task_id` performs no second
   assessment, publishes no second `risk.review.completed` event, and emits no second `completed` audit;
   the redelivery is recorded as a single `duplicate_skipped` audit entry. Realized **T083**, asserted
   **T081** (and **T049**).
2. **Duplicate result events are prevented or marked idempotent** — the producer prevents a duplicate
   domain event for the same `task_id` (T083); for the same-`case_id`/different-`task_id` retry the
   consumer treats the second delivery as idempotent — one decision per case (research R8). Asserted
   **T081** (producer) and **T082/T039** (consumer/SC-009).
3. **Tests cover retries and duplicate task submission** — an integration test submits the identical
   `task_id` twice (**duplicate submission**) and a same-`case_id`/new-`task_id` **retry**; a unit test
   asserts verdict determinism across repeated evaluation. **T027** (determinism), **T081** (duplicate),
   **T082** (case-level retry), and **T039/T049** (e2e/contract) cover this.

---

## Highlighted scope — Risk Agent package layout (this `/speckit-tasks` run's focus)

This run requested a more granular package layout for `apps/agents/risk_fraud/`
(`config.py`, `agent.py`, `a2a_handlers.py`, `risk_data_store.py`, `risk_signal_analyzer.py`,
`refund_abuse_detector.py`, `risk_scoring_engine.py`, `recommendation_engine.py`, `agentcore_app.py`,
`models.py`, `tests/`). The existing tasks below already deliver this package — and all four acceptance
criteria — using the **authoritative plan.md §Project Structure / feature-004 module convention**. Per
the same reconciliation precedent used for the AgentCore filenames above, the requested filenames are
treated as the **descriptive intent of the same modules**; no tasks are rewritten. The mapping:

| Requested file | Existing module(s) | Task(s) |
|----------------|--------------------|---------|
| `models.py` | `models.py` (`RiskLevel`, `RecommendedAction`, owned-signal models, `RiskSignals`, `RiskAssessment`, `RiskAssessmentRequest`) | T004, T005, T006, T009 |
| `config.py` | `identity.py` (`AgentCard`/`Capability`) + `policy.py` (`poc-fraud-policy`, thresholds) | T007, T010 |
| `risk_data_store.py` | `mock_data.py` (`load_signals` over seeded owned signals) | T011 |
| `risk_signal_analyzer.py` | `scoring.py` — FP-001 known-fraud / FP-004 instrument / FP-005 standing / FP-006 anomaly | T015 |
| `refund_abuse_detector.py` | `scoring.py` — FP-002 chargeback / FP-003 velocity | T015 |
| `risk_scoring_engine.py` | `scoring.py` — additive score → threshold→level (borderline → upper band) | T015 |
| `recommendation_engine.py` | `scoring.py`/`service.py` — `RiskAssessment` (level + `recommended_action` + `requires_human_review` + confidence + evidence + policy refs) & result mapping | T015, T019 |
| `agent.py` | `service.py` — pure `assess` orchestration (validate → load → score) | T016, T019 |
| `a2a_handlers.py` | `main.py` — registered handler + handler-owned `Publisher` closure | T017, T020 |
| `main.py` | `main.py` — Kafka A2A entrypoint (replaces stub) | T017, T020 |
| `agentcore_app.py` | `app/RiskFraud/main.py` (`RiskFraudExecutor` + `serve_a2a`) + `http_app.py` | T033, T038 |
| `tests/` | `tests/` (unit/contract/integration + A2A contract suite) | T002, T008, T012–T014a, T018, T021, T023–T024, T027, T031–T032, T039, T042–T049 |

> If you prefer the literal granular filenames instead of the plan/004 modules, that is a plan change —
> re-run `/speckit-plan` to update §Project Structure, then `/speckit-tasks` to regenerate.

### Acceptance-criteria coverage (this run's four criteria → tasks)

| Acceptance criterion | Covered by |
|----------------------|------------|
| **Agent runs independently** | T016 (pure `service.assess`, no peer call) + T017 (`main.py` Kafka A2A entrypoint via reused `AgentRuntime`/`run_agent`) + T041 (run validation) |
| **Agent exposes an A2A endpoint** | T010 (card advertises `assess_fraud_risk`, FR-018) + T017/T020 (Kafka A2A `TaskRequest`→`TaskResult`) + Phase 12 contract suite T043–T049; standalone A2A via T033/T038 |
| **Startable through AgentCore local dev** | Phase 10 (story AC) T033 (`RiskFraudExecutor`/`serve_a2a`), T035 (`agentcore.json`), T036/T037 (targets + run guide), T032 (entrypoint test); `agentcore dev` + inspector |
| **No Billing or Customer Resolution logic** | T021/T022 (US3 domain-isolation: evidence only from owned signals/policy, no foreign field/peer call, SC-003/FR-009) + T031 (no supervisor/dispatch) + T040 (zero edits to `customer_resolution`) |

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Expand the single-file stub into the domain package skeleton and test scaffold.

- [X] T001 Expand `apps/agents/risk_fraud/` from the two-file stub into the package layout from plan.md §Project Structure: keep `__init__.py`, plan for `identity.py`, `models.py`, `mock_data.py`, `policy.py`, `scoring.py`, `service.py`, `main.py`, `http_app.py`, `dev_a2a_client.py` (created in later phases). Do not yet delete the stub body of `main.py`.
- [X] T002 [P] Create the test package `apps/agents/risk_fraud/tests/__init__.py` and `apps/agents/risk_fraud/tests/conftest.py` mirroring `apps/agents/billing_entitlement/tests/conftest.py` (shared fixtures: sample `TaskRequest`/input builders, `BROKER_URL`, testcontainers Kafka fixture reused from 004).
- [X] T003 [P] Add the `demo-risk-fraud` run entry and confirm `bedrock-agentcore[a2a]`, `a2a-sdk[all]`, `fastapi`/`uvicorn` (the `[http]` extra) are already declared (introduced by 004) — **no new dependency** is added; record this in `apps/agents/risk_fraud/agentcore/README.md` (created in T028).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Domain models, policy, identity/card, and mock data that **every** user story depends on.

**⚠️ CRITICAL**: No user-story phase can begin until this phase is complete.

- [X] T004 [P] Define `RiskLevel` StrEnum (`LOW="low"`, `ELEVATED="elevated"`, `HIGH="high"`) in `apps/agents/risk_fraud/models.py` (data-model §4; FR-004).
- [X] T005 [P] Define the five frozen owned-signal models — `AccountStanding`, `RefundDisputeHistory`, `PaymentInstrumentSignal`, `BehavioralSignal`, `KnownFraudIndicator` — and the aggregate `RiskSignals` (all fields `| None`) in `apps/agents/risk_fraud/models.py` per data-model §2 (FR-003).
- [X] T006 [P] Define the `RiskAssessment` output model (`risk_level`, `recommended_action`, `confidence` 0..1, non-empty `evidence: list[EvidenceItem]`, `policy_references: list[str]`, non-empty `reasoning_summary`, `requires_human_review`) plus the `RecommendedAction` StrEnum (`approve_risk_clearance`, `allow_with_caution`, `deny_or_escalate`, `request_more_information`, `manual_review`) in `apps/agents/risk_fraud/models.py`, importing `EvidenceItem` unchanged from `packages/contracts`. `recommended_action` is an internal, non-customer-facing field — it is NOT added to the published wire payload (the `recommendation` wire field stays `risk_level.value`, SC-009/R5) (data-model §4; FR-005/FR-006).
- [X] T007 [P] Define the named, citable fraud policy in `apps/agents/risk_fraud/policy.py`: `PolicyRule` + `FraudPolicy` (`poc-fraud-policy` v1.0.0) with rule ids `FP-001..FP-006`, and the threshold constants (`ELEVATED_THRESHOLD=0.5`, `HIGH_THRESHOLD=0.8`, `CHARGEBACK_ELEVATED/HIGH`, `VELOCITY_ELEVATED/HIGH`, `ANOMALY_ELEVATED`, `NEW_ACCOUNT_DAYS`) per data-model §3 and `contracts/fraud-policy.md` (FR-012).
- [X] T008 [P] [US1] **TDD** Write `apps/agents/risk_fraud/tests/test_input_validation.py` (failing first): valid input parses; missing `case_id`, `ticket_id`, or `customer_id` raises `ValueError`; blank `ticket_id`/`customer_id` rejected; unknown/raw-text fields are ignored (no `customer_message_summary` required); negative `requested_refund_amount`/`account_age_days` rejected. Asserts the acceptance criteria for the highlighted input model (FR-002/FR-011).
- [X] T009 [US1] Implement the `RiskAssessmentRequest` input model (aliasing the requested `RefundRiskAssessmentRequest`) in `apps/agents/risk_fraud/models.py` with `ConfigDict(extra="ignore")`, required `case_id: UUID` / `ticket_id` / `customer_id` (non-empty), optional `requested_refund_amount: Decimal | None (>=0)`, `customer_message_summary: str | None`, `account_age_days: int | None (>=0)`, `metadata: dict | None`; make T008 pass. Conforms to `contracts/assess-fraud-risk.input.schema.json`.
- [X] T010 [P] Implement the shared agent identity and `AgentCard` advertising the single `assess_fraud_risk` capability (agent id `risk-fraud-agent`) in `apps/agents/risk_fraud/identity.py`, reusing `AgentCard`/`Capability` from `agent_foundation.runtime` (FR-001/FR-002/FR-018).
- [X] T011 [P] Seed the owned-signal fixture dataset and `load_signals(customer_id) -> RiskSignals | None` in `apps/agents/risk_fraud/mock_data.py` per `contracts/mock-risk-data.md`: include clean, chargeback, high-velocity, instrument-mismatch, anomalous, and blocklist customers, plus an unknown-customer miss → `None` (FR-003/FR-010).

**Checkpoint**: Domain models, policy, identity/card, and signal lookup exist and are import-clean. User stories can now proceed.

---

## Phase 3: User Story 1 - Assess Fraud Risk on a Peer Request (Priority: P1) 🎯 MVP

**Goal**: Accept an `assess_fraud_risk` `TaskRequest`, validate its structured input, load owned signals, score a deterministic risk level, and return it correlated to the request.

**Independent Test**: Send a request for a clearly risky customer → `elevated`/`high`; send a clean customer → `low`; each correlated to the originating request (quickstart §A `test_scoring`, §B step 1).

### Tests for User Story 1

- [X] T012 [P] [US1] **TDD** Write `apps/agents/risk_fraud/tests/test_mock_data.py` (failing first): `load_signals` returns seeded signals for known customers and `None` for an unknown `customer_id` (FR-003/FR-010).
- [X] T013 [P] [US1] **TDD** Write `apps/agents/risk_fraud/tests/test_fraud_policy.py` (failing first): each `FP-001..FP-006` rule fires on its triggering signal; a borderline value exactly on a threshold resolves to the documented upper band (spec Edge Cases; FR-012).
- [X] T014 [P] [US1] **TDD** Write `apps/agents/risk_fraud/tests/test_scoring.py` (failing first) with one named test per requested scenario: **known good customer => low** (`CUS-CLEAN` → `low`, conf `0.9`, ≥1 `fraud_policy` evidence that no rule fired); **new account + high amount => medium/high** (`CUS-NEW-ACCOUNT`, FP-005); **multiple recent refunds => medium/high** (velocity ≥3 `elevated`, ≥5 `high`, FP-003); **prior chargeback => high/manual_review** (1 `elevated`, ≥2 `high`, FP-002); **IP/device mismatch => elevated** (`billing_details_match=False` / `card_testing_pattern=True`, FP-004); **known good offsets minor risk** (long-tenure `good` `0.0` baseline keeps a single minor signal `< ELEVATED_THRESHOLD` at `low`); **score capped at `1.0`** (summed contributions >1.0 clamp to exactly `1.0` → `high`; the requested "capped at 100" in engine units). Plus the full `low/elevated/high` truth table, the **single-signal matrix** (SC-004) shifting the level in the documented direction with the change cited, `CUS-BLOCKLIST` forcing `high` (FP-001 floor, conf `0.95`), and `CUS-BORDERLINE` exactly `0.5`→`elevated` / `0.8`→`high` (upper band, conf `0.6`). Also assert the **recommendation-action mapping**: `low→approve_risk_clearance`, `elevated→allow_with_caution`, `high→deny_or_escalate`, prior-chargeback→`manual_review` (or `deny_or_escalate` when `high`); and the two **command acceptance criteria** that hold for every verdict — `confidence` is present and within `0.0..1.0`, and `evidence` is non-empty.
- [X] T014a [P] [US1] **TDD** Add a no-customer-facing-language guard to `apps/agents/risk_fraud/tests/test_scoring.py`: assert `recommended_action` is always a member of the operational `RecommendedAction` enum and that `reasoning_summary` and every `evidence[].description` use operational phrasing only (no customer-addressed language — e.g. no "you"/"your"/"dear"/apology), satisfying the command acceptance criterion "recommendation does not include customer-facing language".

### Implementation for User Story 1

- [X] T015 [US1] Implement the deterministic rules engine `assess_signals(signals, request) -> RiskAssessment` in `apps/agents/risk_fraud/scoring.py`: apply `FP-001..FP-006` against `RiskSignals`, compute the score, map to `RiskLevel` by thresholds (borderline → upper band), build the `EvidenceItem` set (each tagged with an owned `source` or `fraud_policy`), populate `policy_references`, confidence, and `reasoning_summary`; **derive `recommended_action`** per the action-vocabulary table (`low→approve_risk_clearance`, `elevated→allow_with_caution`, `high→deny_or_escalate`, missing/uncertain→`request_more_information`/`manual_review`, prior-chargeback→`manual_review`/`deny_or_escalate`, VIP/enterprise→`manual_review`) using operational, non-customer-facing language only; make T013/T014/T014a pass (FR-004/FR-005/FR-006/FR-012).
- [X] T016 [US1] Implement the pure orchestration `assess(raw_input) -> (RiskAssessment, RiskAssessmentRequest)` in `apps/agents/risk_fraud/service.py`: validate input (T009) → `load_signals` (T011) → `assess_signals` (T015); raise `ValueError` on invalid input. No Kafka, no I/O (enables AgentCore reuse). Make T012 pass.
- [X] T017 [US1] Replace the stub body of `apps/agents/risk_fraud/main.py` with the real Kafka A2A entrypoint: register a handler that calls `service.assess`, returns an `A2AMessage` data part carrying `recommendation`/`confidence`/`evidence`/`reasoning_summary`/`requires_human_review`/`policy_references`, and serve via the reused `AgentRuntime` with the T010 card (FR-002/FR-008 A2A path). Result-event publishing is added in US2.

**Checkpoint**: The agent stands up, validates input, and returns a correlated risk level over A2A. MVP is demonstrable.

---

## Phase 4: User Story 2 - Publish a Structured Risk Result Event (Priority: P1)

**Goal**: On each completed assessment, publish exactly one `RiskReviewCompletedPayload` to `TOPIC_RISK_RESULT` (the reused contract/topic) carrying level, confidence, evidence, policy references, reasoning, and the human-review flag — the second of the dual delivery paths.

**Independent Test**: Drive one assessment and confirm exactly one result event on `local.risk.review.completed.v1` with level, in-range confidence, non-empty evidence, ≥1 `fraud_policy` evidence item, reasoning summary, and human-review flag — correlated to the case (quickstart §B step 2).

### Tests for User Story 2

- [X] T018 [P] [US2] **TDD** Write `apps/agents/risk_fraud/tests/test_result_contract.py` (failing first): `RiskReviewCompletedPayload` round-trips, is present in `PAYLOAD_REGISTRY[TOPIC_RISK_RESULT]`, the mapping from `RiskAssessment` populates every field, at least one `EvidenceItem` has `source="fraud_policy"` (the policy reference), and the A2A output data part matches the shape `003`'s `normalize_risk_result` consumes (SC-002/SC-009).

### Implementation for User Story 2

- [X] T019 [US2] Add a `to_result_payload(assessment, request) -> RiskReviewCompletedPayload` mapper in `apps/agents/risk_fraud/service.py` per `contracts/risk-result-contract.md` (`recommendation=risk_level.value`, policy refs surfaced as `fraud_policy` evidence items); make T018 pass (FR-007/FR-019).
- [X] T020 [US2] Wire the handler-owned `Publisher` in `apps/agents/risk_fraud/main.py`: open `async with Publisher(identity, BROKER_URL)` in the async entrypoint, capture it in the handler closure, and publish the payload to `TOPIC_RISK_RESULT` with `correlation_id = request.case_id` and `causation_id = task_id` (research R2; FR-008 domain-event path).

**Checkpoint**: Each assessment is delivered on both paths — A2A `TaskResult` and the published domain event.

---

## Phase 5: User Story 3 - Ground Every Assessment in Owned Signals (Priority: P1)

**Goal**: Guarantee every risk level and evidence item traces to one of the five owned signal domains or the fraud policy — never billing/customer-resolution data — and that no peer is called for facts.

**Independent Test**: Vary one signal at a time and confirm the level changes accordingly; confirm every evidence `source` ∈ the owned set and no synchronous peer call is made (quickstart §A `test_domain_isolation`).

### Tests for User Story 3

- [X] T021 [P] [US3] **TDD** Write `apps/agents/risk_fraud/tests/test_domain_isolation.py` (failing first): every `EvidenceItem.source` ∈ `{account_standing, refund_history, payment_instrument, behavioral, known_fraud, fraud_policy}`; the verdict reads no billing/foreign field; the service issues no peer/network call (assert no runtime client is constructed) (SC-003/FR-009).

### Implementation for User Story 3

- [X] T022 [US3] Enforce sourcing in `apps/agents/risk_fraud/scoring.py`: constrain every emitted `EvidenceItem.source` to the owned-signal/policy set and ensure `customer_message_summary`/`metadata` are treated as non-authoritative context that never overrides owned signals; make T021 pass (FR-003/FR-009/SC-003).

**Checkpoint**: Domain ownership is provable; verdicts are fully traceable to owned signals and policy.

---

## Phase 6: User Story 4 - Handle Cases It Cannot Confidently Decide (Priority: P2)

**Goal**: Missing, contradictory, or no-applicable-rule cases flag `requires_human_review` with a recorded reason (never a fabricated level); malformed input returns a structured A2A failure result.

**Independent Test**: Send missing/contradictory-signal cases → human-review flag + reason (no confident level); send malformed input → `failed` result with reason; a well-formed case still returns a normal level (quickstart §A/§B; FR-010/FR-011).

### Tests for User Story 4

- [X] T023 [P] [US4] **TDD** Extend `apps/agents/risk_fraud/tests/test_scoring.py` (failing first) with named tests: **missing profile => request_more_information** — unknown `customer_id` (signal miss) → `requires_human_review=True`, confidence `0.2`, recorded missing-data reason, no fabricated level; **VIP/enterprise profile => manual_review** — a VIP/enterprise account-standing tier routes to `requires_human_review=True` with a "manual review" reason rather than an auto clear/deny; **contradictory signals** (`CUS-CONTRADICTION`) → `elevated`, lowered confidence `0.3`, `requires_human_review`, conflict in evidence/reasoning; **no-applicable-rule** → defined human-review default stance (FR-010; SC-005).
- [X] T024 [P] [US4] **TDD** Add a malformed-input case to `apps/agents/risk_fraud/tests/test_input_validation.py` asserting the runtime surfaces a structured `TaskResult(status="failed")` with a reason rather than a verdict (FR-011).

### Implementation for User Story 4

- [X] T025 [US4] Implement the uncertainty paths in `apps/agents/risk_fraud/scoring.py` / `service.py`: signal-miss → human-review assessment with reason (conf `0.2`); a VIP/enterprise account-standing tier → human-review with a "manual review" reason (extend the FP-005 standing logic in `policy.py` and add the VIP/enterprise seed to `mock_data.py`); contradiction detection → lowered confidence (`0.3`) + `requires_human_review` + conflict captured in evidence/reasoning; no-applicable-rule default stance; make T023 pass (FR-010; spec Edge Cases).
- [X] T026 [US4] Confirm and (if needed) adjust `apps/agents/risk_fraud/main.py` so a `ValueError` from `service.assess` propagates to the reused runtime as `TaskResult(status="failed")` with the reason, leaving no published domain event; make T024 pass (FR-011).

**Checkpoint**: Uncertainty surfaces honestly; the agent never fabricates a verdict.

---

## Phase 7: User Story 5 - Idempotent, Repeatable Assessment (Priority: P2)

**Goal**: A redelivered request (same `task_id`) yields one logical verdict and no duplicate result event; identical signals + policy are deterministic.

**Independent Test**: Deliver the same `TaskRequest` twice → one logical verdict, no second event, duplicate audited `duplicate_skipped`; same signals → same verdict (quickstart §B step 4; SC-006).

### Tests for User Story 5

- [X] T027 [P] [US5] **TDD** Add a determinism assertion to `apps/agents/risk_fraud/tests/test_scoring.py` (failing first): `assess_signals` called twice on identical signals returns an identical `RiskAssessment` (FR-012/SC-006). (Redelivery dedup is verified end-to-end in T039; it is provided by the reused runtime `IdempotencyTracker` and needs no agent code.)

### Implementation for User Story 5

- [X] T028 [US5] Verify (no new mechanism) that `apps/agents/risk_fraud/main.py` serves through the reused `AgentRuntime` so `task_id` dedup short-circuits a redelivered request **before** the handler runs (no second assessment, no duplicate publish); document this reuse in `apps/agents/risk_fraud/agentcore/README.md` (FR-013; research R7).

### Idempotency behavior — this run's tasks (rules + acceptance criteria above)

- [X] T081 [P] [US5] **TDD** Write `apps/agents/risk_fraud/tests/test_idempotency.py` (testcontainers Kafka; mark `integration` and gate behind the live-broker skip/stand-in pattern from `apps/agents/billing_entitlement/tests/test_billing_agent_e2e.py`): **(duplicate submission)** deliver the identical `assess_fraud_risk` `TaskRequest` (same `task_id`) twice and assert exactly **one** `RiskReviewCompletedPayload` on `local.risk.review.completed.v1`, exactly **one** `completed` task-audit, exactly **one** `duplicate_skipped` audit for the replay, and **no** second `service.assess` side effect (acceptance 1 & 2, producer side); **(retry)** deliver the **same `case_id` under a fresh `task_id`** and assert the published `recommendation`/`risk_level`/`confidence`/`evidence` are **identical** (acceptance 3, retry). Fails until T083/T084 (FR-013/SC-006).
- [X] T082 [P] [US5] Extend the end-to-end `apps/agents/risk_fraud/tests/test_risk_agent_e2e.py` (T039) with a **case-level idempotency** assertion: replay one `case_id` (same `task_id`, then again under a new `task_id`) against the **unchanged** 003 Customer Resolution Agent and assert it still emits **exactly one** decision per case (research R8) — same-`case_id` safety together with SC-009 (acceptance 2, consumer side).
- [X] T083 [US5] **Producer idempotency placement** — verify in `apps/agents/risk_fraud/main.py` that the domain-result publish (T020) sits **inside** the handler closure, so the runtime's `tracker.is_duplicate(task_id)` short-circuit (`src/agent_foundation/runtime/runtime.py:240-253`) skips a redelivered `task_id` **before** the handler runs (no second `service.assess`, no second `TOPIC_RISK_RESULT` publish, no second `completed` audit; one `duplicate_skipped`). **No runtime/library change** — confirm placement, add a code comment marking the publish as inside the deduped path, and document the at-least-once crash-window gap between publish and `mark_processed` per research R7 (PoC-acceptable). Makes T081 pass (Rules 1–2; acceptance 1–2).
- [X] T084 [US5] **Case-level retry safety** — confirm the published event sets `correlation_id=request.case_id` (T020/T030) so a same-`case_id` retry under a new `task_id` carries the correlation the 003 consumer keys on, and that the verdict is identical via determinism (T015/T027). Document in the `main.py` handler docstring that case-level idempotency for distinct-`task_id` retries rests on the deterministic verdict + the 003 consumer's per-case `apply_result`/escalation/`DECIDED` guards (research R8) — the agent adds **no** per-`case_id` store. Makes T082 pass (Rule 3; acceptance 2, consumer side).

**Checkpoint**: Verdicts are stable and replay-safe; duplicate submissions and same-`case_id` retries add no second side effect or event (T081–T084).

---

## Phase 8: User Story 6 - Audit Every Assessment (Priority: P2)

**Goal**: Every step — received, decision (with evidence + policy refs), published, and any failure/human-review — leaves a correlated audit trail queryable by case correlation id.

**Independent Test**: Drive an assessment, then `query_by_correlation(case_id)` returns received → assessed → published in causal order, attributed to `risk-fraud-agent` (quickstart §B step 3; SC-007).

### Implementation for User Story 6

- [X] T029 [US6] Add `structlog` per-step logging in `apps/agents/risk_fraud/main.py` and `service.py`: request-received, decision (risk level + evidence + policy refs), result-published, and failure/human-review reason — relying on the reused runtime for the `accepted`/`completed`/`failed`/`rejected`/`duplicate_skipped` task-lifecycle audit events (FR-014; no second audit path).
- [X] T030 [US6] Confirm the published domain event and audit carry `correlation_id=case_id`/`causation_id=task_id` so `audit/store.py:query_by_correlation` reconstructs the trail; assert in T039 (FR-015/SC-007).

**Checkpoint**: Any verdict is reconstructable from the audit trail by correlation id.

---

## Phase 9: User Story 7 - Stay an Independent Domain Agent (Priority: P3)

**Goal**: Confirm the agent only responds to requests addressed to it, originates no task requests, and dispatches no work for others.

**Independent Test**: Inspect interactions across requests — every action is a fraud-risk assessment in response to an addressed request; no task origination, no routing (quickstart §A `test_no_supervisor`; SC-008).

### Tests for User Story 7

- [X] T031 [P] [US7] **TDD** Write `apps/agents/risk_fraud/tests/test_no_supervisor.py`: the agent constructs no peer/runtime **client**, calls no `send`/`request` to another endpoint, and registers only the inbound handler — originates no `TaskRequest` and dispatches no work (SC-008/FR-016).

**Checkpoint**: Decentralization guarantee is proven; no hidden hub-and-spoke coupling.

---

## Phase 10: AgentCore CLI Project Files & Local-Dev Parity (Operational Story: AC) 🖥️

**Goal**: Add the AgentCore CLI project files and Risk-Agent-specific config so the agent runs under
`agentcore dev`, is invocable from the AgentCore inspector UI, and delegates to the **same internal
risk services** (`service.assess`) the A2A/Kafka path uses. Mirrors feature 004
(`apps/agents/billing_entitlement/`); plan §Architecture Decision: AgentCore Parity; research R9. The
standalone AgentCore/HTTP path does **not** publish the Kafka result event (that stays the Kafka
entrypoint's job, US2).

**Independent Test**: From `apps/agents/risk_fraud/`, `agentcore dev` builds the dev venv and serves
the local A2A card + protocol; invoking a structured risk request in the inspector returns
`{recommendation, confidence, evidence, reasoning_summary, requires_human_review, policy_references}`,
and the returned verdict equals what `service.assess` yields for the same input.

**Acceptance criteria** (from the feature request):
1. `agentcore dev` can run the Risk Agent locally.
2. The AgentCore UI (inspector) can invoke the local agent.
3. The AgentCore entrypoint delegates to the **same** internal risk services (`service.assess`) used by the A2A path.

**README acceptance criteria** (this `/speckit-tasks` run's focus — all on `apps/agents/risk_fraud/agentcore/README.md`, realized by **T037**):
4. The README explains how to **launch the local AgentCore UI / terminal UI** (`cd apps/agents/risk_fraud` → `agentcore dev` → inspector).
5. The README explains how to **run local A2A mode separately** — the Kafka peer entrypoint `demo-risk-fraud` (and the CLI-free `http_app`), run independently of `agentcore dev`.
6. The README **clarifies that AgentCore invocation is for local testing/demo, while A2A is for peer-agent collaboration** — `agentcore dev` is standalone and does **not** publish the Kafka result event, whereas the A2A/Kafka peer path is the collaboration path in the three-agent demo.

> Depends only on US1 (`service.assess`) — independent of US2/US5/US6, so the whole phase runs in parallel with the Kafka transport stories.

### Tests for the AgentCore Story

- [X] T032 [P] [AC] **TDD** Write `apps/agents/risk_fraud/tests/test_http_entrypoint.py` (failing first): the A2A surface serves the agent card advertising `assess_fraud_risk`; a valid task returns the verdict data part; bad input returns a structured failure; and for the same input the entrypoint's verdict **equals** `service.assess` output (delegation proof — acceptance #3) (R9).

### Implementation — AgentCore CLI project files & config

- [X] T033 [AC] Create the AgentCore A2A code package `apps/agents/risk_fraud/app/RiskFraud/main.py`: a `RiskFraudExecutor` whose `execute` adapts the AgentCore/`a2a-sdk` request into `RiskAssessmentRequest` and calls **`service.assess` unchanged**, then `serve_a2a(RiskFraudExecutor(), CARD)` using the shared `CARD` from `identity.py`; put the monorepo (`apps/`, `packages/`, `src/`) on `sys.path` from source. Mirrors `apps/agents/billing_entitlement/app/BillingEntitlement/main.py` (satisfies acceptance #2 and #3; R9).
- [X] T034 [P] [AC] Add the dev-venv dependency manifest `apps/agents/risk_fraud/app/RiskFraud/pyproject.toml` (the requested "requirements" file, repo convention) declaring `bedrock-agentcore[a2a]`, `a2a-sdk[all]`, `pydantic`, `structlog` — all already introduced by 004, **no new repo dependency** — plus `apps/agents/risk_fraud/app/RiskFraud/README.md`, mirroring the 004 code package.
- [X] T035 [AC] Create the Risk-Agent AgentCore CLI config folder `apps/agents/risk_fraud/agentcore/` with `agentcore.json` (the requested "agentcore" config, repo convention): project + A2A runtime config, entrypoint `app/RiskFraud/main.py`, agent id `risk-fraud-agent`, capability `assess_fraud_risk`, modeled on `apps/agents/billing_entitlement/agentcore/agentcore.json` (satisfies acceptance #1; R9).
- [X] T036 [P] [AC] Add `apps/agents/risk_fraud/agentcore/aws-targets.json` (deploy-targets array; account/region — `agentcore deploy` is a documented future target, not built) and document `.env.local` (gitignored) usage, mirroring the 004 `agentcore/` files (R9).
- [X] T037 [P] [AC] Write the AgentCore run guide `apps/agents/risk_fraud/agentcore/README.md` (the requested README), mirroring `apps/agents/billing_entitlement/agentcore/README.md` and `quickstart.md` §C, with three explicit sections satisfying README acceptance criteria #4–#6: (a) **"Running locally — launch the AgentCore UI / terminal UI"**: the project-root caveat, `agentcore validate` / `agentcore dev` (build dev venv → start local A2A server → open inspector; `-p`/`--logs`) and the sample structured `agentcore dev '{...CUS-BLOCKLIST...}'` invoke with its expected verdict artifact (criterion #4); (b) **"Run local A2A mode separately"**: the Kafka peer entrypoint `demo-risk-fraud` (`python -m apps.agents.risk_fraud.main`) and the CLI-free FastAPI surface (`http_app` + `dev_a2a_client`), both run independently of `agentcore dev` (criterion #5); (c) **"AgentCore vs A2A — which to use"**: a callout/table stating `agentcore dev` is for **local testing/demo** (standalone; does **not** publish the `risk.review.completed` Kafka event) while the **A2A/Kafka peer entrypoint** is for **peer-agent collaboration** in the three-agent demo, plus a "Note on A2A" distinguishing AgentCore's `a2a-sdk` wire protocol from the repo's feature-002 A2A-over-Kafka runtime (criterion #6). Supports acceptance #1/#2.
- [X] T038 [P] [AC] Add the CLI-free standalone FastAPI surface `apps/agents/risk_fraud/http_app.py` (`GET /.well-known/agent.json`, `POST /a2a/tasks`, `GET /ping`, delegating to `service.assess`) and the dev helper `apps/agents/risk_fraud/dev_a2a_client.py` (GET the card + POST sample tasks), mirroring the 004 equivalents (R9; quickstart §C). Make T032 pass.

**Checkpoint**: `agentcore dev` runs the Risk Agent locally, the inspector can invoke it, and both the AgentCore and A2A paths share `service.assess` (acceptance #1–#3); and `agentcore/README.md` documents launching the AgentCore UI, running local A2A mode separately, and the AgentCore-for-testing vs A2A-for-collaboration distinction (acceptance #4–#6).

---

## Phase 11: Polish & Cross-Cutting Concerns

**Purpose**: End-to-end proof, consumer-compatibility guarantee, and validation cleanup.

- [ ] T039 [US2] Write the end-to-end `apps/agents/risk_fraud/tests/test_risk_agent_e2e.py` (testcontainers Kafka): A2A request → correlated `TaskResult` + exactly one `RiskReviewCompletedPayload` on `TOPIC_RISK_RESULT` + audit trail; missing/contradictory → human review; malformed → `failed`; idempotent redelivery (one verdict, `duplicate_skipped`); and the **003↔005** path proving the unchanged Customer Resolution Agent consumes the real verdict (SC-006/SC-007/SC-009).
- [X] T040 [P] Confirm zero edits to `apps/agents/customer_resolution/` and `packages/contracts/` and `src/agent_foundation/` — no new topic, contract, or dependency (FR-017/FR-019; Principle V); note any incidental diffs.
- [X] T041 [P] Run `pytest apps/agents/risk_fraud/tests -q` and the quickstart §A/§B/§C steps; fix any gaps and record results against the quickstart Success-criteria-mapping table.

---

## Phase 12: A2A Contract Test Suite (this run's focus) 🔌

**Goal**: Pin the agent's A2A protocol-boundary contract in one dedicated file
`apps/agents/risk_fraud/tests/test_a2a_contract.py` — capability advertisement, capability
routing/rejection, task lifecycle, result-contract conformance, and idempotency — over the **reused**
`AgentRuntime` (no new transport/audit/idempotency mechanism). The seven requested scenarios map to
T043–T049; T042 is the shared harness. Broker-dependent scenarios (T044/T048/T049) are marked
`integration` (testcontainers Kafka) with unit-level handler-direct stand-ins for CI.

**Independent Test**: `pytest apps/agents/risk_fraud/tests/test_a2a_contract.py -q` proves the card
advertises `assess_fraud_risk`, an unknown capability is rejected, invalid input fails safely, a valid
task completes, the verdict carries a risk score + non-empty evidence, exactly one
`risk.review.completed` event is published, and a redelivered `task_id` is not reprocessed.

> All of T043–T049 add tests to the **same** new file `test_a2a_contract.py`, so they are authored
> sequentially (not `[P]` with one another) after the shared harness T042. T043 (card) and T045/T046
> (lifecycle) have unit stand-ins runnable without a broker; T044/T048/T049 require the testcontainers
> Kafka runtime. This phase depends on the implementation it pins: US1 (T015–T017), US2 (T019–T020),
> US4 (T025–T026), US5 (T028).

### Harness

- [X] T042 [P] Add A2A-contract fixtures to `apps/agents/risk_fraud/tests/conftest.py`: a
  `make_task_request(capability_id, data)` builder producing a valid A2A `TaskRequest` envelope
  addressed to `endpoint_topic("risk-fraud-agent")`; a `served_risk_agent` fixture that registers the
  real handler from `apps/agents/risk_fraud/main.py` on the reused `AgentRuntime` with the T010 card;
  and a `risk_result_consumer` helper that reads `TOPIC_RISK_RESULT`. Reuse the testcontainers Kafka
  fixture from 004 and gate broker-dependent fixtures behind `pytest.mark.integration`.

### Contract scenarios (same file `apps/agents/risk_fraud/tests/test_a2a_contract.py`)

- [X] T043 [US1] **Agent Card exposes `assess_fraud_risk`** — in `apps/agents/risk_fraud/tests/test_a2a_contract.py`, assert `identity.CARD` (the card the runtime publishes on `TOPIC_AGENT_CARD`) advertises exactly one `Capability` with id `assess_fraud_risk`, agent id `risk-fraud-agent`; document `assess_refund_risk` as the descriptive intent of the same capability. Pure (no broker) (FR-018/FR-002).
- [X] T044 [US1] **Unknown capability is rejected** — in `apps/agents/risk_fraud/tests/test_a2a_contract.py`, send a `TaskRequest` whose capability id is not `assess_fraud_risk` to the agent endpoint and assert the reused runtime emits a `rejected` outcome (no `completed`, handler never invoked, no domain event on `TOPIC_RISK_RESULT`). `integration`; unit stand-in asserts the runtime's capability guard rejects the unsupported id (FR-016/FR-018).
- [X] T045 [US4] **Invalid task input is rejected** — in `apps/agents/risk_fraud/tests/test_a2a_contract.py`, send a `TaskRequest` with a malformed/missing `data` part (missing `case_id`/`ticket_id`/`customer_id`) and assert a structured `TaskResult(status="failed")` with a reason and **no** fabricated verdict and **no** published event. Unit stand-in via `service.assess` raising `ValueError`; `integration` for the surfaced failed result (FR-011).
- [X] T046 [US1] **Valid task succeeds** — in `apps/agents/risk_fraud/tests/test_a2a_contract.py`, send a well-formed `assess_fraud_risk` `TaskRequest` for a seeded customer and assert a `TaskResult(status="completed")` whose A2A output data part carries `recommendation` ∈ `{low, elevated, high}`, correlated to the request by `task_id` (FR-002/FR-008).
- [X] T047 [US2] **Result includes risk score and evidence** — in `apps/agents/risk_fraud/tests/test_a2a_contract.py`, assert the completed result's data part carries a numeric `confidence` (and stub-compatible `score`) within `0.0..1.0` and a **non-empty** `evidence` list with ≥1 item whose `source="fraud_policy"`, matching `RiskReviewCompletedPayload` fields (FR-005/FR-006/SC-002).
- [X] T048 [US2] **Kafka `risk.review.completed` event is published** — in `apps/agents/risk_fraud/tests/test_a2a_contract.py`, drive one assessment and assert exactly one `RiskReviewCompletedPayload` lands on `TOPIC_RISK_RESULT` (`local.risk.review.completed.v1`) with `correlation_id == case_id` and `causation_id == task_id`. `integration` (testcontainers Kafka) (FR-007/FR-008/SC-002).
- [X] T049 [US5] **Duplicate idempotency key does not reprocess** — in `apps/agents/risk_fraud/tests/test_a2a_contract.py`, deliver the identical `TaskRequest` (same `task_id`) twice and assert one logical verdict, **no second** `RiskReviewCompletedPayload`, and a `duplicate_skipped` audit — provided by the reused runtime `IdempotencyTracker` before the handler runs. `integration` (FR-013/SC-006).

**Checkpoint**: The A2A boundary contract is pinned end-to-end in one suite; all seven requested
scenarios pass over the reused runtime with no new transport/audit/idempotency mechanism.

---

---

## Phase 13: Local HTTP A2A Startup Entrypoint (port 8103)

*(consolidated deliverable: Local A2A Startup Entrypoint Deliverable (this run's input))*


**Request**: *"Add local A2A startup entrypoint — `GET /.well-known/agent.json`, `POST /a2a/tasks`.
Acceptance: agent starts on port 8103; Agent Card lists `assess_refund_risk`; Customer Resolution
Agent can call it directly."*

This deliverable makes the Risk Agent **independently startable and callable over HTTP** (the standalone
A2A surface), in addition to its Kafka A2A endpoint. The generic FastAPI/AgentCore shells already exist
in **Phase 10** (`http_app.py` + `dev_a2a_client.py`=**T038**, `app/RiskFraud/`=**T033**, `agentcore/`
config=**T035**, `test_http_entrypoint.py`=**T032**). This run **pins the three acceptance criteria**
onto that surface and adds the genuinely new work, rather than re-creating those files.


**The two HTTP routes** (A2A protocol mode, served by `http_app.py` / T038):

- **`GET /.well-known/agent.json`** — serves the **same** `AgentCard` the Kafka entrypoint advertises
  (built once in `identity.py`/T010), so the discovered card is identical on both transports.
- **`POST /a2a/tasks`** — accepts an A2A `assess_fraud_risk` task, runs the **same** `service.assess`
  pipeline (T016) the Kafka handler uses, and returns the structured verdict data part. This surface
  publishes **nothing** to Kafka — the `risk.review.completed` domain event stays the Kafka entrypoint's
  job (US2, T020).

**Port assignment**: **8103**. Chosen to avoid the billing agent's `:8080` (004) so all demo agents can
run concurrently; pinned in `agentcore/.env.local`, the `http_app.run()` default, and the HTTP console
script.

**Capability-id reconciliation (acceptance 2)**: the request says the card must list
`assess_refund_risk`; the **shipped capability id is `assess_fraud_risk`** (agent `risk-fraud-agent`) —
the id the unchanged Customer Resolution Agent discovers (`config.RISK_CAPABILITY_ID`) and the id the
spec's FR-002 references (research **R0**). `assess_refund_risk` is treated as the descriptive intent of
the same fraud-risk-assessment capability; keeping `assess_fraud_risk` preserves SC-009 with zero edits
to feature 003. The card lists exactly this one capability.

**Acceptance criteria → tasks**:
1. **Agent starts on port 8103** — realized by **T056** (pin `PORT=8103`) + **T057** (HTTP console
   script); asserted by **T059**; launchable via `agentcore dev` (**T062**).
2. **Agent Card lists the capability** — realized by **T087** (card advertises `assess_fraud_risk`, the
   shipped id; served verbatim at `GET /.well-known/agent.json`); asserted by **T088**.
3. **Customer Resolution Agent can call it directly** — realized by **T089** (a direct-call proof: build
   the exact request 003 sends via `build_risk_request_input` and `POST` it to `/a2a/tasks`, then assert
   the verdict normalizes through 003's unchanged `normalize_risk_result`) + **T090** (dev client points
   at `:8103`); documented by **T092**. No edit to feature 003 (SC-009).

### Phase E1: Port + Console Script (Setup)

- [X] T085 [P] Pin the HTTP port to **8103**: set `PORT=8103` in `apps/agents/risk_fraud/agentcore/.env.local` (created in T035, gitignored) and make `8103` the `http_app.run()` uvicorn default in `apps/agents/risk_fraud/http_app.py` (T038) via `int(os.environ.get("PORT", "8103"))` — chosen to avoid the billing agent's `:8080` so both run concurrently
- [X] T086 [P] Register the HTTP console script `demo-risk-fraud-http = "apps.agents.risk_fraud.http_app:run"` in `pyproject.toml` `[project.scripts]` (alongside the existing Kafka `demo-risk-fraud`), mirroring `demo-billing-entitlement-http`

### Phase E2: Endpoints + Direct-Call Proof (Priority: P1) 🎯 Deliverable MVP

- [X] T087 [US1] In `apps/agents/risk_fraud/identity.py` (T010) confirm `build_agent_card()` advertises **exactly one** capability `Capability(id="assess_fraud_risk", …)` (the shipped id; `assess_refund_risk` is its descriptive intent — research R0), and that `GET /.well-known/agent.json` in `apps/agents/risk_fraud/http_app.py` (T038) returns `build_agent_card().model_dump(mode="json")` so the HTTP and Kafka cards are byte-identical (acceptance 2)
- [X] T088 [P] [US1] Extend `apps/agents/risk_fraud/tests/test_http_entrypoint.py` (T032, FastAPI `TestClient`, no broker): assert `GET /.well-known/agent.json` returns a card whose `capabilities` ids include `assess_fraud_risk` (acceptance 2); assert `http_app.run()` resolves the listen port to **8103** from the `PORT` env/default (acceptance 1); assert a valid `assess_fraud_risk` task to `POST /a2a/tasks` returns the verdict data part and a malformed task returns a structured `failed` result (FR-011)
- [X] T089 [US1] Add the **direct-call proof** `apps/agents/risk_fraud/tests/test_resolution_direct_call.py` (FastAPI `TestClient`, no broker): build the request the Customer Resolution Agent sends via `apps.agents.customer_resolution.models.build_risk_request_input` (`case_id=correlation_id`, `ticket_id`, `customer_id`, `requested_refund_amount`, `customer_message_summary`), wrap it as an A2A `TaskRequest` `data` part addressed to `assess_fraud_risk`, `POST` it to `/a2a/tasks`, and assert the returned data part feeds `apps.agents.customer_resolution.event_handlers.normalize_risk_result` to a `low|elevated|high` level with `requires_human_review` carried through — proving 003 can call this agent directly with **no edit to feature 003** (acceptance 3; SC-009)
- [X] T090 [P] [US1] Update `apps/agents/risk_fraud/dev_a2a_client.py` (T038): default `base_url` to `http://localhost:8103`, assert `assess_fraud_risk` is in the fetched card, and `POST` a 003-shaped sample task (the `build_risk_request_input` field set) to `/a2a/tasks`, printing the returned risk level — proves independent, broker-free callability (acceptance 3)

### Phase E3: AgentCore Wiring + Docs (Polish)

- [X] T091 [P] Point `agentcore dev` at the HTTP surface on **8103**: set the entrypoint/port in `apps/agents/risk_fraud/agentcore/agentcore.json` + `.env.local` (T035), and document the local run/invoke flow in `apps/agents/risk_fraud/agentcore/README.md` — `agentcore dev`, `curl http://localhost:8103/.well-known/agent.json`, a `POST http://localhost:8103/a2a/tasks` example, and `python -m apps.agents.risk_fraud.dev_a2a_client`
- [X] T092 [P] Update `specs/005-risk-fraud-agent/quickstart.md` §C and the repo `README.md` to show the local HTTP A2A path on `:8103` — `demo-risk-fraud-http` / `python -m apps.agents.risk_fraud.http_app`, the `GET /.well-known/agent.json` + `POST /a2a/tasks` endpoints, and the 003-direct-call example — alongside the existing Kafka run (`python -m apps.agents.risk_fraud.main`)

### Local A2A Startup Entrypoint — Dependencies, Parallelism & Strategy

- **E1 (T085–T086)**: depends on the Phase 10 shells existing (T038 `http_app.py`, T035 `agentcore/` config); pins port + script. Run together — different files.
- **E2 (T087–T090)**: depends on US1 implementation (`service.assess`=T016, card=T010) and the Phase 10 shells (T038/T032). T087 (card/route) before T088 (asserts it). T089 (direct-call proof) needs T038 + `service.assess` + 003's unchanged `build_risk_request_input`/`normalize_risk_result`. T088/T089/T090 are different files → parallel after T087.
- **E3 (T091–T092)**: depends on E1+E2 landing (documents the finished `:8103` flow).

### Parallel opportunities

- E1: T085 and T086 in parallel (env/default vs. pyproject script).
- E2: after T087, T088 + T089 + T090 run in parallel (three different files).
- E3: T091 + T092 run in parallel once E2 lands.

### Deliverable MVP

T085 → T087 → T088 → T089 proves all three acceptance criteria: the FastAPI app starts on **:8103**, its
`GET /.well-known/agent.json` card lists `assess_fraud_risk`, and the Customer Resolution Agent's exact
request shape is accepted at `POST /a2a/tasks` and normalizes through 003's unchanged handler — no broker
and no edit to feature 003 required.

---
## Phase 14: Local Configuration Module

*(consolidated deliverable: Local Configuration Deliverable (this run's input))*


**Request**: *"Define local config — `AGENT_ID=risk-fraud-agent`, `ENVIRONMENT=local`,
`A2A_ENDPOINT_PORT=8103`, `AGENTCORE_PORT=8083`, `KAFKA_BOOTSTRAP_SERVERS=localhost:9092`,
`RISK_RESULT_EVENT_TYPE=risk.review.completed`, `AUTH_MODE=none`. Acceptance: Kafka topic names are
resolved through the topic resolver; AgentCore port and A2A port are configurable; local dev does not
require AWS deployment."*

This run **centralizes the agent's local configuration** in one module
`apps/agents/risk_fraud/config.py` and pins the three acceptance criteria onto it, rather than
re-creating the entrypoints/cards/ports earlier runs already produced. The feature stays **local-only**
— there is **no `agentcore deploy` task**. Topic names are **never hardcoded**; they resolve through the
existing topic resolver (`packages/contracts/topics.py:topic_for` / `resolve_topic` / `endpoint_topic`),
which already derives `TOPIC_RISK_RESULT` from `topic_for("risk","review","completed")` and reads
`AGENT_ENVIRONMENT` (=`local`) for the prefix.


**Config payload → binding (single source of truth = `config.py`, T093):**

| Key | Value | Bound to | Resolved via |
|-----|-------|----------|--------------|
| `AGENT_ID` | `risk-fraud-agent` | `AgentIdentity.agent_id`, `endpoint_topic(AGENT_ID)` | `config.AGENT_ID` |
| `ENVIRONMENT` | `local` | prefix on **every** topic name | `packages.contracts.topics.AGENT_ENVIRONMENT` (env `AGENT_ENVIRONMENT`) |
| `A2A_ENDPOINT_PORT` | `8103` | `http_app.run()` uvicorn port | `os.environ` → `config.A2A_ENDPOINT_PORT` |
| `AGENTCORE_PORT` | `8083` | `agentcore dev` server port | `agentcore/.env.local` `PORT=8083` |
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | runtime + `Publisher` broker | `AGENT_BROKER_URL` → `apps.agents.common.BROKER_URL` |
| `RISK_RESULT_EVENT_TYPE` | `risk.review.completed` | published domain event topic | `TOPIC_RISK_RESULT = topic_for("risk","review","completed")` (resolver) |
| `AUTH_MODE` | `none` | `AgentCard.security` | `config.AUTH_MODE` |

**Acceptance criteria → tasks:**
1. **Kafka topic names resolved through the topic resolver** — realized by **T093** (config re-exports
   resolver outputs, no literals) + **T094** (audit existing modules use
   `topic_for`/`endpoint_topic`/`TOPIC_RISK_RESULT`); asserted by **T097**.
2. **AgentCore port and A2A port are configurable** — realized by **T093** (`A2A_ENDPOINT_PORT`/
   `AGENTCORE_PORT` from env) + **T095** (`AGENTCORE_PORT=8083` in `.env.local`/`agentcore.json`,
   distinct from the A2A surface's 8103); asserted by **T097**.
3. **Local dev does not require AWS deployment** — realized by **T096** (run paths are `agentcore dev` +
   `http_app` + the Kafka peer; `agentcore deploy` stays a documented future target, not built);
   asserted by **T097**.

### Phase C1: Local Config Module (Setup)

- [X] T093 [P] Create the local config module `apps/agents/risk_fraud/config.py` as the single source of
  truth: `AGENT_ID = "risk-fraud-agent"`, `DISPLAY_NAME`, `TENANT_ID = "poc"`,
  `AUTH_MODE = os.environ.get("AUTH_MODE", "none")`,
  `A2A_ENDPOINT_PORT = int(os.environ.get("A2A_ENDPOINT_PORT", os.environ.get("PORT", "8103")))`,
  `AGENTCORE_PORT = int(os.environ.get("AGENTCORE_PORT", "8083"))`, `BROKER_URL` re-exported from
  `apps.agents.common.BROKER_URL` (`AGENT_BROKER_URL`, default `localhost:9092`), `ENVIRONMENT`
  re-exported from `packages.contracts.topics.AGENT_ENVIRONMENT`, and `RISK_RESULT_TOPIC` re-exported
  from `packages.contracts.topics.TOPIC_RISK_RESULT` (**resolver-derived — do NOT hardcode**
  `local.risk.review.completed.v1`). No new dependency.
- [X] T094 [P] Wire the existing modules to read from `config.py` with no behavior change:
  `apps/agents/risk_fraud/identity.py` takes `AGENT_ID`/`DISPLAY_NAME`/`TENANT_ID`/`AUTH_MODE` from
  `config`; `apps/agents/risk_fraud/http_app.py` reads `config.A2A_ENDPOINT_PORT`;
  `apps/agents/risk_fraud/main.py` uses `config.BROKER_URL` and publishes to `config.RISK_RESULT_TOPIC`.
  Confirm **no module hardcodes a topic string** — all go through
  `topic_for`/`endpoint_topic`/`TOPIC_RISK_RESULT` (acceptance 1).

### Phase C2: Port + Auth Config (Setup)

- [X] T095 [P] Make both ports configurable and **distinct**: set `PORT=8083` (the **AGENTCORE_PORT**) in
  `apps/agents/risk_fraud/agentcore/.env.local` and the entrypoint/port in
  `apps/agents/risk_fraud/agentcore/agentcore.json`, keeping the standalone HTTP A2A surface on **8103**
  so `agentcore dev` (8083) and `http_app` (8103) run concurrently (acceptance 2). Document the env
  overrides (`A2A_ENDPOINT_PORT`, `AGENTCORE_PORT`/`PORT`, `AGENT_BROKER_URL`, `AGENT_ENVIRONMENT`,
  `AUTH_MODE`) in `apps/agents/risk_fraud/agentcore/README.md`.
- [X] T096 [P] Confirm `AUTH_MODE=none` flows to `AgentCard.security="none"` in
  `apps/agents/risk_fraud/identity.py`, and document in `apps/agents/risk_fraud/agentcore/README.md`
  that local dev runs entirely on the foundation's local Kafka + `agentcore dev`/`http_app` with **no
  AWS deployment** — `agentcore deploy` (CodeZip) is a documented future target only, and
  `aws-targets.json` carries a placeholder account (acceptance 3).

### Phase C3: Config Acceptance Test (Polish)

- [X] T097 Write `apps/agents/risk_fraud/tests/test_config.py` (no broker) asserting all three
  acceptance criteria: (1) `config.RISK_RESULT_TOPIC == topic_for("risk","review","completed")` and
  `endpoint_topic(config.AGENT_ID)` is `AGENT_ENVIRONMENT`-prefixed — both resolver-derived;
  (2) `config.A2A_ENDPOINT_PORT == 8103` and `config.AGENTCORE_PORT == 8083` by default and both honor
  their env overrides (via `monkeypatch`); (3) `config.AUTH_MODE == "none"` and
  `build_agent_card().security == "none"`.

### Local Configuration — Dependencies, Parallelism & Strategy

- **C1 (T093–T094)**: T093 (new module) has no dependency and starts immediately; T094 wires the
  existing `identity.py`/`http_app.py`/`main.py` to it.
- **C2 (T095–T096)**: depends on the Phase 10 AgentCore footprint existing + C1.
- **C3 (T097)**: depends on C1 (`config.py`) + C2 (port/auth wiring); proves all three acceptance criteria.

### Parallel opportunities

- C1: T093 first; T094 follows (it imports `config`).
- C2: T095 + T096 in parallel (different files/concerns) after C1.
- C3: T097 last (asserts the finished config surface).

### Deliverable MVP

T093 → T094 → T097 proves the local config: every topic name comes from the resolver, the A2A (8103)
and AgentCore (8083) ports are env-configurable, and local dev runs with `AUTH_MODE=none` and no AWS
deployment.

---
## Phase 15: Customer Resolution Agent Integration Test

*(consolidated deliverable: Customer Resolution Agent Integration Test (this run's input))*


**Request**: *"Add integration test with Customer Resolution Agent. Scenario: Customer Resolution
Agent sends an A2A `assess_refund_risk` task → Risk Agent processes the task → Risk Agent publishes
`risk.review.completed` → Customer Resolution Agent consumes the risk result. Acceptance: the same
correlation id flows through all events; the Risk Agent does not call the Billing Agent; no supervisor
agent is used."*

This deliverable adds a dedicated **cross-agent integration test** that runs the **unchanged** Customer
Resolution Agent (003) and the Risk Agent (005) as two real peers on one testcontainers Kafka broker and
drives the full delegation round-trip — distinct from `test_risk_agent_e2e` (T039, verdict-focused) and
`test_a2a_contract` (T042–T049, single-agent protocol boundary): this suite proves the two real agents
*collaborate* peer-to-peer with no central coordinator. New file:
`apps/agents/risk_fraud/tests/test_resolution_integration.py`.


**Capability-name reconciliation**: the request phrases the task as `assess_refund_risk`. The
shipped/discovered capability id is **`assess_fraud_risk`** — the id 003 already sends via
`config.RISK_CAPABILITY_ID` (research **R0**). These tasks use the shipped id and treat
`assess_refund_risk` as its descriptive intent; keeping `assess_fraud_risk` preserves SC-009 with zero
edits to feature 003.

**Scenario** (request → process → published event → consumed):

1. Customer Resolution Agent sends the A2A `assess_fraud_risk` task to the Risk Agent.
2. Risk Agent processes the task (validate → load owned signals → score).
3. Risk Agent publishes `risk.review.completed` (`RiskReviewCompletedPayload` on `TOPIC_RISK_RESULT`).
4. Customer Resolution Agent consumes the risk result via `risk_result_handler` / `normalize_risk_result`.

**Acceptance criteria → tasks**:

| Acceptance criterion | Realized / asserted by |
|----------------------|------------------------|
| Same correlation id flows through **all** events | **T100** — ticket `correlation_id` == request `case_id`/`correlation_id` == `TaskResult.correlation_id` == published event `correlation_id` == consumer lookup key (`store.get_by_correlation_id`) |
| Risk Agent does **not** call the Billing Agent | **T101** — no `TaskRequest` from `risk-fraud-agent` to `billing-entitlement-agent`; the billing-endpoint sentinel stays silent; verdict sourced only from owned signals (SC-003/FR-009) |
| **No supervisor** agent is used | **T102** — peer-to-peer only: 003 addresses 005 directly via discovery; no router/dispatcher/orchestrator/supervisor id in the case's event stream; 005 originates no task requests (FR-016/SC-008) |

### Phase I1: Customer Resolution Agent Integration Test (Priority: P3) 🤝

**Goal**: Prove the two real agents collaborate end-to-end with one correlation id, no Risk→Billing
call, and no supervisor in the path — using the reused runtime/transport/contract as-is (no new
topic/contract/dependency).

**Independent Test**: `pytest -m integration apps/agents/risk_fraud/tests/test_resolution_integration.py -q`
spins up testcontainers Kafka, runs both real agents as peers, drives one refund case through
003→005→003, and asserts the scenario plus the three acceptance criteria.

> Depends on the Kafka verdict + publish path (US1 **T015–T017**, US2 **T019–T020**) and the unchanged
> 003 consumer. Broker-dependent → `pytest.mark.integration` (reuse the 004 testcontainers Kafka
> fixture). T099–T102 add tests to the **same** new file, authored sequentially after the harness T098.

- [ ] T098 [P] [US7] Add the cross-agent harness to `apps/agents/risk_fraud/tests/conftest.py`: a `resolution_and_risk_peers` fixture that starts the real `apps/agents/risk_fraud/main.py` runtime and the real `apps/agents/customer_resolution/` runtime as two peers on the shared testcontainers Kafka broker (reuse the 004 broker fixture), publishes both agent cards for discovery, and exposes an event-stream tap recording every published envelope (`topic`, `agent_id`, `correlation_id`, `causation_id`) for the case; include a `billing_endpoint_sentinel` subscribed to the billing agent's endpoint topic so the test can assert it receives nothing.
- [ ] T099 [US7] **Scenario round-trip** in `apps/agents/risk_fraud/tests/test_resolution_integration.py`: trigger 003 to send the A2A `assess_fraud_risk` task via its **unchanged** delegation path (publish the `support.ticket.created` refund case that makes 003 call `a2a_handlers.request_risk_analysis`, built from `models.build_risk_request_input`); assert the Risk Agent processes it, publishes exactly one `RiskReviewCompletedPayload` on `TOPIC_RISK_RESULT` (`local.risk.review.completed.v1`), and 003's `risk_result_handler` / `normalize_risk_result` consumes it and reaches one decision for the case (FR-002/FR-007/FR-008; SC-009).
- [ ] T100 [US7] **AC1 — one correlation id across all events** in `apps/agents/risk_fraud/tests/test_resolution_integration.py`: assert the inbound ticket's `correlation_id` equals the `case_id`/`correlation_id` on the outbound `assess_fraud_risk` `TaskRequest`, equals the `correlation_id` on the A2A `TaskResult`, equals the `correlation_id` on the published `RiskReviewCompletedPayload`, and is the key 003 uses to resolve the case (`store.get_by_correlation_id`); confirm the causation chain links ticket→task→result→event (FR-015/SC-007; research R2).
- [ ] T101 [US7] **AC2 — Risk Agent does not call the Billing Agent** in `apps/agents/risk_fraud/tests/test_resolution_integration.py`: assert the recorded stream contains **no** `TaskRequest` originated by `risk-fraud-agent` addressed to `billing-entitlement-agent` (the `billing_endpoint_sentinel` from T098 receives nothing) and no billing/eligibility topic traffic from the risk agent; the verdict is built only from owned signals (reuse the domain-isolation guarantee, SC-003/FR-009).
- [ ] T102 [US7] **AC3 — no supervisor agent is used** in `apps/agents/risk_fraud/tests/test_resolution_integration.py`: assert the flow is strictly peer-to-peer — 003 addresses 005 directly via capability discovery with **no** router/dispatcher/orchestrator/supervisor agent id appearing in the case's event stream, and 005 originates **no** `TaskRequest` of its own (FR-016/FR-018; SC-008). Live two-agent complement to the unit-level `test_no_supervisor` (T031).

**Checkpoint**: The two real agents collaborate end-to-end with one correlation id, no Risk→Billing
call, and no supervisor — the requested integration test is green.

### Dependencies, Parallelism & Strategy

- **Depends on**: US1 (T015–T017) + US2 (T019–T020) for the Risk Agent's served + publishing path, and the unchanged `apps/agents/customer_resolution/` consumer. T098 (harness) precedes T099–T102.
- **Parallelism**: T098 is an independent file ([P]); T099–T102 share one file → authored sequentially.
- **Deliverable MVP**: T098 → T099 → T100 proves the core requested behavior (round-trip + single correlation id); T101 and T102 add the two guardrail assertions.

---
## Phase 16: Behavioral Risk Analyzer

*(consolidated deliverable: Behavioral Risk Analyzer (this run's input))*


**Request**: *"Implement behavioral risk analyzer. Signals: new account, device mismatch, IP/location
mismatch, high request velocity, unusual refund amount, missing account history. Acceptance: analyzer
does not make the final refund decision; analyzer produces risk factors and evidence; missing data lowers
confidence."*

This run implements the **behavioral risk analyzer** — the behavioral leg of the deterministic scoring
engine (`scoring.assess_signals`, **T015**). It classifies six behavioral/account signals into named
**risk factors** with **evidence** and contributes a partial behavioral score to the engine. It is a
pure, unit-testable classifier — **not** a second decision path and **not** a refund decision-maker. The
existing US3 grounding/isolation (T021/T022) and US4 uncertainty (T023/T025) guarantees carry over.


**Signals → owned data + policy rule** (two signals reuse existing rules; three are genuinely new):

| Behavioral signal | Owned field | Policy rule | Realized by |
|-------------------|-------------|-------------|-------------|
| new account | `account_standing.tenure_days < NEW_ACCOUNT_DAYS` | `FP-005` *(exists)* | T007/T015 + factor in **T107** |
| high request velocity | `behavioral.refund_requests_in_window ≥ VELOCITY_*` | `FP-003` *(exists)* | T007/T015 + factor in **T107** |
| device mismatch | `behavioral.device_mismatch: bool` *(NEW)* | `FP-007` *(NEW, +0.4)* | **T103/T104/T107** |
| IP/location mismatch | `behavioral.ip_location_mismatch: bool` *(NEW)* | `FP-008` *(NEW, +0.4)* | **T103/T104/T107** |
| unusual refund amount | `requested_refund_amount` vs `behavioral.typical_refund_amount` *(NEW)* | `FP-009` *(NEW, +0.3, ratio `UNUSUAL_AMOUNT_RATIO=3.0`)* | **T103/T104/T107** |
| missing account history | `refund_history is None` (signals partly present) | confidence rule | **T108** |

**Acceptance criteria → tasks**:
1. **Analyzer does not make the final refund decision** — the analyzer returns `BehavioralFactor`s + a
   partial score; the agent's only verdict vocabulary is `low|elevated|high` + `requires_human_review`,
   never approve/deny/refund (FR-016/US7). Realized in **T107**; asserted in **T106** and **T109**.
2. **Analyzer produces risk factors and evidence** — each fired signal yields a named `BehavioralFactor`
   carrying its `FP-00x` reference and an `EvidenceItem` (`source` = owned signal domain) naming the
   source and what it shows (FR-005). Realized in **T107**; asserted in **T106**.
3. **Missing data lowers confidence** — when a signal domain is **partially** absent (notably
   `refund_history is None`) while others are present, record a missing-history factor and **lower** the
   assessment confidence rather than fabricating or fully failing; a total `load_signals` miss still
   takes the human-review path (conf 0.2, FR-010). Realized in **T108**; asserted in **T108**'s test.

### Phase B1: New Behavioral Signals, Rules & Seeds (Foundational extension)

> Extends the Phase 2 foundation. T103 extends `models.py` (T005), T104 extends `policy.py` (T007), T105
> extends `mock_data.py` (T011). All three are different concerns and run in parallel.

- [X] T103 [P] Add the three new behavioral fields to `BehavioralSignal` in `apps/agents/risk_fraud/models.py` (extends T005): `device_mismatch: bool` (default `False`), `ip_location_mismatch: bool` (default `False`), `typical_refund_amount: float | None` (default `None`, `>= 0` when present) — illustrative PoC fields, keeping the model frozen and within the owned behavioral domain (FR-003/SC-003).
- [X] T104 [P] Add the three new policy rules + constant to `apps/agents/risk_fraud/policy.py` (extends T007 / `contracts/fraud-policy.md`): `PolicyRule` entries `FP-007` device-mismatch (`+0.4`), `FP-008` ip-location-mismatch (`+0.4`), `FP-009` unusual-refund-amount (`+0.3`), and constant `UNUSUAL_AMOUNT_RATIO = 3.0` (requested amount `≥ ratio × typical_refund_amount` fires). Additive into the existing score (capped at `1.0`); each id cited as `fraud_policy` evidence (FR-005/FR-012).
- [X] T105 [P] Add behavioral seed customers to `apps/agents/risk_fraud/mock_data.py` (extends T011 / `contracts/mock-risk-data.md`): `CUS-DEVICE` (`device_mismatch=True`, else clean → `elevated` via FP-007), `CUS-GEO` (`ip_location_mismatch=True`, else clean → `elevated` via FP-008), `CUS-UNUSUAL-AMOUNT` (low `typical_refund_amount` vs a high requested amount → `elevated` via FP-009), and `CUS-MISSING-HISTORY` (`refund_history=None`, other signals present → normal level with lowered confidence). Keeps unknown-customer miss → `None` (FR-010).

### Phase B2: Behavioral Analyzer + Missing-Data Confidence (Priority: P1) 🎯 Deliverable MVP

> Depends on US1 (`scoring.assess_signals` T015, `service.assess` T016) and B1 (T103–T105). The analyzer
> folds into the existing engine — it is not a separate decision path.

### Tests (TDD — write first, must fail)

- [ ] T106 [P] [US3] **TDD** Write `apps/agents/risk_fraud/tests/test_behavioral_analyzer.py` (failing first; acceptance 1 & 2): a **deterministic matrix** over the six signals (new account, device mismatch, IP/location mismatch, high velocity, unusual amount, missing history), each evaluated twice yielding identical `BehavioralFactor`s (no clock/random — FR-012); assert each fired signal emits a named factor + an `EvidenceItem` whose `source` is the owned signal domain (`account_standing`/`behavioral`) and carries its `FP-00x` reference (acceptance 2); and assert the analyzer's return type is **risk factors + a partial score only — no `approve`/`deny`/refund field anywhere** (acceptance 1).

### Implementation

- [ ] T107 [US3] Implement the **behavioral risk analyzer** in `apps/agents/risk_fraud/behavioral_analyzer.py` (acceptance 1 & 2; depends on T005/T103, T007/T104, T015): `analyze_behavioral(signals, request, policy) -> BehavioralAnalysis` — a **pure, deterministic** classification of the six signals into a list of named `BehavioralFactor`s (new-account `FP-005`, high-velocity `FP-003`, device-mismatch `FP-007`, ip-location-mismatch `FP-008`, unusual-amount `FP-009` comparing `request.requested_refund_amount` to `behavioral.typical_refund_amount × UNUSUAL_AMOUNT_RATIO`), each factor carrying its `FP-00x` reference, its partial score contribution, and a `build_evidence()` `EvidenceItem` (`source` = owned signal domain). Returns factors + a capped partial behavioral score and **no refund recommendation** (acceptance 1). Integrate into `apps/agents/risk_fraud/scoring.py` `assess_signals` (T015): the behavioral partial score folds into the additive total and the behavioral `EvidenceItem`s/policy refs into the verdict, keeping every `EvidenceItem.source` in the owned set (T021/T022 isolation).
- [ ] T108 [US4] Implement the **missing-account-history confidence rule** in `apps/agents/risk_fraud/scoring.py` / `service.py` (extends T025; acceptance 3): when `load_signals` returns a `RiskSignals` with `refund_history is None` (or another single domain absent) while other signals are present, the analyzer records a missing-history `BehavioralFactor` and the engine **lowers the assessment confidence** (e.g. to ≈0.6) with the gap noted in `reasoning_summary`/`evidence` — rather than fabricating a confident verdict or fully failing; a **total** signal miss still takes the existing human-review path (conf 0.2, T025/FR-010). Extend `apps/agents/risk_fraud/tests/test_scoring.py` to assert `CUS-MISSING-HISTORY` yields a normal level with the lowered confidence and the missing-history factor (SC-005).
- [ ] T109 [P] [US7] Extend `apps/agents/risk_fraud/tests/test_no_supervisor.py` (T031; acceptance 1): assert the behavioral analyzer (T107) and the agent's output expose **only** risk levels / risk factors and **no** approve/deny/refund decision field — the analyzer judges behavioral risk, the refund decision belongs to the Customer Resolution Agent (FR-016/SC-008).

**Checkpoint**: The behavioral analyzer classifies all six signals into named risk factors with owned-source
evidence, folds a partial score into the existing deterministic engine, **makes no refund decision**, and
**lowers confidence on partial-missing data** — all three run-input acceptance criteria met.

### Behavioral Risk Analyzer — Dependencies, Parallelism & Strategy

- **B1 (T103–T105)**: extends Phase 2 foundation; T103/T104/T105 are three different files → parallel.
- **B2 (T106–T109)**: depends on US1 (T015/T016) + B1. T106 (test) before T107 (impl). T107 before T108
  (missing-data rule builds on the analyzer). T109 is a different test file → parallel with T107/T108.
- **Deliverable MVP**: T103 → T104 → T105 → T106 → T107 proves acceptance 1 & 2 (named factors + evidence,
  no refund decision); T108 adds acceptance 3 (missing data lowers confidence); T109 pins the
  no-refund-decision guardrail.

### Parallel opportunities

- B1: T103, T104, T105 in parallel (models / policy / mock data — different files).
- B2: after T106→T107, T108 and T109 run in parallel (scoring/service vs. the no-supervisor test file).

---
## Phase 17: Mock Risk/Fraud Signal Data Store

*(consolidated deliverable: Mock Risk/Fraud Signal Data Store Deliverable (this run's input))*


**Request**: *"Create mock risk data store; seed `customer_id, account_age_days, prior_refund_count,
prior_refund_total_amount, prior_chargebacks, recent_failed_payments_signal, ip_country_mismatch,
device_change_count, suspicious_velocity_count, support_abuse_flags, known_good_customer`; example
scenarios: known-good/low-history, new-account/high-refund, multiple recent refunds, prior chargeback,
IP/device mismatch, missing profile, enterprise/VIP requiring manual review. Acceptance: risk data is
deterministic; fixtures support unit tests; the store interface can later be replaced with
Postgres/DynamoDB."*

This deliverable hardens the agent's **owned, in-process, seeded signal data store** — the data behind
every verdict (FR-003) — building on the foundational seed task **T011** and signal models **T005**, and
adding the **replaceable store seam** the request asks for. The store's only job is to return the seeded
signals (or `None`); mapping signals → a verdict stays in `scoring.py` (US1/US4), so the VIP/missing rows
carry the marker/absence the scoring engine later turns into `requires_human_review`.


**Seed field mapping** (requested flat fields → owned signal domains from data-model §2; **NEW** = field
added on top of the data-model):

| Requested seed field | Signal domain · field | Task |
|----------------------|------------------------|------|
| `customer_id` | lookup key (`RiskSignals.customer_id`) | T112 |
| `account_age_days` | `AccountStanding.tenure_days` | T112 |
| `prior_refund_count` | `RefundDisputeHistory.prior_refunds` | T112 |
| `prior_refund_total_amount` | `RefundDisputeHistory.prior_refund_total_amount` **NEW** | T110 |
| `prior_chargebacks` | `RefundDisputeHistory.chargebacks` | T112 |
| `recent_failed_payments_signal` | `PaymentInstrumentSignal.recent_failed_payments` **NEW** | T110 |
| `ip_country_mismatch` | `BehavioralSignal.ip_country_mismatch` **NEW** | T110 |
| `device_change_count` | `BehavioralSignal.device_change_count` **NEW** | T110 |
| `suspicious_velocity_count` | `BehavioralSignal.refund_requests_in_window` | T112 |
| `support_abuse_flags` | `AccountStanding.support_abuse_flags` **NEW** | T110 |
| `known_good_customer` | `AccountStanding.known_good_customer` **NEW** (paired with `status="good"`) | T110 |
| *(VIP/enterprise marker)* | `AccountStanding.segment ∈ {standard, vip, enterprise}` **NEW** | T110 |

**Seed scenario coverage** (deterministic, keyed by `customer_id`; T112/T116) — the seven requested
example scenarios:

| # | Requested scenario | Seed `customer_id` | Key signal | Lookup result |
|---|--------------------|--------------------|-----------|---------------|
| 1 | known good customer, low refund history | `CUS-CLEAN` | `known_good_customer=True`, `prior_refunds=1` | `RiskSignals` (clean) |
| 2 | new account, high refund amount | `CUS-NEW-HIGH-REFUND` | `tenure_days=5`, `prior_refund_total_amount=850.0` | `RiskSignals` |
| 3 | multiple refunds in last 30 days | `CUS-VELOCITY` | `refund_requests_in_window=5`, `velocity_window_days=30` | `RiskSignals` |
| 4 | prior chargeback | `CUS-ONE-CHARGEBACK` / `CUS-CHARGEBACKS` | `chargebacks=1` / `2` | `RiskSignals` |
| 5 | IP/device mismatch | `CUS-IP-DEVICE` | `ip_country_mismatch=True`, `device_change_count=3` | `RiskSignals` |
| 6 | missing risk profile | `CUS-UNKNOWN` (no record) | — | `None` (FR-010 review path) |
| 7 | enterprise/VIP requiring manual review | `CUS-VIP-ENTERPRISE` | `segment="enterprise"` | `RiskSignals` (downstream → review) |

**Acceptance criteria → tasks**:

1. **Risk data is deterministic** — **T110** (frozen models, integer day-counts, **no timestamps**) +
   **T112** (`_DATASET` is a pure literal — no `datetime.now`/`random`) + **T117** (repeatable-lookup,
   frozen-mutation, and static no-wall-clock/no-random assertions). Contrast: the `004` billing
   `mock_data.py` uses `datetime.now`; this store deliberately does not (FR-012).
2. **Fixtures support unit tests** — **T113** (`risk_store` / `seed_customer_ids` conftest fixtures),
   consumed by **T114/T115/T116/T117**.
3. **Store interface replaceable with Postgres/DynamoDB** — **T111** (`RiskSignalStore` `Protocol` +
   `InMemoryRiskSignalStore`; `default_store()` injection seam; a `PostgresRiskSignalStore` /
   `DynamoDbRiskSignalStore` drops in by implementing the same `load_signals`).

### Phase D1: Signal Fields + Replaceable Store Seam (Foundational)

- [X] T110 [P] [US3] Extend the owned-signal models in `apps/agents/risk_fraud/models.py` (T005) with the requested flat fields as **frozen** Pydantic v2 fields using **integer day-counts only (no timestamps)**: `AccountStanding` += `support_abuse_flags: int>=0 = 0`, `known_good_customer: bool = False`, `segment: Literal["standard","vip","enterprise"] = "standard"`; `RefundDisputeHistory` += `prior_refund_total_amount: float>=0 = 0.0`; `PaymentInstrumentSignal` += `recent_failed_payments: int>=0 = 0`; `BehavioralSignal` += `ip_country_mismatch: bool = False`, `device_change_count: int>=0 = 0`. Keep `model_config = ConfigDict(frozen=True)` (acceptance #1 — deterministic, immutable shape)
- [X] T111 [US3] Add the replaceable store seam `apps/agents/risk_fraud/store.py`: a `RiskSignalStore` `typing.Protocol` with `load_signals(self, customer_id: str) -> RiskSignals | None`, and an `InMemoryRiskSignalStore(records: dict[str, RiskSignals])` doing a case-sensitive lookup (miss → `None`). Module docstring documents that a `PostgresRiskSignalStore` / `DynamoDbRiskSignalStore` drops in by implementing the same Protocol, injected via `default_store()` — callers depend on the Protocol, never on `_DATASET` (acceptance #3) (depends T110)

### Phase D2: Deterministic Seeds, Lookup & Fixtures (Priority: P1) 🎯 Deliverable MVP

- [X] T112 [US3] Refactor `apps/agents/risk_fraud/mock_data.py` (T011) so the dataset is a **pure literal** `_DATASET: dict[str, RiskSignals]` (no `datetime.now`, no randomness) built via a `_clean_signals(customer_id, **overrides)` baseline-plus-single-field-override helper, seeding the seven requested scenarios — `CUS-CLEAN`, `CUS-NEW-HIGH-REFUND`, `CUS-VELOCITY`, `CUS-ONE-CHARGEBACK`/`CUS-CHARGEBACKS`, `CUS-IP-DEVICE`, `CUS-VIP-ENTERPRISE` (and the existing `contracts/mock-risk-data.md` seeds). Expose `default_store() -> RiskSignalStore` returning `InMemoryRiskSignalStore(_DATASET)` and keep `load_signals(customer_id) -> RiskSignals | None` delegating to it, preserving the T011/T016 lookup contract (acceptance #1; depends T110, T111)
- [X] T113 [P] [US3] Add reusable fixtures to `apps/agents/risk_fraud/tests/conftest.py` (T002): a `risk_store` fixture returning `default_store()` and a `seed_customer_ids` fixture listing every seeded id, so unit tests consume the seeded data without rebuilding it (acceptance #2; depends T112)

### Phase D3: Unit Tests — Coverage, Isolation, Determinism (Priority: P1)

- [X] T114 [P] [US3] Extend `apps/agents/risk_fraud/tests/test_mock_data.py` (T012): table-driven over `seed_customer_ids`, assert each scenario's mapped flat fields equal the documented values (`account_age_days→tenure_days`, `suspicious_velocity_count→refund_requests_in_window`, etc.) and that `CUS-CLEAN` is `known_good_customer=True` with low refund history (acceptance #2; depends T113)
- [X] T115 [P] [US3] Add an isolation test to `apps/agents/risk_fraud/tests/test_mock_data.py`: `RiskSignals` and its sub-models expose **only** risk/fraud-domain fields — assert no subscription/invoice/payment-eligibility/entitlement/usage or customer-resolution fields leak in (SC-003/FR-009; depends T110)
- [X] T116 [P] [US4] Extend `apps/agents/risk_fraud/tests/test_mock_data.py`: `load_signals("CUS-UNKNOWN")` returns `None` (missing-profile path, FR-010) and `load_signals("CUS-VIP-ENTERPRISE").account_standing.segment == "enterprise"` so the scoring engine (T023/T025) routes it to `requires_human_review` (depends T112, T113)
- [X] T117 [P] [US5] Add determinism + immutability tests to `apps/agents/risk_fraud/tests/test_mock_data.py`: `load_signals("CUS-CLEAN") == load_signals("CUS-CLEAN")` across calls; mutating a returned model field raises `ValidationError` (frozen); and a static-source assertion that `apps/agents/risk_fraud/mock_data.py` and `apps/agents/risk_fraud/store.py` reference no `datetime.now`/`time.`/`random`/`uuid` (acceptance #1; FR-012; depends T112)

### Phase D4: Contract Sync (Polish)

- [X] T118 [P] Update `specs/005-risk-fraud-agent/contracts/mock-risk-data.md`: extend the seed-coverage table with the new flat fields (`prior_refund_total_amount`, `recent_failed_payments`, `ip_country_mismatch`, `device_change_count`, `support_abuse_flags`, `known_good_customer`, `segment`) and the new scenario rows (`CUS-NEW-HIGH-REFUND`, `CUS-IP-DEVICE`, `CUS-VIP-ENTERPRISE`), and document the `RiskSignalStore` swap seam (`default_store()` → Postgres/DynamoDB)

### Mock Risk/Fraud Signal Data Store — Dependencies, Parallelism & Strategy

- **D1 (T110–T111)**: T110 extends the signal models (T005); T111 (store seam) depends on the `RiskSignals` shape from T110. Foundational — blocks D2/D3.
- **D2 (T112–T113)**: T112 (seeds + `default_store`) depends on T110+T111; T113 (fixtures) depends on T112. The store MVP.
- **D3 (T114–T117)**: all four extend the **same** file `test_mock_data.py`, so author them sequentially (independent test functions, one file) after their fixtures/seeds land; `[P]` marks them independent of other deliverables' files.
- **D4 (T118)**: documents the finished store; depends on D1–D2.

### Deliverable MVP

T110 → T111 → T112 → T113 → T114 proves the three acceptance criteria: the store is a deterministic
pure-literal of frozen owned-only signals (acceptance #1), exposed behind the swappable `RiskSignalStore`
Protocol via `default_store()` (acceptance #3), and consumable in unit tests through the `risk_store` /
`seed_customer_ids` fixtures (acceptance #2). T115–T117 then lock isolation, missing-profile/VIP, and
determinism; T118 syncs the contract doc.

---
## Phase 18: AgentCore App Wrapper (agentcore_app.py)

*(consolidated deliverable: AgentCore App Wrapper Deliverable — `agentcore_app.py` (this run's input))*


**Request**: *"Implement AgentCore app wrapper — create `apps/agents/risk_fraud/agentcore_app.py`.
Accept local AgentCore invocation payloads; parse into `RefundRiskAssessmentRequest`; run the risk
assessment service; return structured JSON; do not bypass A2A/Kafka contract tests. Acceptance:
AgentCore local invocation works; response includes risk level, recommendation, confidence, and
evidence; the AgentCore path is a demo/testing interface, not a supervisor."*

A `BedrockAgentCoreApp` `@app.entrypoint` that accepts a **local AgentCore invocation payload**, parses
it into `RiskAssessmentRequest` (alias `RefundRiskAssessmentRequest`, **T009**), runs the **existing**
`service.assess` unchanged (**T016**), and returns a structured JSON response. It is **distinct** from
the `serve_a2a` A2A server (`app/RiskFraud/main.py`, **T033**) and the FastAPI surface (`http_app.py`,
**T032/T038**): a single-shot **dict-in / JSON-out demo/testing** entrypoint for plain `agentcore` local
invocation.


**Acceptance criteria → tasks**:
1. **AgentCore local invocation works** — the `@app.entrypoint` is invocable locally and returns a result (T120; asserted by T119).
2. **Response includes risk level, recommendation, confidence, and evidence** — the JSON carries `recommendation` (= `risk_level.value`), `confidence`, `evidence`, `reasoning_summary`, `requires_human_review`, and `policy_references` (T120; asserted by T119).
3. **Demo/testing interface, not a supervisor** — reuses `service.assess`, originates no `TaskRequest`, dispatches no work, makes no peer call, and publishes **nothing** to Kafka (that stays the Kafka entrypoint's job, **T020**), so it **does not bypass the A2A/Kafka contract tests** (**T032/T039**) (T120; asserted by T119 — no `Publisher`, no peer/runtime client; SC-008/FR-016).

> Depends only on US1 (`service.assess`, **T016**) + the Foundational input model (**T009**) — independent of US2/US5/US6 and of the `serve_a2a`/`http_app` shells.

- [X] T119 [P] [AC] **TDD** Write `apps/agents/risk_fraud/tests/test_agentcore_app.py` (failing first; **no broker**): invoking the `@app.entrypoint` in-process with a blocklist-customer payload returns `recommendation="high"` with a non-empty `evidence` set and ≥1 `fraud_policy` evidence item; a clean-customer payload returns `low`; a malformed payload returns a structured failure (reason, no fabricated verdict, FR-011); for the same input the entrypoint's verdict **equals** `service.assess` output (delegation proof); and the wrapper constructs **no** `Publisher` and **no** peer/runtime client and publishes nothing (demo/testing, not a supervisor — SC-008/FR-016).
- [X] T120 [AC] Implement `apps/agents/risk_fraud/agentcore_app.py`: a `BedrockAgentCoreApp` with an `@app.entrypoint` `invoke(payload)` that (1) accepts a dict **or** JSON-string AgentCore payload, (2) parses it into `RiskAssessmentRequest` (T009) — on `ValueError` returns a structured error JSON with a reason, never a fabricated verdict (FR-011), (3) calls **`service.assess` unchanged** (T016), and (4) returns a JSON dict with `recommendation` (= `risk_level.value`), `confidence`, `evidence` (each item's `source`/`description`/`value`), `reasoning_summary`, `requires_human_review`, and `policy_references`; guard `if __name__ == "__main__": app.run()`. Add no peer call, no `TaskRequest`, no Kafka publish (FR-016). Make T119 pass.

**Checkpoint**: `agentcore_app.py` returns a structured risk verdict (risk level + recommendation + confidence + evidence) from a local AgentCore invocation, reusing `service.assess`, and bypasses no A2A/Kafka contract test.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Foundational (Phase 2)**: Depends on Setup — **BLOCKS all user stories** (models, policy, identity, mock data).
- **US1 (Phase 3)**: Depends on Foundational. The MVP front door; US2–US7 build on its scoring/service.
- **US2 (Phase 4)**: Depends on US1 (needs `RiskAssessment` + service).
- **US3 (Phase 5)**: Depends on US1 (constrains scoring evidence). Independent of US2.
- **US4 (Phase 6)**: Depends on US1 (extends scoring/service + runtime failure path).
- **US5 (Phase 7)**: Depends on US1 (determinism); redelivery dedup is reused-runtime behavior.
- **US6 (Phase 8)**: Depends on US1+US2 (audits the received/decision/published steps).
- **US7 (Phase 9)**: Depends on US1 (inspects the established behavior). Independent of US2–US6.
- **AgentCore CLI (Phase 10, story AC)**: Depends on US1 (reuses `service.assess`). Independent of US2/US5/US6 — runs in parallel with the Kafka transport stories.
- **Polish (Phase 11)**: Depends on all desired stories; T039 e2e exercises US1–US6 + SC-009.
- **A2A Contract Suite (Phase 12)**: Depends on the implementation it pins — US1 (T015–T017), US2 (T019–T020), US4 (T025–T026), US5 (T028). T043 (card) needs only Foundational T010; T042 harness precedes T043–T049.
- **Consolidated deliverables (Phases 13-18)**: Independent feature expansions from separate `/speckit-tasks` runs (HTTP startup entrypoint, local config, resolution integration test, behavioral analyzer, mock data store, AgentCore app wrapper). Each depends primarily on US1 (`service.assess` T016) plus the foundation; per-phase dependency/parallelism notes are inline at the end of each phase. All reuse the runtime/transport/contract as-is (no new topic/contract/dependency).

### Within Each User Story

- TDD tests are written first and must FAIL before the implementation task in the same phase.
- Models (Phase 2) before scoring; scoring before service; service before the Kafka entrypoint.
- Core verdict path (US1) before result-event (US2), uncertainty (US4), audit (US6), and AgentCore CLI (P10, story AC).

### Parallel Opportunities

- Setup: T002, T003 in parallel.
- Foundational: T004, T005, T006, T007, T008, T010, T011 are all different files / independent and run in parallel; T009 follows T008.
- Per story, all `[P]` test tasks (T012/T013/T014; T023/T024; etc.) run in parallel before their implementation tasks.
- Phase 10 (AC) tasks T032, T034, T036, T037, T038 are independent files and run in parallel once US1 is done; T033 (executor) precedes T035 (config pointing at it).
- Once Foundational is complete, US1 must land first; thereafter US2, US3, US7, and Phase 10 (AgentCore) can proceed in parallel by different developers.
- Phase 12: T042 (harness) and T043 (card, unit) can start as soon as their deps land; T043–T049 share one file (`test_a2a_contract.py`) so they are authored sequentially, not in parallel with each other.

---

## Parallel Example: Foundational (Phase 2)

```bash
# Different files, no interdependencies — launch together:
Task: "Define RiskLevel enum in apps/agents/risk_fraud/models.py"           # T004
Task: "Define owned-signal models + RiskSignals in models.py"               # T005
Task: "Define RiskAssessment output model in models.py"                     # T006
Task: "Define fraud policy + thresholds in apps/agents/risk_fraud/policy.py" # T007
Task: "Write failing test_input_validation.py"                             # T008
Task: "Implement identity.py AgentCard (assess_fraud_risk)"                 # T010
Task: "Seed mock_data.py load_signals"                                      # T011
```

## Parallel Example: User Story 1 tests

```bash
Task: "Write failing test_mock_data.py"     # T012
Task: "Write failing test_fraud_policy.py"  # T013
Task: "Write failing test_scoring.py"       # T014
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1 Setup → 2. Phase 2 Foundational (CRITICAL) → 3. Phase 3 US1.
4. **STOP and VALIDATE**: a clean customer returns `low`, a risky customer returns `elevated`/`high`, correlated to the request.
5. Demo the standalone verdict path (optionally via Phase 10 AgentCore once US1 lands).

### Incremental Delivery

1. Setup + Foundational → foundation ready.
2. US1 → correlated A2A verdict (MVP).
3. US2 → published domain event (dual-path) → 003 can consume.
4. US3 → domain-isolation guarantee; US4 → honest uncertainty; US5 → idempotency/determinism.
5. US6 → audit reconstruction; US7 → decentralization guarantee.
6. Phase 10 → AgentCore CLI project files + local-dev parity; Phase 11 → e2e + SC-009 + quickstart validation.

### Parallel Team Strategy

After Foundational + US1 land: Developer A → US2 + US6; Developer B → US3 + US7; Developer C → US4 + US5; Developer D → Phase 10 (AgentCore CLI). Converge on Phase 11 (T039 e2e proves SC-009).

---

## Notes

- `[P]` = different files, no dependency on an incomplete task.
- `[Story]` maps each task to its user story for traceability; Setup/Foundational/Polish carry no story label.
- Reused foundation/runtime/contract code is never re-created — tasks add only the `apps/agents/risk_fraud/` domain package, its AgentCore/HTTP shells, and tests.
- Verify each TDD test fails before implementing; commit after each task or logical group.
- Highlighted A2A input model: T008 (test) → T009 (model) → T011 (validation surface) cover the acceptance criteria — missing `case_id`/`ticket_id`/`customer_id` rejected, invalid input → structured A2A error, no raw sensitive customer text required.
- A2A contract suite (Phase 12, this run): the seven requested scenarios are T043–T049 in `apps/agents/risk_fraud/tests/test_a2a_contract.py`, pinning the runtime boundary distinctly from the `003`↔`005` e2e (T039). `assess_refund_risk` (requested) ≡ `assess_fraud_risk` (shipped/discovered) — T043 asserts the shipped id.

---
