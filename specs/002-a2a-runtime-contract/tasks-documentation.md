---
description: "Standalone task list for the A2A Runtime architecture documentation deliverable (FR-016)"
---

# Tasks: Architecture Documentation — Shared A2A Runtime Contract

**Input**: Design documents from `/specs/002-a2a-runtime-contract/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md (all present)

**Why this is a separate file**: The feature's main `tasks.md` is being extended concurrently by
other `/speckit-tasks` runs (Phases 1–13, IDs up to T115+). To avoid task-ID collisions and edit
races, this documentation deliverable is tracked here as a self-contained list with its own `D###`
IDs. It can be folded back into `tasks.md` as a phase later if desired (the previously-drafted
"Phase 14 / T116–T122" maps 1:1 to D001–D007 below).

**Scope**: Documentation **only** — no production code. Produces the four architecture documents the
user requested under `docs/architecture/`, satisfying spec **FR-016** ("all documentation required
for an agent author … MUST be present in the repository") and supporting **SC-001** (an author can
stand up an agent in <15 min following only the docs).

**Tests**: None. A docs-verification task (link/consistency check against the contracts) stands in
for tests in the Polish phase.

**Organization**: Tasks are grouped by the spec user story each document primarily serves, so each
document is an independently completable, independently reviewable increment.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which spec user story this document serves (US1, US3, US5)
- All paths are relative to the repository root.

## Authoritative sources (every doc task MUST cite these; copy contract details faithfully — do not invent topic names, field names, validation rules, or API/CLI signatures)

- `specs/002-a2a-runtime-contract/spec.md` — FR-001…FR-016, SC-001…SC-008, Edge Cases, Assumptions.
- `specs/002-a2a-runtime-contract/plan.md` — Summary, Project Structure, Complexity Tracking, Constitution Check.
- `specs/002-a2a-runtime-contract/data-model.md` — §1 entities, §4 state machine, §5 topics.
- `specs/002-a2a-runtime-contract/contracts/runtime-api.md` — `AgentRuntime`, `A2AClient`, discovery, CLI.
- `specs/002-a2a-runtime-contract/contracts/topics.md` and `contracts/*.schema.json`.
- `specs/002-a2a-runtime-contract/quickstart.md` — Scenarios 1–6.
- `.specify/memory/constitution.md` — Principles I–V.

**Deliverables**: `docs/architecture/a2a-runtime-contract.md`, `docs/architecture/agent-discovery.md`,
`docs/architecture/no-supervisor-pattern.md`, `docs/architecture/adding-a2a-capability.md`
(+ `docs/architecture/README.md` index).

---

## Phase 1: Setup (Documentation Home)

**Purpose**: Create the documentation directory and its index entry point.

- [ ] D001 Create the `docs/architecture/` directory at the repository root and add `docs/architecture/README.md` as the index page: a top-level heading "A2A Runtime — Architecture Documentation", a one-line statement that these docs describe the `002-a2a-runtime-contract` feature built on `001-event-foundation`, and a "Contents" list with relative links to the four docs (filled out in D007). Add a "Documentation" pointer from the repository root `README.md` (create if absent) to `docs/architecture/README.md`.

---

## Phase 2: Foundational (Shared Glossary — Blocking)

**Purpose**: Establish the shared terminology, source map, and reading order every document links
back to, so the four docs stay mutually consistent and non-duplicative.

**⚠️ CRITICAL**: Complete before writing any individual document (D003–D006).

- [ ] D002 Populate `docs/architecture/README.md` with: (a) a **Glossary** table defining the canonical terms from spec "Key Entities" / `data-model.md` — Agent Endpoint, Agent Card, Capability/AgentSkill, Task Request, Task Result, Task Lifecycle Outcome {accepted, completed, failed, rejected}, Task Audit Event; (b) an **Artifact source map** mapping each doc to its upstream spec/contract sources (per "Authoritative sources" above); (c) a **Reading order**: `no-supervisor-pattern.md` → `a2a-runtime-contract.md` → `agent-discovery.md` → `adding-a2a-capability.md`. Use relative links to the four doc files.

**Checkpoint**: Glossary and source map exist; the four documents can now be written in parallel.

---

## Phase 3: User Story 1 — Runtime Contract Reference (Priority: P1) 🎯 MVP

**Goal**: `docs/architecture/a2a-runtime-contract.md` — the authoritative human-readable reference for
the runtime contract: addressable endpoints, the payload contracts, the task lifecycle state machine,
and reuse of the foundation's transport/audit/idempotency.

**Independent Test**: A reader unfamiliar with the code can, from this doc alone, explain how a task
flows from request to result, name the four lifecycle outcomes and the exactly-one-terminal rule, and
identify which Kafka topics carry requests, results, cards, and audit — all matching `data-model.md`
and `contracts/`.

- [ ] D003 [P] [US1] Create `docs/architecture/a2a-runtime-contract.md` with sections: **Overview** (paraphrase `plan.md` Summary — a thin agent runtime over the `001-event-foundation` transport; ships the runtime + an `echo` example agent, no refund-domain logic per FR-015); **Constitution alignment** (Principles I–V; every interaction is a Kafka event, not a direct call); **Contracts** (field tables for `AgentCard`/`AgentSkill`/`Capability`, `TaskRequest`, `TaskResult`, `TaskError`, and the extended `AuditPayload`, copied faithfully from `data-model.md` §1 incl. the `TaskResult` conditional rules and the rejection-vs-failure error categories per FR-007); **Task lifecycle** (a Mermaid `stateDiagram-v2`/`flowchart` of the `data-model.md` §4 machine — received → REJECTED, or → ACCEPTED → COMPLETED|FAILED — plus the four FR-009 invariants: exactly one of {rejected} or {accepted + one terminal}; validation before accept per FR-005; duplicate `task_id` → `duplicate_skipped` per FR-010; `accepted` is non-terminal; map each transition to its audit outcome and `TaskResult.status`); **Transport & topics** (table from `contracts/topics.md` / `data-model.md` §5 with purpose/retention/key; note reuse of the foundation `Publisher`/`Consumer`/`IdempotencyTracker`/audit store with no parallel transport per FR-014; a Mermaid `sequenceDiagram` of a request→result round-trip with audit at accept and terminal). Link the README glossary.

**Checkpoint**: The runtime contract reference is complete and self-consistent with `data-model.md`
and `contracts/`. This is the MVP — every other doc links to it.

---

## Phase 4: User Story 3 — Agent Discovery (Priority: P2)

**Goal**: `docs/architecture/agent-discovery.md` — how agents publish capabilities and how peers
discover a capable target with no central registry.

**Independent Test**: A reader can describe how `echo.alpha` becomes discoverable, why
latest-published-wins, and how a requester selects a target for capability `echo` purely by reading
the compacted card topic — with no registry service in the path.

- [ ] D004 [P] [US3] Create `docs/architecture/agent-discovery.md` covering: the **publish/read** model (not query/respond) per spec Assumptions and FR-003/FR-013 (an agent publishes its `AgentCard` on startup and via `republish_card()`); the discovery topic `local.agent.agent-card.published.v1` is **compacted**, keyed by `agent_id`, so the latest card supersedes earlier ones (FR-013); the discovery API `discover_agents()` / `find_capable(capability_id)` from `contracts/runtime-api.md` §3, stating explicitly that the caller selects the target and the runtime does **not** arbitrate or load-balance between competing providers (spec "Competing providers" edge case); the malformed-card edge case (refused, prior valid card stays in effect); and a Mermaid sequence/flow diagram (agent publishes card → compacted topic → peer reads → peer addresses endpoint directly). Tie back to `quickstart.md` Scenario 2 (`discover` / `discover --capability echo`). Optionally reference the static-roster overlay (`config/peers.yaml`, `PeerRegistry`) as a complementary local-discovery mechanism.

**Checkpoint**: Discovery doc explains decentralized capability lookup end-to-end.

---

## Phase 5: User Story 5 — No-Supervisor Pattern (Priority: P3)

**Goal**: `docs/architecture/no-supervisor-pattern.md` — the guardrail document asserting and
explaining the decentralized, no-orchestrator design.

**Independent Test**: A reviewer can confirm from this doc that no component receives, queues, or
dispatches tasks on behalf of other agents, and can trace a delegation as requester → performer
endpoint with no intermediary (SC-008).

- [ ] D005 [P] [US5] Create `docs/architecture/no-supervisor-pattern.md`. It MUST include, prominently near the top, this exact statement **verbatim**:

  > There is no central router, planner, supervisor, or orchestrator. Each agent independently
  > reacts to events, discovers peer capabilities, and sends A2A task requests directly to the
  > relevant peer agent.

  Then cover: **Why** (Constitution Principle I "Agent Autonomy" + FR-011 — no supervisor/router/dispatcher/orchestrator mediates delegation; delegation is peer-to-peer); **How it is structurally enforced** (every interaction — request, result, card, audit — is a Kafka event addressed to a specific agent's endpoint topic via `A2AClient.submit`/`send_task`, per `contracts/runtime-api.md` §2 and `plan.md` Constitution Check); **What this is NOT** (no hub-and-spoke, no central capability service, no dispatcher-owned task queue, no load-balancer arbitrating competing providers); a Mermaid diagram contrasting the **rejected** hub-and-spoke design with the **adopted** direct peer-to-peer flow; and a **How to verify** section mapping to SC-008 and `quickstart.md` Scenario 6 (only agents, `A2AClient` callers, and Kafka run; trace any task → requester → performer with no intermediary). Note the liveness/timeout out-of-scope gap (spec Assumptions).

**Checkpoint**: The no-supervisor guarantee is documented and independently verifiable.

---

## Phase 6: User Story 1 — Adding an A2A Capability (Author How-To) (Priority: P1)

**Goal**: `docs/architecture/adding-a2a-capability.md` — a step-by-step guide for an agent author to
wrap an agent, declare a capability, accept a task, return a result, and inspect the audit trail,
writing zero transport/validation/audit code (SC-001, FR-016).

**Independent Test**: A new author can follow this doc end-to-end to stand up a capability-serving
agent and see an "accepted" audit event in under 15 minutes, with every step grounded in the runtime
API and CLI contracts.

> Depends on D003 (the runtime-contract reference it links to).

- [ ] D006 [US1] Create `docs/architecture/adding-a2a-capability.md` as a numbered walkthrough: (1) **Define the AgentCard + AgentSkill** (fields/validation from `data-model.md` §1, or `build_agent_card(identity, skills, …)` if that helper exists); (2) **Construct `AgentRuntime`** and register an async handler with `@runtime.handler(capability_id)` returning an `A2AMessage` on success / raising to fail — exact signatures from `contracts/runtime-api.md` §1, noting `TaskHandler = Callable[[TaskRequest], Coroutine[..., A2AMessage]]`; (3) **`serve()`** behavior (ensures topics, publishes the card, drives validate→accept|reject→handler→complete|fail, emits audit, publishes exactly one `TaskResult`); (4) **Delegate to a peer** via `A2AClient.submit`/`send_task(target, capability, input, …)`; (5) **Inspect the audit trail** via `query-task-audit --task-id`. Include a minimal runnable snippet modeled on `examples/echo_agent.py` and the `serve-echo`/`submit-task`/`discover`/`query-task-audit` CLI from `contracts/runtime-api.md` §5. Add a **Behavior you get for free** callout (validation before handler per FR-005; rejection vs failure per FR-007; exactly-one-terminal audit per FR-009; idempotency by `task_id` per FR-010) and a **Known gaps** note reproducing the liveness/timeout out-of-scope assumption. Reference `quickstart.md` and state the SC-001 "<15 min, zero transport/validation/audit code" goal. Cross-link the other three docs.

**Checkpoint**: An author has a complete, self-contained how-to grounded in the runtime API and CLI.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Make the four docs cohere as a set and verify they match the source contracts.

- [ ] D007 Finalize and verify the doc set: complete the `docs/architecture/README.md` "Contents" list with one-line descriptions and relative links to all four docs; add reciprocal cross-links across the four docs (each intro links the README glossary and the other docs where referenced) and ensure terminology matches the glossary exactly; run a **consistency check** confirming every contract detail cited (topic names, payload field names/types/validation, lifecycle outcomes, API/CLI signatures) matches `data-model.md`, `contracts/topics.md`, `contracts/runtime-api.md`, and the `contracts/*.schema.json` files; confirm the verbatim no-supervisor statement is present in `no-supervisor-pattern.md` (D005); and confirm all relative Markdown links resolve. Fix any drift.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1, D001)**: No dependencies — start immediately.
- **Foundational (Phase 2, D002)**: Depends on D001 — **BLOCKS all document tasks** (provides the
  shared glossary, source map, and reading order every doc links to).
- **Document phases (Phases 3–6)**: All depend on D002. Phase 6 (D006, how-to) additionally depends
  on Phase 3 (D003, runtime-contract reference). D003, D004, and D005 are mutually independent.
- **Polish (Phase 7, D007)**: Depends on all four documents existing.

### Document → Story mapping

| Document | Task | Primary story | Spec drivers |
|----------|------|---------------|--------------|
| `a2a-runtime-contract.md` | D003 | US1 (P1) | FR-001/002/004/005/006/007/008/009/010/014; data-model §1/§4 |
| `agent-discovery.md` | D004 | US3 (P2) | FR-003/013; runtime-api §3; topics.md |
| `no-supervisor-pattern.md` | D005 | US5 (P3) | FR-011; SC-008; Principle I |
| `adding-a2a-capability.md` | D006 | US1 (P1) | FR-016; SC-001; runtime-api §1/§5 |

### Parallel Opportunities

- Once D002 completes, **D003, D004, and D005 can be written in parallel** by different authors —
  separate files, no cross-dependency.
- D006 starts once D003 is complete.
- D007 runs last (touches all docs).

---

## Parallel Example: After Foundational (D002) completes

```bash
# Three independent documents, one author each:
Task: "D003 [US1] Write docs/architecture/a2a-runtime-contract.md"
Task: "D004 [US3] Write docs/architecture/agent-discovery.md"
Task: "D005 [US5] Write docs/architecture/no-supervisor-pattern.md"
# Then, once the runtime-contract reference exists:
Task: "D006 [US1] Write docs/architecture/adding-a2a-capability.md"
```

---

## Implementation Strategy

### MVP First (Runtime Contract Reference)

1. D001 Setup (dir + index skeleton).
2. D002 Foundational (glossary, source map, reading order) — CRITICAL, blocks all docs.
3. D003 `a2a-runtime-contract.md` — the reference every other doc depends on.
4. **STOP and VALIDATE**: a reader can explain the full request→result lifecycle and the topic map
   from this doc alone, matching `data-model.md`/`contracts/`.

### Incremental Delivery

1. D001 + D002 → docs home ready.
2. D003 → review → publish (MVP).
3. D004 → review → publish.
4. D005 (with the verbatim statement) → review → publish.
5. D006 → review → publish.
6. D007 → cross-link + consistency check.

---

## Notes

- [P] = different files, no dependency on an incomplete task.
- [Story] maps each document to the spec user story it serves.
- Every doc task is grounded in a named source artifact — do not invent contract details; copy field
  names, types, validation rules, topic names, and API/CLI signatures faithfully and flag any source
  ambiguity rather than guessing.
- `no-supervisor-pattern.md` MUST contain the user-supplied statement verbatim (D005).
- Use Mermaid for all diagrams (renders in-repo and in Nimbalyst); avoid ASCII art.
- Commit after each document for clean, reviewable increments.
