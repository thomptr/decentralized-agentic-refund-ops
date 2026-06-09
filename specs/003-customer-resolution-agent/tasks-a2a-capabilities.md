---
description: "Focused task list for exposing the Customer Resolution Agent's local A2A capabilities"
---

# Tasks: Customer Resolution A2A Capabilities

**Input**: Design documents from `/specs/003-customer-resolution-agent/`

**Prerequisites**: plan.md (required), spec.md (FR-001, US2/US3), research.md (R2/R7), data-model.md
(§2/§4/§7), contracts/decision-policy.md (§A/§C). Runtime contract:
`specs/002-a2a-runtime-contract/` (AgentCard, capability dispatch, `TaskRequest`/`TaskResult`).

> **Companion file**: The full end-to-end task list lives in `tasks.md` (US1–US6: ticket intake,
> peer delegation, result aggregation, decision event). The ticket-classifier slice lives in
> `tasks-classifier.md`. **This file is a focused slice** covering only the agent's *inbound* A2A
> capability surface — declaring three local capabilities on the Agent Card and wiring their handlers
> to the internal services. It **augments** `tasks.md` (adds the inbound-capability wiring the
> end-to-end list does not cover) and leaves it otherwise unchanged. Where a handler reuses an
> internal service, that service is built in `tasks.md` / `tasks-classifier.md`; this slice depends on
> those service seams (called out in Phase 2).

**Scope**: Expose three **local A2A capabilities** so future peer agents can invoke the resolution
agent over the shared runtime, with each handler delegating to existing internal services (never
reimplementing domain logic):

| Capability id (A2A) | Internal service reused | Purpose |
|---------------------|-------------------------|---------|
| `classify_customer_ticket` | `ticket_classifier.classify()` (US1 triage/classification) | Classify an inbound ticket (refund-vs-direct, review flags). |
| `draft_customer_response` | `response_drafter` / `decision_engine.decide()` (US3) | Draft the customer-facing response for a resolved/triaged case. |
| `close_customer_case` | `state_store.CaseStore` closure (US3/§4 state machine) | Mark a resolution case terminal and return its closure record. |

**Out of scope here** (remains in `tasks.md`): the `support.ticket.created` intake consumer, the
`task.result` aggregation loop, peer delegation, and emitting the `customer.resolution.decided`
event. This slice is purely the **inbound capability endpoint**.

**Acceptance criteria → user stories** (from the `/speckit-tasks` request):

| Acceptance criterion | User story |
|----------------------|------------|
| Agent Card includes these capabilities | **US1** (P1) |
| Capabilities can be called by future agents | **US2** (P1) |
| Capability handlers reuse internal services | **US3** (P1) |
| Unknown capabilities are rejected by A2A runtime | **US4** (P2) |

**Tests**: INCLUDED — three of the four acceptance criteria are externally observable runtime
behaviors (card contents, dispatch, rejection) that the plan's "Testing" section and quickstart's
"Automated validation" require. Test tasks are generated per story and **must fail before** their
implementation.

**Organization**: Grouped by user story; each story maps to one acceptance criterion and is
independently testable. Most wiring lives in two files (`capabilities.py`, `main.py`), so honest
file-level parallelism is limited and called out per task.

## Path conventions

Single Python project (`src/`, `apps/`, `packages/`, `tests/` at repo root), per plan.md. The
resolution agent package is `apps/agents/customer_resolution/`. The runtime library
(`src/agent_foundation/runtime/`) is **reused unchanged** — the capability-check and unknown-capability
rejection already exist in `runtime.py:_handle_message` (FR-016).

---

## Phase 1: Setup

**Purpose**: Create the capability-slice module and its I/O contract; no runtime/library changes.

- [ ] T001 Create `apps/agents/customer_resolution/capabilities.py` with a module docstring and the three A2A capability-id constants `CAP_CLASSIFY_TICKET = "classify_customer_ticket"`, `CAP_DRAFT_RESPONSE = "draft_customer_response"`, `CAP_CLOSE_CASE = "close_customer_case"` (validated against `Capability.id` regex `^[a-z][a-z0-9_.-]{1,62}$`).
- [ ] T002 [P] Author the inbound capability I/O contract in `specs/003-customer-resolution-agent/contracts/customer-resolution-capabilities.md` — the `A2AMessage` data-part shape for each capability's request input and result output (classify: ticket fields → classification; draft: decision context → `customer_response`; close: `correlation_id`/outcome → closure record), referencing data-model.md §2/§4/§7.

**Checkpoint**: Capability module and contract exist; no behavior yet.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Establish the internal-service seams the handlers reuse and the data-part mapping helpers, so every user story below can build on them.

**⚠️ CRITICAL**: No user-story work can begin until this phase is complete. These seams are
implemented in `tasks.md` / `tasks-classifier.md`; this phase imports them (or adds a thin
pass-through if a seam is not yet present) without duplicating domain logic.

- [ ] T003 Confirm the internal service entry points are importable by handlers, adding a thin module-level seam only where missing: `classify(ticket)` in `apps/agents/customer_resolution/ticket_classifier.py`, a response draft function in `apps/agents/customer_resolution/response_drafter.py`, `decide(...)` in `apps/agents/customer_resolution/decision_engine.py`, and `CaseStore` in `apps/agents/customer_resolution/state_store.py` (per `tasks.md` file-layout note).
- [ ] T004 [P] Add A2A data-part (de)serialization helpers in `apps/agents/customer_resolution/capabilities.py`: `ticket_from_message(msg)`, `classification_to_message(result)`, `draft_to_message(text, ...)`, `closure_to_message(case)` — pure functions mapping between `A2AMessage` data parts (per the T002 contract) and the internal models; raise a clear `ValueError` on malformed/missing parts.
- [ ] T005 Expose a single shared `CaseStore` accessor in `apps/agents/customer_resolution/state_store.py` (e.g. a process-scoped instance/factory) so the `close_customer_case` handler operates on the same in-process case state as the event loops (data-model.md §4), preventing a divergent second store.

**Checkpoint**: Service seams and mapping helpers ready — capability handlers can now be wired.

---

## Phase 3: User Story 1 - Agent Card includes these capabilities (Priority: P1) 🎯 MVP

**Goal**: The Customer Resolution Agent's published `AgentCard` declares the three local capabilities
(`classify_customer_ticket`, `draft_customer_response`, `close_customer_case`) with valid metadata, so
peers can discover them (FR-001).

**Independent Test**: Build the agent's `AgentCard` and assert it contains exactly the three capability
ids with valid, unique `Capability` entries; run discovery and confirm the resolution agent advertises
all three.

### Tests for User Story 1 ⚠️

> Write these tests FIRST and ensure they FAIL before implementation.

- [ ] T006 [P] [US1] Contract test in `tests/contract/test_capability_card.py`: construct the resolution agent's `AgentCard` (or import its factory from `apps/agents/customer_resolution/main.py`) and assert its `capabilities` include `classify_customer_ticket`, `draft_customer_response`, `close_customer_case` with valid `id`/`name`/`description` and unique ids (`AgentCard` validators pass).

### Implementation for User Story 1

- [ ] T007 [US1] In `apps/agents/customer_resolution/main.py`, replace the placeholder `resolve_customer_case` capability with the three `Capability(...)` entries (ids from `capabilities.py` constants, descriptive `name`/`description`/`tags`) and bump the card `version` (e.g. `2.0.0`).
- [ ] T008 [US1] Verify discovery output: confirm `apps/agents/discover.py` lists the resolution agent with all three capabilities (no code change expected; add a short note in `specs/003-customer-resolution-agent/quickstart.md` "Confirm all three published cards" step if the capability count is referenced).

**Checkpoint**: The card advertises the three capabilities and they appear in discovery — AC1 satisfied.

---

## Phase 4: User Story 2 - Capabilities can be called by future agents (Priority: P1)

**Goal**: A peer agent can submit an A2A `TaskRequest` for each of the three capabilities to the
resolution agent's endpoint topic and receive a `completed` `TaskResult` with the expected output
(FR-001, runtime task lifecycle).

**Independent Test**: Submit a `TaskRequest` for each capability to
`endpoint_topic("customer-resolution-agent")` and assert a `TaskResult(status="completed")` whose
`output` data part matches the T002 contract.

### Tests for User Story 2 ⚠️

- [ ] T009 [P] [US2] Integration test in `tests/integration/test_capability_dispatch.py`: with a `testcontainers` Kafka broker (pattern from `tests/integration/test_demo_agents_a2a.py`), run the resolution `AgentRuntime`, submit a `TaskRequest` for each of the three capabilities via `A2AClient`, and assert each returns `TaskResult(status="completed")` with the contracted output data part.

### Implementation for User Story 2

- [ ] T010 [P] [US2] Implement `async def handle_classify_customer_ticket(req: TaskRequest) -> A2AMessage` in `apps/agents/customer_resolution/capabilities.py`: parse the ticket via `ticket_from_message`, call `ticket_classifier.classify(...)`, return `classification_to_message(result)`.
- [ ] T011 [P] [US2] Implement `async def handle_draft_customer_response(req: TaskRequest) -> A2AMessage` in `capabilities.py`: parse the decision context, call the `response_drafter`/`decision_engine.decide` service, return `draft_to_message(...)`.
- [ ] T012 [P] [US2] Implement `async def handle_close_customer_case(req: TaskRequest) -> A2AMessage` in `capabilities.py`: resolve the case from the shared `CaseStore` (T005) by `correlation_id`, mark it terminal, return `closure_to_message(case)`.
- [ ] T013 [US2] In `apps/agents/customer_resolution/main.py`, register the three handlers via `@runtime.handler(CAP_*)` decorators wired to the `capabilities.py` functions, and keep `run_agent(runtime)` as the entrypoint (depends on T010–T012 and T007).

**Checkpoint**: All three capabilities are invocable end-to-end over the runtime — AC2 satisfied.

---

## Phase 5: User Story 3 - Capability handlers reuse internal services (Priority: P1)

**Goal**: Each handler is a thin adapter that delegates to the existing internal service and only maps
A2A messages in/out — no triage, decision, or closure logic is reimplemented in the capability layer
(FR-016, US3, US5 traceability).

**Independent Test**: With the internal services spied/mocked, invoke each handler and assert it calls
the corresponding service exactly once with the parsed input and returns output derived from the
service's result; no domain rules live in `capabilities.py`.

### Tests for User Story 3 ⚠️

- [ ] T014 [P] [US3] Unit test in `tests/unit/test_capability_handlers.py`: monkeypatch/spy `ticket_classifier.classify`, the response-drafter service, and `CaseStore` closure; call each handler with a contracted `TaskRequest` and assert the service is invoked with the parsed input and the handler output reflects the service return (proving reuse, not reimplementation).
- [ ] T015 [P] [US3] Unit test in `tests/unit/test_capability_handlers.py`: a malformed/empty A2A input data part causes the handler to raise `ValueError` (which the runtime turns into `TaskResult(status="failed")`), with no fabricated classification/decision/closure.

### Implementation for User Story 3

- [ ] T016 [US3] Refactor the three handlers in `capabilities.py` so they contain only input parsing (Phase 2 helpers), a single internal-service call, and output mapping — move/keep all domain rules in `ticket_classifier.py` / `decision_engine.py` / `state_store.py`; add no duplicate logic.
- [ ] T017 [US3] Make `handle_close_customer_case` operate on the shared `CaseStore` (T005) and be idempotent on an already-closed case (return the existing closure record rather than erroring), consistent with the data-model.md §4 terminal-state rule.

**Checkpoint**: Handlers provably delegate to internal services — AC3 satisfied.

---

## Phase 6: User Story 4 - Unknown capabilities are rejected by the A2A runtime (Priority: P2)

**Goal**: A `TaskRequest` for any capability not declared on the card is rejected by the runtime with
`status="rejected"`, `error.category="unsupported_capability"`, and audited — without reaching a
handler (FR-001, runtime guardrail in `runtime.py:_handle_message`).

**Independent Test**: Submit a `TaskRequest` with an undeclared capability to the resolution agent's
endpoint and assert a rejected `TaskResult` plus a `rejected` audit record; confirm registering a
handler for an undeclared capability is impossible.

### Tests for User Story 4 ⚠️

- [ ] T018 [P] [US4] Integration test in `tests/integration/test_capability_dispatch.py`: submit a `TaskRequest` with an undeclared capability (e.g. `"delete_all_cases"`) to the resolution agent's endpoint and assert `TaskResult(status="rejected", error.category="unsupported_capability")` and a `rejected` audit record (queryable by correlation id).
- [ ] T019 [P] [US4] Unit test in `tests/unit/test_capability_handlers.py`: calling `runtime.handler("not_on_card")` on the resolution runtime raises `ValueError` (the card is the single source of truth for the capability surface).

### Implementation for User Story 4

- [ ] T020 [US4] No new runtime code — confirm the rejection is the reused runtime behavior and keep the registered handler set equal to the declared capability set; add a short note in `capabilities.py` documenting that undeclared capabilities are rejected by `AgentRuntime._handle_message` (FR-016) so no catch-all/dynamic handler is ever added.

**Checkpoint**: Undeclared capabilities are rejected and audited — AC4 satisfied.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T021 [P] Update `apps/agents/README.md` and `docs/architecture/adding-new-agent.md` to document the resolution agent's three inbound capabilities and link the T002 I/O contract.
- [ ] T022 [P] Add the inbound-capability scenarios to `specs/003-customer-resolution-agent/quickstart.md` (submit each capability via a dev task client; submit an unknown capability and observe rejection).
- [ ] T023 Run the slice's validation: `uv run pytest tests/unit/test_capability_handlers.py tests/contract/test_capability_card.py` and `uv run pytest -m integration tests/integration/test_capability_dispatch.py`, then `uv run mypy . && uv run ruff check .`; confirm `tests/integration/test_no_router.py` still passes (no supervisor/router introduced, US6).

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (Phase 1)**: no dependencies — start immediately.
- **Foundational (Phase 2)**: depends on Phase 1; **blocks all user stories**. Depends on the internal
  service seams built in `tasks.md` / `tasks-classifier.md` (T003).
- **User stories (Phases 3–6)**: all depend on Phase 2.
- **Polish (Phase 7)**: depends on the desired user stories being complete.

### User story dependencies

- **US1 (AC1, card)**: after Phase 2. The minimal, independently testable increment.
- **US2 (AC2, dispatch)**: after Phase 2; the runtime only dispatches a capability that is declared on
  the card, so US2 builds on US1's card entries (T007) and the handler implementations.
- **US3 (AC3, reuse)**: after Phase 2; refines the US2 handlers to be thin adapters — testable on its
  own via mocked services even before US2's end-to-end dispatch is green.
- **US4 (AC4, rejection)**: after Phase 2; independently testable. It is largely a *verification* story
  — the runtime already rejects undeclared capabilities — and depends on US1 only to fix the declared
  set against which "unknown" is defined.

### Within each user story

- Tests are written first and must FAIL before implementation.
- Mapping helpers (Phase 2) before handlers; handlers before runtime registration; card entries before
  end-to-end dispatch.

### Parallel opportunities

- T002 (contract doc) runs parallel to T001.
- The three handler implementations T010 / T011 / T012 touch distinct functions in `capabilities.py`
  and can be written in parallel, then serialized at T013 (single `main.py` registration).
- All test-authoring tasks marked [P] (T006, T009, T014, T015, T018, T019) are in different files and
  can be written in parallel.
- Polish T021 / T022 are different files — parallel.

---

## Parallel Example: User Story 2

```bash
# Implement the three capability handlers in parallel (distinct functions):
Task: "Implement handle_classify_customer_ticket in apps/agents/customer_resolution/capabilities.py"
Task: "Implement handle_draft_customer_response in apps/agents/customer_resolution/capabilities.py"
Task: "Implement handle_close_customer_case in apps/agents/customer_resolution/capabilities.py"
# Then serialize the single-file wiring:
Task: "Register the three handlers in apps/agents/customer_resolution/main.py"
```

---

## Implementation Strategy

### MVP First (User Story 1)

1. Phase 1: Setup → Phase 2: Foundational.
2. Phase 3: US1 — declare the three capabilities on the card.
3. **STOP and VALIDATE**: the card advertises all three and discovery shows them (AC1).

### Incremental Delivery

1. Setup + Foundational → seams ready.
2. US1 (card) → discoverable capabilities (MVP, AC1).
3. US2 (handlers + dispatch) → peers can call them (AC2).
4. US3 (thin adapters) → handlers proven to reuse internal services (AC3).
5. US4 (rejection test + guard note) → unknown capabilities rejected (AC4).

---

## Notes

- [P] = different files / functions, no incomplete-task dependency.
- The `agent_foundation` runtime library is reused **unchanged**; the unknown-capability rejection
  (AC4) is an existing runtime guarantee (`runtime.py:_handle_message`), so US4 is mostly verification.
- Keep all domain logic in the internal services; `capabilities.py` is an adapter layer only (AC3).
- This slice augments `tasks.md`; it does not replace it. The end-to-end intake/aggregation/decision
  workflow remains the responsibility of `tasks.md`.
