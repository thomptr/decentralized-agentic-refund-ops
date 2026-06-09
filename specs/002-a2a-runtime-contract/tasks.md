---
description: "Task list for Shared A2A Runtime Contract — Three Local Demo Agents"
---

# Tasks: Shared A2A Runtime Contract + Three Local Demo Agents

**Input**: Design documents from `/specs/002-a2a-runtime-contract/`

**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅, quickstart.md ✅

**Tests**: Included. The feature spec requests them (plan.md *Testing*; SC-002…SC-005 are "demonstrated by a test suite"). Test tasks are marked and may be skipped if you choose a non-TDD path, but they are the acceptance evidence.

**Organization**: Tasks are grouped by user story (spec.md) so each story can be implemented and tested independently.

## Scope note (read first)

Generated from the `/speckit-tasks` input *"Add local demo agents with fake handlers"*, reconciled with the feature spec:

- The three demo agents — `customer_resolution`, `billing_entitlement`, `risk_fraud` — return **mock results only**. They contain **no refund-domain business logic**, so they satisfy spec **FR-015** as the *minimal, non-domain example agents used solely to exercise and demonstrate the contract* (they replace the single `echo` example agent named in the plan). The domain-flavored names/capability ids are labels on mock handlers.
- The agents are a thin layer on the reusable **A2A runtime** that feature 002 defines. None of the runtime exists yet (`src/agent_foundation/runtime/` and `payloads/task.py` are absent), so the runtime is built in **Phase 2 (Foundational)** as a blocking prerequisite for every demo agent.
- **Constitution gate**: before starting any task, re-read `.specify/memory/constitution.md` and confirm the five principles. Every cross-agent call MUST traverse Kafka via `A2AClient` — no direct in-process calls, no supervisor/router (FR-011).

### Demo agent matrix

| Agent (`agent_id`) | Directory | Registered capabilities (mock) | Delegates to |
|--------------------|-----------|--------------------------------|--------------|
| `customer-resolution-agent` | `apps/agents/customer_resolution/` | `resolve_customer_case` | `billing-entitlement-agent` (via A2A) |
| `billing-entitlement-agent` | `apps/agents/billing_entitlement/` | `analyze_refund_eligibility` | — |
| `risk-fraud-agent` | `apps/agents/risk_fraud/` | `assess_fraud_risk` | — |

## Path Conventions

Single Python project. Library code under `src/agent_foundation/`, shared contracts under `packages/contracts/`, runnable demo agents under `apps/agents/`, tests under `tests/`. Paths below are repo-root-relative.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the demo-agent package layout and run configuration. No runtime logic yet.

- [X] T001 Create the demo-agent package tree: `apps/agents/__init__.py`, plus package dirs with `__init__.py` for `apps/agents/customer_resolution/`, `apps/agents/billing_entitlement/`, `apps/agents/risk_fraud/`.
- [X] T002 [P] Create `apps/agents/common.py` with shared demo scaffolding: `BROKER_URL` from env (`AGENT_BROKER_URL`, default `localhost:9092`), and a `run_agent(runtime)` bootstrap that configures `structlog`, installs a SIGINT/SIGTERM `asyncio.Event`, and calls `asyncio.run(runtime.serve(stop_event))`. Keep it ≤40 lines so agents don't duplicate boot code.
- [X] T003 [P] Add console-script entry points in `pyproject.toml` (`[project.scripts]`): `demo-customer-resolution`, `demo-billing-entitlement`, `demo-risk-fraud` → each agent's `main:main`; document the equivalent `python -m apps.agents.<name>.main` invocation.

---

## Phase 2: Foundational (Blocking Prerequisites — the reusable A2A runtime)

**Purpose**: Build the shared runtime contract every demo agent depends on (data-model.md §1–4, contracts/runtime-api.md, contracts/topics.md). **No demo agent can start until this phase is complete.**

**⚠️ CRITICAL**: This is the bulk of feature 002. Reuse the `001-event-foundation` envelope, publisher/consumer, idempotency tracker, and audit module (FR-014) — introduce **no** parallel transport or second audit path.

### Contracts & payloads

- [X] T004 [P] Add topic factories to `packages/contracts/topics.py`: `endpoint_topic(agent_id)` → `local.agent.<agent_id>.task.requested.v1`, `TOPIC_AGENT_CARD` (`topic_for("agent","agent-card","published")`), `TOPIC_TASK_RESULT` (`topic_for("agent","task","result")`). Do **not** add the dynamic endpoint topic to the static `TOPIC_NAMES` map (contracts/topics.md).
- [X] T005 [P] Create `src/agent_foundation/payloads/task.py` with `TaskStatus` literal, `TaskError`, `TaskRequest`, `TaskResult` (data-model.md §1.3–1.5). Implement the cross-field validators: `completed`⟹`output` set & `error` null; `failed`/`rejected`⟹`error` set & `output` null; `rejected`⟹`error.category∈{validation,unsupported_capability,duplicate}`; `failed`⟹`error.category∈{handler_error,internal}`. All models `frozen=True, extra="forbid"`.
- [X] T006 [P] Create `src/agent_foundation/runtime/agent_card.py` with `Capability` (id regex `^[a-z][a-z0-9_.-]{1,62}$`, name, description, tags) and `AgentCard` (agent_id, name, description, semver version, endpoint_topic, non-empty unique-id `capabilities`), both `frozen=True, extra="forbid"` (data-model.md §1.1–1.2).
- [X] T007 [P] Add task-lifecycle log event constants to `src/agent_foundation/logging.py` (e.g. `agent-card.published`, `endpoint.serving`, `task.accepted`, `task.rejected`, `task.completed`, `task.failed`, `task.duplicate-skipped`).
- [X] T008 [P] Add runtime error types to `src/agent_foundation/runtime/errors.py`: `TaskRejected`, `UnsupportedCapability`, `DuplicateTask`, `UnknownTask` (each maps to a `TaskError.category` per data-model.md §4 cross-references).
- [X] T009 Extend `AuditPayload` in `src/agent_foundation/payloads/sample.py`: add optional `task_id: UUID | None = None`; broaden `outcome` with `completed` and `failed`; require `reason` when `outcome` is `rejected` **or** `failed` (data-model.md §1.6). Keep backward compatible (new field optional, existing outcomes retained).
- [X] T010 Register the new payloads in `src/agent_foundation/payloads/__init__.py` `PAYLOAD_REGISTRY`: `agent.task_request.v1→TaskRequest`, `agent.task_result.v1→TaskResult`, `agent.agent_card.v1→AgentCard` (data-model.md §2). Depends on T005, T006.

### Transport & audit touch-points (modifications, not new transport)

- [X] T011 Add the new `NewTopic` definitions to `src/agent_foundation/transport/topics.py`: `TOPIC_AGENT_CARD` (`cleanup.policy=compact`), `TOPIC_TASK_RESULT` (`retention.ms=7d`); support creating a per-agent `endpoint_topic(x)` (7d retention) via the existing `create_topics()` / `extra_topics` path. Depends on T004.
- [X] T012 Add a backward-compatible optional `topic: str | None = None` parameter to `Publisher.publish()` in `src/agent_foundation/transport/publisher.py` that overrides registry topic resolution while keeping payload validation (research R5, contracts/runtime-api.md §4). Default behavior unchanged.
- [X] T013 Add `write_task_audit(publisher, envelope, outcome, task_id, reason=None)` to `src/agent_foundation/audit/store.py` as a thin wrapper over the existing audit write path (contracts/runtime-api.md §4). Depends on T009.

### Runtime, client, discovery

- [X] T014 Implement `AgentRuntime` in `src/agent_foundation/runtime/runtime.py` (contracts/runtime-api.md §1, data-model.md §4): `__init__(identity, card, broker_url)`; `handler(capability_id)` decorator that raises `ValueError` if the capability isn't on the card; `serve(stop_event)` that ensures topics exist, publishes the card, consumes the agent's `endpoint_topic`, and drives each `TaskRequest` through validate → (reject | accept) → run handler → (complete | fail), emitting the matching audit event(s) via `write_task_audit` and publishing exactly one `TaskResult`. Enforce idempotency by `task_id` via the reused `IdempotencyTracker` (duplicate → `duplicate_skipped` audit, no re-run). Add `republish_card()`. Depends on T005, T006, T008, T010, T011, T012, T013.
- [X] T015 [P] Implement `A2AClient` in `src/agent_foundation/runtime/client.py` (contracts/runtime-api.md §2): `submit(target_agent_id, capability, input, *, correlation_id, causation_id, task_id, timeout_s)` publishes a `TaskRequest` to `endpoint_topic(target_agent_id)` via `Publisher.publish(topic=...)`, then awaits the correlated `TaskResult` (filtered by `task_id`) from `TOPIC_TASK_RESULT`; raises `TimeoutError` after `timeout_s`. No router in the path (FR-011). Depends on T005, T012.
- [X] T016 [P] Implement discovery in `src/agent_foundation/runtime/discovery.py` (contracts/runtime-api.md §3): `publish_card(card, broker_url)`, `discover_agents(broker_url)` (read compacted `TOPIC_AGENT_CARD` from earliest, latest-card-per-`agent_id`), `find_capable(capability_id, broker_url)`. No central registry queried. Depends on T006, T011.
- [X] T017 Create `src/agent_foundation/runtime/__init__.py` exporting `AgentRuntime`, `A2AClient`, `AgentCard`, `Capability`, `discover_agents`, `find_capable`, `publish_card`, and the runtime error types. Depends on T014, T015, T016.

### Foundational tests (contract + state machine; no broker needed)

- [X] T018 [P] Unit tests for the payload contracts in `tests/unit/test_task_contracts.py`: valid round-trips and rejected invalid combinations for `TaskRequest`, `TaskResult` (all four validator rules), `TaskError`, `Capability`, `AgentCard` (unique capability ids, semver, regexes). Depends on T005, T006.
- [X] T019 [P] Unit tests for the lifecycle state machine in `tests/unit/test_runtime_state.py`: assert the FR-009 invariant — exactly one of {`rejected`} or {`accepted` + one of `completed`|`failed`} per `task_id`; validation/capability checks run before `accepted`; duplicate `task_id` short-circuits to `duplicate_skipped` with no re-run. Depends on T014.
- [X] T020 [P] Contract tests in `tests/contract/test_runtime_schemas.py`: JSON-schema round-trip of `agent-card`, `task-request`, `task-result`, `task-audit-payload` against `specs/002-a2a-runtime-contract/contracts/*.schema.json`. Depends on T005, T006, T009.

**Checkpoint**: The reusable runtime exists and is unit/contract-tested. Demo agents can now be built.

---

## Phase 3: User Story 1 - Stand up the three demo agents with their own endpoints (Priority: P1) 🎯 MVP

**Goal**: Each demo agent starts independently, exposes its own addressable A2A endpoint, and the runtime accepts only the capabilities that agent registered (rejecting anything else before the handler runs).

**Independent Test**: Start each agent in its own terminal; submit a well-formed task for a capability it declares and observe an `accepted` audit event + delivery to its mock handler; submit a task for an undeclared capability and observe a `rejected` (`unsupported_capability`) result with no handler execution. **Covers acceptance criteria 1 ("all three start independently") and 3 ("each accepts only its registered capabilities").**

### Implementation for User Story 1

- [X] T021 [P] [US1] Create `apps/agents/customer_resolution/main.py`: build `AgentCard(agent_id="customer-resolution-agent", …, capabilities=[Capability(id="resolve_customer_case", …)])`, construct `AgentRuntime`, register an async `@runtime.handler("resolve_customer_case")` returning a **mock** `A2AMessage` (a fixed resolution summary), and a `main()` that calls `apps.agents.common.run_agent(runtime)`.
- [X] T022 [P] [US1] Create `apps/agents/billing_entitlement/main.py`: `AgentCard(agent_id="billing-entitlement-agent", …, capabilities=[Capability(id="analyze_refund_eligibility", …)])`, runtime, `@runtime.handler("analyze_refund_eligibility")` returning a **mock** eligibility verdict `A2AMessage` (e.g. `{"eligible": true, "reason": "mock"}`), `main()` via `run_agent`.
- [X] T023 [P] [US1] Create `apps/agents/risk_fraud/main.py`: `AgentCard(agent_id="risk-fraud-agent", …, capabilities=[Capability(id="assess_fraud_risk", …)])`, runtime, `@runtime.handler("assess_fraud_risk")` returning a **mock** risk score `A2AMessage` (e.g. `{"risk": "low", "score": 0.1}`), `main()` via `run_agent`.
- [X] T024 [US1] Integration test `tests/integration/test_demo_agents_startup.py` (testcontainers Kafka, `@pytest.mark.integration`): start each of the three agents, submit one valid task per agent via `A2AClient` and assert the mock output + an `accepted` audit event; submit one undeclared-capability task per agent and assert `TaskResult(status="rejected", error.category="unsupported_capability")` with no handler side effect. Depends on T021–T023.

**Checkpoint**: All three agents start independently, are addressable, and reject unsupported capabilities. (Acceptance criteria 1 & 3 met.)

---

## Phase 4: User Story 2 - Return structured mock results, success and failure (Priority: P1)

**Goal**: Every accepted task returns a structured `TaskResult` — `completed` with typed mock output, or `failed` with a structured error — and emits the matching terminal audit event, distinct from a rejection (FR-006/FR-007).

**Independent Test**: Submit a task the agent satisfies → `TaskResult(status="completed")` + `completed` audit; submit a task carrying the failure sentinel → `TaskResult(status="failed", error.category="handler_error")` + `failed` audit; confirm exactly one terminal outcome per accepted task.

### Implementation for User Story 2

- [X] T025 [US2] Add a failure path to `apps/agents/billing_entitlement/main.py`: when the input text/part equals the sentinel `"FAIL"`, the `analyze_refund_eligibility` handler raises, so the runtime produces `TaskResult(status="failed", error.category="handler_error")` + a `failed` audit. Document the sentinel in a module docstring.
- [X] T026 [P] [US2] Ensure the `customer_resolution` and `risk_fraud` mock handlers return well-typed `completed` outputs (typed `A2AMessage` parts, not bare strings) so the success contract is exercised across all three agents. Edits `apps/agents/customer_resolution/main.py` and `apps/agents/risk_fraud/main.py`.
- [X] T027 [US2] Add `tests/integration/test_demo_agents_results.py`: assert the success path returns `completed` with the expected mock output for each agent, and the billing `"FAIL"` sentinel returns `failed` (not `rejected`); assert exactly one terminal audit event per accepted `task_id` (FR-009). Depends on T025, T026.

**Checkpoint**: The request→result loop is complete for all three agents, with rejection vs failure clearly distinguished.

---

## Phase 5: User Story 3 - Each agent exposes an Agent Card and one agent calls another via A2A (Priority: P2)

**Goal**: Every agent publishes its Agent Card to the discovery channel on startup (discoverable with no central registry), and one agent delegates a sub-task to another purely over A2A. **Covers acceptance criteria 2 ("each exposes an Agent Card") and 4 ("one agent can call another through A2A").**

**Independent Test**: With all three agents running, `discover_agents()` returns three cards with the right capabilities; trigger `customer-resolution-agent`'s handler and confirm it delegates `analyze_refund_eligibility` to `billing-entitlement-agent` via `A2AClient` and folds the peer's mock result into its own — with the delegation path going requester→performer directly.

### Implementation for User Story 3

- [X] T028 [US3] In `apps/agents/customer_resolution/main.py`, make the `resolve_customer_case` handler instantiate an `A2AClient` and `submit()` an `analyze_refund_eligibility` task to `billing-entitlement-agent`, propagating `correlation_id`/`causation_id` from the incoming request, then include the peer's mock verdict in its own `completed` output (FR-011). Depends on T015, T021, T022.
- [X] T029 [P] [US3] Add a `discover` demo helper (`apps/agents/discover.py` or a function in `apps/agents/common.py`) that calls `discover_agents()`/`find_capable()` and prints the cards, so reviewers can list capabilities with no registry. Depends on T016.
- [X] T030 [US3] Integration test `tests/integration/test_demo_agents_a2a.py`: start all three agents; assert `discover_agents()` returns the three expected cards (criterion 2); submit a `resolve_customer_case` task and assert the result reflects a real A2A round-trip to `billing-entitlement-agent` (criterion 4), with a `billing` audit trail correlated to the originating workflow. Depends on T028, T029.

**Checkpoint**: Capability discovery and peer-to-peer delegation work end-to-end across the three agents. (Acceptance criteria 2 & 4 met.)

---

## Phase 6: User Story 4 - Audit the full task lifecycle across the demo agents (Priority: P2)

**Goal**: Every task any demo agent handles leaves a queryable audit trail (accepted/rejected/completed/failed) recoverable by `task_id` and by `correlation_id` (FR-008/FR-012).

**Independent Test**: Drive a mix of accepted, rejected, completed, and failed tasks across the three agents; query by `task_id` and confirm each task's full lifecycle (outcome, agent identity, timestamp, and reason for rejection/failure); query the cross-agent `resolve_customer_case` workflow by `correlation_id` and confirm both the customer-resolution and billing audit events appear in causal order.

### Implementation for User Story 4

- [X] T031 [US4] Add a `query-task-audit --task-id <uuid>` capability for the demo (reuse the runtime CLI command from contracts/runtime-api.md §5, or add `apps/agents/audit_query.py`) that reads the audit topic and prints a task's lifecycle ordered by Kafka offset. Depends on T013, T014.
- [X] T032 [US4] Integration test `tests/integration/test_demo_agents_audit.py`: assert per-`task_id` audit sequences — completed ⇒ `accepted`→`completed`; failed ⇒ `accepted`→`failed` (with reason); rejected ⇒ single `rejected` (with reason); and that the cross-agent workflow's events share one `correlation_id`. Depends on T030, T031.

**Checkpoint**: The four-outcome lifecycle is fully auditable and queryable for the demo agents.

---

## Phase 7: User Story 5 - Confirm there is no supervisor or central router (Priority: P3)

**Goal**: Verify the demo wiring contains no supervisor/router/dispatcher/orchestrator; every delegation is requester→performer over the agent's endpoint topic (FR-011, SC-008).

**Independent Test**: Inspect the three `main.py` files and `common.py`; confirm the only components are agents, `A2AClient` callers, and Kafka. Trace the `customer-resolution`→`billing-entitlement` delegation and confirm it addresses `endpoint_topic("billing-entitlement-agent")` directly.

### Implementation for User Story 5

- [X] T033 [US5] Test `tests/integration/test_no_router.py`: assert (a) no module under `apps/agents/` imports or defines a dispatcher/router/orchestrator, (b) cross-agent traffic in the `resolve_customer_case` flow lands on the target's `endpoint_topic` with no intermediary topic, and (c) starting an agent creates only its own endpoint topic plus the shared card/result topics. Depends on T030.
- [X] T034 [US5] Add a short "No supervisor / no router" subsection to `apps/agents/README.md` describing how a reviewer confirms the direct delegation path with the three demo agents (mirrors quickstart.md Scenario 6).

**Checkpoint**: Decentralization is demonstrated and documented for the demo. (All four acceptance criteria + the constitutional guardrail covered.)

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, runnability, and cleanup spanning all stories.

- [X] T035 [P] Write `apps/agents/README.md`: how to start each agent independently, run `discover`, submit a cross-agent task, and query the audit trail — the demo-agent counterpart to `quickstart.md`. Note the mock-only nature and the `"FAIL"` sentinel.
- [X] T036 [P] Add `infra/local/run-demo-agents.sh` (or document the commands) to launch all three agents for a one-command demo, reusing the foundation's `docker compose` Kafka stack.
- [ ] T037 [P] Update the agent-context file via `/speckit-agent-context-update` so the new `runtime/` package, `payloads/task.py`, demo agents, and topics are reflected.
- [X] T038 Run `uv run ruff`/formatter and the foundation's lint/security checks across new `src/`, `packages/`, `apps/`, and `tests/` code; fix findings.
- [ ] T039 Run the full quickstart validation (`specs/002-a2a-runtime-contract/quickstart.md`) adapted to the three demo agents; confirm Scenarios 1–6 pass end-to-end.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Foundational (Phase 2)**: Depends on Setup. **Blocks every user story** — the demo agents cannot import a runtime that doesn't exist.
- **User Stories (Phases 3–7)**: All depend on Foundational completion.
  - US1 (P1) → US2 (P1) build on the same `apps/agents/*/main.py` files, so run in priority order.
  - US3 (P2) depends on US1 (agents exist) + Foundational `A2AClient`/discovery; US4 (P2) depends on US3 (cross-agent workflow to audit); US5 (P3) depends on US3.
- **Polish (Phase 8)**: Depends on all desired user stories.

### User Story Dependencies

- **US1 (P1)**: After Foundational. Independently testable (start + reject).
- **US2 (P1)**: After US1 (extends the same handler files with success/failure outputs).
- **US3 (P2)**: After Foundational + US1 (needs running agents to discover/delegate).
- **US4 (P2)**: After US3 (audits the cross-agent workflow; single-agent lifecycle auditable after US2).
- **US5 (P3)**: After US3 (traces the delegation path).

### Within Each Story

- Tests (where included) should fail before implementation, or be written alongside, per your TDD preference.
- Contracts/models before runtime; runtime before demo agents; agents before cross-agent/audit/no-router tests.

### Parallel Opportunities

- Setup `[P]` tasks T002, T003 run in parallel after T001.
- Foundational `[P]` contract/model/error/log tasks T004–T008 run in parallel; T015/T016 in parallel after T014's deps; T018–T020 in parallel once their deps land.
- US1 agent files T021/T022/T023 run fully in parallel (different files).
- Polish T035–T037 run in parallel.

---

## Parallel Example: User Story 1

```bash
# The three demo agents are independent files — build them together:
Task: "Create apps/agents/customer_resolution/main.py (resolve_customer_case mock handler)"      # T021
Task: "Create apps/agents/billing_entitlement/main.py (analyze_refund_eligibility mock handler)" # T022
Task: "Create apps/agents/risk_fraud/main.py (assess_fraud_risk mock handler)"                   # T023
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1: Setup.
2. Phase 2: Foundational — build and unit/contract-test the reusable runtime (the critical path).
3. Phase 3: US1 — three agents start independently and reject unsupported capabilities.
4. **STOP and VALIDATE**: acceptance criteria 1 & 3 met; demo the three agents standing up.

### Incremental Delivery

1. Setup + Foundational → runtime ready.
2. US1 → three independent, addressable agents (MVP — criteria 1, 3).
3. US2 → structured mock results, success + failure.
4. US3 → Agent Card discovery + one-agent-calls-another (criteria 2, 4) — **all four acceptance criteria met here**.
5. US4 → full lifecycle audit.
6. US5 → no-supervisor/no-router confirmation.
7. Polish → docs + one-command demo.

---

## Acceptance-Criteria Traceability

| Acceptance criterion (from `/speckit-tasks` input) | Satisfied by |
|----------------------------------------------------|--------------|
| All three agents start independently | T021–T024 (US1) |
| Each exposes an Agent Card | T014/T016 (runtime publishes card) + T030 (US3 discovery assertion) |
| Each accepts only its registered capabilities | T014 (validation) + T024 (US1 rejection test) |
| One agent can call another through A2A | T015/T028/T030 (US3 cross-agent delegation) |

## Notes

- `[P]` = different files, no incomplete-task dependency.
- `[Story]` label maps each task to a spec.md user story for traceability.
- Demo handlers are **mock-only** — no refund-domain logic (FR-015). Keep them trivial.
- Reuse the foundation's transport/audit/idempotency everywhere; do not add a parallel path (FR-014).
- Commit after each task or logical group.

---

## Phase 9: A2A Contract Tests — Focused Test Deliverable

**Added by the "Add A2A contract tests" `/speckit-tasks` run.** This phase delivers the **10
explicitly requested contract test cases** that pin the runtime's externally-observable behavior.
It is a **test-only** deliverable (plus one tiny client enhancement, T044, called out below) and
**reuses, not duplicates**, the contracts/behavior built earlier: `AgentCard`/`Capability` (T006),
`TaskRequest`/`TaskResult`/`TaskError` (T005), the `endpoint_topic`/`TOPIC_AGENT_CARD`/
`TOPIC_TASK_RESULT` factories (T004), the `AgentRuntime` lifecycle (T014: validate → reject/accept →
run handler → complete/fail + `task_id` idempotency), `A2AClient.submit` (T015), discovery (T016),
the `write_task_audit` helper + audit query (T013/T031), and the three demo agents (T021–T023, with
the billing `"FAIL"` sentinel from T025).

> **Task-ID note**: IDs start at **T040** to continue past the highest existing ID (T039, Phase 8).

> **File-isolation decision**: these cases land in **new, dedicated** modules
> (`tests/contract/test_a2a_contract.py`, `tests/unit/test_a2a_contract.py`,
> `tests/integration/test_a2a_contract.py`) rather than editing the shared test files Phases 2–7
> already write (`test_task_contracts.py`, `test_runtime_state.py`, `test_runtime_schemas.py`,
> `test_demo_agents_*.py`). This keeps the suite independently runnable and conflict-free. Where a
> case overlaps an existing planned test (noted per task), this is the **named, focused** version of
> that assertion, not a second source of truth for the behavior.

> **⚠️ Timeout-case scope clarification (case 8)**: "Timeout returns structured error" maps to the
> **client-side** await-timeout in `A2AClient.submit(..., timeout_s=...)` (T015 raises `TimeoutError`
> if no correlated `TaskResult` arrives in time). It is **NOT** server-side handler liveness/deadline
> detection, which the spec explicitly defers ("Liveness and timeout handling are out of scope", spec
> Assumptions). The test asserts the client surfaces a typed timeout within ~`timeout_s` and documents
> the distinction.

> **Client-preflight gap (case 3)**: the current `A2AClient.submit` (T015) only *publishes* — it has
> no client-side capability check. To make "Client rejects unknown capability **before sending**"
> green-able rather than dangling, T044 adds a small preflight to the client (consult discovery, raise
> before publishing). T043 is the test for it.

**Tests are written TDD-first** and must FAIL until their referenced tasks land.

**Test case → task → story → file map**:

| # | Requested test case | Task | Story | File | Validates |
|---|---------------------|------|-------|------|-----------|
| 1 | Agent Card validates successfully | T041 | US3 | tests/contract/test_a2a_contract.py | T006 |
| 2 | Agent Card endpoint returns expected metadata | T042 | US3 | tests/contract/test_a2a_contract.py | T006/T004 |
| 3 | Client rejects unknown capability before sending task | T043 (+T044 impl) | US1 | tests/unit/test_a2a_contract.py | T015/T016 |
| 4 | Server rejects unknown capability | T045 | US1 | tests/integration/test_a2a_contract.py | T014 |
| 5 | Server rejects wrong target_agent_id | T046 | US1 | tests/integration/test_a2a_contract.py | T014 |
| 6 | Valid task executes registered handler | T047 | US1/US2 | tests/integration/test_a2a_contract.py | T014/T021–T023 |
| 7 | Duplicate idempotency key does not re-execute handler | T048 | US1 | tests/integration/test_a2a_contract.py | T014 |
| 8 | Timeout returns structured error | T049 | US2 | tests/integration/test_a2a_contract.py | T015 |
| 9 | Failure emits audit event | T050 | US4 | tests/integration/test_a2a_contract.py | T025/T013 |
| 10 | Completed task emits audit event | T051 | US4 | tests/integration/test_a2a_contract.py | T014/T013 |

**Independent Test**: `uv run pytest tests/contract/test_a2a_contract.py tests/unit/test_a2a_contract.py`
(no broker) and `uv run pytest -m integration tests/integration/test_a2a_contract.py` (testcontainers
Kafka); all 10 named cases pass once their referenced tasks are complete, demonstrating
SC-002/SC-003/SC-004/SC-005 from one focused suite.

### Shared fixtures (Phase 9 prerequisite)

- [X] T040 [P] Add Phase-9 test fixtures: broker-free builders in `tests/conftest.py` (`make_agent_card`, `make_task_request`, `make_task_error`, reusing the existing `sample_agent_identity` fixture) and a live-broker harness in `tests/integration/conftest.py` (module-scoped `kafka_bootstrap_servers` via testcontainers `KafkaContainer("confluentinc/cp-kafka:7.6.0")`, matching `tests/integration/test_idempotency.py`; a `create_runtime_topics(broker)` helper ensuring `endpoint_topic(agent_id)` + `TOPIC_TASK_RESULT` + `TOPIC_AGENT_CARD` exist; a `serving_agent` fixture starting one demo agent's `AgentRuntime.serve()` in a background task — default `billing-entitlement-agent` so the `"FAIL"` sentinel from T025 is available; and an `a2a_client` fixture). Builders block T041–T043; harness blocks T045–T051. Depends on Foundational (T005, T006, T011, T014, T015) + demo agents (T021–T023, T025).

### Tests for A2A Contract Tests ⚠️ (write first, ensure they FAIL before implementing)

- [X] T041 [P] [US3] **Case 1 — Agent Card validates successfully**: in `tests/contract/test_a2a_contract.py` (new file), build a valid `AgentCard` via `make_agent_card` and assert it validates and JSON round-trips (`AgentCard.model_validate_json(card.model_dump_json())`); and that a malformed card (empty `capabilities`, duplicate `Capability.id`, or non-semver `version`) raises `pydantic.ValidationError` (data-model §1.1–§1.2, T006). No broker → [P]. Depends on T040. (Focused version of the card checks in T018/T020.)
- [X] T042 [US3] **Case 2 — Agent Card endpoint returns expected metadata**: in `tests/contract/test_a2a_contract.py`, assert a built card exposes the expected metadata — `agent_id`, `name`, `description`, semver `version`, the declared `Capability.id`s, and `endpoint_topic == endpoint_topic(agent_id)` from `packages/contracts/topics.py` (T004, contracts/topics.md). Same file as T041 → run after T041. Depends on T040, T004.
- [X] T043 [P] [US1] **Case 3 — Client rejects unknown capability before sending task**: in `tests/unit/test_a2a_contract.py` (new file, discovery + `Publisher` stubbed, no broker), stub the target's published card to declare only its real capability, then call `A2AClient.submit(target, capability="does_not_exist", ...)` and assert it raises `UnsupportedCapability` **before** publishing — assert the stubbed `Publisher.publish` was never called. Depends on T040, T044, T016. [P] (distinct file).
- [X] T044 [US1] **(impl) Add client-side capability preflight to `A2AClient.submit`** in `src/agent_foundation/runtime/client.py` (extends T015, depends on T016): before publishing the `TaskRequest`, resolve the target's latest `AgentCard` via `discover_agents()`/`find_capable()` and raise `UnsupportedCapability` if `capability` is not a declared `Capability.id` for `target_agent_id`; on the happy path, publish exactly as before. No router introduced (FR-011). Makes T043 green.
- [X] T045 [US1] **Case 4 — Server rejects unknown capability**: in `tests/integration/test_a2a_contract.py` (new file, `pytestmark = pytest.mark.integration`), submit a `TaskRequest` to the serving agent's endpoint naming a capability it does not declare; assert `TaskResult.status == "rejected"` with `error.category == "unsupported_capability"`, the handler did **not** run, and a single `rejected` audit (no `accepted`) is recorded (FR-005, T014). Depends on T040.
- [X] T046 [US1] **Case 5 — Server rejects wrong target_agent_id**: in `tests/integration/test_a2a_contract.py`, deliver a `TaskRequest` whose `target_agent_id` is not the serving agent's id to that agent's endpoint topic; assert it is rejected (`error.category == "validation"`) before the handler runs (data-model §4 invariant 2, T014). Same file → run after T045.
- [X] T047 [US1] **Case 6 — Valid task executes registered handler**: in `tests/integration/test_a2a_contract.py`, `a2a_client.submit(target, <declared capability>, input)` for the serving demo agent's real capability (e.g. `analyze_refund_eligibility`); assert the mock handler ran (typed output present), `TaskResult.status == "completed"`, and `performer_agent_id` is the serving agent (T014, T022/T026). Same file → run after T046.
- [X] T048 [US1] **Case 7 — Duplicate idempotency key does not re-execute handler**: in `tests/integration/test_a2a_contract.py`, submit two requests sharing the same `task_id` (replay the request envelope as in `tests/integration/test_idempotency.py`); assert the handler is invoked exactly once, the second is audited `duplicate_skipped`, and no second terminal `TaskResult` is produced (FR-010, T014). Same file → run after T047.
- [X] T049 [US2] **Case 8 — Timeout returns structured error**: in `tests/integration/test_a2a_contract.py`, call `a2a_client.submit(target=<no agent serving that id>, capability=<any>, ..., timeout_s=<short>)` and assert it raises a typed `TimeoutError` within ~`timeout_s` (T015). Add an inline comment citing spec Assumptions: client await-timeout, NOT server-side handler liveness (out of scope). Same file → run after T048.
- [X] T050 [US4] **Case 9 — Failure emits audit event**: in `tests/integration/test_a2a_contract.py`, submit an `analyze_refund_eligibility` task carrying the `"FAIL"` sentinel (T025) so the billing handler raises; query the audit trail by `task_id` (T013/T031) and assert the sequence is `accepted` then `failed`, the `failed` record carries a non-null `reason`, and `TaskResult.status == "failed"` with `error.category == "handler_error"` (FR-007/FR-008). Same file → run after T049.
- [X] T051 [US4] **Case 10 — Completed task emits audit event**: in `tests/integration/test_a2a_contract.py`, submit a successful task and query the audit trail by `task_id` (T013/T031); assert the sequence is exactly `accepted` then `completed` — never both terminal, never neither (FR-009, T014). Same file → run after T050.

**Checkpoint**: All 10 named A2A contract tests exist as a focused, independently-runnable suite;
each fails red until its referenced task lands, then pins the card-validation, client-preflight,
server-side reject/accept/idempotency, client-timeout, and audit-lifecycle contracts
(SC-002/SC-003/SC-004/SC-005).

### Phase 9 dependencies

- Depends on **Foundational (Phase 2)** (T004 topic factories, T005 task contracts, T006 card models,
  T011 topics, T013 audit helper, T014 runtime, T015 client, T016 discovery) and on **US1/US2 demo
  agents** (T021–T023, T025 `"FAIL"` sentinel) and the **US4 audit query** (T031, for T050/T051).
- Does not block any other phase — it is a verification layer over existing behavior; only T044 adds
  production code (a backward-compatible client preflight).
- Parallel: T040 (fixtures) first; then T041 (contract) and T043 (unit) run in parallel with the
  integration cases. Same-file cases serialize: contract `test_a2a_contract.py` T041 → T042;
  integration `test_a2a_contract.py` T045 → T046 → T047 → T048 → T049 → T050 → T051.

---

## Phase 10: Agent Card Endpoint — Identity, Skills, Capabilities & Auth Metadata

**Added by the "Implement Agent Card endpoint" `/speckit-tasks` run.** Original input: *"Each agent
should expose `GET /.well-known/agent.json`; endpoint returns valid JSON; includes agent identity,
skills, capabilities, and auth metadata; no central registry is required for local discovery."*

This phase is a **focused delta**, not a rewrite. Agent Card publication and discovery already exist
and are **reused, not duplicated**: the `AgentCard`/`Capability` models (T006), the
`endpoint_topic`/`TOPIC_AGENT_CARD` factories (T004), card publication on `serve()` start +
`republish_card()` (T014), the compacted-topic discovery `discover_agents()`/`find_capable()` (T016),
the demo `discover` helper (T029), the discovery integration test (T030), and the card contract tests
(T041 card-validates, T042 card-returns-expected-metadata). This phase adds only what those tasks do
not yet cover.

> **Three decisions applied to this run (from the `/speckit-tasks` clarification):**
> 1. **Transport = Kafka compacted discovery topic** (`local.agent.agent-card.published.v1`), per
>    research R1/R2. This *is* the "Agent Card endpoint" and satisfies "no central registry required
>    for local discovery." The literal HTTP `GET /.well-known/agent.json` is **NOT built here** — it
>    is recorded as a future AWS Bedrock AgentCore concern (research R6) in T058.
> 2. **AgentCard gains an auth-metadata stub** (A2A-style `securitySchemes`/`security` defaulting to
>    `"none"`) to satisfy the "includes auth metadata" criterion while honoring the no-auth deferral
>    (Principle V). This is a delta over the current `data-model.md`/`agent-card.schema.json`.
> 3. **Scope = full feature** — already realized by Phases 1–9; this phase only completes the card
>    acceptance criteria.

> **Task-ID note**: IDs start at **T052** to continue past the highest existing ID (T051, Phase 9).

### Acceptance-criteria traceability (this run)

| Acceptance criterion | Satisfied by |
|----------------------|--------------|
| Endpoint returns valid JSON | T056/T057 (published card round-trips as valid JSON over the discovery topic) — builds on T041 |
| Includes agent identity, skills, capabilities | T042 (existing: `agent_id`/`name`/`version`/`Capability.id`s) + T056 assertion |
| Includes auth metadata | T052 (model field) + T053 (schema) + T056 (assert present == `"none"` stub) |
| No central registry required for local discovery | T016/T029/T030 (existing compacted-topic discovery) + T057 (documented) |

### Implementation for Agent Card Endpoint

- [X] T052 [US3] Add the auth-metadata stub field to `AgentCard` in `src/agent_foundation/runtime/agent_card.py` (extends T006): an A2A-aligned `security_schemes` / `security` field defaulting to the PoC stub `"none"` (e.g. `security: Literal["none"] = "none"`, or a minimal `securitySchemes: dict = {}` + `security: list[str] = []` pair — choose the A2A-closest shape and keep `frozen=True, extra="forbid"`). Backward compatible: existing card construction in T021–T023 stays valid.
- [X] T053 [US3] Update `specs/002-a2a-runtime-contract/contracts/agent-card.schema.json` and `data-model.md` §1.2 to add the new auth-metadata field (matching T052: type, default `"none"`, `additionalProperties:false` preserved) so the schema/contract stays in sync with the model.
- [X] T054 [P] [US3] Set auth metadata explicitly on each demo agent's `AgentCard` (security = `"none"`) in `apps/agents/customer_resolution/main.py`, `apps/agents/billing_entitlement/main.py`, and `apps/agents/risk_fraud/main.py`, so the published cards demonstrate the auth-metadata field rather than relying solely on the default. Depends on T052.
- [X] T055 [US3] Update the existing card schema/contract tests for the new field: in `tests/contract/test_runtime_schemas.py` (T020) and `tests/contract/test_a2a_contract.py` (T041/T042), assert the auth-metadata field is present, defaults to `"none"`, and JSON round-trips; assert a card with an invalid auth value raises `pydantic.ValidationError`. Depends on T052, T053.

### Tests for Agent Card Endpoint

- [X] T056 [US3] **Card acceptance test (all three criteria, no broker)** in `tests/contract/test_a2a_contract.py`: build a card via `make_agent_card` (with auth stub) and assert `AgentCard.model_dump_json()` is valid JSON that contains **identity** (`agent_id`, `name`, `version`), **skills/capabilities** (non-empty `capabilities` with `Capability.id`/`name`/`description`), and **auth metadata** (the T052 field == `"none"`). This is the named acceptance-criteria assertion for this run; reuses T041/T042. Depends on T052.
- [X] T057 [US3] **Discovery acceptance test over Kafka (no central registry)** in `tests/integration/test_demo_agents_a2a.py` (extends T030, `@pytest.mark.integration`): after the three agents publish, call `discover_agents()` (reading only the compacted `TOPIC_AGENT_CARD`) and assert each returned card is valid JSON including identity + capabilities + auth metadata, and that no registry/router process participates (the listing comes purely from the event log). Depends on T054, T030.

### Documentation

- [X] T058 [P] [US3] Document the Agent Card endpoint in `apps/agents/README.md` (and/or `docs/runtime.md`): (a) the A2A Agent Card is served over the compacted Kafka discovery topic — "registry-like without a central registry" — and discovered via `discover_agents()`; (b) the HTTP `GET /.well-known/agent.json` URI is a **future AWS Bedrock AgentCore** concern, intentionally not built in this PoC (research R6); (c) auth metadata is a **stub only** (`"none"`; real auth/TLS/ACLs deferred per Principle V). Reference quickstart Scenario 2.

**Checkpoint**: Every agent publishes a JSON-valid Agent Card carrying identity, skills/capabilities,
and auth metadata, discoverable peer-to-peer with no central registry — the four acceptance criteria
for this run are met and verified.

### Phase 10 dependencies

- Depends on **Foundational** (T004 factories, T006 card model, T011 topics, T016 discovery) and the
  **demo agents** (T021–T023) and **discovery test** (T030).
- Order within the phase: T052 → T053 → (T054 ∥ T055) → T056 → T057 → T058. T054 and T058 are `[P]`
  (distinct files); the schema/contract-test edits (T055) and the card model (T052) gate the tests.
- Does not block other phases — it completes the card acceptance criteria on top of existing behavior.
  Only T052/T053/T054 touch production code/contracts (all backward compatible).
