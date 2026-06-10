# Implementation Plan: Demo UI — A2A Card & Audit Aggregator

**Branch**: `007-demo-ui-aggregator` | **Date**: 2026-06-10 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/007-demo-ui-aggregator/spec.md`

> **⚠️ Implementation reconciliation (T029, 2026-06-10).** The feature was **implemented as a
> Streamlit app at `apps/demo_ui/`**, per the tasks.md "Stack override" and a confirmed user
> decision, **not** the FastAPI + Jinja2 + HTMX service at `apps/ui/` that the Technical Context,
> Project Structure, and `contracts/ui-http-api.md` below describe. All design *semantics* are
> preserved — same read-side reuse (`discover_agents`, `query_by_correlation` /
> `consume_all_audit_records`, `trace_case`), same view models, same `event_id` dedup, same
> single-bounded-write trigger, same no-supervisor guarantee. What changed is the delivery mechanism:
> Streamlit sidebar nav + `?view=&case=` query-param deep-links replace HTTP routes; auto-refresh
> replaces HTMX polling; view models live inside their owning modules instead of `viewmodels.py`.
> The authoritative usage docs for the shipped UI are [quickstart.md](./quickstart.md) and
> [apps/demo_ui/README.md](../../apps/demo_ui/README.md). The sections below are retained as the
> original design record; `contracts/ui-http-api.md` no longer applies as written.

## Summary

Build a read-only, single-screen demo dashboard that makes the decentralized refund-ops system
observable without code inspection or broker tailing. It aggregates the three peer agents'
self-published **Agent Cards** (roster + capabilities + liveness), renders a **causal case timeline**
for any `correlation_id`, and shows a **live audit stream** across all cases with agent/type/case
filters. The UI is an observer: its only write is a single, clearly-bounded **demo trigger** that
publishes a root `support.ticket.created` domain event (the same root event the existing
`apps/api/dev_publish_ticket.py` CLI emits) so a presenter can start a case from the screen. It never
publishes A2A task requests, never routes work, and contains no orchestration logic — the
no-supervisor / no-central-router guarantee is preserved.

**Technical approach**: A small FastAPI app (`apps/ui/`) reusing the existing foundation read-side —
`runtime.discovery.discover_agents`, `audit.store.query_by_correlation` / `consume_all_audit_records`,
and `customer_resolution.trace.trace_case` for causal ordering — so the UI and the existing
`trace_case.py` CLI tell the identical story. Pages are server-rendered with Jinja2 and refreshed by
HTMX polling (≤5 s interval) to meet the "live" success criterion without a hard real-time channel.
The app is launched as a fourth service by `scripts/start-local-system.sh`.

## Technical Context

**Language/Version**: Python 3.12 (constitution: Python is the exclusive language — no JS/TS build step; HTMX is a vendored static script, not a Python dependency).

**Primary Dependencies**: FastAPI ≥0.111 + uvicorn[standard] ≥0.30 (already present in the `http` extra), Jinja2 ≥3.1 (NEW — server-side templates), `httpx` ≥0.27 (already present; used to probe agent `/ping` for liveness). Reuses `agent_foundation` (aiokafka, pydantic, structlog).

**Storage**: None of its own. Source of truth is the existing Kafka topics — `local.agent.agent-card.published.v1` (compacted, discovery) and `local.audit.envelope.recorded.v1` (compacted, audit). The UI may hold a short-lived in-process cache of the last poll only; it persists nothing.

**Testing**: pytest 8 + pytest-asyncio (unit, with fabricated `AgentCard` / `AuditPayload` / `EventEnvelope` fixtures); `testcontainers[kafka]` integration test driving one case end-to-end and asserting the rendered timeline matches `trace_case`. FastAPI `TestClient` for endpoint/route tests.

**Target Platform**: Local single-node demo (Linux/WSL + Docker Redpanda). Modern browser for the viewer. No deployment beyond local.

**Project Type**: Web application — Python backend (FastAPI) + server-rendered HTML/HTMX frontend, added as `apps/ui/` alongside the existing agent apps.

**Performance Goals**: Roster + stream refresh visible within ≤5 s (SC-003); first-time viewer identifies all three agents + capabilities in ≤30 s (SC-001). A large case (hundreds of events) renders in a scrollable view without freezing.

**Constraints**: Strictly observational with respect to agent coordination (FR-014, SC-006) — the single permitted write is a root `support.ticket.created` event. Deduplicate audit events by `event_id` (FR-015). Never crash on malformed / late / duplicate / orphaned events (FR-016). Reuse existing causal-ordering semantics (causation-then-time) so UI == CLI.

**Scale/Scope**: A handful of concurrent viewers; three known agents; demo-volume cases. No auth, multi-tenant isolation, or production hardening (out of scope per Principle V).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Assessment | Status |
|-----------|------------|--------|
| **I. Agent Autonomy** | The UI is not an agent and performs no coordination. The bounded demo trigger publishes a **root domain event** (`support.ticket.created`), identical to the existing `dev_publish_ticket.py` tool — it is intake, not task delegation, routing, or supervision. Agents still discover and delegate autonomously. | PASS (see Complexity Tracking) |
| **II. Event-Driven Coordination** | UI reads exclusively from Kafka (discovery + audit topics); the one write is a root event on Kafka. No agent is invoked directly; no back-channel introduced. | PASS |
| **III. Idempotency & Safety** | UI is read-mostly and side-effect-free except the trigger. Each trigger mints a fresh `correlation_id`/`event_id` (a distinct new case — intended semantics, no duplicate side effects). Display deduplicates by `event_id` (FR-015). | PASS |
| **IV. Observability-First** | This feature *is* the Observability-First payoff: it makes the audit trail end-to-end readable without code inspection (SC-004). | PASS — directly advances |
| **V. PoC Scope Discipline** | One small FastAPI app, server-rendered, polling; maximal reuse of existing read-side helpers; one new dependency (Jinja2). The single write path is the only deviation from the spec's strict read-only stance and is justified below. | PASS |

**Result**: PASS. One documented deviation (bounded demo trigger) recorded in Complexity Tracking. Re-evaluated post-design: still PASS — no contract, topic, or agent was added; the UI consumes existing contracts and emits only the pre-existing `support.ticket.created` root event.

## Project Structure

### Documentation (this feature)

```text
specs/007-demo-ui-aggregator/
├── plan.md              # This file (/speckit-plan output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (UI HTTP contract + references)
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
apps/ui/                         # NEW — the demo UI app (read-only observer + bounded trigger)
├── __init__.py
├── server.py                    # FastAPI app factory + run(): routes wire aggregator → templates
├── aggregator.py                # Read-side: roster (discover + announce-time + liveness), case
│                                #   timeline (delegates to trace_case), audit stream (dedup+filter)
├── viewmodels.py                # Pydantic view models: RosterEntry, TimelineView, StreamView, etc.
├── demo_trigger.py              # The ONLY write: publish a root support.ticket.created envelope
│                                #   (thin reuse of apps/api/dev_publish_ticket.py logic)
├── templates/                   # Jinja2 server-rendered pages + HTMX partials
│   ├── base.html
│   ├── roster.html              # Story 1
│   ├── case.html                # Story 2 (timeline)
│   ├── stream.html              # Story 3 (live feed + filters)
│   └── partials/                # _roster_cards.html, _timeline.html, _stream_rows.html
└── static/
    ├── htmx.min.js              # vendored (no network at runtime, no JS build)
    └── styles.css

apps/api/
└── dev_publish_ticket.py        # EXISTING — demo_trigger.py reuses its publish helper

src/agent_foundation/            # EXISTING — reused read-side, unchanged
├── runtime/discovery.py         #   discover_agents()
├── audit/store.py               #   query_by_correlation(), consume_all_audit_records()
└── ...
apps/agents/customer_resolution/
└── trace.py                     # EXISTING — trace_case() reused for causal ordering, unchanged

tests/
├── unit/ui/                     # NEW — aggregator dedup/filter/ordering, viewmodels, demo_trigger
│   ├── test_aggregator_roster.py
│   ├── test_aggregator_timeline.py
│   ├── test_aggregator_stream.py
│   └── test_routes.py           # FastAPI TestClient: routes, empty states, read-only assertion
└── integration/ui/              # NEW — testcontainers: one case end-to-end → rendered timeline == trace_case
    └── test_ui_end_to_end.py

scripts/start-local-system.sh    # EXISTING — extended to launch demo-ui (PORT 8200) as 4th service
pyproject.toml                   # EXISTING — add `ui` optional extra + `demo-ui` console script
```

**Structure Decision**: Web application laid out as a new `apps/ui/` package, mirroring the existing
`apps/agents/*/http_app.py` FastAPI convention. The UI's read-side delegates entirely to existing
`agent_foundation` helpers and `trace_case`; it adds no new event contract, no new Kafka topic, and no
new agent. The lone write (`demo_trigger.py`) reuses the existing `dev_publish_ticket.py` publish path.

## Complexity Tracking

> Filled because the Constitution Check records one justified deviation.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|--------------------------------------|
| **Bounded demo trigger** (UI publishes a root `support.ticket.created` event — a deviation from spec.md FR-014's strict read-only stance). | Explicitly requested for the portfolio demo so a presenter can start a case from the screen ("submit sample refund tickets"). It is the **only** write and emits a pre-existing root domain event — no task-request, routing, or orchestration — so the no-supervisor guarantee holds. spec.md FR-014 updated to carve out this single exception. | "Stay strictly read-only, inject via the CLI" rejected: forces the presenter to context-switch to a terminal mid-demo, undermining the single-screen observability story. The trigger reuses existing publish code, adding no new contract or coupling. |
| **New dependency: Jinja2 ≥3.1** | Server-side HTML rendering keeps the UI Python-only (constitution: Python is the exclusive language) with no JS build toolchain. FastAPI + uvicorn + httpx are already in the `http` extra. | Hand-built string templating rejected (error-prone, unsafe escaping); a JS/TS SPA rejected (violates Python-exclusive language constraint and adds a build step against Principle V). HTMX is a vendored static file, not a package. |

## Phase 0 — Research

See [research.md](./research.md). Resolves: liveness signal per agent (HTTP `/ping` for billing/risk vs.
Kafka-only customer-resolution → card-presence + last-announced), audit polling strategy and dedup,
causal-ordering reuse, refresh mechanism (HTMX polling), and the bounded-trigger boundary.

## Phase 1 — Design & Contracts

- [data-model.md](./data-model.md): view models (RosterEntry/Capability, TimelineEntry/TimelineView,
  StreamEvent/StreamView, DemoTriggerRequest/Result) mapped to existing `AgentCard`, `AuditPayload`,
  `EventEnvelope`, and `TraceStep`.
- [contracts/](./contracts/): the UI HTTP API (read endpoints + the single demo-trigger POST), plus
  references to the existing AgentCard and AuditPayload contracts (not duplicated).
- [quickstart.md](./quickstart.md): runnable validation scenarios proving Stories 1–3 and SC-001..006.
