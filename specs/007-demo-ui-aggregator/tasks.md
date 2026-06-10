---
description: "Task list for Demo UI — A2A Card & Audit Aggregator (Streamlit-first)"
---

# Tasks: Demo UI — A2A Card & Audit Aggregator

**Input**: Design documents from `/specs/007-demo-ui-aggregator/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: INCLUDED. The spec mandates pytest unit + integration coverage (SC-002/005/006), the
acceptance criteria require provable guarantees ("UI does not contain business decision logic",
read-only with one bounded write), and the requested layout includes a `tests` folder.

## ⚠️ Stack override (user input supersedes plan.md)

`plan.md` / `research.md` / `contracts/` describe a **FastAPI + Jinja2 + HTMX** app at `apps/ui/`.
The `/speckit-tasks` request explicitly overrides this with a **Streamlit-first** app at
`apps/demo_ui/` and a fixed module layout (confirmed by the user: "Replace with Streamlit"). These
tasks follow the override while preserving **all** design semantics:

- Reuse foundation read-side only: `runtime.discovery.discover_agents`,
  `audit.store.query_by_correlation` / `consume_all_audit_records`,
  `apps.agents.customer_resolution.trace.trace_case` (UI == CLI causal ordering).
- Dedup audit events by `event_id`; newest-first stream; AND-combined filters (FR-010/011/015).
- Distinguish "announced" from "live" (liveness probe) and never show stale-as-live (R2/R3).
- The **only** write is one root `support.ticket.created` envelope (`causation_id=None`),
  reusing the `apps/api/dev_publish_ticket.py` publish path (FR-014, SC-006).
- No business decision logic in the UI; refresh ≤5 s; honest degraded states, never crash (FR-016).

> **Follow-up**: `plan.md`, `research.md`, and `contracts/` still describe the FastAPI/`apps/ui`
> approach. They should be reconciled to Streamlit/`apps/demo_ui` (re-run `/speckit-plan`) so the
> design artifacts and this task list agree. Tracked as task T029 below.

View models from `data-model.md` (RosterEntry/CapabilityView, TimelineEntry/TimelineView,
StreamEvent/StreamView, DemoTriggerRequest/Result) are defined **inside their owning module**
(no separate `viewmodels.py`, since the requested layout omits it).

## Acceptance criteria (from request) → where satisfied

- **UI runs independently** → T002 (own extra/script), T005 (standalone Streamlit shell with empty
  states), T024 (4th service in start script), T025 (verify it starts with no agents/broker data).
- **No business decision logic** → enforced by construction in T007/T011/T015 (read + display only)
  and asserted by guard test T022.
- **Streamlit first for speed** → entire stack is Streamlit (`apps/demo_ui/app.py` + `views/`).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1 / US2 / US3 for user-story phases only
- All paths are repo-root-relative

## Path conventions

- App package: `apps/demo_ui/` (per user request)
- Unit tests: `tests/unit/demo_ui/`; integration tests: `tests/integration/demo_ui/`
  (repo convention — `tests/` tree is where pytest collects; this is the requested `tests` folder
  mapped onto the existing test root)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project skeleton and dependency wiring so the Streamlit app can run independently.

- [X] T001 Create the package skeleton: `apps/demo_ui/__init__.py`, `apps/demo_ui/views/__init__.py`,
  empty module stubs `apps/demo_ui/{app,config,agent_cards,event_stream,timeline,ticket_form}.py`,
  and test dirs `tests/unit/demo_ui/__init__.py`, `tests/integration/demo_ui/__init__.py`.
- [X] T002 Add a `ui` optional-dependencies extra (`streamlit>=1.36`; `httpx` already present) and a
  `demo-ui` entry under `[project.scripts]` (a thin launcher that runs `streamlit run apps/demo_ui/app.py`
  on port 8200) in `pyproject.toml`. Verify `uv sync --extra ui` resolves.
- [X] T003 [P] Implement configuration in `apps/demo_ui/config.py`: broker URL from `AGENT_BROKER_URL`
  (fallback `localhost:9092`), `UI_PORT=8200`, `REFRESH_SECONDS=5`, `EXPECTED_AGENT_IDS =
  ("customer-resolution-agent", "billing-entitlement-agent", "risk-fraud-agent")`, and per-agent
  HTTP liveness endpoints (billing `:8101/ping`, risk `:8103/ping`; customer-resolution = none).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The async→sync bridge and the app shell that every view plugs into. Streamlit is
synchronous; all foundation read-side helpers are `async`.

**⚠️ CRITICAL**: No user-story view can render until this phase is complete.

- [X] T004 Add an async bridge + tiny last-poll cache in `apps/demo_ui/config.py`: a `run_async(coro)`
  helper (wraps `asyncio.run`) and a short-TTL in-process cache keyed by call so concurrent reruns
  within one refresh interval reuse the last Kafka read (research R6). Pure plumbing — no domain logic.
- [X] T005 Implement the standalone Streamlit shell in `apps/demo_ui/app.py`: `st.set_page_config`,
  a sidebar nav selecting Roster / Case / Stream / Trigger, dispatch to each view's render function,
  and a top-level `try/except` that renders an honest degraded banner instead of crashing (FR-016).
  Reading a `?case=<uuid>` / `?view=` query param routes to the case view (used by deep-links).
  Must run cleanly with no broker/agents up (empty states, no traceback) — the "runs independently" base.

**Checkpoint**: `streamlit run apps/demo_ui/app.py` launches and shows empty states with nothing else running.

---

## Phase 3: User Story 1 - Agent roster & capabilities (Priority: P1) 🎯 MVP

**Goal**: Show all three expected agents as cards (identity, version, accepting endpoint,
capabilities) with announced-vs-live liveness; missing agents shown as not-announced, no stale dupes.

**Independent Test**: Start the system, open the UI; three cards appear with correct names/versions/
capabilities. Stop one HTTP agent → it flips to `liveness: unknown` within a refresh; an agent that
never published shows `announced: false` rather than being omitted.

### Tests for User Story 1

- [X] T006 [P] [US1] Unit test roster aggregation in `tests/unit/demo_ui/test_agent_cards.py` with
  fabricated `AgentCard` fixtures: latest-card-per-agent (FR-003, no superseded dupes), missing agent
  → `RosterEntry(announced=False, liveness="not_announced")` (FR-004), capability mapping, and
  liveness mapping (`live` / `unknown` from probe, `not_announced` when absent).

### Implementation for User Story 1

- [X] T007 [P] [US1] Implement `apps/demo_ui/agent_cards.py`: `RosterEntry` + `CapabilityView`
  view models (data-model.md) and `build_roster()` which calls `discover_agents(broker_url)`, runs a
  thin envelope reader to capture each card's `last_announced` envelope timestamp (research R2), probes
  HTTP `/ping` per `config` for liveness via `httpx` with a short timeout (R3, failures → `unknown`,
  never raise), and returns exactly one `RosterEntry` per `EXPECTED_AGENT_IDS`. Read + map only.
- [X] T008 [US1] Implement `apps/demo_ui/views/roster_view.py`: `render(broker_url)` drawing one card
  per agent (name, description, version, accepting endpoint topic, capabilities with tags), a liveness
  badge, a `last_announced` timestamp, a "waiting for agents" empty state, and a `REFRESH_SECONDS`
  auto-refresh (`st_autorefresh`/rerun). Pure presentation of `build_roster()` output.
- [X] T009 [US1] Wire `roster_view` into `apps/demo_ui/app.py` as the default landing page.

**Checkpoint**: US1 fully functional and demoable on its own (SC-001).

---

## Phase 4: User Story 2 - Trace a single case end to end (Priority: P2)

**Goal**: For a `correlation_id`, render the full causal timeline (intake → triage → review requests →
Billing & Risk results → decision) using `trace_case`, each row attributed with actor/type/outcome/
timestamp/caused-by, failures showing reason, with an explicit "no events found" state.

**Independent Test**: Drive one case (CLI `dev_publish_ticket.py` or the Phase 6 trigger), open
`?view=case&case=<id>`; the timeline matches the known sequence in causal order and equals the
`trace_case.py` CLI output.

### Tests for User Story 2

- [X] T010 [P] [US2] Unit test timeline aggregation in `tests/unit/demo_ui/test_timeline.py` with
  fabricated `AuditPayload`/`EventEnvelope` fixtures: ordering equals `trace_case` (causation-then-time),
  `outcome`/`reason` joined by `event_id`, orphan parent → `is_orphan=True` (not dropped, FR-016),
  failed/rejected rows expose `reason` (FR-008), and empty input → `TimelineView(found=False)` (FR-009).

### Implementation for User Story 2

- [X] T011 [P] [US2] Implement `apps/demo_ui/timeline.py`: `TimelineEntry` + `TimelineView` view models
  and `build_timeline(broker_url, correlation_id)` which calls `query_by_correlation`, maps to
  `[r.original_envelope ...]`, calls `trace_case(correlation_id, envelopes)`, joins each `TraceStep` to
  its `AuditPayload` `outcome`/`reason` by matching `original_envelope.event_id`, flags orphans, and
  sets `found=False` for empty results. No re-implementation of ordering — delegate to `trace_case`.
- [X] T012 [US2] Implement `apps/demo_ui/views/case_view.py`: `render(broker_url, correlation_id)` with
  a correlation-id input box, an ordered table (seq, actor, event_type, outcome, timestamp, caused_by),
  reason shown for failed/rejected, an orphan/"parent not found" marker, a "no events found for this
  case" empty state, and auto-refresh while a case is open.
- [X] T013 [US2] Wire `case_view` into `apps/demo_ui/app.py` nav and honor the `?case=<uuid>` deep-link
  query param (target of the Story 3 stream row links and the Phase 6 trigger result).

**Checkpoint**: US1 and US2 both work independently; UI timeline == CLI trace (SC-002, SC-004).

---

## Phase 5: User Story 3 - Live audit stream & filters (Priority: P3)

**Goal**: Newest-first cross-case audit feed, deduped by `event_id`, with AND-combined agent / event-type /
case filters, auto-refresh ≤5 s, and per-row deep-link to the case timeline.

**Independent Test**: With the system running, drive cases; new rows appear within ≤5 s without a manual
full reload; filtering by agent narrows the list and clearing restores it; clicking a row opens its case.

### Tests for User Story 3

- [X] T014 [P] [US3] Unit test stream aggregation in `tests/unit/demo_ui/test_event_stream.py`:
  dedup by `event_id` keeps one row for replayed records (FR-015/SC-005), newest-first sort by
  timestamp (FR-010), AND-combined filters by agent / event_type / correlation_id with clearing
  restoring the full set (FR-011).

### Implementation for User Story 3

- [X] T015 [P] [US3] Implement `apps/demo_ui/event_stream.py`: `StreamEvent` + `StreamView` view models
  and `build_stream(broker_url, filter_agent=None, filter_event_type=None, filter_correlation_id=None)`
  which calls `consume_all_audit_records`, dedups by `original_envelope.event_id` (first-seen),
  sorts newest-first, then applies in-memory AND filters. Read + filter only, no decisions.
- [X] T016 [US3] Implement `apps/demo_ui/views/stream_view.py`: `render(broker_url)` with a newest-first
  table, filter widgets (agent select, event-type select, case text input), `REFRESH_SECONDS`
  auto-refresh, and per-row "open case" controls that deep-link to the case view via `?case=`.
- [X] T017 [US3] Wire `stream_view` into `apps/demo_ui/app.py` nav.

**Checkpoint**: All three user stories independently functional (SC-003, SC-005).

---

## Phase 6: Bounded Demo Trigger (the only write — cross-cutting)

**Purpose**: Let a presenter start a case from the screen by publishing exactly one root
`support.ticket.created` event. Additive: stories 1–3 remain testable via the CLI without this.

**Constraint**: Publishes nothing but the single root envelope (`causation_id=None`); no task-request,
result, audit, or agent-card event (FR-014, SC-006).

### Tests for Bounded Demo Trigger

- [X] T018 [P] Unit test the trigger in `tests/unit/demo_ui/test_ticket_form.py`: `DemoTriggerRequest`
  defaults/validation (amount > 0, 3-letter currency, auto ids) map to `SupportTicketCreatedPayload`;
  with a mocked `Publisher`, exactly ONE envelope is published, its `event_type ==
  topic_for("support","ticket","created")` and `causation_id is None`, and `DemoTriggerResult` returns
  the new `correlation_id`/`event_id` (SC-006 read-only guarantee).

### Implementation for Bounded Demo Trigger

- [X] T019 [P] Implement `apps/demo_ui/ticket_form.py`: `DemoTriggerRequest` + `DemoTriggerResult` view
  models and `publish_demo_ticket(req, broker_url)` reusing the `dev_publish_ticket.py` path
  (`AgentIdentity`, `SupportTicketCreatedPayload`, `Publisher.publish`, `topic_for`), minting a fresh
  `correlation_id` and `causation_id=None`. May construct no other payload type.
- [X] T020 Implement `apps/demo_ui/views/trigger_view.py`: `render(broker_url)` with a form (amount,
  currency, reason, optional ticket/customer id) that on submit calls `publish_demo_ticket`, shows the
  result, and offers a deep-link to the new case's timeline (`?view=case&case=<correlation_id>`).
- [X] T021 Wire `trigger_view` into `apps/demo_ui/app.py` nav.

**Checkpoint**: A presenter starts a case from the UI and is taken to its live timeline.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T022 [P] Guard test `tests/unit/demo_ui/test_no_business_logic.py`: assert no `apps/demo_ui`
  module imports decision/scoring logic (e.g. `apps.agents.customer_resolution.decision`,
  billing/risk scoring modules) and that aggregators reference only the allowed read-side helpers +
  `ticket_form` the publish path — encoding the "no business decision logic" acceptance criterion.
- [X] T023 Integration test `tests/integration/demo_ui/test_ui_end_to_end.py` (`@pytest.mark.integration`,
  `testcontainers[kafka]`): publish one root ticket, let the agents react, then assert
  `build_timeline(...)` ordering/attribution equals `trace_case` for that `correlation_id` (UI == CLI,
  SC-002) and that replayed audit records appear once (SC-005).
- [X] T024 Extend `scripts/start-local-system.sh` to launch the demo UI as a 4th background service on
  port 8200 (`streamlit run apps/demo_ui/app.py --server.port 8200 --server.headless true`), inheriting
  `AGENT_BROKER_URL`, with PID/log under `.local-run/`; update `scripts/stop-local-system.sh` to stop it (FR-017).
- [X] T025 Verify "runs independently": start the UI alone (no broker/agents) and confirm all four views
  render honest empty/degraded states without crashing; document the standalone run command.
- [X] T026 [P] Add `apps/demo_ui/README.md`: how to run (`uv sync --extra ui` then
  `streamlit run apps/demo_ui/app.py`), the four views, and the read-only + single-write guarantees.
- [X] T027 Run `ruff check apps/demo_ui tests/unit/demo_ui tests/integration/demo_ui` (and format) so the
  GitHub CI lint passes; fix findings.
- [ ] T028 Execute `specs/007-demo-ui-aggregator/quickstart.md` scenarios 1–4 against the local system
  and confirm SC-001..SC-006 (update quickstart commands that reference the old `apps/ui`/HTTP routes to
  the Streamlit `apps/demo_ui` run command + views as part of this task).
- [X] T029 Reconcile design artifacts to the Streamlit decision: update `plan.md` (Technical Context,
  Project Structure, dependencies), `research.md` (R6/R9 refresh + packaging), and `contracts/` (the
  HTTP-API contract no longer applies as written) — or re-run `/speckit-plan` — so the design docs and
  this Streamlit task list agree.

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (Phase 1)**: no dependencies — start immediately.
- **Foundational (Phase 2)**: depends on Setup — BLOCKS all user stories and the trigger.
- **User Stories (Phases 3–5)**: each depends only on Foundational; mutually independent, so they can
  proceed in parallel or in priority order (P1 → P2 → P3).
- **Bounded Demo Trigger (Phase 6)**: depends on Foundational; independent of US1–US3 (deep-links into
  US2 when present but does not require it for its own test).
- **Polish (Phase 7)**: depends on the stories/trigger it exercises (T023/T028 need US1–US3 + trigger).

### Within each story

- Aggregator module (read-side) before its view; view before app wiring.
- Unit test [P] alongside the aggregator (different file); written to fail first if doing TDD.

### Parallel opportunities

- T003 (config) runs once T001 lands.
- After Foundational, the three story aggregators are independent: **T007, T011, T015** can run in
  parallel (different files), as can their unit tests **T006, T010, T014, T018**.
- Polish [P] tasks **T022, T026** are independent.

---

## Parallel Example: post-Foundational fan-out

```bash
# After Phase 2, launch the three story aggregators + the trigger module in parallel:
Task: "Implement apps/demo_ui/agent_cards.py (roster + liveness)"      # T007 [US1]
Task: "Implement apps/demo_ui/timeline.py (trace_case timeline)"        # T011 [US2]
Task: "Implement apps/demo_ui/event_stream.py (dedup + filters)"        # T015 [US3]
Task: "Implement apps/demo_ui/ticket_form.py (bounded write)"           # T019

# And their unit tests together:
Task: "tests/unit/demo_ui/test_agent_cards.py"     # T006
Task: "tests/unit/demo_ui/test_timeline.py"        # T010
Task: "tests/unit/demo_ui/test_event_stream.py"    # T014
Task: "tests/unit/demo_ui/test_ticket_form.py"     # T018
```

---

## Implementation Strategy

### MVP first (User Story 1 only)

1. Phase 1 Setup → 2. Phase 2 Foundational → 3. Phase 3 US1 (roster).
4. **STOP and VALIDATE**: open the UI, confirm three agent cards + capabilities + liveness (SC-001).
5. Demo the roster as the first observable slice.

### Incremental delivery

- Setup + Foundational → app shell runs independently with empty states.
- + US1 → roster (MVP). + US2 → case timeline. + US3 → live stream.
- + Bounded trigger → start cases from the screen. + Polish → start-script wiring, parity/integration
  tests, guard test, quickstart validation, design-doc reconciliation.

---

## Notes

- [P] = different files, no incomplete dependencies. [Story] maps a task to its user story.
- Keep all decision/scoring logic OUT of `apps/demo_ui` — read recorded outcomes and display them only.
- The trigger is the sole write and emits exactly one root `support.ticket.created` envelope.
- Reuse `trace_case` verbatim so the UI timeline and the CLI tell the identical story.
- Commit after each task or logical group; stop at any checkpoint to validate a story independently.

---

## Phase 10: Local Demo Launcher — `make demo-ui` (cross-cutting) 🚀

> **Added by a `/speckit-tasks` run** invoked with the focused context **"Add local demo launcher —
> `make demo-ui`"**. This `tasks.md` was co-authored by several concurrent runs; IDs here start at
> **T200** to leave a wide margin above the highest ID then present (~T136) and avoid collisions.
> This phase builds on **T024** (which extends `start-local-system.sh` to launch `demo-ui`) and adds
> the one-command `make demo-ui` entrypoint plus the no-supervisor acceptance check.

**Purpose**: One command brings up the entire portfolio demo — **Kafka/Redpanda + Kafka UI + all three
agents + the demo UI** — and starts **no supervisor/orchestrator service**. Maps to FR-017 and research
R9; mirrors the existing `Makefile` `demo-*` convention and the `KAFKA_UI_PORT=8080` constant in
`scripts/lib/common.sh`.

**Acceptance criteria (from the request)**:
1. One command (`make demo-ui`) launches the portfolio demo.
2. No supervisor service is started — the start script still exits after launching independent agents
   (no wait loop, no central router); the UI is an observer with one bounded write only.

- [ ] T200 Add `DEMO_UI_PORT=8200` to `scripts/lib/common.sh` alongside the existing `KAFKA_UI_PORT=8080`, `BILLING_HTTP_PORT=8101`, `RISK_HTTP_PORT=8103` constants, so the start/stop scripts and the Makefile share one source of truth for the UI port.
- [ ] T201 Ensure `scripts/start-local-system.sh` launches `demo-ui` behind a `--with-ui` flag via the existing `start_agent` helper (`start_agent "demo-ui" "PORT=${DEMO_UI_PORT} uv run demo-ui"`), placed AFTER the three agents and BEFORE the script's immediate exit. Reconcile with T024: if T024 launches `demo-ui` unconditionally, convert that to this `--with-ui` flag. Append the demo-ui PID/log line and `UI: http://localhost:${DEMO_UI_PORT}` to the trailing summary. MUST NOT add any wait loop or supervisor (preserves AC2). Depends on T200.
- [ ] T202 [P] Extend `scripts/stop-local-system.sh` to `stop_agent "demo-ui"` so the fourth service is torn down with the agents (idempotent when never started). Depends on T200.
- [ ] T203 Add a `demo-ui` target to the root `Makefile` (and to `.PHONY`): depend on `demo-infra-up` (already starts Redpanda + Kafka UI via `infra/local/docker-compose.yml`), then run `bash scripts/start-local-system.sh --with-http --with-ui`, and `@echo` the URLs (UI `http://localhost:8200`, Kafka UI `http://localhost:8080`). Net effect: this single target starts Redpanda, Kafka UI, all three agents, and the demo UI (AC1) and starts no supervisor (AC2). Depends on T201.
- [ ] T204 Verify both acceptance criteria: run `make demo-ui`; confirm one command brought up Redpanda + Kafka UI (`:8080`) + billing (`:8101`) + risk (`:8103`) + customer-resolution + demo UI (`:8200`); confirm NO supervisor/router process exists — only `infra` containers plus the four agent/UI PIDs under `.local-run/pids/` (no extra coordinator process, no central-router log). Tear down via `make demo-agents-down` / `make demo-clean`. Depends on T201, T202, T203.

**Checkpoint**: `make demo-ui` launches the full portfolio demo in one command, with no supervisor started.

### Launcher dependencies & parallelism

- T200 is the prerequisite for T201/T202 (shared port constant).
- T201 -> T203 (the Makefile target invokes the `--with-ui` start path).
- T202 runs in parallel with T201/T203 (different file: `stop-local-system.sh`).
- T204 is the final gate — depends on T201, T202, T203.
- This phase depends only on the `demo-ui` console script existing (T002); best run once US1 is demoable so the launched UI shows the roster.

---

## Addendum — Focused context: "Add final decision panel" (User Story 6, P4)

> **Stack:** Streamlit-first (`apps/demo_ui/`), consistent with the "⚠️ Stack override" at the top of
> this file. (An earlier draft of this addendum was FastAPI/Jinja2/HTMX-framed; it was re-framed to
> Streamlit per the user's "Replace with Streamlit" decision. Design semantics are unchanged.)

This `/speckit-tasks` run was invoked to add a **final-decision panel** to the **case view**
(`apps/demo_ui/views/case_view.py`, US2) that summarizes a refund case's terminal outcome at a glance:
**decision, confidence, billing recommendation, risk recommendation, requires-human-review, reasoning
summary, and the customer-facing response draft**. It is pure observation — no write, no publisher, no
new event contract, topic, or agent (FR-014 / SC-006 preserved), and it contains **no business decision
logic** (it reads recorded outcomes and displays them; reinforced by the T022 guard). It is sourced
entirely from events the UI already reads for the US2 timeline (each domain event wrapped in an
`AuditPayload` on the audit topic, fetched via `query_by_correlation`).

This is **User Story 6 (P4)**. It depends on **Phase 2 (Foundational)** and the **US2 read-side**
(`build_timeline` / `query_by_correlation` in `apps/demo_ui/timeline.py`); it renders inside the US2 case
view and shares its `REFRESH_SECONDS` auto-refresh. Task IDs are **T160–T169** (this band was reconciled
against the live file; re-grep `^- \[ \] T[0-9]{3}` before reusing it).

**Panel field → authoritative source (existing contract — no new contract added):**

| Panel field (requested) | Source |
|-------------------------|--------|
| **decision** | `CustomerResponseDecisionPayload.outcome` on `TOPIC_RESOLUTION_DECIDED` (`local.customer.resolution.decided.v1`) |
| **confidence** | `CustomerIssueClassifiedPayload.confidence` on `TOPIC_ISSUE_CLASSIFIED` — the decided event carries no blended confidence, so the observer surfaces the published decision-time signal rather than re-deriving the engine score (no business logic in the UI; Principle V) |
| **billing recommendation** | `BillingRefundAnalysisCompletedPayload.recommendation` (fallback `decided.billing_summary`) |
| **risk recommendation** | `RiskReviewCompletedPayload.recommendation` (fallback `decided.risk_summary`) |
| **requires human review** | `CustomerResponseDraftedPayload.requires_human_approval` on `TOPIC_RESPONSE_DRAFTED` (fallback `outcome == escalate_human`) |
| **reasoning summary** | `CustomerResponseDecisionPayload.rationale` — INTERNAL; rendered in a clearly-separated internal section (e.g. a collapsed `st.expander`), never inside the customer draft |
| **customer response draft** | `CustomerResponseDraftedPayload.draft_response` — already fraud-safe by construction (the drafter excludes `INTERNAL_ONLY_DRAFT_FIELDS` + fraud-scoring fields) |

### Foundational view model (precedes the panel)

- [ ] T160 [P] [US6] Add a `DecisionPanelView` view model to `apps/demo_ui/decision.py` (per the Streamlit convention of co-locating view models with their owning module — no shared `viewmodels.py`; extends data-model.md): `found: bool`, `decision: str | None` (the `outcome`), `confidence: float | None`, `billing_recommendation: str | None`, `risk_recommendation: str | None`, `requires_human_review: bool`, `reasoning_summary: str | None`, `customer_response_draft: str | None`, `escalation_reason: str | None`, `is_escalated: bool`. Field names/types/optionality documented in data-model.md (T169).

### Tests for User Story 6 (write first, ensure they FAIL)

- [ ] T161 [P] [US6] Unit test `tests/unit/demo_ui/test_decision.py` with fabricated `AuditPayload`/`EventEnvelope` fixtures (no broker): `build_decision_panel(broker_url, correlation_id)` maps the case's latest `local.customer.resolution.decided.v1` event → `decision=outcome`, `reasoning_summary=rationale`, `escalation_reason`; `billing_recommendation` from `BillingRefundAnalysisCompletedPayload.recommendation` (fallback `decided.billing_summary`); `risk_recommendation` from `RiskReviewCompletedPayload.recommendation` (fallback `decided.risk_summary`); `confidence` from `CustomerIssueClassifiedPayload.confidence`; `requires_human_review` from the drafted event's `requires_human_approval` (fallback `outcome == escalate_human`).
- [ ] T162 [P] [US6] Extend `test_decision.py` for **escalation**: an `escalate_human` decision yields `is_escalated=True` with a non-empty `escalation_reason` (e.g. `low_confidence` / `peer_failure` / `analysis_timeout` / `conflicting_analyses`); a non-escalated outcome yields `is_escalated=False`, `escalation_reason=None` (acceptance: "Escalated cases show escalation reason").
- [ ] T163 [P] [US6] Extend `test_decision.py` for **fraud-safety**: `customer_response_draft` equals the drafted event's `draft_response` and contains NONE of the case's `INTERNAL_ONLY_DRAFT_FIELDS` values (`rationale`, `escalation_reason`, `billing_summary`, `risk_summary`) nor any `FRAUD_SCORING_FIELDS` content (`score`, risk `evidence`, risk `reasoning_summary`); when the drafted event is absent the panel leaves `customer_response_draft=None` rather than falling back to any internal text (acceptance: "Fraud details are not shown in customer-facing draft").
- [ ] T164 [P] [US6] Extend `test_decision.py` for **robustness + empty state**: a case with no decided event → `DecisionPanelView(found=False)`; a duplicated decided `event_id` collapses to the single latest entry (FR-015); malformed/late records degrade honestly without raising (FR-016). Add a render smoke check via `streamlit.testing.v1.AppTest` (or by calling the render function directly) asserting the panel shows a "no decision yet" state when `found=False` and never raises when the drafted event is missing.

### Implementation for User Story 6

- [ ] T165 [P] [US6] Implement `build_decision_panel(broker_url, correlation_id)` in `apps/demo_ui/decision.py`: call `query_by_correlation(broker_url, correlation_id)` (via the `config.run_async` bridge), dedup records by `event_id`, then select the case's latest decided (`CustomerResponseDecisionPayload`), latest drafted (`CustomerResponseDraftedPayload`), classified (`CustomerIssueClassifiedPayload`), and billing/risk result payloads; map them to `DecisionPanelView` per the source table above; populate `customer_response_draft` **only** from `draft_response` (never from internal fields); set `found=False` when no decided event exists; tolerate missing/duplicate/malformed records without raising (FR-016). **Read + map only — no decision/scoring logic** (reuses the US2 read-side; adds no new contract).
- [ ] T166 [US6] Implement `render_decision_panel(view: DecisionPanelView)` in `apps/demo_ui/decision.py` using Streamlit widgets: a prominent **decision** indicator (the `ResolutionOutcome`), `confidence` (e.g. `st.metric`), billing recommendation, risk recommendation, a requires-human-review badge, the `reasoning_summary` inside a clearly-labeled **internal** `st.expander`, and the customer-facing response draft in a **separate "Customer response" section rendered only from `customer_response_draft`**; an escalation-reason callout (`st.warning`) shown when `is_escalated`; an explicit "no decision yet" empty state when `found=False`. Pure presentation of the T165 output.
- [ ] T167 [US6] Embed the panel at the **top** of `apps/demo_ui/views/case_view.py` `render(broker_url, correlation_id)` (above the timeline table), calling `build_decision_panel(...)` then `render_decision_panel(...)`; it rides the case view's existing `REFRESH_SECONDS` auto-refresh so the panel fills in/updates within one refresh interval when the decision event arrives, with no manual reload (acceptance: "Panel updates when decision event arrives"; FR-012 / SC-003). Depends on T165, T166.
- [ ] T168 [P] [US6] Extend the no-business-logic guard test `tests/unit/demo_ui/test_no_business_logic.py` (T022) to assert `apps/demo_ui/decision.py` imports only the allowed read-side helpers (`audit.store.query_by_correlation`) and event-payload contracts — never `apps.agents.customer_resolution.decision_engine`, the billing/risk scoring modules, or `response_drafter` — encoding "no business decision logic" for the decision panel.
- [ ] T169 [P] [US6] Document the panel: add `DecisionPanelView` (with the field→source mapping above and the fraud-safety rule) to `specs/007-demo-ui-aggregator/data-model.md`, and add a "Final decision panel" check to Scenario 2 of `specs/007-demo-ui-aggregator/quickstart.md` (Streamlit case view). Note in the T029 design-reconciliation that the panel is a Streamlit view, not an HTTP route, so `contracts/ui-http-api.md` adds no endpoint for it.

**Checkpoint**: Opening the case view for a completed case shows the decision panel with all seven fields;
the panel updates within the refresh interval as the decision lands; escalated cases display their
escalation reason; and the customer-facing draft never contains fraud/internal details. Independently
testable; depends only on Phase 2 + the US2 read-side.

### Acceptance-criteria mapping

| Acceptance criterion | Where satisfied |
|----------------------|-----------------|
| Panel **updates when the decision event arrives** | T167 (renders in the case view under its `REFRESH_SECONDS` auto-refresh) + T165 (re-query decided event each refresh) |
| **Escalated cases show escalation reason** | T162 (test) + T165 (`escalation_reason`/`is_escalated` mapping) + T166 (escalation callout) |
| **Fraud details are not shown in the customer-facing draft** | T163 (test) + T165 (`customer_response_draft` sourced only from fraud-safe `draft_response`) + T166 (separate customer section, internal fields kept in an internal expander) + T168 (guard) |

---

## Addendum — Focused context: "Add sample ticket submission form" (User Story 8)

Invoked context: a sample ticket submission **form** with fields `customer_id`, `ticket_id`,
`refund_amount`, `purchase_reference`, `customer_message`, `scenario`; on submit publish
`local.support.ticket.created.v1`. Acceptance: **(a)** the UI publishes ONLY the initial root event;
**(b)** the UI does NOT call Billing or Risk directly; **(c)** a `correlation_id` is generated and
displayed.

Home: the bounded write path in **Phase 6 (Bounded Demo Trigger — the only write)**. These tasks add the
operator-facing form on top of it. Labelled **US8**; IDs start at **T300** to clear the concurrently
authored lower-numbered tasks.

**Field → contract mapping (NO new contract — `SupportTicketCreatedPayload` is frozen, `extra="forbid"`,
fields `ticket_id, customer_id, amount, currency, reason, created_at`)**: `customer_id→customer_id`,
`ticket_id→ticket_id`, `refund_amount→amount`, `customer_message→reason`, `purchase_reference` folded
into the `reason` text, `currency` defaults `"USD"`, `created_at=now`. **`scenario` is a UI-only
field** — it selects sample field values (reusing a scenario-preset catalog if one exists in the build,
else a small local sample map) and is NEVER published as a payload field, so the frozen contract and the
no-supervisor guarantee are untouched.

### Tests for User Story 8 ⚠️ (write first, ensure they FAIL)

- [ ] T300 [P] [US8] Unit test `tests/unit/ui/test_demo_trigger.py` (extend): a `DemoTriggerRequest` with the six form fields maps to a `SupportTicketCreatedPayload` where `amount==refund_amount`, `reason` contains both `customer_message` and `purchase_reference`, and `currency=="USD"` by default; `publish_ticket()` mints a fresh `correlation_id`, publishes exactly ONE root envelope of `event_type == local.support.ticket.created.v1` with `causation_id is None`, and writes to NO billing/risk task-request, result, audit, or agent-card topic (acceptance a + b); `DemoTriggerResult.correlation_id` is the minted id (acceptance c).
- [ ] T301 [P] [US8] Route test `tests/unit/ui/test_routes.py` (extend): `POST /demo/ticket` accepting the six fields (form-encoded AND JSON) returns/renders the generated `correlation_id` plus a link to `/case/{correlation_id}`; selecting only a `scenario` pre-fills the remaining fields; assert no `Publisher` is invoked on any GET route (read-only guarantee — encodes all three acceptance criteria).

### Implementation for User Story 8

- [ ] T302 [US8] Extend `DemoTriggerRequest` in `apps/ui/demo_trigger.py` (per data-model.md) to the six form fields — `customer_id`, `ticket_id`, `refund_amount` (> 0, mapped to `amount`), `purchase_reference`, `customer_message` (mapped to `reason`), `scenario` (optional) — with defaults/validation; document the field→`SupportTicketCreatedPayload` mapping in the model docstring (`purchase_reference` folded into `reason`; `scenario` form-only, never published). Reuses, does not modify, the frozen `SupportTicketCreatedPayload`.
- [ ] T303 [US8] Update `publish_ticket()` in `apps/ui/demo_trigger.py` to apply the mapping and, when `scenario` is set, pre-fill missing fields from the scenario sample map (reuse the preset catalog if present) before constructing the single `SupportTicketCreatedPayload`; publish exactly one root `support.ticket.created` envelope (`causation_id=None`) via the existing `apps/api/dev_publish_ticket.py` path — no other topic written (makes T300 pass).
- [ ] T304 [P] [US8] Create `apps/ui/templates/partials/_ticket_form.html`: the six inputs incl. a `scenario` `<select>`; HTMX `POST /demo/ticket`; a result region rendering the returned `correlation_id` (acceptance c) with a deep link to `/case/{correlation_id}`.
- [ ] T305 [US8] Surface the form (include `_ticket_form.html` on the roster landing + a `base.html` nav link) and extend the Phase 6 `POST /demo/ticket` route to accept the six form fields (form-encoded + JSON) and respond with the generated `correlation_id` (JSON) or a redirect/partial that displays it (HTML) (depends on T302, T303, T304).
- [ ] T306 [P] [US8] Update `specs/007-demo-ui-aggregator/contracts/ui-http-api.md` (`POST /demo/ticket` request schema → the six form fields + the field→contract mapping note) and `quickstart.md` Scenario 4 to drive the case via the form.

### Acceptance-criteria mapping

| Acceptance criterion | Where satisfied |
|----------------------|-----------------|
| (a) UI publishes only the initial event | T300 (single root `support.ticket.created`, `causation_id=None`, no other topic) + T303 |
| (b) UI does not call Billing or Risk directly | T300/T301 (no task-request/result/audit/agent-card publish; GET routes read-only) |
| (c) Correlation ID generated and displayed | T300 (minted `correlation_id`) + T304 (rendered in form result) + T305 (route returns/redirects with it) |

---

## Addendum — Focused context: "Add raw event inspector"

This `/speckit-tasks` run was invoked with the **raw event inspector** context: for every event, show
`event_id`, `event_type`, `topic`, `correlation_id`, `causation_id`, `producer_agent_id`, `timestamp`,
`payload`, and `metadata`. Acceptance criteria: **useful for a GitHub portfolio walkthrough**,
**supports copy JSON**, and **sensitive fields can be redacted**.

This is a new **User Story 9 (P4) — Raw Event Inspector**. It depends only on **Phase 2
(Foundational)** and on the deduped audit list built in **US3** (`build_stream` /
`consume_all_audit_records`); its deep-link entry point comes from US3's stream rows but the inspector
view is independently testable via `GET /api/event/{event_id}`. This feature is co-authored by several
concurrent `/speckit-tasks` runs, so this block uses a deliberately high task-ID band (**T900+**) and
story label **[US9]** to avoid colliding with the lower-numbered blocks above.

**Field-source grounding (see data-model.md and `src/agent_foundation/envelope.py`):** `EventEnvelope`
has `event_id, correlation_id, causation_id, agent_id, tenant_id, timestamp, event_type, schema_version,
payload` — there is **no native `topic` or `metadata` field**, so:
- **`producer_agent_id`** ← `original_envelope.agent_id`.
- **`topic`** is DERIVED — in this system the publish topic string equals the `event_type` (e.g.
  `local.support.ticket.created.v1`); derive it, do not invent a field.
- **`metadata`** is COMPOSED — the non-payload envelope fields (`tenant_id`, `schema_version`) plus the
  audit-record fields from `AuditPayload` (`outcome`, `reason`, `recorded_at`, `task_id`). `payload` is
  the verbatim `original_envelope.payload`.

> Relationship to any concurrent timeline/stream redaction tasks: those keep the *timeline/stream view
> models* from leaking raw payloads at all. The inspector deliberately exposes `payload` / `metadata`
> for the walkthrough, so it needs its OWN field-level redaction (mask configured sensitive keys, default
> ON) — reuse the same sensitive-key whitelist so the two stay consistent.

### Tests for User Story 9 (write first, ensure they FAIL)

- [ ] T900 [P] [US9] Unit test `tests/unit/ui/test_aggregator_raw_event.py`: `build_raw_event(event_id)`
  returns a `RawEventView` populating all nine fields from the matched `AuditPayload` / `original_envelope`;
  `producer_agent_id == original_envelope.agent_id`; `topic == topic_for_event_type(event_type)`;
  `metadata` composes `tenant_id`, `schema_version`, `outcome`, `reason`, `recorded_at`, `task_id` (and
  contains NO domain payload); an unknown `event_id` returns a not-found marker without raising (FR-016);
  a malformed source record degrades honestly rather than crashing.
- [ ] T901 [P] [US9] Unit test `tests/unit/ui/test_raw_event_redaction.py`: `redact_event(view, sensitive_keys)`
  masks every configured sensitive key (default set incl. `customer_id`, `amount`, `email`) wherever it
  appears in `payload` / `metadata`, replacing values with a `"***redacted***"` sentinel; it does not
  mutate the source view; redaction is applied identically to the JSON endpoint and the rendered HTML;
  with redaction off (only when config permits) raw values are revealed; the default is redaction ON.
- [ ] T902 [P] [US9] Route test in `tests/unit/ui/test_routes.py` (FastAPI `TestClient`, aggregator
  monkeypatched): `GET /api/event/{event_id}` returns the redacted `RawEventView` JSON (all nine fields)
  and `GET /event/{event_id}` renders the inspector page; an unknown id renders an explicit "event not
  found" state (HTTP 200, not 5xx); the request performs no publish/write (read-only — spy the publisher,
  assert zero calls, FR-014 / SC-006).

### Implementation for User Story 9

- [ ] T903 [P] [US9] Add a `RawEventView` Pydantic view model to `apps/ui/viewmodels.py` (extends
  data-model.md) with `event_id`, `event_type`, `topic`, `correlation_id`, `causation_id`,
  `producer_agent_id`, `timestamp`, `payload: dict`, `metadata: dict`, and `redacted: bool`; document
  that `topic` is derived and `metadata` is composed.
- [ ] T904 [P] [US9] Implement `apps/ui/redaction.py`: `redact_event(view, sensitive_keys) -> RawEventView`
  (and a `redact_mapping` helper) that recursively masks configured keys in `payload` / `metadata` with
  `"***redacted***"`, never mutating the source, safe on nested/malformed structures; define the default
  sensitive-key set and read overrides from config/env in `server.py`.
- [ ] T905 [US9] Implement `build_raw_event(event_id, *, redacted=True)` in `apps/ui/aggregator.py`: index
  the deduped audit list (from `build_stream`'s `consume_all_audit_records`) by
  `original_envelope.event_id`, map the matched record to `RawEventView` (set `producer_agent_id`,
  `topic = topic_for_event_type(event_type)`, compose `metadata`, copy verbatim `payload`), apply
  `redact_event(...)` when `redacted` is True, and return a not-found marker for unknown ids. Reuse the
  shared `topic_for_event_type` helper (no new Kafka read beyond the existing audit consume).
- [ ] T906 [US9] Add routes to `apps/ui/server.py`: `GET /event/{event_id}` (HTML inspector page) and
  `GET /api/event/{event_id}` (JSON `RawEventView`, redacted by default; honor `?redacted=false` only when
  config permits). Both strictly read-only; guard malformed ids → honest "event not found" state.
- [ ] T907 [P] [US9] Create `apps/ui/templates/raw_event.html` (extends `base.html`) and
  `apps/ui/templates/partials/_raw_event.html`: a labeled view of all nine fields with pretty-printed
  `payload` / `metadata` JSON blocks, a visible redaction indicator, and a **Copy JSON** button (a small
  vendored clipboard helper that copies the exact `/api/event/{event_id}` body) — laid out for a clean
  portfolio walkthrough.
- [ ] T908 [US9] Wire the inspector into the stream: add an "Inspect" affordance per row in
  `apps/ui/templates/partials/_stream_rows.html` (and optionally per step in
  `apps/ui/templates/partials/_timeline.html`) opening `/event/{event_id}` (HTMX-loaded modal or a new
  view) so the raw inspector is reachable in the demo flow without leaving the stream/timeline.
- [ ] T909 [P] [US9] Document the inspector: add `GET /event/{event_id}` + `GET /api/event/{event_id}`
  (with the redaction note and the nine surfaced fields) to
  `specs/007-demo-ui-aggregator/contracts/ui-http-api.md`, and add a "Raw event inspector" subsection to
  `specs/007-demo-ui-aggregator/quickstart.md` (open from a stream row, verify all nine fields, Copy JSON,
  redaction ON by default).

**Checkpoint**: From any stream row a viewer opens the raw event and sees all nine fields, can copy valid
JSON matching `GET /api/event/{event_id}`, and sees sensitive fields redacted by default. Independently
testable; depends only on Phase 2 + the US3 audit read-side.

### Acceptance-criteria mapping

| Requested item | Where satisfied |
|----------------|-----------------|
| Show the nine fields per event | T903 (`RawEventView`) + T905 (mapping/derivation) + T907 (rendering); covered by T900 |
| Useful for GitHub portfolio walkthrough | T907 (clean labeled view) + T908 (reachable from stream/timeline) + T909 (quickstart) |
| Supports copy JSON | T907 (Copy JSON button) + T906 (`/api/event/{event_id}` body it copies); covered by T902 |
| Sensitive fields can be redacted | T904 (`redact_event` + default key set) + T905/T906 (redacted by default); covered by T901 |

---

## Addendum — Focused context: "Add agent health panel" (User Story 7, P1)

> **Added by a `/speckit-tasks` run** invoked with the focused context **"Add agent health panel"**.
> This `tasks.md` is co-authored by several concurrent runs and has thrashed between a FastAPI/`apps/ui`
> and a **Streamlit/`apps/demo_ui`** stack; this addendum targets the **Streamlit/`apps/demo_ui`** body
> that is live in Phase 1 (T001–T003: `streamlit run apps/demo_ui/app.py`). IDs use the **T220–T236**
> band (free at author time). NOTE: a later sibling block also labels itself "User Story 7" — these are
> distinct; this one is the P1 agent-health panel.

**Goal**: A dedicated **Agent Health** panel in the Streamlit demo UI listing the three agents —
`Customer Resolution Agent`, `Billing & Entitlement Agent`, `Risk & Fraud Agent` — each marked
**online / offline** (unknown when unreachable), auto-refreshing, with status read from each agent's
`GET /health` endpoint.

**Scoping decisions (confirmed for this slice)**:
- Billing & Risk get a **new `GET /health`** endpoint added alongside their existing `/ping`.
- The Kafka-only **Customer Resolution agent gets a new minimal HTTP surface** exposing `GET /health`
  (port `8102`), so all three are probed uniformly over `/health`.
- The Streamlit UI probes `/health` only — it never starts, stops, or controls an agent (observe-only).

**Acceptance criteria (from the request)**:
- **AC1** — Status uses each agent's `/health` endpoint (uniform `GET /health` probe).
- **AC2** — The UI does NOT start or control agents (read-only `GET`; no lifecycle calls).
- **AC3** — The UI only observes status (online / offline / unknown derived from the probe).
- **Display** — the three named agents, each with an online/offline indicator.

This is a new **User Story 7 (P1)**. It depends on **Phase 2 (Foundational)** (the `apps/demo_ui` app +
`config.py` from T001–T003) and on the new agent `/health` endpoints below; it is independent of the
other stories and the demo trigger.

### Foundational — agent `/health` endpoints & startup (must precede the panel)

- [ ] T220 [US7] Add `GET /health` to `apps/agents/billing_entitlement/http_app.py` returning `{"status": "ok", "agent_id": _card.agent_id}` (mirror the existing `/ping` handler; keep `/ping` unchanged). Read-only — publishes nothing to Kafka.
- [ ] T221 [US7] Add `GET /health` to `apps/agents/risk_fraud/http_app.py` returning `{"status": "ok", "agent_id": _card.agent_id}` (mirror the existing `/ping` handler; keep `/ping` unchanged). Read-only — publishes nothing to Kafka.
- [ ] T222 [US7] Create `apps/agents/customer_resolution/http_app.py` — a minimal FastAPI app exposing `GET /health` -> `{"status": "ok", "agent_id": AGENT_ID}` (reuse `apps.agents.customer_resolution.config.AGENT_ID = "customer-resolution-agent"`; optionally also serve `GET /.well-known/agent.json` from `a2a_handlers.build_agent_card()` for parity). Add `run()` launching uvicorn on `PORT`/`A2A_ENDPOINT_PORT` default `8102`. Observation-only — performs no Kafka publishing (mirrors the billing/risk `http_app.py` convention).
- [ ] T223 [US7] Register `demo-customer-resolution-http = "apps.agents.customer_resolution.http_app:run"` under `[project.scripts]` in `pyproject.toml` (next to `demo-billing-entitlement-http` / `demo-risk-fraud-http`).
- [ ] T224 [US7] Add `CR_HTTP_PORT=8102` to `scripts/lib/common.sh`; extend `scripts/start-local-system.sh` to launch all three `/health` surfaces so the panel has live data out of the box — billing (`PORT=8101`), risk (`A2A_ENDPOINT_PORT=8103`), and customer-resolution (`PORT=8102 uv run demo-customer-resolution-http`) via the existing `start_agent` helper; update `scripts/stop-local-system.sh` to also `stop_agent "customer-resolution-http"`. Reconcile with any existing `--with-http` / launcher tasks (e.g. Phase 10 T201/T204) rather than duplicating their launch logic.

### Setup — Streamlit UI config & health model

- [ ] T225 [US7] Extend `apps/demo_ui/config.py` (created in T003) with a `/health` registry: map each expected agent id to `(display_name, health_url)`, env-overridable — `customer-resolution-agent` -> "Customer Resolution Agent", default `CR_HEALTH_URL=http://localhost:8102/health`; `billing-entitlement-agent` -> "Billing & Entitlement Agent", default `BILLING_HEALTH_URL=http://localhost:8101/health`; `risk-fraud-agent` -> "Risk & Fraud Agent", default `RISK_HEALTH_URL=http://localhost:8103/health`. Add `HEALTH_PROBE_TIMEOUT_SECONDS` (~1.5). (This adds the previously-absent customer-resolution `/health` surface alongside the existing `:8101/ping` / `:8103/ping` liveness entries.)
- [ ] T226 [P] [US7] Define an `AgentHealth` dataclass in `apps/demo_ui/health.py`: `agent_id: str`, `display_name: str`, `status: Literal["online","offline","unknown"]`, `health_url: str`, `checked_at: datetime | None` (plain dataclass — the Streamlit body uses module-level render functions, not Pydantic view models).

### Tests for User Story 7 (write first, ensure they FAIL)

- [ ] T227 [P] [US7] Unit test the agent `/health` endpoints in `tests/unit/agents/test_health_endpoints.py` (FastAPI `TestClient` against `billing_entitlement.http_app`, `risk_fraud.http_app`, `customer_resolution.http_app`): each `GET /health` returns 200 with `status == "ok"` and the correct `agent_id` (AC1).
- [ ] T228 [P] [US7] Unit test the health prober in `tests/unit/demo_ui/test_health_prober.py` (mock `httpx`): 200 -> `online`; connection error / timeout / non-2xx -> `offline`; assert the prober issues ONLY `GET <health_url>` requests (no POST/PUT/DELETE, no lifecycle/control call) — encodes AC2/AC3; the prober never raises (FR-016).
- [ ] T229 [P] [US7] Render test in `tests/unit/demo_ui/test_health_panel.py` using `streamlit.testing.v1.AppTest` (prober monkeypatched): `get_agent_health()` returns exactly one `AgentHealth` per expected agent with `status in {online, offline, unknown}`; running the app renders an "Agent Health" section naming all three agents with their indicators; a probe failure renders `unknown`/`offline` rather than raising (robustness).

### Implementation for User Story 7

- [ ] T230 [US7] Implement the health prober in `apps/demo_ui/health.py`: a function that, given the T225 registry, issues a `GET` to each agent's `health_url` via `httpx.Client` with the configured timeout, mapping 2xx -> `online` and any error/timeout/non-2xx -> `offline`. It never raises to the caller (FR-016) and performs NO writes or control calls — strictly observational (AC2/AC3).
- [ ] T231 [US7] Add `get_agent_health()` to `apps/demo_ui/health.py` calling the T230 prober for the three expected agents and returning an ordered `list[AgentHealth]` (Customer Resolution, Billing & Entitlement, Risk & Fraud); unreachable agents are included with `status="offline"`/`"unknown"`, never omitted.
- [ ] T232 [US7] Add `render_health_panel()` to `apps/demo_ui/health.py` decorated with `@st.fragment(run_every=REFRESH_SECONDS)` (Streamlit >=1.36, matching the T003 `REFRESH_SECONDS=5`) so the panel auto-refreshes without a full rerun: render each `AgentHealth` as a row with the display name, a status indicator (🟢 online / 🔴 offline / ⚪ unknown), and the last-checked time (FR-012/SC-003).
- [ ] T233 [US7] Wire the panel into `apps/demo_ui/app.py`: call `render_health_panel()` under an "Agent Health" header near the agent roster/cards section so all three agents' online/offline status is visible on the main screen.

### Polish & validation

- [ ] T234 [P] [US7] Read-only guarantee test in `tests/unit/demo_ui/test_health_readonly.py`: rendering the panel and calling `get_agent_health()` issues only `GET` probes to the `/health` URLs and constructs/uses no `Publisher` and no agent-control call (reinforces AC2/AC3 and 007 SC-006).
- [ ] T235 [P] [US7] Integration test in `tests/integration/demo_ui/test_health_panel_end_to_end.py` (`-m integration`, live `/health` surfaces): bring up the three surfaces, assert `get_agent_health()` reports all `online`; stop one surface, assert it flips to `offline` within the refresh interval while the others stay `online` and the agent process is unaffected by the UI.
- [ ] T236 [P] [US7] Document the panel in `specs/007-demo-ui-aggregator/quickstart.md` (an "Agent health panel" section: the three `/health` ports CR 8102 / billing 8101 / risk 8103, the `CR_HEALTH_URL`/`BILLING_HEALTH_URL`/`RISK_HEALTH_URL` overrides, and the online/offline/unknown semantics) and record in `specs/007-demo-ui-aggregator/research.md` the decision to add a uniform `/health` (incl. the new customer-resolution HTTP surface) — superseding R3's `/ping`-only liveness for this panel.

**Checkpoint**: All three agents answer `GET /health`; the Streamlit panel shows the three named agents
online/offline, auto-refreshing, sourced only from `/health`; stopping an agent flips it to offline
without the UI affecting the agent. Independently testable; depends on Phase 2 + the new `/health`
endpoints.

### Acceptance-criteria mapping

| Requested item | Where satisfied |
|----------------|-----------------|
| AC1 — status uses each agent's `/health` endpoint | T220/T221/T222 (uniform `/health` on all three) + T227 (endpoint tests) + T230/T231 (UI probes `/health`) |
| AC2 — UI does not start or control agents | T230 (prober issues only `GET`, no lifecycle call) + T228/T234 (assert only `GET`, zero publish/control) |
| AC3 — UI only observes status | T230/T231 (status derived from probe; never mutates) + T232/T233 (render-only) + T234 (zero-write assertion) |
| Display the three named agents online/offline | T232/T233 (panel rows) + T231 (ordered list of all three) + T229 (render test names all three) |

---

## Addendum — Focused context: "Add A2A task graph view" (User Story 7, P4)

This `/speckit-tasks` run was invoked to add an **A2A task graph view** to the case page: a per-case
**directed graph** of the actual agent-to-agent task invocations recorded in the audit trail —

```text
Customer Resolution Agent
  -> Billing & Entitlement Agent : analyze_refund_eligibility
  -> Risk & Fraud Agent          : assess_fraud_risk
```

— with **failed and timeout task edges visibly marked**. It is distinct from the timeline's inline
decision-node rendering (US6 final-decision panel; US2 orders events causally): US7 is a dedicated,
graph-shaped view (nodes + status-bearing edges + capability labels + a `/case/{id}/graph` page). It is
pure observation — no write, no publisher, no new event contract, topic, or agent (FR-014 / SC-006
preserved). It is sourced entirely from events the UI already reads for the US2 timeline (each domain
event wrapped in an `AuditPayload` on the audit topic, fetched via `query_by_correlation`).

This is **User Story 7 (P4)**. It depends on **Phase 2 (Foundational)** and the **US2 read-side**
(`query_by_correlation` / `trace_case`); it links into US2's `/case/{id}` page. Task IDs start at
**T310** to avoid colliding with the concurrently-authored lower-numbered blocks.

**Acceptance criterion (from request) -> where satisfied:**

| Acceptance criterion | Where satisfied |
|----------------------|-----------------|
| Graph is **derived from audit events** | T314 builds nodes/edges only from recorded `TaskRequest` / `local.resolution.refund-review.requested.v1` and `TaskResult` / result envelopes read via `query_by_correlation` — no separate source, no hidden state |
| UI **does not infer hidden orchestration** | T314 draws an edge ONLY where a real `TaskRequest` exists; `requester`/`target`/`capability` are read from the payload, never assumed or hardcoded (T311 asserts zero requests => zero edges) |
| **Failed/timeout task edges visibly marked** | Edge `status` = `TaskResult.status` (`completed`/`failed`/`rejected`); a request with no matching result (past the Spec 006 reaper timeout) => `status="timeout"`; T316 renders failed/rejected/timeout edges distinctly from completed |

> **Capability labels are derived, not hardcoded.** They come from the recorded `TaskRequest.capability`
> field (today `analyze_refund_eligibility` for billing and `assess_fraud_risk` for risk per
> `apps/agents/customer_resolution/config.py`). The request's `assess_refund_risk` is displayed as
> whatever the audit trail actually recorded, honoring the "derived from audit events" criterion.

### Foundational view models (precede the graph)

- [ ] T310 [P] [US7] Add `TaskGraphNode` (`agent_id`, `display_name: str | None`, `liveness: str | None`), `TaskGraphEdge` (`requester_agent_id`, `target_agent_id`, `capability`, `task_id: UUID`, `status` in {completed,failed,rejected,timeout}, `reason: str | None`), and `TaskGraphView` (`correlation_id`, `nodes: list[TaskGraphNode]`, `edges: list[TaskGraphEdge]`, `found: bool`) Pydantic view models to `apps/ui/viewmodels.py` (extends data-model.md; field names/types documented in T318).

### Tests for User Story 7 (write first, ensure they FAIL)

- [ ] T311 [P] [US7] Unit test `tests/unit/ui/test_aggregator_graph.py`: from fabricated case envelopes (a `local.resolution.refund-review.requested.v1` carrying `billing_task_id`/`risk_task_id`, then `local.billing.refund-analysis.completed.v1` and `local.risk.review.completed.v1` results), `build_task_graph(correlation_id)` yields one `TaskGraphEdge` per recorded request with `requester_agent_id`, `target_agent_id`, and `capability` read from the payload; nodes are derived only from agent ids seen in those payloads; the Customer Resolution node has exactly two outgoing edges (-> billing `analyze_refund_eligibility`, -> risk `assess_fraud_risk`). Assert a case with **zero** request envelopes yields **zero** edges (no inferred orchestration), and `found=False` for an unknown id.
- [ ] T312 [P] [US7] Extend `test_aggregator_graph.py` for edge status (FR-016): a result with `TaskResult.status == "failed"`/`"rejected"` sets the edge `status` and `reason` accordingly; a request with **no** matching result (by `task_id`) sets `status="timeout"`; a `completed` result sets `status="completed"`; malformed/duplicate payloads are skipped/deduped without raising.
- [ ] T313 [P] [US7] Route test in `tests/unit/ui/test_routes.py` (FastAPI `TestClient`, aggregator monkeypatched): `GET /api/case/{cid}/graph` returns `{found, nodes[], edges[]}` with each edge's `status` and `capability`; a case with no A2A tasks returns nodes-only with `edges: []` (never a fabricated edge); an unknown `correlation_id` -> `{"found": false, "nodes": [], "edges": []}` with HTTP 200 (not 5xx); a malformed UUID -> honest empty graph, never 5xx.

### Implementation for User Story 7

- [ ] T314 [US7] In `apps/ui/aggregator.py`, implement `build_task_graph(correlation_id)`: call `query_by_correlation(broker, correlation_id)`, dedup by `event_id`; collect `TaskRequest` payloads (and/or `refund-review.requested` task ids) keyed by `task_id` -> one `TaskGraphEdge` each, with `requester`/`target`/`capability` taken from the payload (never hardcoded); join `TaskResult` payloads by `task_id` for `status` + error `reason`; edges with no matching result -> `status="timeout"` (Spec 006 reaper semantics); derive nodes from the agent ids referenced, enriching `display_name`/`liveness` from `build_roster()`. Draw **no** edge without a recorded request; return `found=False` with empty nodes/edges when the case has no records; never raise on malformed payloads (FR-016). May reuse a `derive_task_graph(entries)` helper alongside the US2 read-side; adds no new contract.
- [ ] T315 [US7] Add routes to `apps/ui/server.py`: `GET /case/{correlation_id}/graph` (HTML page), `GET /api/case/{correlation_id}/graph` (JSON), and `GET /partials/case/{correlation_id}/graph` (HTMX fragment for in-page refresh). Malformed UUID -> honest empty graph, never 5xx (FR-016).
- [ ] T316 [P] [US7] Create `apps/ui/templates/partials/_task_graph.html`: a **server-side** inline-SVG (or HTML/CSS box-and-arrow) directed graph — requester -> target arrows labelled with the `capability`; `failed`/`rejected`/`timeout` edges marked distinctly (color + dashed stroke + a status badge with the `reason`) versus `completed`; render "no A2A tasks recorded for this case" when `edges` is empty. Python-only render — no JS graph library (constitution: Python-exclusive, no JS build).
- [ ] T317 [US7] Add a "Task graph" tab/link in `apps/ui/templates/case.html` pointing at `/case/{correlation_id}/graph` (optionally embedding `/partials/case/{cid}/graph` with an HTMX `every 5s` poll), so the US2 timeline and the A2A graph are reachable for the same case and refresh live.
- [ ] T318 [P] [US7] Document the graph surface: add `GET /case/{cid}/graph` + `GET /api/case/{cid}/graph` to `specs/007-demo-ui-aggregator/contracts/ui-http-api.md`, add `TaskGraphView`/`TaskGraphNode`/`TaskGraphEdge` to `specs/007-demo-ui-aggregator/data-model.md`, and add an "A2A task graph" scenario to `specs/007-demo-ui-aggregator/quickstart.md` (the two expected edges + the failed/timeout marking check).

**Checkpoint**: Opening `/case/{cid}/graph` for a case shows a directed A2A task graph reconstructed
purely from audit events — Customer Resolution -> Billing (`analyze_refund_eligibility`) and -> Risk
(`assess_fraud_risk`) — with failed/timeout edges visibly marked and no edge drawn that was not actually
requested. Independently testable; depends only on Phase 2 + the US2 read-side.

### Acceptance-criteria mapping

| Acceptance criterion | Where satisfied |
|----------------------|-----------------|
| Graph is derived from audit events | T314 (`query_by_correlation` -> requests/results only) + T311 (test) |
| UI does not infer hidden orchestration | T314 (edge only per recorded `TaskRequest`; payload-sourced fields) + T311 (zero requests => zero edges) |
| Failed/timeout task edges visibly marked | T312 (status/timeout test) + T314 (status mapping) + T316 (distinct edge rendering) |

---

## Addendum — Focused context: "Define demo UI config"

This `/speckit-tasks` run was invoked to define the demo UI's **configuration surface** and enforce a
config-driven roster. Provided config:

```
ENVIRONMENT=local
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
CUSTOMER_AGENT_URL=http://localhost:8101
BILLING_AGENT_URL=http://localhost:8102
RISK_AGENT_URL=http://localhost:8103
```

**Acceptance criteria**: **(1)** Agents can be added **by config only**; **(2)** there is **no
hardcoded agent list inside UI logic**.

This supersedes the earlier hardcoded approach: the original Foundational task seeds an
`EXPECTED_AGENT_IDS = (...)` literal tuple in `apps/ui/aggregator.py`, and the US1 liveness task
hardcodes ports (billing `:8101`, risk `:8103`). The tasks below replace those literals with a single
`apps/ui/config.py` from which the expected-agent ids, display names, and agent base URLs are derived —
so adding a fourth agent is an env/config change, never a code change. The resolved port mapping from
**this run's config wins** (customer `8101` / billing `8102` / risk `8103`) and overrides the
references.md / R3 / R9 mapping; regardless, no port or id is hardcoded in UI logic. This addendum
concretizes the partial config tasks (config-driven roster) elsewhere in this file and supplies the base
URLs the HTTP-card fetch and liveness/health probes consume. Task IDs use the **T500** block to avoid
colliding with the concurrently-authored T001–T149 / T200–T204 / T300–T306 blocks.

### Coverage map (acceptance area → where covered)

| Acceptance area | Status | Task(s) |
|-----------------|--------|---------|
| Central config (`ENVIRONMENT`, broker, per-agent URLs) | new | **T500** |
| Roster derived from config, no hardcoded id list (criteria 1+2) | supersedes hardcoded `EXPECTED_AGENT_IDS` | **T501**, **T503** |
| Liveness/health + HTTP-card URLs from config, not hardcoded ports | supersedes hardcoded ports | **T502** |
| "Agent added by config only" verified by test | new test | **T504** |
| Startup passes config env through to `demo-ui` | extends start-script task | **T506** |

### Foundational config module (precedes/supersedes the hardcoded roster)

- [ ] T500 [P] Create `apps/ui/config.py`: a `UIConfig` (pydantic-settings `BaseSettings`) loaded from
  env — `environment` (`ENVIRONMENT`, default `local`), `kafka_bootstrap_servers`
  (`KAFKA_BOOTSTRAP_SERVERS`, default `localhost:9092`, used as the broker url), and an ordered list of
  `AgentConfig(agent_id, display_name, base_url)` resolved from `CUSTOMER_AGENT_URL`/`BILLING_AGENT_URL`/
  `RISK_AGENT_URL` (defaults `http://localhost:8101` / `:8102` / `:8103`). Support adding further agents
  by config alone (e.g. an `AGENT_URLS` map or `<NAME>_AGENT_URL` convention) with **no UI-logic change**.
  Provide `UIConfig.from_env()` and an `expected_agent_ids` property derived solely from the configured
  agents. This module is the single source of truth for the roster; record the resolved port mapping
  (customer 8101 / billing 8102 / risk 8103) in its docstring.
- [ ] T501 Make the roster config-driven in `apps/ui/aggregator.py` (**supersedes the hardcoded
  `EXPECTED_AGENT_IDS` tuple**): delete the literal tuple; have `Aggregator(config: UIConfig)` take the
  config and derive the expected-agent set, display names, and broker url from `config` only.
  `build_roster()` iterates `config.agents`; an announced-but-unexpected discovered agent still surfaces,
  never dropped (FR-004). No agent id, name, or URL literal remains in `aggregator.py`, routes, or
  templates.
- [ ] T502 Drive probes from config in `apps/ui/aggregator.py` (**supersedes the hardcoded `:8101`/`:8103`
  liveness ports**): the `/ping` liveness probe and the `/.well-known/agent-card.json` HTTP-card fetch
  read each agent's `AgentConfig.base_url` from `config`; agents with no health URL resolve to
  `announced`/`not_announced`; failures degrade to `unknown`/`offline`, never raise (R3, FR-016). Wire
  `create_app(config)` / `run()` in `apps/ui/server.py` to build `UIConfig.from_env()` once and inject it
  into the `Aggregator`.

### Tests for the config surface (write first, ensure they FAIL)

- [ ] T503 [P] Unit test `tests/unit/ui/test_config.py`: `UIConfig.from_env()` parses `ENVIRONMENT`,
  `KAFKA_BOOTSTRAP_SERVERS`, and `CUSTOMER_AGENT_URL`/`BILLING_AGENT_URL`/`RISK_AGENT_URL` into the
  ordered `AgentConfig` list with the resolved ports; defaults apply when env is unset. **No-hardcoded-
  list guard**: assert (via source scan / import) that `apps/ui/aggregator.py` contains no agent-id
  string literal and no `EXPECTED_AGENT_IDS` constant — the expected set comes only from `UIConfig`.
- [ ] T504 [P] "Agent added by config only" test in `tests/unit/ui/test_config.py`: given a `UIConfig`
  with a **fourth** `AgentConfig` added (e.g. `FRAUD_REVIEW_AGENT_URL`),
  `Aggregator(config).build_roster()` yields a `RosterEntry` for the new id with
  `announced=False`/`not_announced` health **without any code change**; removing an agent from config
  removes it from the roster. Update the roster tests to seed expected agents through a `UIConfig`
  fixture rather than the deleted module constant.

### Docs & startup wiring

- [ ] T505 [P] Document the config surface: add an "Environment / configuration" section to
  `specs/007-demo-ui-aggregator/quickstart.md` and `apps/ui/README.md` listing `ENVIRONMENT`,
  `KAFKA_BOOTSTRAP_SERVERS`, and the `*_AGENT_URL` variables with the resolved port mapping, noting it
  overrides the references.md / R3 / R9 port references for this UI. State the "agents by config only"
  guarantee explicitly.
- [ ] T506 Pass the config env through in `scripts/start-local-system.sh`: export `ENVIRONMENT`,
  `KAFKA_BOOTSTRAP_SERVERS`, and `CUSTOMER_AGENT_URL`/`BILLING_AGENT_URL`/`RISK_AGENT_URL` into the
  `demo-ui` service launch so the running UI resolves its roster from the same config the agents use;
  confirm overriding a `*_AGENT_URL` at launch is reflected in `/api/roster` without code edits.

**Checkpoint**: The expected-agent roster, display names, broker, and probe/card-fetch base URLs all flow
from `apps/ui/config.py`; T503/T504 prove a new agent appears by config alone and that no agent list is
hardcoded in UI logic (both acceptance criteria satisfied). No new event contract, topic, or agent.

### Acceptance-criteria mapping

| Acceptance criterion | Where satisfied |
|----------------------|-----------------|
| Agents can be added by config only | T500 (`AgentConfig` from env) + T501 (roster iterates config) + T504 (4th-agent test) + T506 (launch override) |
| No hardcoded agent list inside UI logic | T501 (delete `EXPECTED_AGENT_IDS`) + T502 (probe/card URLs from config) + T503 (no-hardcoded-list source-scan guard) |


---

## Addendum — Focused context: "Add documentation" (`docs/demo/`)

This `/speckit-tasks` run was invoked to author four demonstration docs under `docs/demo/`:
`demo-ui.md`, `audit-timeline.md`, `agentcore-local-ui.md`, and `portfolio-walkthrough.md`. These are
**documentation deliverables** (matching the existing `docs/architecture/` style), authored from the
design artifacts (`spec.md`, `plan.md`, `data-model.md`, `contracts/`, `quickstart.md`) and from the
implementation/feature tasks above. They add no event contract, topic, or agent, and produce no source
code. Because `apps/ui/` may not yet be fully implemented, each doc describes the **designed** behavior,
cites the authoritative artifact for each claim, and is flagged for re-verification against the code.
Task IDs start at **T400** to clear the concurrently-authored lower-numbered blocks (T001–T029,
T044/047/049, T090–T094, T100–T111, T120–T126, T136, T500–T169, T200–T204, T300–T306) by a wide margin.

**Docs → primary story / source:**

| Doc (`docs/demo/`) | Primary story | Authoritative sources |
|--------------------|---------------|------------------------|
| `demo-ui.md` | US1 + UI overview | `spec.md` Overview, `plan.md`, `data-model.md`, `contracts/ui-http-api.md` |
| `audit-timeline.md` | US2 (timeline) + US3 (stream) | `contracts/ui-http-api.md` `/api/case` + `/api/stream`, `data-model.md`, `quickstart.md` Sc. 2–3 |
| `agentcore-local-ui.md` | Operational (FR-017) | `quickstart.md`, `scripts/start-local-system.sh`, `apps/agents/*/agentcore/`, T120 (R10 verified ports/paths) |
| `portfolio-walkthrough.md` | Cross-cutting capstone | `quickstart.md` Sc. 1–4, `spec.md` Success Criteria |

### Setup & shared facts (must precede the docs)

- [ ] T400 [P] Create the `docs/demo/` directory with four stub files (`docs/demo/demo-ui.md`,
  `docs/demo/audit-timeline.md`, `docs/demo/agentcore-local-ui.md`, `docs/demo/portfolio-walkthrough.md`),
  each an H1 + one-line purpose, and register them in the docs index `docs/architecture/README.md` under a
  new "Demo & Operations" subsection (match the README's existing link style).
- [ ] T401 [P] Compile/verify the canonical fact set the four docs share — against
  `specs/007-demo-ui-aggregator/contracts/ui-http-api.md` and `data-model.md`: the three expected agent
  ids + capabilities; the UI endpoint table; the topics read (`local.agent.agent-card.published.v1`,
  `local.audit.envelope.recorded.v1`) and the single topic written (`local.support.ticket.created.v1`);
  ports (UI `:8200`, billing `:8101`, risk `:8103`, Redpanda console `:8080`). Reconcile the AgentCore
  port/card-path discrepancy recorded in T120/`contracts/references.md` and reuse T120's verified values
  (research R10) so no doc repeats unverified flags. Capture the result as the "System reference" section
  of `docs/demo/demo-ui.md` (the single source the other three docs link to).

### Documentation deliverables

- [ ] T402 [US1] Write `docs/demo/demo-ui.md` — the Demo UI reference/overview: purpose and read-only
  observer role (no-supervisor / no-central-router guarantee, Observability-First payoff); architecture &
  read-side reuse (`apps/ui/` layout; reuse of `discover_agents`, `query_by_correlation` /
  `consume_all_audit_records`, and `trace_case` so UI == CLI; FastAPI + Jinja2 + HTMX-polling ≤5 s on
  `:8200`) with a Mermaid data-flow diagram from `data-model.md` "Mapping summary"; the agent-roster page
  (`GET /` + `/api/roster`, `RosterEntry`/`CapabilityView`, one entry per expected agent, `announced=false`
  for missing — FR-004, latest-card-only — FR-003, `liveness ∈ {live,unknown,not_announced}` — SC-001);
  and the bounded demo trigger as the only write (`POST /demo/ticket`, single root
  `local.support.ticket.created.v1`, `causation_id=null`, SC-006). Cross-link `agentcore-local-ui.md`
  and `audit-timeline.md`.
- [ ] T403 [US2] Write the "Causal case timeline" half of `docs/demo/audit-timeline.md`:
  `GET /case/{correlation_id}` + `GET /api/case/{correlation_id}`, the `TimelineEntry` fields,
  causation-then-time ordering reused from `trace_case` (UI == CLI, cite `apps/api/trace_case.py`), a
  worked example with a Mermaid causal diagram (`support.ticket.created → customer-issue.classified →
  refund-review.requested → (billing.refund-analysis.completed AND risk.review.completed) →
  customer-resolution.decided`), and edge cases (empty case "no events found" — FR-009; failed/rejected
  `reason` — FR-008; orphan flagged `is_orphan` — FR-016; large case scrollable). Cite FR-005..FR-008,
  SC-002, SC-004 and `quickstart.md` Scenario 2.
- [ ] T404 [US3] Write the "Live audit stream" half of `docs/demo/audit-timeline.md`:
  `GET /stream` + `GET /api/stream` (params `agent`, `event_type`, `correlation_id`, `ticket_id`,
  `limit`), `StreamEvent` fields, newest-first ordering (FR-010), dedup by `event_id` so each event shows
  once (FR-015, SC-005), AND-combined filters that clear back to the full stream (FR-011), live refresh
  ≤5 s (FR-012, SC-003), and row deep-link to `/case/{correlation_id}` (FR-013), with filter examples.
  Link field definitions back to the `demo-ui.md` "System reference" (T401) instead of re-listing them.
  Cite `contracts/ui-http-api.md` `/api/stream` and `quickstart.md` Scenario 3.
- [ ] T405 Write `docs/demo/agentcore-local-ui.md` — running the agents + Demo UI locally, end to end
  (FR-017): prerequisites (`uv sync --extra dev --extra http --extra ui`); the integrated startup
  `bash scripts/start-local-system.sh --with-http` (Redpanda + three agents + UI) with the T401 ports;
  running each agent individually via the AgentCore CLI from `apps/agents/<agent>/agentcore/agentcore.json`
  + `agentcore_app.py` (use the T120-verified commands/ports/card path, with the "verify CLI flags against
  your installed AgentCore version" caveat); the `GET /healthz` UI liveness check; teardown via
  `bash scripts/stop-local-system.sh`; and a troubleshooting list (card not announced, `liveness:unknown`,
  broker unreachable). Cross-link the in-app `/help/agentcore` page (T120–T126) and `quickstart.md`.
- [ ] T406 Write `docs/demo/portfolio-walkthrough.md` — a presenter's narrated walkthrough tying the three
  stories together: a step-by-step script mapped to `quickstart.md` Scenarios 1–4 (open roster & name the
  three agents/capabilities → click "Submit sample refund ticket" / a scenario preset to start a case →
  watch the live stream fill in → open the case timeline and narrate the causal chain to the final
  decision), each step stating what to say and the expected on-screen result; a "Talking points" section
  mapping architectural proof points to success criteria (P2P discovery / no registry; decentralized
  choreography, no supervisor; single bounded write — SC-006; Observability-First — SC-004); and a
  "Before you present" checklist + recovery notes (start per `agentcore-local-ui.md`, confirm all three
  cards announced/`live`, keep a fallback `correlation_id`, what to do on `liveness:unknown`). Reference
  the scenario presets (T100–T111) and link to the other three docs.

### Polish

- [ ] T407 [P] Cross-link + consistency pass across all four `docs/demo/*.md` and the
  `docs/architecture/README.md` index: every cross-link resolves; agent ids, capability names, endpoint
  paths, topic names, and ports match the T401 "System reference" exactly (no drift, no duplicated
  authority); tone/headings/Mermaid usage match `docs/architecture/`; add a header note to each doc —
  "Status: reflects design; re-verify against `apps/ui/` once implemented."

**Checkpoint**: All four `docs/demo/` files exist, are mutually cross-linked, draw their facts from the
single `demo-ui.md` "System reference", and the walkthrough references the other three.

### Dependencies (documentation addendum)

- T400, T401 precede all doc-writing tasks (shared home + canonical facts).
- T401 reuses T120's verified AgentCore ports/card path (research R10) — coordinate with that block.
- T402 (`demo-ui.md`) is a different file from T403/T404 (`audit-timeline.md`) → can run in parallel.
- T403 (timeline) and T404 (stream) edit the **same file** → NOT `[P]`; do T403 then T404.
- T405 (`agentcore-local-ui.md`) is independent of the story docs (different file) → parallelizable after T401.
- T406 (`portfolio-walkthrough.md`) depends on T402–T405 existing (it links to all three).
- T407 (polish) depends on all four docs existing.

### Acceptance-criteria mapping

| Requested doc | Where authored | Verifies |
|---------------|----------------|----------|
| `docs/demo/demo-ui.md` | T400, T401, T402 | US1 (FR-001..004, SC-001), observer role + the only write (SC-006) |
| `docs/demo/audit-timeline.md` | T403 (timeline) + T404 (stream) | US2 (FR-005..009, SC-002/004), US3 (FR-010..013, FR-015, SC-003/005) |
| `docs/demo/agentcore-local-ui.md` | T405 | FR-017 local run; reuses T120 (R10) verified AgentCore details |
| `docs/demo/portfolio-walkthrough.md` | T406 | Cross-cutting capstone over Scenarios 1–4; SC-004 / SC-006 narrative |
