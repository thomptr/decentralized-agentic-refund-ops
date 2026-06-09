# Tasks Delta: A2A Task Request & Result Models

**Status**: MERGE-PENDING delta for `tasks.md` (written separately to avoid racing a concurrent
session that is actively regenerating `tasks.md`).
**Source**: `/speckit-tasks` request "Define A2A task request and result models".
**Apply to**: `specs/002-a2a-runtime-contract/tasks.md`.

This delta refines **only** the task-contract model work. It does **not** touch the Agent Card
expansion (T004–T007 in the live file) or any runtime/CLI/test-harness tasks beyond renaming the
model classes they reference. IDs below reference the live file **as last read** (T001–T050 layout
where the models live at **T008**, the registry at **T015**, and task-contract tests at
**T018/T019**). If the other session renumbered, match by the quoted anchor text, not the bare ID.

---

## Confirmed decisions (from this session)

1. **A2A-prefixed names** — `A2ATaskRequest`, `A2ATaskResult`, `A2ATaskError`, `A2ATaskStatus`,
   `A2ATaskArtifact` (consistent with the existing `a2a.py`: `A2APart`/`A2AMessage`/`A2ATask`).
2. **Two new models added** beyond the current design: `A2ATaskStatus` (status enum) and
   `A2ATaskArtifact` (typed artifact carried by results).
3. **Envelope-only correlation** — `correlation_id` / `causation_id` are carried by the
   `EventEnvelope` (FR-014) and are **NOT** duplicated into the payload models, even though the
   original `/speckit-tasks` field list named them.
4. The rest of the user's field list **is** added: `idempotency_key`, `source_agent_id`,
   `target_agent_id`, `priority`, `timeout_seconds`, `created_at`, `metadata` (request);
   `artifacts`, `started_at`, `completed_at`, `metadata` (result).
5. Acceptance criteria mapping: strongly typed → all models (T008a–T008f); requests serialize to
   JSON → T008d/T019; results validated before publish → T008e/T008e-validator; unknown capabilities
   rejected → T008f + serve-time check (live T024).

> **Divergence flagged**: this expands beyond `data-model.md §1.4–§1.5` and
> `contracts/task-request.schema.json` / `task-result.schema.json`. **R1 below** reconciles those
> artifacts. The `source_/target_agent_id` naming replaces the design's `requester_/performer_agent_id`.

---

## 1. REPLACE the model task (live **T008**)

> **Anchor (remove this whole line):**
> `- [ ] T008 [P] Implement `TaskStatus`, `TaskError`, `TaskRequest`, and `TaskResult` models in `src/agent_foundation/payloads/task.py` …`

**Replace with** (keep them in Phase 2 Foundational, no story label; sub-IDs avoid renumbering):

- [ ] T008a [P] Implement `A2ATaskStatus` in `src/agent_foundation/payloads/task.py` as a string enum (`class A2ATaskStatus(str, Enum)`) with `ACCEPTED="accepted"`, `COMPLETED="completed"`, `FAILED="failed"`, `REJECTED="rejected"`. Docstring notes `accepted` is non-terminal and is NOT a valid `A2ATaskResult.status`; values JSON-serialize to their strings (AC: strongly typed).
- [ ] T008b [P] Implement `A2ATaskError` in `src/agent_foundation/payloads/task.py`: `category: Literal["validation","unsupported_capability","handler_error","duplicate","internal"]`, `message: str = Field(min_length=1, max_length=500)`; `model_config = ConfigDict(frozen=True, extra="forbid")` (matches `task-result.schema.json $defs/TaskError`).
- [ ] T008c [P] Implement `A2ATaskArtifact` in `src/agent_foundation/payloads/task.py`: `artifact_id: UUID`, `name: str = Field(min_length=1, max_length=80)`, `description: str | None = None`, `parts: list[A2APart]` (reuse `agent_foundation.a2a.A2APart`; `model_validator` requiring non-empty), `metadata: dict[str, Any] = Field(default_factory=dict)`; frozen + `extra="forbid"`.
- [ ] T008d Implement `A2ATaskRequest` in `src/agent_foundation/payloads/task.py` (frozen, `extra="forbid"`) with fields: `task_id: UUID`, `idempotency_key: str = Field(min_length=1, max_length=200)`, `source_agent_id: str` & `target_agent_id: str` (both `Field(pattern=AGENT_ID_PATTERN)`), `capability: str = Field(pattern=CAPABILITY_PATTERN)`, `input: A2AMessage` (reuse `a2a`), `priority: Literal["low","normal","high"] = "normal"`, `timeout_seconds: float = Field(gt=0, le=3600)`, `created_at: datetime`, `metadata: dict[str, Any] = Field(default_factory=dict)`. **`correlation_id`/`causation_id` are NOT fields here** — they live on the `EventEnvelope` (FR-014). Confirm `model_validate_json(model_dump_json(x)) == x` round-trips (AC: requests serialize to JSON).
- [ ] T008e Implement `A2ATaskResult` in `src/agent_foundation/payloads/task.py` (frozen, `extra="forbid"`) with fields: `task_id: UUID`, `source_agent_id: str` (the performer) & `target_agent_id: str` (the original requester) (both `Field(pattern=AGENT_ID_PATTERN)`), `capability: str = Field(pattern=CAPABILITY_PATTERN)`, `status: A2ATaskStatus`, `output: A2AMessage | None = None`, `artifacts: list[A2ATaskArtifact] = Field(default_factory=list)`, `error: A2ATaskError | None = None`, `started_at: datetime`, `completed_at: datetime`, `metadata: dict[str, Any] = Field(default_factory=dict)`. **`correlation_id` stays on the envelope (FR-014).** Add a `model_validator(mode="after")`: `COMPLETED`⟹`output` set & `error` null; `FAILED`/`REJECTED`⟹`error` set & `output` null; `REJECTED` ⟹ `error.category ∈ {validation,unsupported_capability,duplicate}`; `FAILED` ⟹ `error.category ∈ {handler_error,internal}`; reject `status == A2ATaskStatus.ACCEPTED` (non-terminal); require `completed_at >= started_at`. This is the "validate before returning/publishing" gate (AC: results validated before publish).
- [ ] T008f [P] Define `AGENT_ID_PATTERN` and `CAPABILITY_PATTERN` (`r"^[a-z][a-z0-9_.-]{1,62}$"`) constants and an `ensure_known_capability(capability: str, known: Iterable[str]) -> str` helper (raises `UnsupportedCapability`) in `src/agent_foundation/payloads/task.py`. The request enforces capability **format** at the model layer; **membership** against the target's declared skills is enforced at serve time (live T024) — together satisfying AC "unknown capabilities are rejected".

---

## 2. UPDATE the payload registry task (live **T015**)

> **Anchor:** `… `agent.task_request.v1→TaskRequest`, `agent.task_result.v1→TaskResult`, `agent.agent_card.v1→AgentCard` …` and `(depends on T004, T008)`.

- Rename model targets: `agent.task_request.v1→A2ATaskRequest`, `agent.task_result.v1→A2ATaskResult` (AgentCard unchanged).
- Update dependency: `(depends on T004, T008d, T008e)`.
- (`A2ATaskArtifact` is nested inside `A2ATaskResult` and is **not** separately registered.)

---

## 3. UPDATE the contract test task (live **T018**)

> **Anchor:** `… JSON-schema round-trip for `TaskRequest`, `TaskResult`, and the full `AgentCard` …`

- Rename to `A2ATaskRequest`, `A2ATaskResult`.
- Add coverage: an `A2ATaskResult` instance carrying a non-empty `artifacts: list[A2ATaskArtifact]`, and one instance per `A2ATaskStatus` terminal value (`completed`/`failed`/`rejected`); assert `status == accepted` is rejected as a result status.

---

## 4. UPDATE the unit test task (live **T019**)

> **Anchor:** `… valid/invalid construction of `TaskRequest`/`TaskResult`/`TaskError` (all cross-field rules) …`

- Rename to `A2ATaskRequest`/`A2ATaskResult`/`A2ATaskError`; add `A2ATaskStatus` and `A2ATaskArtifact` construction tests.
- Add field-level cases: `timeout_seconds` must be `> 0` and `<= 3600`; `idempotency_key` length bounds; `priority` enum; `metadata` defaults to `{}`; `artifacts` defaults to `[]`; immutability (`frozen`) and `extra="forbid"`; `A2ATaskRequest.capability` rejects malformed ids and `ensure_known_capability` raises on an undeclared capability; `completed_at >= started_at` enforced.

---

## 5. ADD a reconciliation task (new — append to Phase 8 Polish, e.g. **T051**)

- [ ] T051 [P] Reconcile the task-contract design artifacts with the implemented A2A models: update `specs/002-a2a-runtime-contract/data-model.md §1.3–§1.5` and `contracts/task-request.schema.json` / `contracts/task-result.schema.json` to the A2A-prefixed shape — add `idempotency_key`, `priority`, `timeout_seconds`, `created_at`, `metadata` (request) and `artifacts`, `started_at`, `completed_at`, `metadata` (result); rename agent-id fields to `source_/target_agent_id`; add the `A2ATaskArtifact` `$def`; and record the explicit decision (FR-014) that `correlation_id`/`causation_id` remain envelope-only and are NOT payload fields.

---

## 6. Consistency rename (rest of `tasks.md`)

For coherence, rename remaining bare references in the live file so every mention matches the model
classes: `TaskRequest`→`A2ATaskRequest`, `TaskResult`→`A2ATaskResult`, `TaskError`→`A2ATaskError`,
`TaskStatus`→`A2ATaskStatus` (e.g. in T020, T022, T024, T026, T032, the phase goals, and the Notes).
Leave the lowercase event types (`agent.task_request.v1`) and the `task.requested` topic name
unchanged. Note: the error type `UnknownTaskResult` (live T009) refers to *a result for an unknown
task*; rename to `UnknownA2ATaskResult` only if you want strict consistency — it is not one of the
five contract models.
