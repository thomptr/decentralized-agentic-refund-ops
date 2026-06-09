---
description: "Focused task list for the Case State Store slice of the Customer Resolution Agent"
---

# Tasks: Case State Store (Customer Resolution Agent)

**Input**: Design documents from `/specs/003-customer-resolution-agent/`

**Prerequisites**: plan.md (required), spec.md (US2/US3 aggregation + idempotency), data-model.md (§4 Resolution Case + state machine), research.md (R3 async aggregation, R5/R6 in-process store + durability gap), contracts/topics.md (correlation conventions)

> **Companion file**: The full-feature task list lives in `tasks.md` (US1–US6 end-to-end agent). This
> file is a **focused slice** covering only the case state store. It **supersedes the simple
> `CaseStore` tasks** in `tasks.md` — the `CaseStatus`/`ResolutionCase` portion of **T008**, the store
> implementation **T010**, and the terminal-transition work **T033** — with a richer, **pluggable**
> `CaseStateStore` abstraction (replaceable by Postgres/DynamoDB), an expanded field set, and an
> expanded status enum drawn from the user input. When the store here is built, the broader `tasks.md`
> should import `CaseState`/`CaseStateStore`/`InMemoryCaseStateStore` from `state_store.py` instead of
> the simpler `CaseStore`/`ResolutionCase`. The rest of `tasks.md` is otherwise unchanged.

**Scope**: This list covers **only the case state store** — the in-process, pluggable persistence seam
that holds one working record per case and correlates the ticket, the classification, and the two
asynchronous peer results back to that record. The intake handler, classifier, delegation, decision
policy, response drafting, and the final `customer.resolution.decided` event are **out of scope here**
and remain in `tasks.md`; this slice gives them a durable-by-interface place to read and write case
state.

**State store data contract** (from user input):

| Field | Type | Meaning |
|-------|------|---------|
| `case_id` | `str` | Primary key for the case (the case identity; mirrors the envelope `correlation_id` but stored as the store's own key). |
| `ticket_id` | `str` | Originating support ticket business key (e.g. `TKT-001`). |
| `correlation_id` | `UUID` | Envelope correlation id; the cross-cutting key all peer results carry (FR-006/FR-007). |
| `classification` | `Classification \| None` | Structured classifier output (see `tasks-classifier.md`); `None` until classified. |
| `billing_result` | `BillingFinding \| None` | Normalized billing peer result; `None` until received. |
| `risk_result` | `RiskFinding \| None` | Normalized risk peer result; `None` until received. |
| `pending_tasks` | `dict[UUID, str]` | Outstanding peer `task_id` → review kind (`"billing"`/`"risk"`); emptied as results arrive. |
| `status` | `CaseStatus` | Current lifecycle state (nine-state enum below). |
| `created_at` | `datetime` | Set once at case creation (UTC). |
| `updated_at` | `datetime` | Bumped on every successful mutation (UTC). |
| `deadline_at` | `datetime \| None` | Soft target by which both peer results are expected; advisory only (no liveness/timeout enforcement — research R6, plan Constraints). |

**Status enum** (from user input — `CaseStatus`):

`received` → `classified` → `waiting_for_peer_reviews` → `ready_for_decision` → `decided` →
`response_drafted` → `closed`; with `escalated` and `failed` as terminal off-ramps reachable from any
non-terminal state.

**Acceptance criteria** (from user input):

1. Store interface can later be replaced with Postgres or DynamoDB.
2. Duplicate events do not corrupt state.
3. Result events are correlated by `case_id` and `correlation_id`.

**Tests**: REQUESTED — the acceptance criteria are concrete and testable (pluggability, idempotency,
correlation). Unit tests are written per story and **must fail before** the corresponding implementation.

**Organization**: Grouped by user story; each story maps to one acceptance criterion and is
independently testable. Most logic lives in two modules (`models.py` for the record/enum, `state_store.py`
for the interface + in-memory impl), so cross-story file-level parallelism is limited and called out
honestly below.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1–US3)
- Exact file paths are included in every task

## Acceptance-criteria → user-story map

| Acceptance criterion (user input) | Story |
|-----------------------------------|-------|
| Store interface can later be replaced with Postgres or DynamoDB | US1 |
| Duplicate events do not corrupt state | US2 |
| Result events are correlated by `case_id` and `correlation_id` | US3 |

## Path Conventions

Single Python project (per `plan.md`). The case record/enum live in
`apps/agents/customer_resolution/models.py`; the store interface and in-memory implementation live in
`apps/agents/customer_resolution/state_store.py`; tests under
`apps/agents/customer_resolution/tests/test_state_store.py` (matching the package-local test layout in
`tasks.md`).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the store module and its unit-test file so all later work has a home.

- [ ] T001 [P] Create/extend `apps/agents/customer_resolution/state_store.py` with a module docstring, `from __future__ import annotations`, and imports (`abc.ABC`/`abstractmethod`, `asyncio`, `copy.deepcopy`, `datetime`, `uuid.UUID`, and the `CaseState`/`CaseStatus` symbols from `apps/agents/customer_resolution/models.py`). Lay out `# --- interface ---` and `# --- in-memory impl ---` sections. No behavior yet.
- [ ] T002 [P] Create `apps/agents/customer_resolution/tests/test_state_store.py` with pytest scaffolding: module docstring, `import pytest` + `pytestmark = pytest.mark.asyncio`, imports of the store symbols, and a `_case(**overrides) -> CaseState` helper plus a `_uuid(n: int) -> UUID` deterministic-uuid helper (no `uuid4()` in tests) reused by every test below.

**Checkpoint**: Module and test file exist and import cleanly.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Define the case record, the nine-state status enum, and the legal-transition map every
store operation depends on.

**⚠️ CRITICAL**: No store behavior can be implemented until the record, enum, and transition map exist.

- [ ] T003 [US1] Define `CaseStatus(str, Enum)` in `apps/agents/customer_resolution/models.py` with exactly nine members: `RECEIVED="received"`, `CLASSIFIED="classified"`, `WAITING_FOR_PEER_REVIEWS="waiting_for_peer_reviews"`, `READY_FOR_DECISION="ready_for_decision"`, `DECIDED="decided"`, `RESPONSE_DRAFTED="response_drafted"`, `CLOSED="closed"`, `ESCALATED="escalated"`, `FAILED="failed"`.
- [ ] T004 [US2] Define the lifecycle rules in `apps/agents/customer_resolution/models.py`: `TERMINAL_STATUSES: frozenset[CaseStatus] = {CLOSED, ESCALATED, FAILED}` and `VALID_TRANSITIONS: dict[CaseStatus, frozenset[CaseStatus]]` encoding the data contract's state machine — `RECEIVED→{CLASSIFIED, FAILED}`, `CLASSIFIED→{WAITING_FOR_PEER_REVIEWS, READY_FOR_DECISION, ESCALATED, FAILED}` (non-refund skips straight to `READY_FOR_DECISION`), `WAITING_FOR_PEER_REVIEWS→{READY_FOR_DECISION, ESCALATED, FAILED}`, `READY_FOR_DECISION→{DECIDED, ESCALATED, FAILED}`, `DECIDED→{RESPONSE_DRAFTED, ESCALATED, FAILED}`, `RESPONSE_DRAFTED→{CLOSED}`, and each terminal → `frozenset()`. Add `def can_transition(src: CaseStatus, dst: CaseStatus) -> bool`. Depends on T003.
- [ ] T005 [US1] Define the `CaseState` Pydantic v2 model in `apps/agents/customer_resolution/models.py` with `model_config = ConfigDict(extra="forbid")` (NOT frozen — the store mutates `status`/`updated_at`/results in place) and the eleven fields from the data contract: `case_id: str`, `ticket_id: str`, `correlation_id: UUID`, `classification: Classification | None = None`, `billing_result: BillingFinding | None = None`, `risk_result: RiskFinding | None = None`, `pending_tasks: dict[UUID, str] = Field(default_factory=dict)`, `status: CaseStatus = CaseStatus.RECEIVED`, `created_at: datetime`, `updated_at: datetime`, `deadline_at: datetime | None = None`. Depends on T003 (and references `Classification`/`BillingFinding`/`RiskFinding` from `models.py`; if `Classification` is not yet defined, import-guard or `TYPE_CHECKING`-stub it so this slice stays buildable).
- [ ] T006 [US1] Define the abstract `CaseStateStore(ABC)` interface in `apps/agents/customer_resolution/state_store.py` with `@abstractmethod` async signatures only (no bodies): `async def get_or_create(self, *, case_id, ticket_id, correlation_id, deadline_at=None) -> CaseState`, `async def get(self, case_id: str) -> CaseState | None`, `async def get_by_correlation_id(self, correlation_id: UUID) -> CaseState | None`, `async def get_by_task_id(self, task_id: UUID) -> CaseState | None`, `async def save(self, case: CaseState) -> CaseState`, `async def transition(self, case_id: str, to: CaseStatus) -> CaseState`, `async def register_pending_tasks(self, case_id: str, tasks: dict[UUID, str]) -> CaseState`, `async def apply_result(self, *, task_id: UUID, correlation_id: UUID, finding) -> CaseState`, and `async def list_cases(self) -> list[CaseState]`. Add a class docstring stating the interface is **transport-agnostic and async so it can be re-implemented over Postgres or DynamoDB** (acceptance criterion 1). Depends on T005.

**Checkpoint**: `CaseState`, `CaseStatus`, `VALID_TRANSITIONS`, and the `CaseStateStore` ABC are importable. User stories can begin.

---

## Phase 3: User Story 1 - Pluggable Store Replaceable by Postgres/DynamoDB (Priority: P1) 🎯 MVP

**Goal**: An `InMemoryCaseStateStore(CaseStateStore)` that fully implements the abstract async interface
and returns **defensive copies** (so callers can never mutate stored state by reference), proving the
interface is the only coupling point and a Postgres/DynamoDB store could drop in unchanged. Maps to
acceptance criterion *"Store interface can later be replaced with Postgres or DynamoDB."*

**Independent Test**: Construct `InMemoryCaseStateStore()` as a `CaseStateStore`, `get_or_create` a
case, `get` it back, mutate the returned object, `get` again and assert the store copy is unchanged —
purely in-process, no Kafka.

### Tests for User Story 1 (write first, ensure they FAIL) ⚠️

- [ ] T007 [P] [US1] In `apps/agents/customer_resolution/tests/test_state_store.py`, add tests asserting: `issubclass(InMemoryCaseStateStore, CaseStateStore)`; every abstract method is implemented (instantiation does not raise `TypeError`); `get_or_create` then `get` round-trips all eleven fields; `get` of an unknown `case_id` returns `None`; and mutating a returned `CaseState` does **not** change the stored copy (defensive-copy contract). Run and confirm they FAIL (no `InMemoryCaseStateStore` yet).

### Implementation for User Story 1

- [ ] T008 [US1] Implement `InMemoryCaseStateStore.__init__` in `apps/agents/customer_resolution/state_store.py`: a `self._cases: dict[str, CaseState]` primary map keyed by `case_id`, a `self._lock = asyncio.Lock()` guarding all mutations, and a private `_now() -> datetime` helper (UTC; injectable clock param defaulting to `datetime.now(timezone.utc)` so tests pass fixed times — no bare `datetime.now()` scattered in logic). Depends on T006.
- [ ] T009 [US1] Implement the read paths `get`, `list_cases`, and the `_copy(case) -> CaseState` defensive-copy helper (`case.model_copy(deep=True)`) in `apps/agents/customer_resolution/state_store.py`; `get`/`list_cases` return copies, never the stored instance. Make the round-trip and defensive-copy assertions in T007 pass. Depends on T008.
- [ ] T010 [US1] Implement `save(case)` in `apps/agents/customer_resolution/state_store.py`: under `self._lock`, set `case.updated_at = self._now()`, deep-copy into `self._cases[case.case_id]`, and return a copy. This is the single write primitive every other mutator funnels through. Depends on T009.

**Checkpoint**: `InMemoryCaseStateStore` satisfies the `CaseStateStore` ABC, round-trips a case, and never leaks mutable internal state. The store is provably swap-for-Postgres/DynamoDB. MVP reached.

---

## Phase 4: User Story 2 - Duplicate Events Do Not Corrupt State (Priority: P1)

**Goal**: `get_or_create` is idempotent (a re-delivered ticket returns the **existing** case, never a
second case and never an overwrite of progress), and `transition` enforces `VALID_TRANSITIONS` —
illegal, backwards, and any-from-terminal transitions are rejected — so duplicate or out-of-order
events can never move a case into a corrupt state. Maps to acceptance criterion *"Duplicate events do
not corrupt state."* and spec FR-011/FR-012.

**Independent Test**: `get_or_create` the same `case_id` twice → identical case, store size 1, second
call does not reset `status`/`created_at`; advance a case to `CLOSED`, then call
`transition(case_id, RECEIVED)` and assert it raises/no-ops and the case stays `CLOSED`.

### Tests for User Story 2 (write first, ensure they FAIL) ⚠️

- [ ] T011 [P] [US2] In `apps/agents/customer_resolution/tests/test_state_store.py`, add tests: (a) two `get_or_create` calls with the same `case_id` return the same case, leave `len(await store.list_cases()) == 1`, and the second call does **not** overwrite a non-`RECEIVED` `status` or the original `created_at`; (b) `transition` to a non-adjacent state (e.g. `RECEIVED→DECIDED`) raises `InvalidTransitionError`; (c) any `transition` out of a terminal state (`CLOSED`/`ESCALATED`/`FAILED`) raises; (d) a redundant transition to the **current** status is a safe no-op (idempotent), not an error. Confirm they FAIL.
- [ ] T012 [P] [US2] In `apps/agents/customer_resolution/tests/test_state_store.py`, add a concurrency test: `asyncio.gather` two concurrent `get_or_create` calls for the same `case_id` and assert exactly one case exists with no lost update (the `asyncio.Lock` serializes the read-modify-write). Confirm it FAILS.

### Implementation for User Story 2

- [ ] T013 [US2] Define `class InvalidTransitionError(Exception)` in `apps/agents/customer_resolution/state_store.py` (or `models.py` if shared) with a message naming the rejected `from`/`to` pair.
- [ ] T014 [US2] Implement idempotent `get_or_create` in `apps/agents/customer_resolution/state_store.py`: under `self._lock`, return a copy of the existing case if `case_id` is present (touching nothing); otherwise build a fresh `CaseState` with `status=RECEIVED`, `created_at=updated_at=self._now()`, the given `deadline_at`, and persist via the `save` path. Make T011(a) and T012 pass. Depends on T010.
- [ ] T015 [US2] Implement `transition(case_id, to)` in `apps/agents/customer_resolution/state_store.py`: under `self._lock`, load the case (raise `KeyError` if absent); if `to == case.status` return a copy unchanged (idempotent no-op); else if `can_transition(case.status, to)` set `status` and `save`; else raise `InvalidTransitionError`. Terminal states have empty transition sets, so they reject everything. Make T011(b)(c)(d) pass. Depends on T014 + models T004.

**Checkpoint**: Re-delivered tickets and out-of-order/duplicate transitions cannot corrupt or duplicate a case; the lock serializes concurrent writers.

---

## Phase 5: User Story 3 - Result Events Correlated by case_id and correlation_id (Priority: P1)

**Goal**: The store correlates the two asynchronous peer results back to the right case by **both**
keys — `task_id`→case (so the result loop, which only knows the `task_id`, finds the owning case) and
`correlation_id` (validated against the case so a mismatched result is **rejected, not misapplied**) —
and advances the case to `READY_FOR_DECISION` once `pending_tasks` is empty. Maps to acceptance
criterion *"Result events are correlated by `case_id` and `correlation_id`."* and spec FR-006/FR-007/FR-008.

**Independent Test**: Register two pending tasks (billing+risk) on a case, `apply_result` the billing
`task_id` → `billing_result` set, task removed from `pending_tasks`, status stays
`WAITING_FOR_PEER_REVIEWS`; `apply_result` the risk `task_id` → `risk_result` set, `pending_tasks`
empty, status auto-advances to `READY_FOR_DECISION`; `apply_result` with a `correlation_id` that
doesn't match the located case raises and changes nothing.

### Tests for User Story 3 (write first, ensure they FAIL) ⚠️

- [ ] T016 [P] [US3] In `apps/agents/customer_resolution/tests/test_state_store.py`, add tests for the correlation indexes: after `register_pending_tasks(case_id, {t_billing: "billing", t_risk: "risk"})`, `get_by_task_id(t_billing)` and `get_by_correlation_id(case.correlation_id)` both return the same case; `get_by_task_id` of an unknown id returns `None`. Confirm it FAILS.
- [ ] T017 [P] [US3] In `apps/agents/customer_resolution/tests/test_state_store.py`, add tests for `apply_result`: billing result attaches to `billing_result` and removes its `task_id` from `pending_tasks` (status unchanged, one task still pending); the second (risk) result empties `pending_tasks` and the store transitions the case to `READY_FOR_DECISION`; a result whose `correlation_id` does not equal the located case's `correlation_id` raises `CorrelationMismatchError` and mutates nothing; a duplicate result for an already-applied/already-removed `task_id` is a safe no-op (does not double-apply or corrupt — ties back to AC2). Confirm it FAILS.

### Implementation for User Story 3

- [ ] T018 [US3] Add the secondary correlation indexes to `InMemoryCaseStateStore` in `apps/agents/customer_resolution/state_store.py`: `self._by_correlation: dict[UUID, str]` (correlation_id→case_id) maintained in `get_or_create`, and `self._by_task: dict[UUID, str]` (task_id→case_id). Implement `get_by_correlation_id` and `get_by_task_id` to resolve through these maps and return copies. Make T016 pass. Depends on T014.
- [ ] T019 [US3] Implement `register_pending_tasks(case_id, tasks)` in `apps/agents/customer_resolution/state_store.py`: under `self._lock`, merge `tasks` into `case.pending_tasks`, register each `task_id` in `self._by_task`, transition `CLASSIFIED→WAITING_FOR_PEER_REVIEWS` (via the guarded `transition` path), and `save`. Depends on T018 + T015.
- [ ] T020 [US3] Define `class CorrelationMismatchError(Exception)` and implement `apply_result(*, task_id, correlation_id, finding)` in `apps/agents/customer_resolution/state_store.py`: under `self._lock`, locate the case via `self._by_task[task_id]` (return unchanged copy / no-op if the `task_id` is unknown or already removed — duplicate-safe, AC2); **assert the supplied `correlation_id` equals the case's `correlation_id`**, else raise `CorrelationMismatchError` (AC3) and mutate nothing; set `billing_result` or `risk_result` from `pending_tasks[task_id]`'s kind, pop the `task_id` from `pending_tasks` and `self._by_task`; if `pending_tasks` is now empty, transition to `READY_FOR_DECISION`; `save` and return a copy. Make T017 pass. Depends on T019.

**Checkpoint**: Peer results are correlated by `task_id`→case and validated by `correlation_id`; both-results completeness flips the case to `READY_FOR_DECISION`; mismatched/duplicate results are rejected or inert.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Export the store, bridge the broader `tasks.md` onto it, document it, and verify quality gates.

- [ ] T021 [US1] Export the store symbols (`CaseState`, `CaseStatus`, `CaseStateStore`, `InMemoryCaseStateStore`, `InvalidTransitionError`, `CorrelationMismatchError`) from `apps/agents/customer_resolution/__init__.py` so the intake and result loops (`event_handlers.py`) can import them.
- [ ] T022 Bridge the broader feature onto this store: in `apps/agents/customer_resolution/state_store.py` add a `CaseStore = InMemoryCaseStateStore` alias (and a one-line comment) so `tasks.md` T010/T011/T035 — which wire a shared `CaseStore` into `agent.py` and the consumers — consume this richer store without a rename churn; note in the comment that this file supersedes the simple `CaseStore`/`ResolutionCase` design in `data-model.md §4`.
- [ ] T023 [P] Add a short "Case State Store" subsection to `specs/003-customer-resolution-agent/quickstart.md` documenting the eleven case fields, the nine-state status enum + legal transitions, and the three acceptance-criteria→behavior mappings (pluggable async interface, lock+guard idempotency, dual-key correlation).
- [ ] T024 Run `uv run pytest apps/agents/customer_resolution/tests/test_state_store.py`, then `uv run mypy apps/agents/customer_resolution/state_store.py apps/agents/customer_resolution/models.py` and `uv run ruff check apps/agents/customer_resolution/state_store.py apps/agents/customer_resolution/models.py apps/agents/customer_resolution/tests/test_state_store.py`; fix any failures. Depends on all prior tasks.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories (defines `CaseState`, `CaseStatus`, `VALID_TRANSITIONS`, and the `CaseStateStore` ABC).
- **User Stories (Phases 3–5)**: All depend on Foundational. US1 establishes the store + write primitive; US2 and US3 add behavior **on top of** US1's `save`/`get_or_create`, so they are best done in priority order (US1 → US2 → US3); US2 and US3 both build on US1.
- **Polish (Phase 6)**: Depends on US1–US3 being complete.

### User Story Dependencies

- **US1 (P1)**: Establishes `InMemoryCaseStateStore`, the `save` write primitive, and defensive copying — foundation for the rest.
- **US2 (P1)**: Adds idempotent `get_or_create` + guarded `transition` (builds on US1's `save`).
- **US3 (P1)**: Adds the correlation indexes + `apply_result` (builds on US2's `get_or_create`/`transition`).

### Within Each User Story

- Write the unit test(s) first and confirm they FAIL, then implement.
- Record/enum/transition map (Phase 2) before any store logic.
- Every mutator funnels through `save` (US1) so `updated_at`/locking/copying stay in one place.

### Parallel Opportunities

- **Setup**: T001 (`state_store.py`) and T002 (`test_state_store.py`) are different files → run in parallel.
- **Foundational**: T003 must precede T004/T005; T004 and T005 both touch `models.py` → sequential; T006 (in `state_store.py`) can start once T005 lands.
- **Tests**: within a story the test tasks marked `[P]` (T007; T011/T012; T016/T017) are independent additions to the test file and can be drafted together, but the **implementation** tasks (T008–T010, T013–T015, T018–T020) all edit the single `InMemoryCaseStateStore` class → **sequential**, not parallel.
- **Polish**: T023 (docs) is independent of T021/T022/T024 → can run in parallel with them.
- Honest note: because the store is one cohesive class, this slice is largely linear; the main
  parallelism is Setup, the docs task, and drafting each story's tests while reviewing the prior impl.

---

## Parallel Example: Setup

```bash
# Different files, no dependencies — run together:
Task: "Create apps/agents/customer_resolution/state_store.py skeleton (T001)"
Task: "Create apps/agents/customer_resolution/tests/test_state_store.py scaffolding (T002)"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1: Setup (T001–T002)
2. Phase 2: Foundational — `CaseState` + `CaseStatus` + `VALID_TRANSITIONS` + `CaseStateStore` ABC (T003–T006)
3. Phase 3: User Story 1 — `InMemoryCaseStateStore` with `get`/`save`/defensive copy (T007–T010)
4. **STOP and VALIDATE**: the store satisfies the abstract interface and never leaks mutable state —
   the "replaceable by Postgres/DynamoDB" acceptance criterion is met on its own.

### Incremental Delivery

1. Setup + Foundational → record, enum, transition map, and interface ready.
2. US1 → pluggable in-memory store (MVP) → validate.
3. US2 → idempotent `get_or_create` + guarded `transition` → duplicate events can't corrupt → validate.
4. US3 → dual-key (`task_id` + `correlation_id`) result correlation + `READY_FOR_DECISION` flip → validate.
5. Polish → export, bridge `tasks.md`, docs, mypy/ruff/pytest green.

Each step adds behavior on top of the single `save` write primitive without breaking earlier tests.

---

## Notes

- `[P]` = different files, no dependencies on incomplete tasks.
- `[Story]` label maps each task to its acceptance criterion for traceability.
- The interface is **async and abstract on purpose** (acceptance criterion 1): a future
  `PostgresCaseStateStore`/`DynamoCaseStateStore` re-implements the same `CaseStateStore` methods with
  no caller change — the in-memory map, `asyncio.Lock`, and copies are implementation details behind it.
- **State durability across process restart is a documented PoC gap** (research R6, plan Constraints):
  the in-memory store is volatile; the durable record remains the audit trail. `deadline_at` is stored
  but **not enforced** — there is no liveness/timeout sweeper in scope (plan Constraints).
- `CaseState` is intentionally **not frozen** (unlike the wire contracts) because the store mutates
  `status`/`updated_at`/results in place; external callers only ever receive **deep copies**, so the
  not-frozen choice never leaks shared mutable state.
- This file **supersedes** the simple `CaseStore` tasks in `tasks.md` (the enum/model part of T008,
  the store T010, and terminal transitions T033); the rest of `tasks.md` is unchanged and should import
  the store from `state_store.py`.
- Commit after each story checkpoint; verify each story's tests fail before implementing.
