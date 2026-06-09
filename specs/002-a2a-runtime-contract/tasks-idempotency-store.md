---
description: "Scoped task list: pluggable idempotency TaskStore for the A2A runtime"
---

# Tasks: Pluggable Idempotency TaskStore

**Input**: Design documents from `/specs/002-a2a-runtime-contract/` (plan.md, spec.md, research.md,
data-model.md, contracts/) plus the user-supplied component spec below.

**Scope**: This is a **focused slice** of feature `002-a2a-runtime-contract`. It covers only the
pluggable idempotency **TaskStore** that backs FR-010 (task idempotency) and the "duplicate-safe
response" behavior. The full-feature task list lives in `tasks.md` and is intentionally left
untouched. Where the two overlap, this file is authoritative for the TaskStore design.

**Component spec (user-supplied)**:

> Implement idempotency store. For POC use in-memory first (`InMemoryTaskStore`), later replaceable
> with `PostgresTaskStore`, `DynamoDBTaskStore`, `RedisTaskStore`.
>
> Acceptance criteria:
> 1. Same `idempotency_key` does not execute the handler twice.
> 2. An existing result can be returned for duplicate requests.
> 3. The store interface is pluggable.

**Design decision (supersedes research R7 for task-level dedup)**: R7 originally reused the
foundation's `IdempotencyTracker`, which only records processed-ID *booleans* and cannot return a
prior result (it cannot satisfy acceptance criterion #2). This slice introduces a dedicated,
pluggable `TaskStore` abstraction that both **claims** a key atomically (criterion #1) and
**stores/returns the terminal result** (criterion #2), with swappable backends (criterion #3). The
`AgentRuntime` uses the `TaskStore` for task-level idempotency keyed by `task_id`; envelope-level
`event_id` dedup in `IdempotencyTracker` is unchanged.

**Tests**: INCLUDED. The three acceptance criteria are directly testable and map 1:1 to the three
user stories below; the feature's Success Criteria (SC-005 idempotency, SC-003 one-terminal-outcome)
also require demonstrated tests.

**Idempotency key**: The user's `idempotency_key` is the `TaskRequest.task_id` (a `UUID`) per
data-model §1.4. "Key" and `task_id` are used interchangeably below.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1–US3 (maps to the three acceptance criteria)
- All paths are repository-relative (single Python project per plan.md "Structure Decision")

## Path Conventions

- Store code: `src/agent_foundation/runtime/`
- Runtime integration: `src/agent_foundation/runtime/runtime.py` (created by `tasks.md` T018–T021)
- Tests: `tests/unit/`, `tests/integration/`
- Docs: `docs/`

---

## Phase 1: Setup (Module Skeletons)

**Purpose**: Create the empty module landing spots so subsequent tasks have a place to write. No new
third-party dependency is added — `pydantic`, `aiokafka`, `pytest`, `pytest-asyncio` already exist
from `001-event-foundation` (plan.md Technical Context).

- [ ] T001 [P] Create `src/agent_foundation/runtime/__init__.py` if absent (package docstring, `__all__ = []`); this slice will export the store types from it in T013. If `tasks.md` T001 already created it, just confirm it exists.
- [ ] T002 [P] Create the store backend stub module file `src/agent_foundation/runtime/task_store_backends.py` with a module docstring stating these are deferred POC scaffolds (Principle V), and an empty body to be filled by T012.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The `StoredTask` record and the abstract `TaskStore` interface that every story
implements/consumes. This realizes acceptance criterion #3's contract surface and blocks US1–US3.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T003 [P] Implement the `StoredTask` Pydantic v2 model in `src/agent_foundation/runtime/task_store.py`: fields `key: UUID`, `result: TaskResult | None = None` (None ⟹ claimed-but-pending), with a `status` computed property returning `"pending"` when `result is None` else `result.status`. `model_config = ConfigDict(frozen=True, extra="forbid")`. Import `TaskResult` from `agent_foundation.payloads.task` (created by `tasks.md` T005); if that module does not yet exist, define `StoredTask.result` against a `TYPE_CHECKING` import and accept any object at runtime so this slice stays independently testable.
- [ ] T004 Define the abstract `TaskStore` interface in `src/agent_foundation/runtime/task_store.py` (depends on T003) as an `abc.ABC` with three async methods — the full pluggable contract:
  - `async def claim(self, key: UUID) -> bool` — atomically reserve `key`. Returns `True` if newly claimed (caller MUST run the handler), `False` if the key was already present (duplicate). Idempotent and race-free under concurrent callers.
  - `async def get(self, key: UUID) -> StoredTask | None` — return the stored record (with result if terminal) or `None` if never claimed.
  - `async def record_result(self, key: UUID, result: TaskResult) -> None` — persist the terminal result for a previously-claimed key (idempotent: re-recording the same key is a no-op or overwrite-equal).
  Document the required semantics in the class docstring so alternate backends conform.

**Checkpoint**: The pluggable contract (`TaskStore`) and record (`StoredTask`) exist — stories can begin.

---

## Phase 3: User Story 1 - Same Key Does Not Execute Handler Twice (Priority: P1) 🎯 MVP

**Goal**: Acceptance criterion #1. An `InMemoryTaskStore` provides an **atomic** `claim()` so that
when the same `task_id` is submitted concurrently or repeatedly, exactly one caller is told to run
the handler and the handler executes at most once.

**Independent Test**: Construct an `InMemoryTaskStore`; call `claim(k)` twice for the same `k` and
assert the first returns `True`, the second `False`; fire N concurrent `claim(k)` coroutines via
`asyncio.gather` and assert exactly one returns `True` (proves atomicity, no double execution).

### Tests for User Story 1 ⚠️ (write first, ensure they FAIL before implementing)

- [ ] T005 [P] [US1] Unit test in `tests/unit/test_task_store.py`: `claim(k)` returns `True` then `False` for a repeated key; `asyncio.gather` of N=50 concurrent `claim(k)` for one key yields exactly one `True`; `claim` for distinct keys all return `True`. Use `@pytest.mark.asyncio` (matches the foundation's async test setup).

### Implementation for User Story 1

- [ ] T006 [US1] Implement `InMemoryTaskStore(TaskStore)` in `src/agent_foundation/runtime/task_store.py` (depends on T004): back it with a `dict[UUID, StoredTask]` guarded by a single `asyncio.Lock`. `claim(k)` acquires the lock, inserts a pending `StoredTask(key=k)` and returns `True` if absent, else returns `False`; `get(k)` returns the record or `None`. Atomicity comes from holding the lock across the check-and-insert.
- [ ] T007 [US1] Wire claim-before-execute into `AgentRuntime` in `src/agent_foundation/runtime/runtime.py` (depends on T006; depends on `tasks.md` T018–T020 having created the lifecycle): immediately after a request passes validation/accept, call `await self._store.claim(task_request.task_id)`; when it returns `False`, **do not invoke the handler** and route to the duplicate path (completed in US2); when `True`, proceed to run the handler. This replaces the `IdempotencyTracker` task-level check from `tasks.md` T021 (keep `IdempotencyTracker` for envelope `event_id` dedup only).

**Checkpoint**: A repeated/concurrent `task_id` can never trigger a second handler execution — criterion #1 satisfied and independently unit-testable.

---

## Phase 4: User Story 2 - Existing Result Returned for Duplicate Requests (Priority: P1)

**Goal**: Acceptance criterion #2. After a handler completes, its `TaskResult` is stored against the
key; a later duplicate request returns that stored result instead of re-running the handler, and the
runtime re-publishes it with a `duplicate_skipped` audit event.

**Independent Test**: `claim(k)` → `record_result(k, r)` → `get(k)` returns a `StoredTask` whose
`result == r` and `status == r.status`; a second `claim(k)` returns `False` and the cached result is
retrievable. End-to-end: submit the same `task_id` twice through the runtime and assert the handler
ran once and both responses carry the identical `TaskResult`.

### Tests for User Story 2 ⚠️ (write first, ensure they FAIL before implementing)

- [ ] T008 [P] [US2] Extend `tests/unit/test_task_store.py` (depends on T005): after `claim(k)` + `record_result(k, r)`, `get(k).result == r` and `get(k).status == r.status`; `record_result` for an unclaimed key behaves per the documented contract (claim-then-record or explicit error — assert whichever T004 specifies); re-`record_result(k, r)` is idempotent.
- [ ] T009 [P] [US2] Integration test in `tests/integration/test_task_store_idempotency.py` (`-m integration`, testcontainers Kafka; depends on `tasks.md` T019/T028 runtime serve + terminal path): submit a `TaskRequest` with a fixed `task_id`, await its `TaskResult`; submit the **same** `task_id` again and assert (a) the handler executed exactly once (assert via a call counter in the echo agent), (b) the second `TaskResult` is byte-identical to the first, (c) exactly one `duplicate_skipped` audit event was emitted for that `task_id` (SC-005).

### Implementation for User Story 2

- [ ] T010 [US2] Implement `InMemoryTaskStore.record_result` in `src/agent_foundation/runtime/task_store.py` (depends on T006): under the lock, replace the pending record for `key` with `StoredTask(key=key, result=result)`; ensure `get(key)` then returns the cached result. Make re-recording idempotent.
- [ ] T011 [US2] Implement the duplicate-replay path in `AgentRuntime` in `src/agent_foundation/runtime/runtime.py` (depends on T007, T010): when `claim()` returned `False`, load `await self._store.get(task_id)`; if a stored `result` is present, **re-publish that exact `TaskResult`** to `TOPIC_TASK_RESULT` (correlated to the new request envelope) and emit a single `duplicate_skipped` audit via `write_task_audit` — no handler run, no second terminal outcome (FR-010, data-model §4 invariant 3). After a successful handler run (US1 path), call `await self._store.record_result(task_id, result)` before returning so the result is cached for future duplicates.

**Checkpoint**: Duplicate requests return the stored result with the handler run only once — criteria #1 + #2 satisfied; this is the demonstrable MVP of the idempotency store.

---

## Phase 5: User Story 3 - Pluggable Store Interface (Priority: P2)

**Goal**: Acceptance criterion #3. The `TaskStore` is dependency-injected into `AgentRuntime` so any
backend can be swapped in; ship the deferred Postgres/DynamoDB/Redis scaffolds so the extension
points are explicit without building production backends (Principle V).

**Independent Test**: Instantiate `AgentRuntime` with a trivial in-test `TaskStore` subclass and
confirm the lifecycle uses it (claim/record observed); confirm `InMemoryTaskStore` is the default
when none is injected; confirm each backend stub is importable and raises `NotImplementedError` with
a descriptive message.

### Tests for User Story 3 ⚠️ (write first, ensure they FAIL before implementing)

- [ ] T012 [P] [US3] Unit test in `tests/unit/test_task_store_pluggable.py`: define a minimal in-test `FakeTaskStore(TaskStore)` recording calls; assert `AgentRuntime(..., task_store=FakeTaskStore())` routes `claim`/`record_result` through it; assert `AgentRuntime(...)` with no `task_store` uses an `InMemoryTaskStore` (default); assert importing `PostgresTaskStore`/`DynamoDBTaskStore`/`RedisTaskStore` and calling any method raises `NotImplementedError`.

### Implementation for User Story 3

- [ ] T013 [US3] Add dependency injection in `AgentRuntime.__init__` in `src/agent_foundation/runtime/runtime.py` (depends on T006): accept `task_store: TaskStore | None = None`, defaulting to `InMemoryTaskStore()`; store as `self._store`. Export `TaskStore`, `StoredTask`, `InMemoryTaskStore` from `src/agent_foundation/runtime/__init__.py` `__all__`.
- [ ] T014 [P] [US3] Implement the deferred backend scaffolds in `src/agent_foundation/runtime/task_store_backends.py` (depends on T004): `PostgresTaskStore`, `DynamoDBTaskStore`, `RedisTaskStore`, each subclassing `TaskStore`, each `__init__` accepting its connection params, and each method raising `NotImplementedError("PostgresTaskStore is a deferred POC scaffold — see docs/idempotency-store.md")` (and equivalents). Add a class docstring per backend describing the intended atomic-claim mechanism (Postgres: `INSERT ... ON CONFLICT DO NOTHING`; DynamoDB: conditional `PutItem` with `attribute_not_exists`; Redis: `SET key val NX`).

**Checkpoint**: The store is fully pluggable and the runtime defaults to in-memory — all three acceptance criteria satisfied.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Documentation (FR-016) and full-slice validation.

- [ ] T015 [P] Write `docs/idempotency-store.md`: the `TaskStore` contract (claim/get/record_result semantics), the in-memory default, and a "swap the backend" guide showing `AgentRuntime(..., task_store=...)` plus the atomic-claim primitive each future backend should use. Referenced by the `NotImplementedError` messages from T014.
- [ ] T016 Run the fast suite (`uv run pytest tests/unit/test_task_store.py tests/unit/test_task_store_pluggable.py`) and the integration test (`uv run pytest -m integration tests/integration/test_task_store_idempotency.py`); confirm all three acceptance criteria are demonstrated green.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Foundational (Phase 2)**: Depends on Setup — **BLOCKS all user stories**.
- **User Stories (Phase 3+)**: All depend on Foundational completion.
  - US1 (P1): Foundational only. The pure-store half (T005, T006) is independent of the runtime.
  - US2 (P1): Builds on US1 (`claim` must exist before result-replay is meaningful).
  - US3 (P2): Foundational + US1's `InMemoryTaskStore`; the DI/scaffold work is largely independent of US2.
- **Polish (Phase 6)**: Depends on the targeted stories.

### Cross-file dependency on `tasks.md`

The runtime-integration tasks (T007, T011, T013) edit `src/agent_foundation/runtime/runtime.py`,
which is created by `tasks.md` T018–T021/T028. The **pure store** tasks (T003–T006, T010, and unit
tests T005/T008/T012) have **no** dependency on the runtime and can be completed and tested
standalone first — making the MVP store independently deliverable ahead of the full runtime.

### Within Each User Story

- Tests are written first and must FAIL before implementation.
- `StoredTask` (model) and `TaskStore` (interface) before any implementation.
- `InMemoryTaskStore.claim` (US1) before result-replay (US2).
- Store code before the runtime wiring that consumes it.

### Parallel Opportunities

- Setup T001, T002 are [P].
- Foundational: T003 [P]; T004 follows (same file, depends on T003).
- US1 test T005 [P]. US2 tests T008, T009 are [P] (distinct files). US3 test T012 [P].
- US3 impl: T014 (backend stubs, distinct file) is [P] with T013 (runtime DI).
- Polish T015 [P] with the test run T016.

---

## Parallel Example: Foundational + US1

```bash
# Setup (distinct files):
Task: "Create runtime __init__ in src/agent_foundation/runtime/__init__.py"            # T001
Task: "Create backend stub module src/agent_foundation/runtime/task_store_backends.py" # T002

# After T003/T004, write the failing store tests (distinct files):
Task: "Unit test claim atomicity in tests/unit/test_task_store.py"                      # T005
Task: "Unit test pluggable DI in tests/unit/test_task_store_pluggable.py"              # T012
```

---

## Implementation Strategy

### MVP First (User Stories 1 + 2, store-only)

1. Phase 1 Setup → Phase 2 Foundational (`StoredTask` + `TaskStore` interface).
2. Phase 3 US1 (`InMemoryTaskStore.claim`, atomic) → validate with the concurrency unit test.
3. Phase 4 US2 (`record_result` + cached replay) → **STOP and VALIDATE**: the pure store satisfies
   criteria #1 and #2 via `tests/unit/test_task_store.py` with no runtime needed. This is the
   demonstrable MVP and can land before the full A2A runtime exists.

### Incremental Delivery

1. Foundational → pluggable contract ready.
2. US1 + US2 (store core) → criteria #1 + #2, unit-tested standalone.
3. Runtime wiring (T007, T011) once `runtime.py` exists → end-to-end duplicate replay (T009).
4. US3 → DI + backend scaffolds → criterion #3.
5. Polish → docs (FR-016) + full validation.

---

## Notes

- [P] = different files, no dependency on an incomplete task.
- [Story] label maps each task to its acceptance criterion (US1→#1, US2→#2, US3→#3).
- This slice supersedes `tasks.md` T021's "reuse IdempotencyTracker for task_id" decision: task-level
  idempotency now uses the pluggable `TaskStore`; `IdempotencyTracker` still handles envelope dedup.
- The store core (T003–T006, T010) is intentionally runtime-free so it is independently testable.
- Backend stubs are deferred scaffolds (Principle V) — they establish pluggability without building
  production storage.
- Commit after each task or logical group; verify tests fail before implementing.
