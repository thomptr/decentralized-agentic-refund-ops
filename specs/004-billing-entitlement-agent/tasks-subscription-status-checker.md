---
description: "Task list for the Subscription Status Checker — a component of the Billing and Entitlement Agent"
---

# Tasks: Subscription Status Checker (Billing and Entitlement Agent)

**Input**: Design documents from `/specs/004-billing-entitlement-agent/`

**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅

**Relationship to `tasks.md`**: This is a **companion** task list for one component of the feature.
The primary `tasks.md` covers the deterministic **refund-eligibility recommendation engine**
(`rules_engine.py`). This file covers the **subscription status checker** the engine consumes —
the module that resolves an account's normalized subscription status from owned facts. Task IDs are
prefixed `S0xx` so they never collide with `tasks.md`'s `T0xx`. Where the two overlap (the
`Subscription` model in `models.py`, the seeded `mock_data.py`), this file's tasks **extend** rather
than redefine, and call out the reconciliation explicitly.

**Scope (this task set)**: Resolve an account's subscription status into exactly one of:

`active`, `trialing`, `past_due`, `canceled`, `expired`, `unknown`

**Acceptance criteria (from request)**:
- A **missing account** (no owned subscription record) resolves to `unknown`.
- An **enterprise or otherwise ambiguous** account can be flagged as **requires manual review**.
- Every status output **includes evidence** naming the owned facts that determined it.

**Status-vocabulary reconciliation (decision: new checker, map to existing)**: The six statuses here
are a **refinement** over `data-model.md` §2's `Subscription.status` (`active`/`cancelled`/`lapsed`).
This task set adds a new `SubscriptionStatus` enum and a dedicated `subscription_status.py` module,
and includes an explicit task (S005) to map the new vocabulary onto the existing field
(`cancelled → canceled`, `lapsed → expired`, plus the new `trialing`/`past_due`/`unknown`) and to flag
`data-model.md` for a follow-up revision — without breaking the existing `Subscription` model or the
recommendation engine that reads it.

**Tests**: INCLUDED — `plan.md` (Testing) and `spec.md` Success Criteria (SC-001, SC-003, SC-004,
SC-005) require a unit/parameterized suite proving status resolution, the missing-account path, the
manual-review path, and evidence presence.

**Determinism (FR-012)**: The checker is a **pure function** of `(facts, policy)`; identical facts
always yield the identical status.

**Domain isolation (FR-009 / SC-003)**: Every status and every evidence item derives **solely** from
the agent's owned billing/entitlement facts — never risk/fraud or another agent's data, and never via
a synchronous peer call.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1–US4 (this component's user stories; each maps to spec.md stories, noted inline)
- All paths are repo-root-relative; the agent package is `apps/agents/billing_entitlement/`

## Path Conventions

- Component module: `apps/agents/billing_entitlement/subscription_status.py`
- Shared (extended, not redefined): `apps/agents/billing_entitlement/models.py`, `mock_data.py`, `policy.py`
- Co-located tests: `apps/agents/billing_entitlement/tests/`
- **REUSED UNCHANGED** (do not modify): `src/agent_foundation/`, `packages/contracts/` (`EvidenceItem` is reused)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish the module and test surface for the checker without changing shared contracts.

- [ ] S001 Create the component module stub (module docstring only) `apps/agents/billing_entitlement/subscription_status.py`; if `apps/agents/billing_entitlement/models.py`, `mock_data.py`, and `policy.py` do not yet exist (they are created in `tasks.md` Phase 1–2), create docstring-only stubs so this component can be developed independently, leaving a `# extended by tasks.md` note
- [ ] S002 [P] Ensure the co-located test package exists: `apps/agents/billing_entitlement/tests/__init__.py` and `apps/agents/billing_entitlement/tests/conftest.py` (reuse the `apps/agents/customer_resolution/tests/conftest.py` fixture style); add a `subscription` fact factory fixture if not already present
- [ ] S003 [P] Confirm no new dependency is introduced (Principle V / FR-017) — verify `pydantic` v2, `structlog`, `pytest` already resolve; do **not** edit `pyproject.toml`

**Checkpoint**: Component module + test surface import-clean.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The six-status vocabulary, the account facts the checker reads, the policy constants, and
the seeded accounts every story below depends on. **No story work can begin until this phase is done.**

**⚠️ CRITICAL**: Defines the six-member enum and the owned facts the checker resolves from.

- [ ] S004 Define the `SubscriptionStatus` enum (`enum.StrEnum`) with exactly the six members `active`, `trialing`, `past_due`, `canceled`, `expired`, `unknown` in `apps/agents/billing_entitlement/models.py`, with a docstring stating each member's deciding facts and that `unknown` is reserved for the missing/unresolvable case (never a fabricated definitive status)
- [ ] S005 Map the new vocabulary onto the existing `Subscription.status` in `apps/agents/billing_entitlement/models.py`: add a `to_subscription_status(subscription) -> SubscriptionStatus` helper implementing `active→active`, `cancelled→canceled`, `lapsed→expired`, and add the fields the richer statuses need — `account_type: Literal["standard","enterprise"]`, `trial_ends_at: datetime | None`, `current_period_end: datetime`, `last_payment_failed: bool` — keeping the existing `status`/`term`/`started_at`/`renewed_at` fields intact so the recommendation engine (`tasks.md` T013) is unaffected. Add a one-line `# TODO(data-model.md): reconcile six-status vocabulary` note flagging the doc revision
- [ ] S006 Define the `SubscriptionStatusResult` model in `apps/agents/billing_entitlement/models.py` (Pydantic v2, `extra="forbid"`): `status: SubscriptionStatus`, `requires_human_review: bool`, `evidence: list[EvidenceItem]` (reusing `packages/contracts/events/payloads.py:EvidenceItem`), `reasoning: str`; add a validator asserting `evidence` is non-empty so the "includes evidence" invariant holds by construction
- [ ] S007 [P] Add status-checker policy constants to `apps/agents/billing_entitlement/policy.py`: `PAST_DUE_GRACE_DAYS` (grace before past_due → expired), an `ENTERPRISE_REQUIRES_REVIEW = True` rule, and a citable `policy_reference` id (e.g. `SS-001`..`SS-00x` in the `policy_name@policy_version` style of `contracts/refund-policy.md`)
- [ ] S008 [P] Seed `apps/agents/billing_entitlement/mock_data.py` with subscription fixtures keyed by account id covering every branch — one each of `active`, `trialing`, `past_due`, `canceled`, `expired`; one `enterprise` account; one internally contradictory account (e.g. `status="active"` with `current_period_end` long past, or active entitlement on a cancelled subscription); and ensure at least one referenced account id has **no** record. Expose `lookup_subscription(account_id) -> Subscription | None`

**Checkpoint**: Enum, account facts, policy constants, and dataset ready — stories can proceed.

---

## Phase 3: User Story 1 - Resolve a Definitive Subscription Status (Priority: P1) 🎯 MVP

**Goal**: Given an account with owned facts, the checker returns exactly one definitive status
(`active`, `trialing`, `past_due`, `canceled`, or `expired`), determined deterministically from those
facts and the policy. (Maps to spec US1/US3; SC-001, SC-004.)

**Independent Test**: Five accounts whose facts clearly imply each definitive status return that
status; flipping a single relevant fact (e.g. `current_period_end` future→past) changes the result.

### Tests for User Story 1 (write first; ensure they FAIL before implementation)

- [ ] S009 [P] [US1] Write parameterized happy-path tests in `apps/agents/billing_entitlement/tests/test_subscription_status.py` asserting each of `active`, `trialing`, `past_due`, `canceled`, `expired` is returned for its seeded account from `mock_data.py`
- [ ] S010 [P] [US1] Write a single-fact-matrix + determinism test in `apps/agents/billing_entitlement/tests/test_subscription_status.py`: changing one fact flips the status consistently (e.g. `current_period_end` past ⇒ `expired`; `last_payment_failed=True` within grace ⇒ `past_due`), and two identical calls return an equal result (FR-012, SC-004)

### Implementation for User Story 1

- [ ] S011 [US1] Implement `check_subscription_status(subscription, policy) -> SubscriptionStatusResult` in `apps/agents/billing_entitlement/subscription_status.py` as a pure deterministic resolver over owned facts, with documented precedence: `canceled` (status cancelled) → `expired` (current_period_end in the past beyond grace) → `past_due` (payment failed, within grace) → `trialing` (trial_ends_at in the future) → `active`. No I/O, no peer call
- [ ] S012 [US1] Add explicit boundary handling in `apps/agents/billing_entitlement/subscription_status.py` so an account exactly on `current_period_end`, exactly at `trial_ends_at`, or exactly at `PAST_DUE_GRACE_DAYS` resolves to a single documented side (per spec "borderline within thresholds" edge case), recorded in `reasoning`

**Checkpoint**: The checker returns a correct, deterministic definitive status for well-formed accounts.

---

## Phase 4: User Story 2 - Status Output Includes Evidence (Priority: P1)

**Goal**: Every status result carries a non-empty evidence set; each item names its source (an owned
fact) and what it shows, plus the policy reference applied — so the status is self-describing.
(Maps to spec US2/US3; SC-002, SC-003. Satisfies the "output includes evidence" acceptance criterion.)

**Independent Test**: For any resolved status the result's `evidence` is non-empty, every item's
`source` is in `{subscription, invoice, payment, entitlement, refund_policy}`, and the cited fact
actually drove the status (e.g. an `expired` result cites `current_period_end`).

### Tests for User Story 2 (write first; ensure they FAIL before implementation)

- [ ] S013 [P] [US2] Write `apps/agents/billing_entitlement/tests/test_subscription_status_evidence.py`: assert every status result has non-empty `evidence`, each `EvidenceItem.source` is in the owned-domain/policy allowlist, and the applied policy-reference id (`SS-00x`) is present (SC-003)
- [ ] S014 [P] [US2] Add to `test_subscription_status_evidence.py` a per-status assertion that the evidence cites the specific deciding fact (e.g. `trialing` cites `trial_ends_at`; `past_due` cites `last_payment_failed`)

### Implementation for User Story 2

- [ ] S015 [US2] Extend `check_subscription_status` in `apps/agents/billing_entitlement/subscription_status.py` to emit one `EvidenceItem` per deciding fact (`source`/`description`/`value`) plus a human-readable `reasoning` string explaining how the facts + policy produced the status (FR-005, FR-006)
- [ ] S016 [US2] Constrain evidence `source` by construction in `apps/agents/billing_entitlement/subscription_status.py` to the owned-domain/policy allowlist so a foreign source is impossible, and guard that a definitive status can never be returned with empty evidence

**Checkpoint**: Every status result is self-describing with owned-domain evidence and a policy citation.

---

## Phase 5: User Story 3 - Missing Account Returns `unknown` (Priority: P2)

**Goal**: When the agent owns no subscription record for the referenced account, the checker returns
`unknown` (with evidence of the missing record) rather than fabricating a status.
(Maps to spec US4; SC-005. Satisfies the "missing account returns unknown" acceptance criterion.)

**Independent Test**: Resolving status for an account id absent from `mock_data.py` returns
`SubscriptionStatus.unknown` with evidence naming the missing lookup and a `reasoning` stating the
record was not found — and never one of the five definitive statuses.

### Tests for User Story 3 (write first; ensure they FAIL before implementation)

- [ ] S017 [P] [US3] Write `apps/agents/billing_entitlement/tests/test_subscription_status_missing.py`: an absent account id resolves to `SubscriptionStatus.unknown`, with non-empty evidence citing the missing record and a recorded `reasoning` (FR-010, SC-005)
- [ ] S018 [P] [US3] Add a negative test to `test_subscription_status_missing.py` asserting `unknown` is NEVER returned for an account that has a valid seeded record (no false-unknowns)

### Implementation for User Story 3

- [ ] S019 [US3] Implement `resolve_status_for_account(account_id: str, policy) -> SubscriptionStatusResult` in `apps/agents/billing_entitlement/subscription_status.py`: call `mock_data.lookup_subscription`; on a `None` miss return `SubscriptionStatusResult(status=unknown, evidence=[…missing record…], reasoning=…)` instead of calling `check_subscription_status`

**Checkpoint**: Missing accounts honestly surface as `unknown`, never a fabricated definitive status.

---

## Phase 6: User Story 4 - Enterprise / Ambiguous Accounts Can Require Manual Review (Priority: P2)

**Goal**: When an account is `enterprise` or its facts are internally contradictory/ambiguous, the
result carries `requires_human_review=True` with the trigger captured in evidence and reasoning,
rather than asserting a confident status. (Maps to spec US4; SC-005. Satisfies the "enterprise or
ambiguous account can require manual review" acceptance criterion.)

**Independent Test**: An `enterprise` account and an account with contradictory facts each return
`requires_human_review=True` with evidence naming the trigger; a clean standard account returns
`requires_human_review=False`.

### Tests for User Story 4 (write first; ensure they FAIL before implementation)

- [ ] S020 [P] [US4] Write `apps/agents/billing_entitlement/tests/test_subscription_status_review.py`: an `account_type="enterprise"` account yields `requires_human_review=True` with evidence citing the enterprise rule (`SS-00x`)
- [ ] S021 [P] [US4] Add to `test_subscription_status_review.py`: a contradictory-facts account (e.g. `status="active"` with `current_period_end` long past) yields `requires_human_review=True` with the conflict in evidence/reasoning, and a clean standard account yields `requires_human_review=False`

### Implementation for User Story 4

- [ ] S022 [US4] Add an ambiguity/contradiction detector in `apps/agents/billing_entitlement/subscription_status.py` that scans owned facts for conflicts and, together with the `enterprise` policy rule from `policy.py`, sets `requires_human_review=True` and appends an evidence item naming the trigger — **without changing** the underlying resolved `status` value
- [ ] S023 [US4] Compose review-flagging in `resolve_status_for_account` so it applies to both the definitive-status path (US1) and the `unknown` path (US3); record the review reason in `reasoning`

**Checkpoint**: Ambiguous and enterprise accounts surface for human review with cited triggers.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Logging, isolation proof, full truth table, and validation across all four stories.

- [ ] S024 [P] Add `structlog` step logging in `apps/agents/billing_entitlement/subscription_status.py` for status-resolved, missing-account, and review-flagged outcomes (Principle IV / FR-014), never logging foreign-domain data
- [ ] S025 [P] Write `apps/agents/billing_entitlement/tests/test_subscription_status_isolation.py` asserting no evidence `source` is ever a risk/fraud or foreign-domain value, and that the checker makes no network/peer call (SC-003, FR-009)
- [ ] S026 [P] Add a full-truth-table parameterized test in `apps/agents/billing_entitlement/tests/test_subscription_status.py` covering all six statuses × the review flag, asserting exactly one status per input from the defined set (SC-001)
- [ ] S027 Run the checker suite (`pytest apps/agents/billing_entitlement/tests/test_subscription_status*.py`), apply `ruff format` to `apps/agents/billing_entitlement/`, and confirm green per quickstart.md
- [ ] S028 Reconcile the data model: update `specs/004-billing-entitlement-agent/data-model.md` §2 to document the six-status vocabulary and the `cancelled→canceled` / `lapsed→expired` mapping introduced in S005 (closes the `# TODO(data-model.md)` note)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies — start immediately
- **Foundational (Phase 2: S004–S008)**: depends on Setup — **BLOCKS all stories** (enum, model, policy, dataset)
- **User Stories (Phases 3–6)**: all depend on Foundational
  - US1 (P1) is the MVP backbone (`check_subscription_status`)
  - US2 (P1) extends US1's result with evidence
  - US3 (P2) wraps lookup-miss handling around US1
  - US4 (P2) composes review-flagging over US1 + US3
- **Polish (Phase 7)**: depends on all desired stories complete

### Critical path

S001 → S004 → S005 → S006 → S011 (resolver) → S015 (evidence) → S019 (unknown path) → S022/S023 (review) → S027

### User Story Dependencies

- **US1 (P1)**: after Foundational — no dependency on other stories
- **US2 (P1)**: extends US1's `check_subscription_status` / result (S011)
- **US3 (P2)**: wraps lookup around US1 (S011)
- **US4 (P2)**: composes over US1 and US3 (S011, S019)

### Within Each User Story

- Tests written first and FAIL before implementation
- Enum/model/policy/dataset (Phase 2) before any resolver logic
- Resolver (`check_subscription_status`) before the lookup wrapper and the review composition

### Parallel Opportunities

- **Setup**: S002, S003 in parallel
- **Foundational**: S007, S008 in parallel (distinct files); S004→S005→S006 are same-file (`models.py`) sequential
- **Per-story tests**: the `[P]` test tasks in each story touch distinct files and run in parallel
- **Cross-story**: once US1 (S011) lands, US3 (S017/S018) and US4 (S020/S021) test-authoring can proceed in parallel; US4 implementation waits on US3 implementation
- **Polish**: S024, S025, S026 in parallel

---

## Parallel Example: User Story 1

```bash
# Author US1 tests together (they fail until impl lands):
Task: "test_subscription_status.py — parameterized happy path for all five definitive statuses"
Task: "test_subscription_status.py — single-fact matrix + determinism"

# Foundational data can be drafted in parallel before the resolver:
Task: "Add status-checker policy constants in policy.py"
Task: "Seed subscription fixtures + lookup_subscription in mock_data.py"
# Then implement the resolver:
Task: "Implement check_subscription_status (deterministic resolver) in subscription_status.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1 Setup → Phase 2 Foundational (enum, model, policy, dataset)
2. Phase 3 US1: `check_subscription_status` — the five definitive statuses
3. **STOP and VALIDATE**: each definitive status resolves correctly and deterministically

### Incremental Delivery

1. Setup + Foundational → ready
2. US1 → definitive statuses (MVP)
3. US2 → evidence on every result ("output includes evidence")
4. US3 → missing account → `unknown`
5. US4 → enterprise/ambiguous → requires manual review
6. Polish → logging, isolation proof, full truth table, data-model reconciliation

---

## Notes

- **Companion to `tasks.md`**: `S0xx` IDs never collide with `T0xx`. Where both touch `models.py` /
  `mock_data.py`, this file **extends** the recommendation-engine models rather than redefining them
  (S005 keeps `Subscription.status` intact for `tasks.md` T013).
- **Reuse, don't redefine**: `EvidenceItem` is reused from `packages/contracts/events/payloads.py`.
- **Status vocabulary**: the six statuses refine `data-model.md` §2; S005 maps them onto the existing
  field and S028 updates the doc — no breaking change to the recommendation engine.
- This component adds **no new shared contract, topic, or dependency** (Principle V, FR-017/FR-019).
- `[P]` = different files, no incomplete dependencies. Commit after each story checkpoint.
