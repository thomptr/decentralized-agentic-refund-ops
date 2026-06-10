---
description: "Focused task list — No-Supervisor Architecture Verification for Decentralized Workflow & Event Choreography (006)"
---

# Tasks: No-Supervisor Architecture Verification (006 · User Story 5 — decentralization proof)

**Input**: Design documents from `/specs/006-workflow-choreography/`

**Scope**: This is a **focused subset** of the full feature tasks (`tasks.md`), covering only the
**no-supervisor / no-orchestrator architecture verification** requested. It hardens the constitutional
decentralization guarantee (Constitution Principle I; FR-021, FR-025; SC-009, SC-010) into a single,
broker-free, CI-runnable architecture test plus the documentation that explains *why* this system is
**choreography, not orchestration**. It corresponds to `tasks.md` Phase 8 (T031/T032) and extends the
three existing guards rather than replacing them. IDs here are prefixed `NS` to avoid collision with the
shared `tasks.md` (`T###`) and the other focused lists (`FP`, `TT`, `TR`).

**Prerequisites**: plan.md ✅, spec.md ✅ (FR-021/FR-025, SC-009/SC-010), research.md ✅,
`.specify/memory/constitution.md` ✅ (Principle I — "no supervisor agent, no central router, no hidden
orchestrator"). No live broker, no running agents, and no other 006 task are required: every check is a
static filesystem/AST scan that runs in a plain `pytest` invocation.

**Tests**: INCLUDED — FR-021a and SC-009a explicitly require an **automated architecture/structural
test**. Test tasks are written **before** any consolidation and must be runnable (and, where a real
violation is seeded, must FAIL) before the documentation task closes the loop.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files / independent test functions, no dependencies on incomplete tasks)
- **[Story]**: US5 (maps to spec User Story 5 — decentralization & traceability proof; FR-021/FR-025)
- All paths are repository-root-relative

---

## The single source of truth (what "no supervisor" means here)

`apps/agents/` contains **exactly three** autonomous peer agents, each owning one domain; coordination is
emergent over Kafka + A2A, never directed by a central component:

| Allowed agent package (`apps/agents/`) | Domain it owns | Talks to whom |
|---|---|---|
| `customer_resolution` | triage, opinion **aggregation**, terminal decision | requests opinions from **its own** cases' billing + risk peers |
| `billing_entitlement` | billing eligibility opinion | answers requests; calls **no** peer |
| `risk_fraud` | fraud-risk opinion | answers requests; calls **no** peer |

Forbidden role vocabulary anywhere under non-test source (`apps/`, `src/`): `supervisor`, `router`,
`orchestrator`, `dispatcher`, `coordinator`, `workflow_engine`, `controller`, `broker_router`,
`middleware_router`. Forbidden process-owning dependencies in `pyproject.toml`: any workflow/orchestration
engine (`temporal`, `airflow`, `prefect`, `dagster`, `celery`, `dramatiq`, `luigi`, `camunda`, `zeebe`,
`conductor`, AWS Step Functions wrappers).

**Reuse note**: three guards already exist and stay authoritative — extend, do not duplicate, them:
`apps/agents/customer_resolution/tests/test_no_supervisor.py` (also billing & risk),
`tests/integration/test_no_router.py`, and `apps/agents/*/tests/test_domain_isolation.py`.

---

## Acceptance criteria → task map

| Requested check | Spec / constitution refs | Realizing test |
|---|---|---|
| No supervisor agent package exists | Const. I; FR-021a; SC-009a | **NS02** |
| No central router service exists | Const. I/II; FR-021a; SC-009a | **NS03** |
| No workflow engine owns the business process | Const. I/V; FR-021a | **NS04** |
| Customer Resolution Agent only coordinates its **own** cases | Const. I; FR-021; FR-025 | **NS05** |
| Billing Agent never calls Risk Agent | Const. I/II; FR-025 | **NS06** |
| Risk Agent never calls Billing Agent | Const. I/II; FR-025 | **NS07** |
| **Architecture constraint is testable** (acceptance) | FR-021a; SC-009a/SC-010 | **NS01 + NS08** (one CI-runnable module) |
| **Documentation explains choreography, not orchestration** (acceptance) | Const. I; FR-021 | **NS09 + NS10** |

---

## Phase 1: Foundational (the shared, broker-free verification harness — blocks the checks)

**Purpose**: One place that defines the canonical agent set and the static-scan primitives, so the six
checks below stay consistent with the existing guards and don't drift. No new dependency, no new topic,
no broker.

- [ ] NS01 [US5] Create the architecture-test package `tests/architecture/` (`__init__.py` + `helpers.py`) providing broker-free static-scan primitives reused by every check: `agent_packages()` → the package dirs under `apps/agents/` that are real agents (excludes `__pycache__`, `common.py`, `discover.py`, `README.md`); `EXPECTED_AGENTS = {"customer_resolution", "billing_entitlement", "risk_fraud"}`; `source_files(root, exclude_tests=True, exclude_vendored=True)` (skips `tests/`, `.venv`, `site-packages`, `node_modules`); and AST walkers `defined_symbols(path)` / `imported_modules(path)` / `capability_ids(path)`. Mirror the proven logic in `tests/integration/test_no_router.py` and `apps/agents/customer_resolution/tests/test_no_supervisor.py` so the rules are identical. File: `tests/architecture/helpers.py`

**Checkpoint**: A helper module can enumerate the three agents and scan any source tree without a broker.

---

## Phase 2: The six architecture checks (write first; each must be CI-runnable and fail on a seeded violation)

All six live in **one** module — `tests/architecture/test_no_supervisor_architecture.py` — as independent
functions, so the whole constraint is a single `pytest` target. `[P]` = independent test functions
sharing one file.

- [ ] NS02 [P] [US5] **No supervisor agent package exists.** Assert `agent_packages()` equals `EXPECTED_AGENTS` exactly — no extra package — and that **no** agent package directory name and **no** non-test symbol/capability id under `apps/agents/` contains a forbidden role word (`supervisor`, `orchestrator`, `coordinator`, `controller`, `dispatcher`, `router`). Seed a throwaway `apps/agents/supervisor/` dir in the test (or assert via a parametrized fixture) to confirm the check FAILS, then remove it. File: `tests/architecture/test_no_supervisor_architecture.py` (FR-021a, SC-009a)
- [ ] NS03 [P] [US5] **No central router service exists.** Scan all non-test source under `apps/` and `src/` (esp. `apps/api/`, `src/agent_foundation/`) and assert no module **imports**, **defines**, or **registers a capability id** matching `router`/`dispatcher`/`orchestrator`/`broker_router`/`middleware_router`, and that no single module subscribes to **all three** agents' result topics in order to re-dispatch them (heuristic: no non-agent module references ≥2 peer endpoint topics *and* publishes `task.requested`). File: `tests/architecture/test_no_supervisor_architecture.py` (FR-021a, Const. II)
- [ ] NS04 [P] [US5] **No workflow engine owns the business process.** Assert `pyproject.toml` declares **no** workflow/orchestration-engine dependency (`temporal`, `airflow`, `prefect`, `dagster`, `celery`, `dramatiq`, `luigi`, `camunda`, `zeebe`, `conductor`, Step-Functions wrappers) and that no non-test module defines a `workflow_engine`/`state_machine`/`process_manager` that drives the three agents; positively assert the only business-process decision function, `apps/agents/customer_resolution/decision_engine.decide()`, is imported **solely** within `apps/agents/customer_resolution/` (it is the resolution agent's own logic, not a shared engine). File: `tests/architecture/test_no_supervisor_architecture.py` (FR-021a, Const. I/V)
- [ ] NS05 [P] [US5] **Customer Resolution Agent only coordinates its own cases.** Assert the resolution agent (a) keys all working state by **its own** `correlation_id` via `InMemoryCaseStateStore` (no store/handler keyed by a peer's task or another case's id), (b) issues `task.requested` **only** to its two declared peers (`BILLING_PEER_AGENT_ID == "billing-entitlement-agent"`, `RISK_PEER_AGENT_ID == "risk-fraud-agent"` from `config.py`) and never dispatches a task **on behalf of** a peer (re-assert `build_agent_card()` exposes no router/dispatch capability — extend, don't duplicate, `test_no_supervisor.py`), and (c) addresses peers via `endpoint_topic()`/`A2AClient`, never a shared intermediary/routing topic. File: `tests/architecture/test_no_supervisor_architecture.py` (FR-021, FR-025)
- [ ] NS06 [P] [US5] **Billing Agent never calls Risk Agent.** Scan all non-test source under `apps/agents/billing_entitlement/` and assert it contains **no** reference to the risk peer — no import of `apps.agents.risk_fraud`, no literal `"risk-fraud-agent"`, no `RISK_*` peer-id/endpoint constant, and no `A2AClient.submit(...)`/`publish(...)` targeting a risk endpoint topic. Billing only **answers** opinion requests; it originates no peer call. File: `tests/architecture/test_no_supervisor_architecture.py` (FR-025, Const. I/II)
- [ ] NS07 [P] [US5] **Risk Agent never calls Billing Agent.** Symmetric to NS06: scan `apps/agents/risk_fraud/` and assert **no** reference to the billing peer — no import of `apps.agents.billing_entitlement`, no literal `"billing-entitlement-agent"`, no `BILLING_*` peer-id/endpoint constant, and no `A2AClient.submit(...)`/`publish(...)` targeting a billing endpoint topic. Risk only **answers** opinion requests. File: `tests/architecture/test_no_supervisor_architecture.py` (FR-025, Const. I/II)

**Checkpoint**: All six requested checks are encoded as independent functions in one broker-free module;
each has been demonstrated to fail when a violation is seeded.

---

## Phase 3: Make-it-testable gate (the constraint runs green in CI)

- [ ] NS08 [US5] Make the architecture constraint a **single testable target**: confirm `pytest tests/architecture/test_no_supervisor_architecture.py -q` runs with **no broker / no running agents** and passes on the current (conforming) tree; register the path so it is collected by the default `pytest` run and any CI step (no `-m integration` marker — it must run in the fast unit lane). Fix any *genuine* leakage the checks surface (do not weaken a check to make it pass). File: `tests/architecture/test_no_supervisor_architecture.py` (+ `pyproject.toml`/`pytest.ini` if collection config is needed) — satisfies acceptance "Architecture constraint is testable" (FR-021a, SC-009a/SC-010)

**Checkpoint**: One command proves the no-supervisor architecture; it is wired into CI and green.

---

## Phase 4: Documentation — *why this is choreography, not orchestration*

- [ ] NS09 [US5] Write `docs/architecture/choreography-not-orchestration.md` explaining the design: contrast **orchestration** (a central conductor that calls/sequences workers) with this system's **choreography** (each agent reacts to events and decides for itself); walk the live flow (`support.ticket.created` → resolution triage → independent A2A billing + risk requests → peers publish their **own** result events → resolution correlates by `correlation_id`/`task_id` and emits exactly one decision) showing **no component directs the others**; map each of the six checks (NS02–NS07) to the constitutional principle it enforces (Principle I/II; FR-021/FR-025) and link `tests/architecture/test_no_supervisor_architecture.py` as the **executable proof**; note that decisioning emerges purely from peer events (the SC-009b audit-trail proof lives in `tasks.md` T032 / `test_workflow_choreography.py`). Include a Mermaid sequence diagram of the choreographed flow with no orchestrator lane. File: `docs/architecture/choreography-not-orchestration.md` — satisfies acceptance "Documentation explains why this is choreography, not orchestration"
- [ ] NS10 [P] [US5] Cross-link the doc so it is discoverable: add a "Decentralization / no-supervisor" pointer to `apps/agents/README.md` and a reference line in `specs/006-workflow-choreography/plan.md` (under the existing "Constitution Check → I. Agent Autonomy" note) pointing to both `docs/architecture/choreography-not-orchestration.md` and the architecture test. Files: `apps/agents/README.md`, `specs/006-workflow-choreography/plan.md`

**Checkpoint**: The architecture rule is documented, the doc names the test that enforces it, and the test names the doc.

---

## Phase 5: Regression gate (all decentralization guards together)

- [ ] NS11 [US5] Run the full decentralization guard set in one pass and confirm green with no regressions: `pytest tests/architecture/test_no_supervisor_architecture.py apps/agents/customer_resolution/tests/test_no_supervisor.py apps/agents/billing_entitlement/tests/test_no_supervisor.py apps/agents/risk_fraud/tests/test_no_supervisor.py apps/agents/*/tests/test_domain_isolation.py tests/integration/test_no_router.py -q`; confirm the new module adds **no new dependency, no new topic, no new event contract** (Constitution Principle V) and that the existing guards are unchanged except for any agreed extension referenced by NS05. File: (verification only — no source change)

**Checkpoint**: Supervisor-absence and domain-isolation are provable in a single command across all guards.

---

## Dependencies & Execution Order

- **Foundational (Phase 1)**: NS01 (helpers) blocks NS02–NS07.
- **Checks (Phase 2, NS02–NS07)**: all depend on NS01; mutually independent → fully parallel (separate functions in one file).
- **Gate (Phase 3)**: NS08 depends on NS02–NS07 (it runs and greens the whole module).
- **Docs (Phase 4)**: NS09 depends on NS08 (it links the passing test); NS10 depends on NS09.
- **Regression (Phase 5)**: NS11 last — requires NS08 plus the untouched existing guards.

```
NS01 ─►┬─ NS02 ─┐
       ├─ NS03 ─┤
       ├─ NS04 ─┤
       ├─ NS05 ─┼─► NS08 ─► NS09 ─► NS10 ─► NS11
       ├─ NS06 ─┤
       └─ NS07 ─┘
```

## Parallel Opportunities

```bash
# After NS01 lands, author all six checks together (one file, six independent functions):
Task: "NS02 No supervisor agent package exists — tests/architecture/test_no_supervisor_architecture.py"
Task: "NS03 No central router service exists — tests/architecture/test_no_supervisor_architecture.py"
Task: "NS04 No workflow engine owns the business process — tests/architecture/test_no_supervisor_architecture.py"
Task: "NS05 Customer Resolution coordinates only its own cases — tests/architecture/test_no_supervisor_architecture.py"
Task: "NS06 Billing never calls Risk — tests/architecture/test_no_supervisor_architecture.py"
Task: "NS07 Risk never calls Billing — tests/architecture/test_no_supervisor_architecture.py"
```

## Notes

- **No new dependency, no new topic, no new event contract** — every check is a static filesystem/AST
  scan over existing source; the only genuinely-new artifacts are `tests/architecture/helpers.py`, the
  six-function `test_no_supervisor_architecture.py`, and `docs/architecture/choreography-not-orchestration.md`.
- **Extend, don't duplicate**, the three existing guards (`test_no_supervisor.py`, `test_no_router.py`,
  `test_domain_isolation.py`); the new module consolidates the six requested checks into one CI-runnable,
  broker-free target and is the single answer to "is the architecture constraint testable?" (yes — NS08).
- Each check should be demonstrated to **fail on a seeded violation** before being trusted (a guard that
  can never fail proves nothing).
- The structural test (NS02–NS08) proves **no central component exists**; the complementary audit-trail
  proof that decisions **emerge purely from peer events** (SC-009b) is `tasks.md` T032 in
  `tests/integration/test_workflow_choreography.py` — reference it from the doc (NS09), don't re-implement it here.
- This focused list corresponds to `tasks.md` Phase 8 (T031/T032). Keep `tasks.md` authoritative for the
  full feature; fold NS01–NS11 in there if/when you implement the whole feature. Commit after each task
  or logical group.
