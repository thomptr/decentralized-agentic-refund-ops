---
description: "Task list for Billing and Entitlement Agent"
---

# Tasks: Billing and Entitlement Agent

**Input**: Design documents from `/specs/004-billing-entitlement-agent/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Included — the plan's Testing section and the co-located `apps/agents/billing_entitlement/tests/`
layout explicitly request unit, contract, and integration tests. Test tasks precede the
implementation they cover within each story.

## Scope decision (from `/speckit-tasks` input — supersedes plan/research where noted)

This run **defines the billing result payload**. The result payload is **expanded** and the
recommendation vocabulary is the **5-value set**:

- **Expanded shared contract** — `packages/contracts/events/payloads.py:BillingRefundAnalysisCompletedPayload`
  is modified (not reused as-is) to add `case_id`, `customer_id`, `billing_account_id`,
  `subscription_status`, `invoice_status`, `payment_status`, `entitlement_status`, `usage_level`,
  `refund_window_status`, `eligible_refund_amount: Decimal` alongside the existing `ticket_id`,
  `recommendation`, `confidence`, `evidence`, `reasoning_summary`, `requires_human_review`.
  This is a deliberate **contract change** that overrides `FR-019`'s "no contract change"; the `003`
  consumer is updated in lockstep (T016/T017) so `SC-009` is met against the new shape.
- **5-value recommendation enum** — `approve_full_refund`, `approve_partial_refund`, `deny_refund`,
  `request_more_information`, `manual_review` (replaces the plan/research `approve`/`deny`/
  `requires_human_review`/`partial_refund`). The `003` normalizer mappings are extended (T016) so the
  new labels resolve instead of falling through to `indeterminate`.

## Entitlement-checker focus (this run's input)

This run implements the **entitlement checker** — the entitlement leg of the deterministic rules
engine. It classifies the agent's owned `Entitlement` fact (cross-checked against `Subscription`) so
`RP-003`, the contradiction gate, the cited `entitlement` evidence, and the confidence score all rest
on an explicit, unit-testable entitlement evaluation. Part of owned-data grounding (US3) and
uncertainty handling (US4); it adds no new dependency and reads only owned facts (FR-009). Supporting
fields land on `Entitlement` at **T005** (already added); thresholds at **T006**.

**Checks** (four signals, deterministic from the owned `Entitlement`/`Subscription` facts):

| Check | Owned field | Engine use |
|-------|-------------|------------|
| product access **granted** | `access_granted: bool` | did the customer receive what they paid for |
| product access **used** | `access_used: bool` (≈ `delivered`) | delivered/consumed value weakens a refund claim (`RP-003`) |
| subscription **feature enabled** | `feature_enabled: bool` | the disputed feature is/was switched on for the account |
| account **still has access** | `account_active: bool` (vs. `subscription.status`) | access continuity vs. a cancelled/lapsed subscription |

**Acceptance criteria** (this run):
1. **Entitlement mismatch requires manual review** — when the four signals conflict with each other or
   with the subscription (e.g. `access_granted=False` yet `access_used=True`; `account_active=True` on a
   `cancelled` subscription; `status="revoked"` while `feature_enabled=True`), the checker raises the
   **contradiction gate** → `manual_review` with lowered confidence (≈0.3) and the conflict in the
   evidence (FR-010). Realized in **T054/T055**, tested in **T053**.
2. **No entitlement found may support refund** — when the case has **no entitlement record** (or
   `access_granted=False`/`access_used=False`/not delivered), the customer did not receive the value, so
   `RP-003` contributes **approve-supporting** evidence (subject to the window/paid gates). Realized in
   **T006/T054**, tested in **T019/T053**.
3. **Active access with high usage may reduce refund eligibility** — when `account_active=True`/
   `access_used=True` **and** the usage level is `high` (`usage_ratio ≥ USAGE_HEAVY_THRESHOLD`), `RP-003`
   + `RP-004` (+ `RP-005` active-subscription) weaken the claim toward `deny_refund` (or
   `approve_partial_refund`). Realized in **T054**, tested in **T009/T053**.

The checker reuses the **same** `rules_engine.evaluate` core (T010) and the owned `BillingFacts`
(T005/T007) — an explicit, unit-testable entitlement classifier, not a second decision path. It folds
into Phases 5 (US3) and 6 (US4) and depends on US1 implementation (T005–T011). IDs continue at
**T053–T055** (above the AgentCore deliverable range, so nothing above is renumbered):

- [X] T053 [P] [US3] Write `apps/agents/billing_entitlement/tests/test_entitlement_checker.py` (covers this run's acceptance criteria): a **deterministic four-signal matrix** over representative `Entitlement`/`Subscription` inputs (`access_granted`/`access_used`/`feature_enabled`/`account_active`), each evaluated twice yielding the identical `EntitlementCheck` (no clock/random — FR-012); **mismatch combinations** (`access_granted=False` with `access_used=True`; `account_active=True` on a cancelled sub; `status="revoked"` with `feature_enabled=True`) → `manual_review` with the conflict in evidence (acceptance 1 — fails until T055); **no/absent entitlement or not-delivered** → approve-supporting via `RP-003` (acceptance 2); **active access + `high` usage** → `deny_refund`/`approve_partial_refund` (acceptance 3); and assert the emitted `entitlement` `EvidenceItem` carries a concise status summary (source=`entitlement`), never raw account internals
- [X] T054 [US3] Implement the **entitlement checker** in `apps/agents/billing_entitlement/entitlement_checker.py` (depends on T005, T006, T010): `check_entitlement(facts) -> EntitlementCheck` — a **pure, deterministic** evaluation of the four owned signals (`access_granted`, `access_used`/`delivered`, `feature_enabled`, `account_active` vs. `subscription.status`) returning `granted`/`used`/`feature_enabled`/`has_access` booleans, a `mismatch: bool` flag (signals conflict with each other or the subscription), and a concise `summary` string; plus `build_entitlement_evidence(check) -> EvidenceItem` (source=`entitlement`). Integrate into `apps/agents/billing_entitlement/rules_engine.py` `RP-003`: no/absent or not-used entitlement → approve-supporting; delivered/used → weakens; active access + `high` usage → weakens (with `RP-004`/`RP-005`); emit the `entitlement` `EvidenceItem` + the `RP-003` policy reference. Add the four signal fields on `Entitlement` in `apps/agents/billing_entitlement/models.py` (T005, done)
- [X] T055 [US4] In `apps/agents/billing_entitlement/rules_engine.py`, feed an **entitlement `mismatch`** (from `entitlement_checker.check_entitlement`, T054) into the contradiction gate (T010/T023): set `requires_human_review=True`, recommend `manual_review`, lower confidence (≈0.3), and capture the conflicting signals in `evidence`/`reasoning_summary` rather than emitting a confident verdict — acceptance 1, consistent with the contradiction gate and the confidence schedule (research R6)
## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1–US7)
- All paths are repo-root-relative; run commands from the repo root inside WSL/Linux.

## Path conventions

Single Python project. The agent lives in `apps/agents/billing_entitlement/` (expanded from the
single-file stub); shared contracts in `packages/contracts/`; the reused runtime/transport/audit in
`src/agent_foundation/` (no edits). The consumer being kept compatible is
`apps/agents/customer_resolution/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the domain package skeleton and test scaffolding.

- [X] T001 [P] Create the billing_entitlement domain module files with module docstrings only:
  `apps/agents/billing_entitlement/models.py`, `mock_data.py`, `policy.py`, `rules_engine.py`,
  `service.py` (mirrors the `003` package shape from plan.md Project Structure).
- [X] T002 [P] Create the test package scaffolding in `apps/agents/billing_entitlement/tests/`:
  `__init__.py` and `conftest.py` with shared fixtures — a valid `RefundEligibilityRequest`-shaped
  input dict, a `requires_broker` integration marker, and a Kafka broker fixture mirroring
  `apps/agents/customer_resolution/tests/conftest.py`.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The expanded shared contract and the domain data structures every user story depends on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T003 Expand `BillingRefundAnalysisCompletedPayload` in
  `packages/contracts/events/payloads.py`: add `case_id: UUID`, `customer_id: str`,
  `billing_account_id: str | None = None`, `subscription_status: str`, `invoice_status: str`,
  `payment_status: str`, `entitlement_status: str`, `usage_level: str`, `refund_window_status: str`,
  `eligible_refund_amount: Decimal` (import `Decimal` from `decimal`) — keeping the existing
  `ticket_id`, `recommendation`, `confidence`, `evidence`, `reasoning_summary`,
  `requires_human_review`. Keep `model_config = ConfigDict(frozen=True, extra="forbid")`. Give the
  newly added non-`recommendation` fields safe defaults where the `003` consumer would otherwise fail
  to deserialize older events (`billing_account_id` defaults `None`; status strings may default to a
  sentinel like `"unknown"`), and confirm `Decimal` round-trips through `model_dump(mode="json")`.
- [X] T004 Confirm `src/agent_foundation/payloads/__init__.py:PAYLOAD_REGISTRY[TOPIC_BILLING_RESULT]`
  still resolves to the expanded `BillingRefundAnalysisCompletedPayload` (no edit expected — verify the
  import path and that `TOPIC_BILLING_RESULT` is in `transport/topics.py:_CANONICAL_TOPICS` /
  `TOPIC_NAMES`, per `contracts/topics.md`).
- [X] T005 Implement domain models in `apps/agents/billing_entitlement/models.py`: a
  `Recommendation` StrEnum (`approve_full_refund`, `approve_partial_refund`, `deny_refund`,
  `request_more_information`, `manual_review`); `RefundEligibilityRequest` (Pydantic v2,
  `extra="ignore"`, fields per `contracts/analyze-refund-eligibility.input.schema.json`:
  `case_id: UUID`, `ticket_id`, `customer_id`, `requested_refund_amount: float ≥ 0`,
  `purchase_reference`, optional `customer_message_summary`, `policy_context`); the five owned-fact
  models `Subscription`, `Invoice`, `Payment`, `Entitlement` (incl. this run's entitlement-checker signals `access_granted`/`access_used`/`feature_enabled`/`account_active`), `ProductUsage` and the `BillingFacts`
  aggregate (each sub-model `None`-able) per data-model.md §2; and `EligibilityRecommendation`
  (`recommendation: Recommendation`, `confidence: float [0,1]`, `evidence: list[EvidenceItem]`,
  `policy_references: list[str]`, `reasoning_summary`, `requires_human_review`,
  `eligible_refund_amount: Decimal`, and the derived `*_status`/`usage_level`/`refund_window_status`
  strings) per data-model.md §4.
- [X] T006 [P] Implement `apps/agents/billing_entitlement/policy.py`: a named `RefundPolicy` with
  `policy_name="poc-refund-policy"`, `policy_version="1.0.0"`, constants `REFUND_WINDOW_DAYS=30` and
  `USAGE_HEAVY_THRESHOLD=0.8`, and `PolicyRule` entries `RP-001`..`RP-005` (id, name, description) per
  `contracts/refund-policy.md`. Depends on T005.
- [X] T007 [P] Implement `apps/agents/billing_entitlement/mock_data.py`: the seeded owned-fact dataset
  and `load_facts(purchase_reference: str, customer_id: str) -> BillingFacts | None` keyed by
  `purchase_reference` (fallback `customer_id`), with the seed rows from `contracts/mock-billing-data.md`
  (`PR-APPROVE`, `PR-WINDOW-EXPIRED`, `PR-UNPAID`, `PR-ALREADY-REFUNDED`, `PR-HEAVY-USAGE`,
  `PR-CONTRADICTION`, `PR-BORDERLINE`); a miss returns `None`. Depends on T005.

**Checkpoint**: Contract expanded, registry verified, domain models + policy + data ready.

---

## Phase 3: User Story 1 - Analyze Refund Eligibility on a Peer Request (Priority: P1) 🎯 MVP

**Goal**: The agent stands up as an independent domain agent that accepts an `analyze_refund_eligibility`
task and returns a recommendation correlated to the originating request (approve vs. deny on clear cases).

**Independent Test**: Send a request whose facts clearly warrant a refund → recommendation
`approve_full_refund`; send one that clearly does not → `deny_refund`; each correlated to the request.

### Tests for User Story 1

- [X] T008 [P] [US1] Input-validation tests in
  `apps/agents/billing_entitlement/tests/test_input_validation.py`: valid `data` part accepted;
  missing/empty required field or non-`data` input part → invalid (handler raises) (FR-002/FR-011).
- [X] T009 [P] [US1] Rules-engine truth-table tests in
  `apps/agents/billing_entitlement/tests/test_rules_engine.py`: the approve/deny/human-review matrix,
  the single-fact matrix off `PR-APPROVE` (SC-004), the documented borderline sides, and fixed
  per-path confidence values (research R6). Map expected `recommendation` to the 5-value enum.

### Implementation for User Story 1

- [X] T010 [US1] Implement `evaluate(facts, request, policy) -> EligibilityRecommendation` in
  `apps/agents/billing_entitlement/rules_engine.py` as a pure deterministic function following the
  precedence in `contracts/refund-policy.md` (data-completeness gate → contradiction gate → hard
  denials RP-001/RP-002 → usage gate RP-004 → approve → no-applicable-rule default), emitting the
  5-value `Recommendation` (`approve_full_refund`; `approve_partial_refund` for the policy-configured
  partial path; `deny_refund`; `request_more_information` for missing/unresolvable data;
  `manual_review` for contradictions / no-applicable-rule), the per-path confidence (0.9/0.6/0.3/0.2),
  and `requires_human_review`. Depends on T005–T007.
- [X] T011 [US1] Implement `service.py` orchestration in
  `apps/agents/billing_entitlement/service.py`: `validate input → load_facts → evaluate → build A2A
  output data part` as a pure function; raise a clear error on invalid input (no fabricated verdict,
  FR-011). The A2A `data` part carries `recommendation`, `confidence`, `evidence`,
  `reasoning_summary`, `requires_human_review` so `003`'s `normalize_billing_result` resolves it.
- [X] T012 [US1] Replace the stub `apps/agents/billing_entitlement/main.py` with the real entrypoint:
  `AgentIdentity` + `AgentCard` advertising the single `analyze_refund_eligibility` capability
  (drop the "(mock)" description), an async `main()` that registers the handler closure and calls
  `runtime.serve(stop_event)` with signal handling per `research.md` R2. The handler validates input,
  calls `service`, and returns the correlated `A2AMessage`. (Domain Publisher is added in US2.)

**Checkpoint**: A peer can request analysis and receive an approve/deny recommendation correlated to its task.

---

## Phase 4: User Story 2 - Publish a Structured Billing Result Event (Priority: P1)

**Goal**: Each completed analysis publishes exactly one structured `BillingRefundAnalysisCompletedPayload`
on `TOPIC_BILLING_RESULT` (the expanded shape) and returns the same verdict on the A2A path (FR-008).

**Independent Test**: Drive one analysis end-to-end → exactly one result event correlated to the case,
carrying the recommendation, a confidence in range, a non-empty evidence set, `policy_references`, a
reasoning summary, and the populated billing-status fields + `eligible_refund_amount`.

### Tests for User Story 2

- [X] T013 [P] [US2] Result-contract test in
  `apps/agents/billing_entitlement/tests/test_result_contract.py`: build the expanded
  `BillingRefundAnalysisCompletedPayload`, assert a JSON round-trip (including `Decimal`
  `eligible_refund_amount` and the new status fields), assert `PAYLOAD_REGISTRY[TOPIC_BILLING_RESULT]`
  resolves it, and assert the A2A result `data`-part shape matches what `003`'s normalizer consumes.

### Implementation for User Story 2

- [X] T014 [US2] Add `build_result_payload(recommendation, facts, request)` in
  `apps/agents/billing_entitlement/service.py` mapping `EligibilityRecommendation` + `BillingFacts` +
  request onto the expanded payload: `case_id`, `ticket_id`, `customer_id`, `billing_account_id`,
  `subscription_status`/`invoice_status`/`payment_status`/`entitlement_status`/`usage_level`/
  `refund_window_status` derived from the owned facts, `eligible_refund_amount: Decimal`,
  `recommendation`, `confidence`, `evidence`, `reasoning_summary`, `requires_human_review`.
- [X] T015 [US2] In `apps/agents/billing_entitlement/main.py`, open a handler-owned
  `async with Publisher(identity, BROKER_URL) as domain_pub` in the async entrypoint and have the
  handler closure publish the payload to `TOPIC_BILLING_RESULT` with `correlation_id = request.case_id`
  and `causation_id` derived from the inbound request envelope `event_id` (dual-path delivery,
  research R2/R8); the runtime A2A result path is unchanged.
- [X] T016 [US2] Extend the `003` consumer mappings in
  `apps/agents/customer_resolution/event_handlers.py` — in both `normalize_billing_result`
  (~lines 83–90) and `billing_result_handler` (~lines 536–543) add:
  `approve_full_refund → eligible`, `approve_partial_refund → partial`, `deny_refund → ineligible`,
  `request_more_information → indeterminate`, `manual_review → indeterminate` (with
  `requires_human_review` routing to escalation). Keep the legacy `approve`/`deny`/`partial_refund`
  values for backward compatibility.
- [X] T017 [P] [US2] Update the `003` adapter tests in
  `apps/agents/customer_resolution/tests/test_adapters.py` to cover the five new recommendation labels
  mapping to the correct `BillingFinding.eligibility` (proves SC-009 against the new vocabulary).

**Checkpoint**: A completed analysis emits one expanded result event and the matching A2A output; `003` consumes both.

---

## Phase 5: User Story 3 - Ground Every Recommendation in Owned Billing & Entitlement Data (Priority: P1)

**Goal**: Every recommendation is derived solely from the five owned fact domains + published policy,
with each evidence item and policy reference tracing back to an owned source — no foreign-domain data,
no synchronous peer call.

**Independent Test**: Vary one billing fact at a time (window, paid state, entitlement, usage) and
confirm the verdict and evidence change accordingly, with every `EvidenceItem.source` in the owned set.

### Tests for User Story 3

- [X] T018 [P] [US3] Mock-data lookup tests in
  `apps/agents/billing_entitlement/tests/test_mock_data.py`: each seeded `purchase_reference` resolves
  the expected `BillingFacts`; an unknown reference returns `None` (missing-data path, FR-003/FR-010).
- [X] T019 [P] [US3] Policy tests in
  `apps/agents/billing_entitlement/tests/test_refund_policy.py`: each named rule `RP-001`..`RP-005`
  fires on its triggering fact, and the borderline boundaries resolve to the documented inclusive side.
- [X] T020 [P] [US3] Domain-isolation test in
  `apps/agents/billing_entitlement/tests/test_domain_isolation.py`: every produced `EvidenceItem.source`
  is in `{subscription, invoice, payment, entitlement, product_usage, refund_policy}`; no risk/fraud or
  foreign field is read (SC-003/FR-009).

### Implementation for User Story 3

- [X] T021 [US3] In `apps/agents/billing_entitlement/rules_engine.py`, populate `evidence`
  (non-empty, SC-002) and `policy_references` for every verdict: each consulted owned fact and each
  fired policy rule contributes an `EvidenceItem` whose `source` is an owned domain or `refund_policy`,
  and the cited rule ids (`RP-00x`) are recorded in `policy_references`. Depends on T010.

**Checkpoint**: Verdicts demonstrably track single billing facts; all evidence traces to owned data.

---

## Phase 6: User Story 4 - Handle Cases It Cannot Confidently Decide (Priority: P2)

**Goal**: Missing/contradictory data → `manual_review`/`request_more_information` with a recorded
reason and lowered confidence; malformed/unanalyzable input → a failure result with a reason — never a
fabricated verdict.

**Independent Test**: Request `PR-UNKNOWN-XYZ` → `request_more_information`/`manual_review`,
`confidence≈0.2`, reason recorded; `PR-CONTRADICTION` → `manual_review`, `confidence≈0.3`, conflict in
evidence; malformed input → `TaskResult(status="failed")`. A well-formed case still returns a normal verdict.

### Tests for User Story 4

- [X] T022 [P] [US4] Uncertainty/fault tests in
  `apps/agents/billing_entitlement/tests/test_rules_engine.py` (missing + contradictory paths,
  confidence lowering) and `tests/test_input_validation.py` (malformed input → failure), asserting no
  confident fabricated approve/deny and that a reason is captured (FR-010/FR-011, SC-005).

### Implementation for User Story 4

- [X] T023 [US4] In `apps/agents/billing_entitlement/service.py` (and the `main.py` handler), ensure
  invalid/unanalyzable input raises so the runtime emits `TaskResult(status="failed",
  error.category="handler_error")` with the reason, and that the missing-data/contradiction
  recommendations from T010 carry their recorded reason in `reasoning_summary`/`evidence`. Depends on
  T010–T012.

**Checkpoint**: Uncertainty surfaces honestly; malformed input fails cleanly with a reason.

---

## Phase 7: User Story 5 - Idempotent, Repeatable Analysis (Priority: P2)

**Goal**: Re-delivery of the same request yields one logical verdict and no duplicate result event;
identical facts under the same policy always yield the same verdict (determinism).

**Independent Test**: Submit the same `task_id` twice → no second analysis, no duplicate
`billing.refund-analysis.completed` event, `duplicate_skipped` audit entry; same facts → same verdict.

### Tests for User Story 5

- [X] T024 [P] [US5] Determinism test in
  `apps/agents/billing_entitlement/tests/test_rules_engine.py`: evaluating the same
  `(facts, request, policy)` repeatedly yields an identical `EligibilityRecommendation` (FR-012/SC-006).

### Implementation for User Story 5

- [X] T025 [US5] Confirm the runtime's `task_id` `IdempotencyTracker` short-circuits a redelivered
  request **before** the handler runs so the domain publish happens at most once (no domain code change
  expected — verify in `apps/agents/billing_entitlement/main.py` that the publish is inside the
  deduped handler path; document the at-least-once crash-window gap per research R7). Full redelivery
  behavior is asserted by the integration test (T028).

**Checkpoint**: Replays are safe; the verdict is reproducible.

---

## Phase 8: User Story 6 - Audit Every Analysis (Priority: P2)

**Goal**: Request-received, the analysis decision (with evidence + policy refs), the published result,
and any failure/human-review reason leave a correlated, immutable trail queryable by correlation id.

**Independent Test**: Drive an analysis, then `query_by_correlation` → ordered trail (`accepted` →
`completed`, or fault reasons) attributed to `billing-entitlement-agent` in causal order.

### Implementation for User Story 6

- [X] T026 [US6] Add `structlog` instrumentation in the `apps/agents/billing_entitlement/main.py`
  handler and `service.py`: log request-received, the decision (recommendation + evidence +
  `policy_references`), the published result, and any human-review/failure reason — relying on the
  reused runtime for the `accepted`/`completed`/`failed`/`duplicate_skipped` task-audit events (FR-014).
  The reconstruction itself is exercised by T028 and quickstart Scenario F.

**Checkpoint**: Every step is observable and reconstructable by correlation id.

---

## Phase 9: User Story 7 - Stay an Independent Domain Agent (Priority: P3)

**Goal**: The agent only responds to refund-eligibility requests addressed to it; it originates no task
requests and dispatches no work for others.

**Independent Test**: Inspect interactions — each is a refund analysis in response to a request; no
outbound `TaskRequest`, no routing.

### Tests for User Story 7

- [X] T027 [P] [US7] No-supervisor test in
  `apps/agents/billing_entitlement/tests/test_no_supervisor.py`: the agent module/handler issues no
  `TaskRequest` to any peer and dispatches no work (SC-008), mirroring
  `apps/agents/customer_resolution/tests/test_no_supervisor.py`.

**Checkpoint**: Decentralization guardrail proven.

---

## Phase 10: Polish & Cross-Cutting Concerns

- [X] T028 End-to-end integration test in
  `apps/agents/billing_entitlement/tests/test_billing_agent_e2e.py` (testcontainers Kafka): quickstart
  Scenarios A–F — approve / deny / missing+contradictory → human review / malformed → failed /
  idempotent redelivery / audit reconstruction — plus the `003 ↔ 004` round-trip proving SC-009 and the
  dual-path delivery dedup (research R8).
- [X] T029 Remove obsolete stub behavior from `apps/agents/billing_entitlement/main.py` (the fixed
  `{"eligible": True}` verdict and, if no longer needed, the `"FAIL"` text sentinel) and confirm the
  `AgentCard` description no longer says "(mock)".
- [X] T030 [P] Run the `specs/004-billing-entitlement-agent/quickstart.md` validation Scenarios A–F
  against a local broker and confirm the expected events/audit.
- [X] T031 [P] Refresh the agent context file via the Spec Kit agent-context update if module paths or
  the contract change need recording (`speckit-agent-context-update`).

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (Phase 1)**: no dependencies.
- **Foundational (Phase 2)**: depends on Setup; **blocks all user stories**. T005 blocks T006/T007;
  T003 blocks the result-contract and consumer tasks.
- **User Stories (Phase 3+)**: all depend on Foundational. US1 is the MVP front door; US2 and US3 build
  on US1's rules engine/service (T010/T011). US4 depends on US1's engine/handler. US5/US6/US7 verify
  behavior established by US1–US2.
- **Polish (Phase 10)**: depends on the user stories it validates (T028 needs US1–US6).

### User story dependencies

- **US1 (P1)**: after Foundational. The base verdict path (rules engine + service + entrypoint).
- **US2 (P1)**: after US1 (uses `EligibilityRecommendation` + handler). Adds the published event,
  expanded payload mapping, and the `003` consumer update.
- **US3 (P1)**: after US1 (enriches evidence/policy refs on the engine output).
- **US4 (P2)**: after US1. Uncertainty/failure paths.
- **US5 (P2)**: after US1–US2 (idempotent publish + determinism).
- **US6 (P2)**: after US1–US2 (audit/observability of the established steps).
- **US7 (P3)**: independent guardrail; after US1 establishes behavior.

### Within each user story

- Tests before implementation; models before services; services before the entrypoint/handler;
  core verdict path before evidence enrichment and the published event.

---

## Parallel Opportunities

- **Setup**: T001 and T002 in parallel.
- **Foundational**: T006 and T007 in parallel (both after T005).
- **US1 tests**: T008 and T009 in parallel before T010–T012.
- **US3 tests**: T018, T019, T020 in parallel.
- **US2**: T017 (consumer tests) parallel with the contract test T013.
- **Polish**: T030 and T031 in parallel.

### Parallel example: User Story 3

```bash
# Launch the US3 tests together (all different files):
Task: "Mock-data lookup tests in apps/agents/billing_entitlement/tests/test_mock_data.py"
Task: "Policy tests in apps/agents/billing_entitlement/tests/test_refund_policy.py"
Task: "Domain-isolation test in apps/agents/billing_entitlement/tests/test_domain_isolation.py"
```

---

## Implementation Strategy

### MVP first (User Stories 1–3, all P1)

1. Phase 1 Setup → Phase 2 Foundational (expanded contract + models + policy + data).
2. US1 → a peer gets an approve/deny recommendation correlated to its task.
3. US2 → the expanded result event is published and `003` consumes it (SC-009).
4. US3 → every verdict is grounded in owned data with traceable evidence.
5. **STOP and VALIDATE**: quickstart Scenarios A–B end-to-end.

### Incremental delivery

- Add US4 (uncertainty/failure), then US5 (idempotency/determinism), then US6 (audit), then US7
  (independence guardrail), validating each independently.
- Finish with Phase 10 (e2e + quickstart + stub cleanup).


---

# Local Startup Entrypoint Deliverable — AWS AgentCore (this run's input)

A focused increment that lets the agent be **run locally with the AWS AgentCore CLI** and **called
independently by a test client** over HTTP, in addition to its Kafka A2A endpoint. Setup follows the
AgentCore CLI guide
(<https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-cli.html#setup-project>).

> **Numbering note**: IDs continue after the implementation track (which ends at **T031**); this
> deliverable uses **T032–T041** and renumbers nothing above it. References to body tasks are by file/role
> as well as id, so they remain valid: `service.analyze` = **T011**, the `main.py` entrypoint/card = **T012**
> (US1 implementation = T010–T012).

The agent exposes two HTTP routes (A2A protocol mode — `agentcore create --protocol A2A`):

- **`GET /.well-known/agent.json`** — serves the **Agent Card** (the same `AgentCard` the Kafka entrypoint
  publishes for discovery), whose `capabilities` list **`analyze_refund_eligibility`**.
- **`POST /a2a/tasks`** — accepts an A2A `analyze_refund_eligibility` task, runs the **same**
  `service.analyze` pipeline (T011), and returns the structured recommendation in the HTTP response. This
  surface does **not** publish to Kafka — the domain result event stays the Kafka entrypoint's job (US2).

**Acceptance criteria** (this run):
1. **Agent Card lists `analyze_refund_eligibility`** — `GET /.well-known/agent.json` returns a card whose
   capabilities include `analyze_refund_eligibility`. Realized by **T036** (shared card builder) + **T038**
   (the `.well-known` route); validated by **T037**.
2. **Agent can be called independently by a test client** — a standalone client GETs the card and POSTs a
   task to `/a2a/tasks`, receiving an approve/deny recommendation, with **no broker and no other agent
   running**. Realized by **T038** (`POST /a2a/tasks`) + **T039** (the `dev_a2a_client.py` test client);
   launchable via `agentcore dev` (**T040**).

This deliverable reuses the **same** `service.analyze` core (T011) and the `AgentCard` built in the
`main.py` entrypoint (T012) — it adds a thin HTTP transport adapter, not a second decision engine. It
depends on US1 implementation (T010–T012).

---

## Phase L1: AgentCore CLI Setup

- [X] T032 [P] Install and verify the AWS AgentCore CLI per the setup-project guide — prerequisites Node.js 20+ and Python 3.10+; run `npm install -g @aws/agentcore` then `agentcore --help`; record the verified CLI version and prerequisites in `apps/agents/billing_entitlement/agentcore/README.md`
- [X] T033 [P] Scaffold the AgentCore **A2A** project config under `apps/agents/billing_entitlement/agentcore/` (`agentcore create … --protocol A2A`, or hand-author) — `agentcore.json`, `aws-targets.json`, and `.env.local` (`AGENT_BROKER_URL=localhost:9092`, `PORT=8080`); add `apps/agents/billing_entitlement/agentcore/.env.local` to `.gitignore`
- [X] T034 [P] Add the local-HTTP entrypoint dependencies (`fastapi`, `uvicorn[standard]`, `httpx`) under an optional `http` group in `pyproject.toml` `[project.optional-dependencies]`; annotate inline that they support **only** the local AgentCore HTTP surface — the Kafka domain agent and the feature's "no new dependency" stance are unchanged for the agent itself (the scoped deviation introduced by this increment)
- [X] T035 [P] Register the HTTP console script in `pyproject.toml` `[project.scripts]`: `demo-billing-entitlement-http = "apps.agents.billing_entitlement.http_app:run"` (alongside the existing Kafka `demo-billing-entitlement`)

**Checkpoint**: `agentcore` CLI installed and configured for an A2A agent; HTTP deps + script available.

---

## Phase L2: HTTP A2A Startup Entrypoint + Independent Test Client (Priority: P1) 🎯 Increment MVP

**Goal**: Serve `GET /.well-known/agent.json` and `POST /a2a/tasks` from a local HTTP app launchable via
`agentcore dev`, and prove it is independently callable.

**Independent Test**: With no broker and no other agent running, `GET /.well-known/agent.json` returns a
card listing `analyze_refund_eligibility`, and `POST /a2a/tasks` for an approve-case `purchase_reference`
returns `approve` / a window-expired one returns `deny` — driven by the standalone `dev_a2a_client.py`.

- [X] T036 [US1] Extract a shared identity/card builder into `apps/agents/billing_entitlement/identity.py` — `build_identity()` (`AgentIdentity` for `billing-entitlement-agent`) and `build_agent_card()` (the `AgentCard` whose `capabilities` is exactly `[Capability("analyze_refund_eligibility", …)]`), refactored out of the T012 `main.py` entrypoint so the Kafka runtime and the HTTP app serve the **same** card (acceptance 1). Update `main.py` (T012) to consume it. Depends on T012
- [X] T037 [P] [US1] Write `apps/agents/billing_entitlement/tests/test_http_entrypoint.py` (FastAPI `TestClient`, no broker): `GET /.well-known/agent.json` returns a card whose `capabilities` include `analyze_refund_eligibility` (acceptance 1); `POST /a2a/tasks` with a sample `analyze_refund_eligibility` task returns the recommendation in the response `data` part (acceptance 2); a malformed task returns a failed `TaskResult` with a reason (FR-011)
- [X] T038 [US1] Implement the HTTP A2A startup entrypoint `apps/agents/billing_entitlement/http_app.py` — a FastAPI app exposing `GET /.well-known/agent.json` (serves `build_agent_card().model_dump(mode="json")` from T036), `POST /a2a/tasks` (parse the A2A `TaskRequest` body → `service.analyze` (T011) → return a `TaskResult`/`A2AMessage` JSON; malformed/unanalyzable input → failed `TaskResult` with reason, mirroring the service validation path / FR-011), and `GET /ping` (AgentCore local health). `run()` launches `uvicorn` on `PORT` (default 8080). Reuses `service.analyze` (T011) and `build_agent_card` (T036); publishes nothing to Kafka. Depends on T011, T036
- [X] T039 [P] [US1] Implement the standalone independent test client `apps/agents/billing_entitlement/dev_a2a_client.py` (`httpx`) — GET the agent card and assert `analyze_refund_eligibility` is listed, POST a sample task to `/a2a/tasks`, and print the returned recommendation; proves the agent is callable independently with no broker/other agent (acceptance 2). Depends on T038
- [X] T040 [US1] Point `agentcore dev` at `http_app:run` on port 8080 (entrypoint reference in `apps/agents/billing_entitlement/agentcore/agentcore.json`) and document the local run/invoke flow (`agentcore dev`, `agentcore dev '<json>'`, `python -m apps.agents.billing_entitlement.dev_a2a_client`) in `apps/agents/billing_entitlement/agentcore/README.md`. Depends on T033, T038, T039

**Checkpoint**: ✅ Agent runs locally over HTTP via the AgentCore CLI; its card lists
`analyze_refund_eligibility`; the test client calls it independently and gets approve/deny. **Increment
acceptance met.**

---

## Phase L3: Documentation Polish (Startup Entrypoint)

- [X] T041 [P] Update `specs/004-billing-entitlement-agent/quickstart.md` and `README.md` with the local AgentCore HTTP run path — `agentcore dev` on `:8080`, `GET /.well-known/agent.json` + `POST /a2a/tasks` examples, and `python -m apps.agents.billing_entitlement.dev_a2a_client` — alongside the existing Kafka run (`python -m apps.agents.billing_entitlement.main`)

---

## Local Startup Entrypoint — Dependencies, Parallelism & Strategy

### Dependencies

- **L1 Setup (T032–T035)**: no dependencies; can run immediately and in parallel with the implementation tracks
- **L2 (T036–T040)**: depends on US1 implementation — `service.analyze` (T011) and the `main.py` card (T012, refactored into `identity.py` by T036); the HTTP app (T038) needs T011+T036; the client (T039) needs T038; the `agentcore dev` wiring (T040) needs T033+T038+T039
- **L3 (T041)**: depends on T038–T040 (documents the finished flow)

### Parallel opportunities

- All of L1 (T032, T033, T034, T035) run in parallel (CLI install / config / deps / script — different files)
- T037 (HTTP test) can be authored in parallel with T036; T038 then makes it pass; T039 follows T038
- T041 runs alongside any L-phase once T038–T040 land

### Increment MVP

1. L1 → AgentCore CLI installed/configured + HTTP deps/script
2. L2 → `identity.py` + `http_app.py` (`GET /.well-known/agent.json`, `POST /a2a/tasks`) + `dev_a2a_client.py`
3. **STOP and VALIDATE**: `agentcore dev`, then `python -m apps.agents.billing_entitlement.dev_a2a_client` → card lists `analyze_refund_eligibility` and an approve/deny comes back — **acceptance met**
4. L3 → document the local HTTP run path
