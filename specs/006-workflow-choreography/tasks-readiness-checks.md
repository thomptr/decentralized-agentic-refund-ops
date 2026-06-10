# Tasks: Decentralized Readiness Checks

**Companion task list for feature** `006-workflow-choreography`. This file is a **scoped slice** —
it does **not** replace the main `tasks.md` (full choreography plan). It follows the existing
`tasks-*.md` companion convention in this directory (`tasks-failure-paths.md`, `tasks-replay.md`,
`tasks-timeout-scenarios.md`, `tasks-topic-bootstrap.md`).

**Input**: User request — "Implement decentralized readiness checks. Each agent exposes
`GET /health` and `GET /.well-known/agent.json`."

**Acceptance criteria (from request)**:

- A startup script can verify all agents are ready.
- Readiness does **not** imply central orchestration.
- Each agent reports its **own** status independently.

**Prerequisites**: plan.md, spec.md (FR-021 no-orchestrator; FR-022/FR-023 observability),
research.md, data-model.md, contracts/. Grounded in the current code: agents are Kafka-based with
no HTTP listener on their main entrypoints; billing/risk already have a separate `http_app.py`
serving `/.well-known/agent.json` + `/ping` (no `/health`, not started by the Kafka mains);
customer-resolution has no HTTP app; `fastapi`/`uvicorn` are already declared as the `http` optional
dependency group (**no new dependency** — Constitution Principle V).

**Tests**: INCLUDED. Verification is part of the acceptance criteria ("startup script can verify all
agents are ready") and FR-021 mandates an automated structural no-orchestrator test.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Exact file paths are included in each task

## Constitution guardrails (apply to every task)

- **Principle I (Agent Autonomy)**: Each agent serves and computes its **own** readiness. No central
  health aggregator, supervisor, or orchestrator may direct the agents. The startup verifier is a
  **read-only observer** (HTTP `GET` only); it never commands an agent.
- **Principle V (PoC Scope Discipline)**: Reuse the existing `http` optional deps (`fastapi`,
  `uvicorn`) and the existing `AgentCard`/`identity` modules. No new dependency, no new transport, no
  new event contract or topic.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Make the HTTP readiness surface installable and give every agent a self-owned port.

- [ ] T001 Confirm/declare the `http` optional dependency group (`fastapi>=0.111`, `uvicorn[standard]>=0.30`, `httpx>=0.27`) is installed for the agent runtime in `pyproject.toml`; if the demo entrypoints need it at runtime, ensure it is part of the default install path the demo uses (document the `uv sync --extra http` step in `specs/006-workflow-choreography/quickstart.md`).
- [ ] T002 [P] Add a self-owned readiness host/port config to each agent: `HEALTH_HOST`/`HEALTH_PORT` in `apps/agents/customer_resolution/config.py` (new, default `8101`), reuse `PORT` (default `8080`) in `apps/agents/billing_entitlement` and `A2A_ENDPOINT_PORT` (default `8103`) in `apps/agents/risk_fraud/config.py`; each value is read independently by its own agent (no shared registry that assigns ports centrally).
- [ ] T003 [P] Add a single source-of-truth port manifest `infra/local/agent-ports.env` listing `BILLING_HEALTH_PORT=8080`, `RISK_HEALTH_PORT=8103`, `CUSTOMER_RESOLUTION_HEALTH_PORT=8101` for the startup verifier to consume (declaration only — not an orchestrator).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: A single reusable, self-contained readiness server + per-agent readiness state that any
agent mounts in-process. **No user story can begin until this phase is complete.**

**⚠️ CRITICAL**: T004–T008 are shared by all three agents.

- [ ] T004 Define the readiness response schema `ReadinessReport` (fields: `agent_id`, `status` ∈ `ready|starting|unready`, `checks` map of `{broker_connected, topics_ensured, card_published, consuming}` → bool, `version`, `capabilities`) as a frozen Pydantic model in `src/agent_foundation/runtime/readiness.py`.
- [ ] T005 Implement `ReadinessState` in `src/agent_foundation/runtime/readiness.py` — a per-agent, in-process mutable status object the owning agent updates as it starts (methods like `mark_broker_connected()`, `mark_topics_ensured()`, `mark_card_published()`, `mark_consuming()`, and `report() -> ReadinessReport`). It reflects only the owning agent's own state.
- [ ] T006 Implement `build_readiness_app(card: AgentCard, state: ReadinessState) -> FastAPI` in `src/agent_foundation/runtime/readiness.py` exposing `GET /health` (HTTP 200 + `ReadinessReport` JSON when `status == ready`, else HTTP 503 + the same report) and `GET /.well-known/agent.json` (returns `card.model_dump(mode="json")`).
- [ ] T007 Wire `AgentRuntime` to own a `ReadinessState` and flip its checks as it starts in `src/agent_foundation/runtime/runtime.py`: set `topics_ensured` after topic creation, `card_published` after `_publish_card()`, `consuming` once the endpoint consumer is running; expose it via `runtime.readiness` so an agent main can build the readiness app from its own runtime.
- [ ] T008 [P] Add `serve_readiness(app, host, port, stop_event)` helper in `src/agent_foundation/runtime/readiness.py` that runs a cancellable `uvicorn.Server` programmatically and shuts down when `stop_event` is set, so an agent `main` can `asyncio.gather` it alongside `runtime.serve()`.

**Checkpoint**: Any agent can now mount its own readiness server from its own runtime state.

---

## Phase 3: User Story 1 - Each agent independently reports its own readiness (Priority: P1) 🎯 MVP

**Goal**: Every agent, from its own process, exposes `GET /health` and `GET /.well-known/agent.json`
reporting only its own status — no cross-agent calls, no central reporter.

**Independent Test**: Start a single agent against a broker; `GET /health` returns 200 `ready` (and
503 `starting`/`unready` before it finishes wiring), and `GET /.well-known/agent.json` returns exactly
that agent's own `AgentCard`. Stopping the broker does not require any other agent to report this one's
health.

### Tests for User Story 1

- [ ] T009 [P] [US1] Unit test `build_readiness_app` in `src/agent_foundation/runtime/tests/test_readiness.py`: `/health` → 503 `starting` before any check is marked; → 200 `ready` once all checks pass; `/.well-known/agent.json` → the provided card's JSON.
- [ ] T010 [P] [US1] Test that `AgentRuntime` flips its own `ReadinessState` to `ready` only after card publish + consumer start, in `src/agent_foundation/runtime/tests/test_readiness_runtime.py` (use a fake/embedded broker or monkeypatched transport per the existing runtime test pattern).

### Implementation for User Story 1

- [ ] T011 [US1] Mount the readiness server in customer-resolution: in `apps/agents/customer_resolution/agent.py` `serve()`, build `build_readiness_app(card, runtime.readiness)` and add `serve_readiness(...)` as an additional `asyncio.gather` task alongside the existing 5 loops; build the card via `apps/agents/customer_resolution/a2a_handlers.build_agent_card()`; read host/port from `config.py` (T002).
- [ ] T012 [P] [US1] Mount the readiness server in billing: in `apps/agents/billing_entitlement/main.py` `_run()`, gather `serve_readiness(build_readiness_app(card, runtime.readiness), host, PORT, stop_event)` alongside `runtime.serve(stop_event)`; reuse `build_agent_card()` from `apps/agents/billing_entitlement/identity.py`.
- [ ] T013 [P] [US1] Mount the readiness server in risk-fraud: in `apps/agents/risk_fraud/main.py`, gather `serve_readiness(...)` alongside `runtime.serve(stop_event)` using `A2A_ENDPOINT_PORT` from `apps/agents/risk_fraud/config.py` and `build_agent_card()` from `apps/agents/risk_fraud/identity.py`.
- [ ] T014 [P] [US1] Add `GET /health` to the existing standalone HTTP apps for parity (so the AgentCore HTTP variant also reports readiness): `apps/agents/billing_entitlement/http_app.py` and `apps/agents/risk_fraud/http_app.py` (reuse `ReadinessReport`; these apps report their own static "ready" since they own no Kafka lifecycle — document the distinction in the route docstring).
- [ ] T015 [US1] Verify no `/health` handler in any agent calls another agent or reads another agent's state — grep-level self-review across `apps/agents/*/` confirming each readiness response is built solely from the owning agent's `ReadinessState`/card (enforces Principle I; pairs with T021).

**Checkpoint**: Each agent independently serves its own `/health` + `/.well-known/agent.json`. MVP complete.

---

## Phase 4: User Story 2 - A startup script verifies all agents are ready (Priority: P2)

**Goal**: One command brings the system up and blocks until every agent reports ready (or fails fast),
by polling each agent's own `/health` — without any agent depending on the script to function.

**Independent Test**: Run the startup verifier against agents that become ready after a delay → it
exits 0 once all are `ready`; against an agent that never becomes ready → it exits non-zero after the
timeout with a clear per-agent status line.

### Tests for User Story 2

- [ ] T016 [P] [US2] Test the verifier polling logic against local mock HTTP servers (one returns 503 then 200 after a delay, one stays 503) asserting success-on-all-ready and non-zero-exit-on-timeout, in `tests/integration/test_readiness_startup.py`.

### Implementation for User Story 2

- [ ] T017 [US2] Create `infra/local/wait-for-agents.sh`: read ports from `infra/local/agent-ports.env` (T003), poll each agent's `GET /health` on an interval until HTTP 200 `ready` or a configurable timeout; print a per-agent ready/not-ready status line; exit 0 only when all are ready, non-zero otherwise (read-only `GET` only — never POSTs/commands).
- [ ] T018 [US2] In `wait-for-agents.sh`, additionally `GET /.well-known/agent.json` for each agent and assert the returned `agent_id` matches the expected id for that port, so discovery and identity are verified alongside liveness.
- [ ] T019 [US2] Wire `wait-for-agents.sh` into `infra/local/run-demo-agents.sh`: after launching the three background agents, replace the fixed `sleep 5`/`sleep 2` waits with a call to `wait-for-agents.sh`; abort the demo with a clear message if it returns non-zero.
- [ ] T020 [US2] Print the health URLs (`http://localhost:<port>/health`) for all three agents in the `run-demo-agents.sh` startup banner so an operator can re-check readiness manually.

**Checkpoint**: `run-demo-agents.sh` now proves all agents are ready before declaring the demo up.

---

## Phase 5: User Story 3 - Readiness without central orchestration (Priority: P3)

**Goal**: Prove that readiness is decentralized — each agent self-reports, the verifier only observes,
and no component centrally dispatches or directs the agents (FR-021 / Principle I).

**Independent Test**: An automated structural test asserts no module aggregates or commands all three
agents' health; a sample run shows each agent's readiness transition recorded in its own audit trail.

### Tests for User Story 3

- [ ] T021 [P] [US3] Structural test in `tests/integration/test_no_router.py` (extend the existing guard): assert no agent's readiness handler imports or calls another agent, and that the readiness server is constructed only from the owning agent's own `ReadinessState`/`AgentCard` (no central health-aggregator module exists).
- [ ] T022 [P] [US3] Test in `tests/integration/test_readiness_startup.py` that the verifier issues only HTTP `GET` requests (read-only observation) and that agents reach `ready` independently even if the verifier is never run.

### Implementation for User Story 3

- [ ] T023 [US3] Emit a structured audit entry when an agent's readiness transitions to `ready` (each agent records its own transition via the existing `audit/store.py` path, actor = own `agent_id`, action = `readiness.ready`), reusing the existing audit emission used elsewhere in `runtime.py` — no new topic/contract.
- [ ] T024 [US3] Document the decentralization rationale (self-reported readiness, observer-only verifier, no orchestrator) in `specs/006-workflow-choreography/contracts/readiness.md` (new contract doc), cross-referencing FR-021/FR-022/FR-023.

**Checkpoint**: Decentralization of readiness is structurally proven and audited.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T025 [P] Create `specs/006-workflow-choreography/contracts/readiness.md` documenting the endpoints (`GET /health`, `GET /.well-known/agent.json`), the `ReadinessReport` schema, status semantics (200 ready / 503 not-ready), and the per-agent port assignments.
- [ ] T026 [P] Update `specs/006-workflow-choreography/quickstart.md` with a "Verify readiness" section showing `wait-for-agents.sh` and the manual `curl http://localhost:<port>/health` checks.
- [ ] T027 [P] Add a `readiness` subcommand to `src/agent_foundation/cli.py` (e.g. `uv run agent-foundation readiness`) that runs the same poll the script does, for parity with the existing `health` broker-check command.
- [ ] T028 Run the full quickstart validation: `run-demo-agents.sh` → `wait-for-agents.sh` passes → `curl` each `/health` returns `ready` → each `/.well-known/agent.json` returns the correct card.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Foundational (Phase 2)**: Depends on Setup; **blocks all user stories** (shared `readiness.py` + runtime wiring).
- **US1 (Phase 3, P1)**: Depends on Foundational. The MVP — each agent self-reports.
- **US2 (Phase 4, P2)**: Depends on US1 (needs live `/health` endpoints to poll).
- **US3 (Phase 5, P3)**: Depends on US1 (structural guard over the mounted servers); independent of US2.
- **Polish (Phase 6)**: Depends on the user stories it documents/validates.

### Within Each User Story

- Tests are written first and expected to fail before implementation.
- Foundation (`readiness.py`, runtime state) before per-agent mounting.
- Per-agent mounting before the startup verifier.

### Parallel Opportunities

- T002, T003 (Setup) run in parallel.
- T008 parallel with T004–T007 review once the schema (T004) lands.
- T009, T010 (US1 tests) run in parallel.
- T012, T013, T014 (billing + risk mounts, different files) run in parallel; T011 (customer-resolution) also parallel.
- T021, T022 (US3 tests) run in parallel.
- T025, T026, T027 (Polish docs/CLI) run in parallel.

---

## Parallel Example: User Story 1

```bash
# Tests first (different files):
Task: "Unit test build_readiness_app in src/agent_foundation/runtime/tests/test_readiness.py"
Task: "Test AgentRuntime readiness flip in src/agent_foundation/runtime/tests/test_readiness_runtime.py"

# Then mount per agent (different files, no cross-dependency):
Task: "Mount readiness server in apps/agents/billing_entitlement/main.py"
Task: "Mount readiness server in apps/agents/risk_fraud/main.py"
Task: "Mount readiness server in apps/agents/customer_resolution/agent.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Complete Phase 1 (Setup) and Phase 2 (Foundational `readiness.py` + runtime wiring).
2. Complete Phase 3 (US1): each agent serves its own `/health` + `/.well-known/agent.json`.
3. **STOP and VALIDATE**: start one agent, `curl /health` (503 → 200) and `curl /.well-known/agent.json`.
4. This alone satisfies "each agent reports its own status independently."

### Incremental Delivery

1. Setup + Foundational → readiness surface available.
2. US1 → self-reporting endpoints (MVP).
3. US2 → `wait-for-agents.sh` verifies all agents (satisfies "startup script can verify all agents are ready").
4. US3 → structural proof + audit (satisfies "readiness does not imply central orchestration").
5. Polish → contract doc, quickstart, CLI parity.

---

## Notes

- [P] tasks = different files, no dependencies.
- Each `/health` is built **only** from the owning agent's own `ReadinessState`/card — no agent reports
  another's health (Principle I).
- The startup verifier is **observe-only** (`GET`) — it proves readiness, it does not orchestrate.
- No new dependency, transport, event contract, or topic is introduced (Principle V): `fastapi`/`uvicorn`
  are the pre-existing `http` optional group, and `AgentCard`/`identity` are reused as-is.
- Commit after each task or logical group; stop at any checkpoint to validate the story independently.
