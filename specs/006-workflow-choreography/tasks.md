---
description: "Task list for Decentralized Workflow & Event Choreography (006)"
---

# Tasks: Decentralized Workflow & Event Choreography

**Input**: Design documents from `/specs/006-workflow-choreography/`

**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅ (choreography, timeout-and-failure-paths, replay-and-trace, decision-rule), quickstart.md ✅

**Tests**: INCLUDED — the spec explicitly requires them (FR-016 automated replay tests; FR-021/SC-009 automated architecture test; quickstart §A end-to-end suite). Test tasks are written before the implementation they cover.

**Organization**: Tasks are grouped by user story (US1–US5) so each story is an independently testable increment. This feature is **integration & choreography over the existing 003/004/005 agents** — no new event contract, no new topic, no new dependency. Genuinely-new code is small (a reaper, a store query, two config knobs, a replay harness, a trace tool); most "implementation" tasks verify/wire reused components.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1, US2, US3, US4, US5 (maps to spec user stories)
- All paths are repository-root-relative

## End-to-End Workflow Contract (the choreography this feature wires)

The single source of truth is `contracts/choreography.md`. Causation flows top-to-bottom; all events
share one `correlation_id` (the case id), minted at the ticket and propagated unchanged:

```
support.ticket.created.v1                 (dev intake → resolution)         [root, causation=null]
  → resolution.customer-issue.classified.v1   (resolution)                  triage marker
  → A2A task.requested → billing-entitlement-agent   (resolution → billing) endpoint topic
  → A2A task.requested → risk-fraud-agent            (resolution → risk)     endpoint topic
  → resolution.refund-review.requested.v1     (resolution)                  delegation marker
  → billing.refund-analysis.completed.v1  (billing → resolution)   ─┐ async, any order,
  → risk.review.completed.v1              (risk → resolution)       ┘ correlated by task_id
  → customer.resolution.decided.v1            (resolution)         exactly one terminal decision
  → resolution.customer-response.drafted.v1   (resolution)         human-readable response
  → case closed   |   case escalated          (terminal lifecycle)
       └ audit.envelope.recorded.v1 emitted at every step (trace tool reconstructs the journey)
```

Failure/timeout edges (`contracts/timeout-and-failure-paths.md`): missing opinion past deadline →
`escalate_human`/`analysis_timeout` (reaper); failed/rejected peer → `escalate_human`/`peer_failure`;
eligible+high-risk → `escalate_human`; ineligible+high-risk → `deny_refund` + separate risk flag;
malformed ticket → `escalate_human`/`malformed_ticket`; late opinion after terminal → recorded, ignored.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Branch hygiene and the two additive config knobs the choreography needs.

- [X] T001 Confirm work is on branch `006-workflow-choreography` and verify `pyproject.toml` introduces **no new third-party dependency** (Constitution Principle V; plan "no new dependency"). File: `pyproject.toml`
- [X] T002 [P] Add `CASE_DEADLINE_SECONDS` (default `15`) and `REAPER_TICK_SECONDS` (default `1.0`) config constants with `AGENT_*` env overrides, distinct from the existing `DELEGATION_TIMEOUT_SECONDS`, in `apps/agents/customer_resolution/config.py` (data-model D2)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The reaper-facing store query, deadline rooting, and the shared multi-agent test harness that every integration test depends on.

**⚠️ CRITICAL**: No user-story integration test can run until T006 (harness) exists; the reaper (US3) cannot be built until T003 (store query) exists.

- [X] T003 Add `async def list_timed_out_cases(self, now: datetime) -> list[ResolutionCase]` to the `CaseStateStore` Protocol and implement it in `InMemoryCaseStateStore` — returns non-terminal cases where `deadline_at is not None`, `now > deadline_at`, and `pending_tasks` is non-empty, executed under the existing `asyncio.Lock` (no `ResolutionCase` schema change). File: `apps/agents/customer_resolution/state_store.py` (data-model D1)
- [X] T004 [P] Unit test for `list_timed_out_cases` covering the three filters (non-terminal status, past-deadline, pending-tasks non-empty) and the under-lock behaviour, in `apps/agents/customer_resolution/tests/test_state_store.py`
- [X] T005 Wire `intake_handler` to root the case deadline as `case.deadline_at = now + CASE_DEADLINE_SECONDS` so the reaper has a bound to enforce (FR-017), in `apps/agents/customer_resolution/event_handlers.py`
- [X] T006 Build the shared end-to-end fixture that starts the **real** billing, risk, and resolution agents in-process over a `testcontainers[kafka]` single broker, with sub-second `CASE_DEADLINE_SECONDS`/`REAPER_TICK_SECONDS` overrides and per-test unique consumer groups, following the existing `test_demo_agents_*.py` pattern, in `tests/integration/conftest.py`

**Checkpoint**: Config + store query + deadline rooting + multi-agent harness ready — user stories can begin.

---

## Phase 2A: Workflow Scenario Fixtures (Foundational Test Data)

**Purpose**: Build the reusable, deterministic scenario fixtures that the US1–US4 integration/replay
tests (T007–T026) consume so each test declares *what* it expects, not *how* to construct it. Each
fixture is pure Python data — no `datetime.now()`, no `random()`, no `uuid()` at module import (mirrors
the determinism rule in `apps/agents/risk_fraud/mock_data.py` / `billing_entitlement/mock_data.py`, FR-016
replay determinism). Every fixture exposes the five components requested: `support_ticket`,
`mock_billing_profile`, `mock_risk_profile`, `expected_events`, `expected_final_state`.

> **ID note**: These tasks were added after the original T001–T034 list and are numbered T035+ to avoid
> renumbering existing IDs other work may reference. **Logically they are foundational**: T035–T047 are
> prerequisites for the integration/replay tests T007–T026 and should be completed alongside / right after
> Phase 2. The Dependencies section records this.

**Reference data already shipped (reuse, don't reinvent)**:
- `support_ticket` → `SupportTicketCreatedPayload` (`packages/contracts/events/payloads.py`): `ticket_id`,
  `customer_id`, `amount`, `currency`, `reason`, `created_at`.
- `mock_billing_profile` → a `BillingFacts` (`apps/agents/billing_entitlement/models.py`) the harness seeds
  under the ticket's lookup key so the **real** billing agent returns a deterministic
  `BillingRefundAnalysisCompletedPayload`. Existing seed verdicts to mirror: `PR-APPROVE` (eligible, full),
  `PR-HEAVY-USAGE` (partial), `PR-WINDOW-EXPIRED`/`PR-UNPAID`/`PR-ALREADY-REFUNDED` (deny).
- `mock_risk_profile` → a `RiskSignals` (`apps/agents/risk_fraud/models.py`) seeded under the same
  `customer_id` so the real risk agent returns a deterministic `RiskReviewCompletedPayload`. Existing seed
  verdicts to mirror: `CUS-CLEAN` (low), `CUS-BLOCKLIST`/`CUS-CHARGEBACKS` (high), `CUS-VELOCITY` (elevated).
- `expected_events` → ordered topic/payload steps per `contracts/choreography.md` (steps 1–7 + audit).
- `expected_final_state` → terminal `CaseStatus` + `ResolutionOutcome` + `escalation_reason` per
  `contracts/timeout-and-failure-paths.md` and `contracts/decision-rule.md`.

### Fixture scaffolding (blocking prerequisites for the 9 scenarios)

- [X] T035 Create the fixtures package: `tests/integration/fixtures/__init__.py` and
  `tests/integration/fixtures/workflow_scenarios/__init__.py` (empty registry stub for now)
- [X] T036 Define the fixture schema as frozen dataclasses/Pydantic models in
  `tests/integration/fixtures/workflow_scenarios/schema.py`: `ExpectedEvent{topic, payload_type,
  caused_by (the prior step it must cite), notes}`; `ExpectedFinalState{case_status: CaseStatus,
  outcome: ResolutionOutcome | None, escalation_reason: str | None, risk_flag_emitted: bool = False,
  expects_decision: bool = True, eligible_refund_amount: Decimal | None = None}`; and
  `WorkflowScenario{name, support_ticket, mock_billing_profile, mock_risk_profile, expected_events,
  expected_final_state}` where a `SILENT` sentinel is an allowed value for a peer profile (no response →
  timeout path)
- [X] T037 Implement shared builders in `tests/integration/fixtures/workflow_scenarios/builders.py`:
  `make_support_ticket(customer_id, *, amount, currency, reason, ticket_id=None, created_at=FIXED_TS)`
  using a module-level `FIXED_TS` (no wall-clock at import); `instantiate(scenario, correlation_id)` to
  mint a fresh per-run case id so the same fixture can be reused for the ≥10 concurrent cases in US2/T013;
  a `SILENT` sentinel; and `expected_event(topic_const, payload_type, caused_by=...)` resolving topics via
  `packages/contracts/topics.py`

### The 9 scenario fixtures (each `[P]` — separate module, no shared mutable state)

- [X] T038 [P] [US1] `happy_path_full_refund` in
  `tests/integration/fixtures/workflow_scenarios/happy_path_full_refund.py`: refund ticket ("charged
  twice"); billing profile mirroring `PR-APPROVE` (eligible, within window, `eligible_refund_amount ==
  amount`); risk profile mirroring `CUS-CLEAN` (low); `expected_events` = ticket → classified → billing &
  risk `task.requested` → refund-review.requested → billing & risk `*.completed` → `decided(approve_refund)`
  → drafted (+ audit at each); `expected_final_state` = `CaseStatus.CLOSED`,
  `ResolutionOutcome.APPROVE_REFUND`, `escalation_reason=None`
- [X] T039 [P] [US1] `partial_refund` in
  `tests/integration/fixtures/workflow_scenarios/partial_refund.py`: refund ticket; billing profile
  mirroring `PR-HEAVY-USAGE` (**partial**: eligible but `eligible_refund_amount < amount`); risk `CUS-CLEAN`
  (low); `expected_events` as happy path; `expected_final_state` = `CaseStatus.CLOSED`,
  `ResolutionOutcome.OFFER_PARTIAL_CREDIT`, `escalation_reason=None`, with `eligible_refund_amount` equal to
  the partial amount the billing profile reports (assert against the existing `decision_engine` — this is
  decision-rule Row 6: `partial` + `low` risk → `offer_partial_credit`). Backs the partial-refund golden
  E2E test (T101).
- [X] T040 [P] [US1] `billing_denied` in
  `tests/integration/fixtures/workflow_scenarios/billing_denied.py`: refund ticket; billing profile
  mirroring `PR-WINDOW-EXPIRED` (ineligible, RP-001); risk `CUS-CLEAN` (low); `expected_events` as happy
  path; `expected_final_state` = `CaseStatus.CLOSED`, `ResolutionOutcome.DENY_REFUND`, `escalation_reason=
  None`, with the billing denial reason expected in `billing_summary`/`customer_response` **⚠️ CORRECTION (see T232)**: `ineligible`+`low` is decision-rule Row 8 (`escalate_human`/`conflicting_analyses`), **not** `deny_refund`; for a genuine `deny_refund` this fixture's `mock_risk_profile` must be `elevated`/`high` (Row 5).
- [X] T041 [P] [US3] `high_risk_escalation` in
  `tests/integration/fixtures/workflow_scenarios/high_risk_escalation.py`: refund ticket; billing profile
  mirroring `PR-APPROVE` (eligible); risk profile mirroring `CUS-BLOCKLIST` / `CUS-CHARGEBACKS` (high);
  `expected_events` = both opinions arrive then `decided(escalate_human)`; `expected_final_state` =
  `CaseStatus.ESCALATED`, `ResolutionOutcome.ESCALATE_HUMAN`, `escalation_reason ∈
  {conflicting_analyses, elevated_risk}` (eligible + high risk conflict, FR-010)
- [X] T042 [P] [US3] `billing_timeout` in
  `tests/integration/fixtures/workflow_scenarios/billing_timeout.py`: refund ticket;
  `mock_billing_profile = SILENT` (billing peer never responds); risk profile mirroring `CUS-CLEAN`
  (responds); `expected_events` = ticket → classified → both `task.requested` → refund-review.requested →
  **risk** `*.completed` only (no billing result) → `decided(escalate_human)` caused by the reaper sweep;
  `expected_final_state` = `CaseStatus.ESCALATED`, `ResolutionOutcome.ESCALATE_HUMAN`,
  `escalation_reason="analysis_timeout"` (FR-017, SC-004)
- [X] T043 [P] [US3] `risk_timeout` in
  `tests/integration/fixtures/workflow_scenarios/risk_timeout.py`: mirror of T042 with the silent peer
  flipped — billing profile mirroring `PR-APPROVE` (responds), `mock_risk_profile = SILENT`;
  `expected_events` include the **billing** result only; `expected_final_state` = `CaseStatus.ESCALATED`,
  `ResolutionOutcome.ESCALATE_HUMAN`, `escalation_reason="analysis_timeout"`
- [X] T044 [P] [US4] `duplicate_ticket_event` in
  `tests/integration/fixtures/workflow_scenarios/duplicate_ticket_event.py`: happy-path billing/risk
  profiles, but the `support.ticket.created` event is marked for **double delivery** (add a
  `redeliver: list[str]` hint on the scenario or a per-event `deliver_times=2`); `expected_final_state` =
  `CaseStatus.CLOSED`, `ResolutionOutcome.APPROVE_REFUND`; `expected_events` assert **exactly one**
  classified, one billing/risk `task.requested` pair, and one `decided` (idempotency: the redelivery emits
  an audit `duplicate_skipped`, FR-011/FR-013, SC-006)
- [X] T045 [P] [US4] `duplicate_peer_result_event` in
  `tests/integration/fixtures/workflow_scenarios/duplicate_peer_result_event.py`: happy-path profiles, but
  the `billing.refund-analysis.completed` result is delivered twice (same `task_id`);
  `expected_final_state` = `CaseStatus.CLOSED`, `ResolutionOutcome.APPROVE_REFUND`; `expected_events`
  assert the result is applied once and exactly one `decided` is emitted; repeated `task_id` returns the
  stored result without re-running analysis (FR-012, SC-006)
- [X] T046 [P] [US4] `unknown_case_result` in
  `tests/integration/fixtures/workflow_scenarios/unknown_case_result.py`: **no** preceding ticket — a lone
  `billing.refund-analysis.completed` (or `risk.review.completed`) result whose `correlation_id` matches no
  open case; `mock_billing_profile`/`mock_risk_profile` describe only the orphan result payload;
  `expected_events` = the orphan result + an audit record showing it was recorded-but-ignored;
  `expected_final_state` = `expects_decision=False`, no case created, no `decided` event (late/orphan result
  recorded not applied, FR-019)
- [X] T047 Populate the registry in `tests/integration/fixtures/workflow_scenarios/__init__.py`:
  `ALL_SCENARIOS: dict[str, WorkflowScenario]` importing all nine modules, a `get_scenario(name)` accessor,
  and a module-level assertion that the nine expected names are present and unique

### Fixture validation (test the test-data)

- [X] T048 [P] Fixture self-validation test in `tests/integration/test_workflow_fixtures.py` (no broker):
  for every scenario assert it is well-formed — the five components are populated; `expected_final_state`
  is internally consistent with the profiles (e.g. `SILENT` peer ⇒ `escalation_reason="analysis_timeout"`;
  eligible+high-risk ⇒ `ESCALATE_HUMAN`); a `decided`-bearing `expected_events` list ⇔
  `expects_decision=True`; payloads validate against their Pydantic models; and `ALL_SCENARIOS` has exactly
  the nine requested names
- [ ] T049 Refactor the US1/US3/US4 integration & replay tests (T007–T009, T017–T020, T024–T026) to consume
  the fixtures via `get_scenario(...)` / `instantiate(...)` — seed each scenario's `mock_billing_profile`
  and `mock_risk_profile` into the real billing/risk agents' in-memory stores in the harness, drive
  `support_ticket`, and assert `expected_events` + `expected_final_state`, in
  `tests/integration/test_workflow_choreography.py` (and `tests/integration/conftest.py` for the seeding seam)

**Checkpoint**: All nine workflow scenario fixtures exist, validate, and back the integration/replay
suite — tests now declare intent and stay DRY across US1–US4.

---

## Phase 2B: Reusable Workflow Test Harness (`packages/testing/workflow_harness.py`)

**Purpose**: Build the **reusable, Kafka+A2A-only** driver that every choreography test uses to interact
with the running agents as a black box — publish a ticket, wait for and collect events by
`correlation_id`, assert the terminal case state, and assert event-ordering constraints. This is distinct
from the in-process agent fixture (T006, `conftest.py`, which *starts* the agents) and from the replay
harness (T027, which re-feeds recorded events): this harness is the **client-side interaction layer** that
enforces the acceptance criteria below for the US1–US5 integration tests.

**Acceptance criteria (from the feature request)**:
1. Tests do **not** call internal agent methods directly — no access to `ResolutionService`,
   `InMemoryCaseStateStore`, `decision_engine`, or any agent-internal object.
2. Tests interact through **Kafka and A2A only** — published events (`Publisher`), consumed events
   (`Consumer`/audit topic), and, where a single agent's capability is exercised directly, the A2A
   `runtime.A2AClient`.
3. The harness is **reusable for future agents** — its collect/wait/assert primitives are parametrized by
   the watched topic set, the root-event factory, and the terminal-event type, with the resolution
   workflow as the default configuration.

> **ID note**: Numbered T090+ to preserve existing IDs (same convention as Phase 2A). Logically this is
> **foundational** — T098 wires the US1–US5 integration tests onto this harness, so T090–T097 are
> prerequisites for those tests (T007–T009, T012–T014, T017–T020, T024–T026, T028). Recorded in Dependencies.

**Reuse (don't reinvent)**: `Publisher.publish(payload, event_type, correlation_id, causation_id=...)` and
`Consumer.subscribe([...])` / `seek_to_beginning()` / `run(handler, stop_event)`
(`src/agent_foundation/transport/`); topic constants + `topic_for`/`endpoint_topic`
(`packages/contracts/topics.py`); `EventEnvelope` (`correlation_id`, `causation_id`, `event_id`,
`event_type`, `payload`); `query_by_correlation(broker, correlation_id)`
(`src/agent_foundation/audit/store.py`); `SupportTicketCreatedPayload` /
`CustomerResponseDecisionPayload` (`packages/contracts/events/payloads.py`); the Phase 2A
`ExpectedEvent` / `ExpectedFinalState` schema (`tests/integration/fixtures/workflow_scenarios/schema.py`).
`packages` is already a wheel package (`pyproject.toml`), so `packages.testing` imports with parity to
`packages.contracts`.

- [X] T090 Scaffold the harness package: create `packages/testing/__init__.py` and
  `packages/testing/workflow_harness.py` with a `WorkflowHarness` class shell — async context-manager
  lifecycle (`__aenter__`/`__aexit__` that opens a `Publisher` and starts/stops a background collector
  `Consumer`) and fully-typed public method stubs with docstrings (`publish_ticket`, `wait_for_events`,
  `collect_events`, `wait_for_decision`, `assert_final_state`, `assert_causal_order`,
  `assert_event_before`) — no logic yet. Confirm `from packages.testing.workflow_harness import
  WorkflowHarness` imports (parity with `packages.contracts`). Files: `packages/testing/__init__.py`,
  `packages/testing/workflow_harness.py`
- [X] T091 Implement the **background event collector** in `packages/testing/workflow_harness.py`: a
  `Consumer` on a per-instance **unique** `group_id` subscribed to the configurable workflow topic set
  (default: choreography steps 1–7 — `support.ticket.created`, `TOPIC_ISSUE_CLASSIFIED`,
  `endpoint_topic(billing)`/`endpoint_topic(risk)`, `TOPIC_REFUND_REVIEW_REQUESTED`,
  `TOPIC_BILLING_RESULT`, `TOPIC_RISK_RESULT`, `TOPIC_TASK_RESULT`, `TOPIC_RESOLUTION_DECIDED`,
  `TOPIC_RESPONSE_DRAFTED`, `TOPIC_AUDIT`, all resolved via `packages/contracts/topics.py`), buffering each
  `EventEnvelope` into an in-memory index keyed by `correlation_id` and preserving Kafka offset + timestamp
  for ordering. Kafka-only; touches no agent internals (acceptance #1/#2)
- [X] T092 Implement `async def publish_ticket(self, *, customer_id, amount, currency, reason,
  ticket_id=None, correlation_id=None) -> UUID` in `packages/testing/workflow_harness.py`: build a
  `SupportTicketCreatedPayload`, mint (or accept) the `correlation_id`, and publish the root
  `support.ticket.created.v1` event through the harness `Publisher` with `causation_id=None` (mirroring
  `apps/api/dev_publish_ticket.py`); return the `correlation_id`. The single Kafka entry point that roots a
  case (responsibility: *publish initial support ticket*)
- [X] T093 Implement `async def wait_for_events(self, correlation_id, expected, *, timeout) ->
  list[EventEnvelope]` and `def collect_events(self, correlation_id) -> list[EventEnvelope]` in
  `packages/testing/workflow_harness.py`: `wait_for_events` polls the collector index until every expected
  event type (or Phase 2A `ExpectedEvent`) for the `correlation_id` is observed or `timeout` elapses,
  raising a descriptive `TimeoutError` naming the still-missing event types; `collect_events` returns the
  buffered, offset-ordered envelopes for a `correlation_id`. Add `async def wait_for_decision(self,
  correlation_id, *, timeout) -> CustomerResponseDecisionPayload` as a convenience over the
  `TOPIC_RESOLUTION_DECIDED` event (responsibilities: *wait for expected events* + *collect events by
  correlation id*)
- [X] T094 Implement `def assert_final_state(self, correlation_id, expected_final_state)` in
  `packages/testing/workflow_harness.py`: assert the terminal case state **purely from observed
  events/audit** — exactly one `customer.resolution.decided` event whose `CustomerResponseDecisionPayload`
  matches the expected `ResolutionOutcome` and `escalation_reason`, the presence of `customer-response.drafted`
  for non-escalated terminals, and the separate risk-flag event when `risk_flag_emitted` is expected —
  reading payloads off Kafka, never from the resolution store. Accepts the Phase 2A `ExpectedFinalState`
  (responsibility: *assert final case state*; enforces acceptance #1)
- [X] T095 Implement the ordering assertions in `packages/testing/workflow_harness.py`:
  `def assert_causal_order(self, correlation_id)` — every non-root observed event's `causation_id` resolves
  to an earlier-observed event for the case and the root is the ticket with `causation_id is None` (uses
  the collector's offset/timestamp for tie-breaking, mirroring the trace tool's causation rules); and
  `def assert_event_before(self, correlation_id, earlier_event_type, later_event_type)` — asserts the
  first occurrence of `earlier` precedes `later` by Kafka offset (responsibility: *assert event ordering
  constraints where required*)
- [X] T096 Make the harness **agent-agnostic** in `packages/testing/workflow_harness.py`: parametrize via
  constructor args the watched topic set, the root-event factory (event_type + payload builder), and the
  terminal-event type/payload model — defaulting to the resolution workflow — so a future agent workflow
  reuses `publish_*`/`wait_for_events`/`collect_events`/ordering without resolution-specific coupling; add
  an optional `async def request_capability(self, target_agent_id, capability, payload, *, timeout) ->
  TaskResult` helper over `agent_foundation.runtime.A2AClient` to exercise a single agent's capability
  directly via **A2A** (acceptance #2/#3); document the extension seam in the module docstring
- [X] T097 [P] Harness unit test in `tests/unit/test_workflow_harness.py` (no broker — feed synthetic
  `EventEnvelope`s into the collector index via a fake/in-memory transport seam): proves `collect_events`
  buckets strictly by `correlation_id` (no cross-case bleed), `wait_for_events` resolves when all expected
  types arrive and raises a missing-types `TimeoutError` otherwise, `assert_causal_order` catches a broken
  causation chain, and `assert_final_state` reads the decided event — validating harness logic without a
  live Kafka broker (under `tests/unit/` so it is collected per `pyproject.toml` `testpaths`)
- [ ] T098 Wire the US1–US5 integration tests (T007–T009, T012–T014, T017–T020, T024–T026, T028) onto the
  harness: expose a `workflow_harness` fixture in `tests/integration/conftest.py` (constructed against the
  testcontainers broker from T006) and refactor the scenarios in
  `tests/integration/test_workflow_choreography.py` to drive each case via `WorkflowHarness.publish_ticket`
  → `wait_for_events` → `assert_final_state` / `assert_causal_order` — so every integration test interacts
  with the agents through **Kafka + A2A only**, calling no internal agent method (acceptance #1/#2)

**Checkpoint**: A reusable, black-box `WorkflowHarness` publishes tickets, collects events by correlation
id, and asserts terminal state + ordering through Kafka/A2A only — every choreography test now drives the
agents without touching their internals, and the primitives carry over to future agents.

---

## Phase 2C: Audit Timeline Builder (`packages/testing/audit_timeline.py`)

**Purpose**: Build a reusable, **read-only** timeline builder that reconstructs a single case's ordered,
human-readable journey **from Kafka events alone, keyed by one `correlation_id`**, and emits both (a) the
numbered text rendering in the request's example and (b) a structured/JSON form that the **Spec 007 demo
UI** consumes. This is the **presentation/serialization** layer over the same audit/event data — distinct
from the US5 trace tool (T029/T030, an operator CLI that prints causal `TraceStep`s over `agent.audit.v1`)
and from the Phase 2B `WorkflowHarness` collector (T091, the test-interaction layer): the builder reuses
their collection + causal-ordering primitives and reshapes the result for a UI feed. It adds **no** agent
code and **no** new contract/topic/dependency (Constitution Principle V) and directs no agent
(Principle I) — it only reads recorded events.

**Acceptance criteria (from the request)**:
1. **Timeline is built from Kafka events** → the builder consumes recorded envelopes (the `agent.audit.v1`
   topic `TOPIC_AUDIT`, and/or the domain step topics) via the existing transport; it never reads any
   agent's in-process case store (FR-022).
2. **Timeline uses correlation ID** → the sole input that scopes a timeline is one `correlation_id` (the
   case id); every entry shares it and no cross-case event leaks in (FR-005/FR-023, SC-005).
3. **Timeline can feed the Spec 007 demo UI** → besides the numbered text `render()`, the builder exposes a
   stable, JSON-serializable `to_dict()`/`to_json()` (ordered list of typed entries) suitable for a UI to
   render without re-deriving order or re-reading Kafka.

> **ID note**: Numbered **T110+** to clear the existing max (`T101`) and the concurrently-added duplicate
> band (`T080`–`T082`), per the parallel-writers convention used by Phases 2A/2B. **Logically these are an
> observability deliverable for US5** (reconstruct a case from one id) and a forward feed for Spec 007;
> tagged `[US5]`. Recorded in Dependencies.
>
> **Event-name reconciliation** (request label → existing topic/state, `contracts/choreography.md` +
> `packages/contracts/topics.py`):
> `support.ticket.created` → `support.ticket.created.v1`;
> `resolution.customer-issue.classified` → `TOPIC_ISSUE_CLASSIFIED`;
> `audit.agent-task.requested <agent>` → the A2A `task.requested` events to `endpoint_topic("billing-entitlement-agent")` /
> `endpoint_topic("risk-fraud-agent")` (a.k.a. their `agent.audit.v1` request records), each **labelled with its
> target agent id** as in the example;
> `billing.refund-analysis.completed` → `TOPIC_BILLING_RESULT`;
> `risk.review.completed` → `TOPIC_RISK_RESULT`;
> `resolution.customer-resolution.decided` → `TOPIC_RESOLUTION_DECIDED` (`customer.resolution.decided.v1`);
> `resolution.customer-response.drafted` → `TOPIC_RESPONSE_DRAFTED`;
> `resolution.case.closed` → the terminal **case state** `CaseStatus.CLOSED`, **NOT** a Kafka event — it is
> **synthesized** as the closing timeline entry from the terminal lifecycle (decided/drafted) observed in
> the audit trail; **no `case.closed` topic exists or is added** (Principle V, "no new topic").

**Reuse (don't reinvent)**: `query_by_correlation(broker, correlation_id)`
(`src/agent_foundation/audit/store.py`) and/or `Consumer.subscribe([...])` + `seek_to_beginning()`
(`src/agent_foundation/transport/consumer.py`) for collection; `EventEnvelope`
(`correlation_id`, `causation_id`, `event_id`, `event_type`, `agent_id`, `payload`, timestamp); the US5
causal-ordering rule (T029 — `event_id → causation_id` map, root at `support.ticket.created`
`causation_id is None`, topo-order with timestamp/offset tie-break); topic constants + `endpoint_topic`
(`packages/contracts/topics.py`). `packages` is already a wheel package, so `from packages.testing.audit_timeline
import AuditTimelineBuilder` imports with parity to `packages.contracts`/`packages.testing.workflow_harness`.

- [X] T110 [P] [US5] Scaffold `packages/testing/audit_timeline.py`: define a JSON-serializable
  `TimelineEntry` model (frozen Pydantic/dataclass) — `{seq: int, event_type: str, label: str, actor: str
  (producer `agent_id`), target_agent: str | None, correlation_id: UUID, causation_id: UUID | None,
  task_id: UUID | None, timestamp: datetime, summary: str}` — plus a `LABEL_MAP`/`reconcile_label(envelope)`
  implementing the event-name reconciliation table above (including the per-target-agent labelling of the
  two `task.requested` steps), and an `AuditTimelineBuilder` class shell with fully-typed method stubs and
  docstrings (`collect`, `build`, `render`, `to_dict`, `to_json`) — no logic yet. Confirm `from
  packages.testing.audit_timeline import AuditTimelineBuilder` imports. File: `packages/testing/audit_timeline.py`
- [X] T111 [US5] Implement event collection in `packages/testing/audit_timeline.py`: `async def
  collect(self, correlation_id: UUID) -> list[EventEnvelope]` that gathers **only** the envelopes for that
  `correlation_id` from Kafka via `query_by_correlation` (audit-topic-backed) and/or a `Consumer` seeked to
  the beginning of the workflow + audit topics, filtering strictly by `correlation_id` so no cross-case
  event is included (acceptance #1/#2, FR-022/FR-023). File: `packages/testing/audit_timeline.py`
- [X] T112 [US5] Implement `build(self, correlation_id) -> list[TimelineEntry]` in
  `packages/testing/audit_timeline.py`: causally order the collected envelopes using the US5 rule (T029) —
  root at `support.ticket.created` (`causation_id is None`), topologically order by causation with
  timestamp-then-offset tie-break — assign sequential `seq` starting at 1, map each to a `TimelineEntry`
  via `reconcile_label`, and **append the synthetic `resolution.case.closed` terminal entry** derived from
  the terminal lifecycle (decided + drafted ⇒ closed; escalated ⇒ an `escalated` terminal entry instead),
  never from a fabricated topic (Principle V). File: `packages/testing/audit_timeline.py`
- [X] T113 [US5] Implement the two output surfaces in `packages/testing/audit_timeline.py`: `def
  render(self, entries) -> str` producing the numbered, human-readable list exactly matching the request's
  example shape (e.g. `3. audit.agent-task.requested billing-entitlement-agent`); and `def to_dict(self,
  entries) -> dict` / `def to_json(self, entries) -> str` emitting a stable, ordered, JSON-serializable
  structure (each entry's full `TimelineEntry` fields) shaped as the **Spec 007 demo UI feed** (acceptance
  #3) — documented as the UI contract in the module docstring. File: `packages/testing/audit_timeline.py`
- [X] T114 [P] [US5] Unit test (no broker) in `tests/unit/test_audit_timeline.py`: feed a synthetic,
  out-of-order set of `EventEnvelope`s for one case (ticket → classified → both `task.requested` → both
  `*.completed` → decided → drafted) plus an unrelated second case's events into the builder's ordering
  seam; assert `build()` returns exactly the nine ordered entries of the example (with the two
  `task.requested` entries labelled `billing-entitlement-agent` / `risk-fraud-agent` and the synthetic
  `resolution.case.closed` last), that cross-case events are excluded (acceptance #2), that `render()`
  reproduces the numbered example text, and that `to_json()` round-trips to the ordered structure
  (acceptance #3). File: `tests/unit/test_audit_timeline.py`
- [X] T115 [P] [US5] Integration test (live broker) in `tests/integration/test_audit_timeline.py`: drive
  the `happy_path_full_refund` scenario end-to-end via the Phase 2B `WorkflowHarness` (T038/T098), then
  build the timeline from Kafka by `correlation_id` alone and assert the rendered sequence equals the
  nine-step example (`support.ticket.created` → `resolution.customer-issue.classified` → two
  `audit.agent-task.requested <agent>` → `billing.refund-analysis.completed` → `risk.review.completed` →
  `resolution.customer-resolution.decided` → `resolution.customer-response.drafted` →
  `resolution.case.closed`), and that `to_dict()` is JSON-serializable for the Spec 007 UI. **Depends on**:
  T110–T113 (builder), T006 (multi-agent harness), T038 (fixture), T098 (`WorkflowHarness`). (US5 AC1,
  FR-022/FR-023, SC-005). File: `tests/integration/test_audit_timeline.py`

**Checkpoint**: From one `correlation_id`, the read-only `AuditTimelineBuilder` reconstructs a case's
nine-step ordered journey from Kafka events and renders it both as the numbered example text and as a
JSON feed ready for the Spec 007 demo UI — no agent internals touched, no new topic/contract/dependency.

---

## Phase 3: User Story 1 - A refund ticket becomes an automated decision (Priority: P1) 🎯 MVP

**Goal**: A `support.ticket.created` event drives the full happy path — triage → dual delegation → aggregation → exactly one terminal decision (`approve_refund` / `deny_refund` / `offer_partial_credit`, or `direct_response` for non-refund) with explanation and a complete audit trail — with no human in the loop.

**Independent Test**: Submit one eligible, low-risk refund ticket and confirm a terminal `approve_refund` decided event with explanation and an audit trail linking back to the originating ticket, with zero manual intervention.

### Tests for User Story 1 ⚠️ (write first; must fail before implementation)

- [X] T007 [P] [US1] Integration test: eligible + low-risk ticket → terminal `approve_refund` decided event with customer-facing explanation and a causal audit trail from ticket to decision (US1 AC1, SC-001), in `tests/integration/test_workflow_choreography.py`
- [X] T008 [P] [US1] Integration test: ineligible ticket → `deny_refund` with the billing reason reflected in the explanation (US1 AC2), in `tests/integration/test_workflow_choreography.py` **⚠️ CORRECTION (see T232)**: a genuine `deny_refund` requires `ineligible` + risk `elevated`/`high` (decision-rule Row 5); `ineligible` + `low` is a Row 8 conflict → `escalate_human`/`conflicting_analyses`. This task's inputs must use `elevated`/`high` risk.
- [X] T009 [P] [US1] Integration test: non-refund ticket → `direct_response` with billing and risk capabilities **never invoked** (US1 AC3, FR-002), in `tests/integration/test_workflow_choreography.py`

### Full happy-path golden E2E test (added per request) ⚠️

> **ID note**: Added after the existing T001–T098 list; numbered T100+ to preserve IDs other work
> references. This is the explicit, end-to-end "golden path" assertion the request asks for (customer
> requests refund → billing eligible full refund → risk low → `approve_refund`). It **reuses** the
> `happy_path_full_refund` fixture (T038) and the black-box `WorkflowHarness` (Phase 2B); it adds **no**
> agent code and **no** new contract/topic/dependency (Constitution V). It is a sharper, sequence-exact
> superset of T007 — keep both: T007 stays the AC1 smoke; T100 pins the exact terminal event order.
>
> **Event-name reconciliation** (request → existing choreography, `contracts/choreography.md`):
> `resolution.customer-resolution.decided` → `customer.resolution.decided.v1` (`TOPIC_RESOLUTION_DECIDED`);
> `resolution.customer-response.drafted` → `resolution.customer-response.drafted.v1` (`TOPIC_RESPONSE_DRAFTED`);
> `resolution.case.closed` → the terminal **case state** `CaseStatus.CLOSED`, **NOT** a Kafka event — no
> `case.closed` topic exists or is added (Principle V, "no new topic"). The test asserts the two emitted
> lifecycle events **plus** the closed terminal state observed from events/audit, never a fabricated topic.

- [X] T100 [P] [US1] Full happy-path golden E2E test in `tests/integration/test_workflow_choreography.py`:
  seed the `happy_path_full_refund` fixture (T038) — a refund-request ticket, billing profile mirroring
  `PR-APPROVE` (eligible, **full** refund, `eligible_refund_amount == amount`), risk profile mirroring
  `CUS-CLEAN` (low) — into the real billing/risk agents via the harness; `harness.publish_ticket(...)` the
  refund ticket; then assert end-to-end through **Kafka only** (no internal agent method): (1) exactly one
  `TOPIC_RESOLUTION_DECIDED` event whose `CustomerResponseDecisionPayload.outcome ==
  ResolutionOutcome.APPROVE_REFUND` and `escalation_reason is None`; (2) exactly one following
  `TOPIC_RESPONSE_DRAFTED` event caused by the decided event; (3) the case reaches terminal
  `CaseStatus.CLOSED` asserted from observed events/audit per the reconciliation note above (no `case.closed`
  topic); (4) `assert_event_before(TOPIC_RESOLUTION_DECIDED, TOPIC_RESPONSE_DRAFTED)` and
  `assert_causal_order(correlation_id)` hold across the full chain (ticket → classified → both
  `task.requested` → refund-review.requested → both `*.completed` → decided → drafted), and the billing &
  risk capabilities were each invoked exactly once. **Depends on**: T038 (fixture), T006 (multi-agent
  harness), T098/T093–T095 (`WorkflowHarness` publish/wait/assert primitives). (US1 AC1, FR-001/FR-002/FR-008/FR-010, SC-001, decision-rule Row 4)

### Partial-refund golden E2E test (added per request) ⚠️

> **ID note**: Added after the existing T001–T100 list; numbered T101 to preserve IDs other work
> references (same convention as T100). This is the explicit, end-to-end partial-eligibility assertion the
> request asks for (customer requests refund → billing **partial** eligibility → risk **low or medium**
> → `offer_partial_credit`). It is the sibling of T100 (full-refund golden path) for **decision-rule Row 6**
> and reuses the `partial_refund` fixture (T039) and the black-box `WorkflowHarness` (Phase 2B); it adds
> **no** agent code and **no** new contract/topic/dependency (Constitution V).
>
> **Risk-band reconciliation** (request → existing risk vocabulary, 005 + `contracts/decision-rule.md`):
> the request's "low or medium risk" maps to the risk agent's bands `low` / `elevated` (there is no
> `medium` level; `elevated` is the middle band). Row 6 holds for **both** `low` and `elevated` — so the
> test is parametrized over both and asserts the same `offer_partial_credit` outcome for each. `high` risk
> is **out of scope** here (it conflicts with eligibility → escalation, covered by T019/T041).
>
> **Event-name reconciliation**: identical to T100 — `customer.resolution.decided.v1`
> (`TOPIC_RESOLUTION_DECIDED`), `resolution.customer-response.drafted.v1` (`TOPIC_RESPONSE_DRAFTED`), and the
> terminal `CaseStatus.CLOSED` **state** (no `case.closed` topic exists or is added, Principle V).

- [X] T101 [P] [US1] Partial-refund golden E2E test in `tests/integration/test_workflow_choreography.py`,
  **parametrized over risk band `[low, elevated]`**: seed the `partial_refund` fixture (T039) — a
  refund-request ticket and a billing profile mirroring `PR-HEAVY-USAGE` (**partial**: eligible with
  `eligible_refund_amount < amount`) — into the real billing/risk agents via the harness, overriding the
  seeded `mock_risk_profile` to the parametrized band (a `CUS-CLEAN`-style **low** profile and an
  `elevated`-band profile mirroring the 005 risk agent's middle tier); `harness.publish_ticket(...)` the
  refund ticket; then assert end-to-end through **Kafka only** (no internal agent method): (1) exactly one
  `TOPIC_RESOLUTION_DECIDED` event whose `CustomerResponseDecisionPayload.outcome ==
  ResolutionOutcome.OFFER_PARTIAL_CREDIT`, `escalation_reason is None`, and whose offered/eligible amount
  equals the billing profile's partial `eligible_refund_amount` (and is `< amount`); (2) exactly one
  following `TOPIC_RESPONSE_DRAFTED` event caused by the decided event, with a customer-facing explanation
  reflecting the partial credit; (3) the case reaches terminal `CaseStatus.CLOSED` asserted from observed
  events/audit (no `case.closed` topic); (4) `assert_event_before(TOPIC_RESOLUTION_DECIDED,
  TOPIC_RESPONSE_DRAFTED)` and `assert_causal_order(correlation_id)` hold across the full chain (ticket →
  classified → both `task.requested` → refund-review.requested → both `*.completed` → decided → drafted),
  and the billing & risk capabilities were each invoked exactly once. **Depends on**: T039 (fixture), T006
  (multi-agent harness), T098/T093–T095 (`WorkflowHarness` publish/wait/assert primitives). (US1 AC1,
  FR-010, SC-007, decision-rule Row 6)

### High-risk escalation golden E2E test (added per request) ⚠️

> **ID note**: Added after the existing T001–T101 list; numbered T102 to preserve IDs other work
> references (same convention as T100/T101). This is the explicit, end-to-end **escalation** assertion
> the request asks for (customer requests refund → billing **eligible** → risk **high** →
> `escalate_human`). It is the sibling of T100 (full-refund approve) and T101 (partial-refund credit) for
> the **conflict/escalation** path, reuses the `high_risk_escalation` fixture (T041) and the black-box
> `WorkflowHarness` (Phase 2B), and adds **no** agent code and **no** new contract/topic/dependency
> (Constitution V).
>
> **Decision/outcome reconciliation** (request → existing vocabulary): the request's `escalate_to_human`
> maps to `ResolutionOutcome.ESCALATE_HUMAN` (constant value `"escalate_human"`, defined in
> `packages/contracts/events/payloads.py`); there is no `escalate_to_human` identifier in the codebase.
>
> **Final-event reconciliation**: the request's `resolution.case.escalated` maps to the terminal **case
> state** `CaseStatus.ESCALATED`, asserted from observed events/audit — **not** a Kafka topic. No
> `resolution.case.escalated` / `case.escalated` topic exists or is added (Principle V, "no new topic"),
> mirroring the `case.closed` reconciliation note above T100. The terminal **events on the wire** are
> `customer.resolution.decided.v1` (`TOPIC_RESOLUTION_DECIDED`, `outcome == escalate_human`) followed by
> `resolution.customer-response.drafted.v1` (`TOPIC_RESPONSE_DRAFTED`, `requires_human_approval == True`):
> `_emit_decision_and_draft` drafts for **all** terminals, escalation included
> (`apps/agents/customer_resolution/event_handlers.py`). (This supersedes the earlier
> "`customer-response.drafted` for non-escalated terminals" aside near the assertion-helper task — the
> live handler drafts on escalation too.)
>
> **Escalation-reason reconciliation**: eligible+high resolves through one of two real code paths
> depending on arrival — the **risk-result fast path** escalates the moment the `high` risk result
> arrives with reason `elevated_risk` (`event_handlers.py` high-risk branch), while the full-aggregation
> path yields decision-rule **Row 8** `conflicting_analyses`. The test asserts `escalation_reason ∈
> {elevated_risk, conflicting_analyses}` (matching fixture T041), with `elevated_risk` the expected value
> when the fast path fires first.

- [X] T102 [P] [US3] High-risk escalation golden E2E test in
  `tests/integration/test_workflow_choreography.py`: seed the `high_risk_escalation` fixture (T041) — a
  refund-request ticket, a billing profile mirroring an **eligible** customer (e.g. `PR-APPROVE`), and a
  risk profile mirroring a **high**-risk customer (005's high band) — into the real billing/risk agents
  via the harness; `harness.publish_ticket(...)` the refund ticket; then assert end-to-end through
  **Kafka only** (no internal agent method): (1) exactly one `TOPIC_RESOLUTION_DECIDED` event whose
  `CustomerResponseDecisionPayload.outcome == ResolutionOutcome.ESCALATE_HUMAN` and `escalation_reason ∈
  {elevated_risk, conflicting_analyses}`; (2) exactly one following `TOPIC_RESPONSE_DRAFTED` event caused
  by the decided event with `requires_human_approval == True`; (3) the case reaches terminal
  `CaseStatus.ESCALATED` asserted from observed events/audit (no `case.escalated` topic); (4) the refund
  is **not** auto-approved (no `approve_refund` decided event ever appears for the case), the risk
  capability was invoked, and `assert_event_before(TOPIC_RESOLUTION_DECIDED, TOPIC_RESPONSE_DRAFTED)` plus
  `assert_causal_order(correlation_id)` hold across the chain (ticket → classified → both `task.requested`
  → refund-review.requested → at least the risk `*.completed` → decided → drafted; the billing
  `*.completed` need not precede escalation when the fast path fires first). **Depends on**: T041
  (fixture), T006 (multi-agent harness), T098/T093–T095 (`WorkflowHarness` publish/wait/assert
  primitives). (US3 AC3, FR-010, SC-007, decision-rule Row 8 / risk-result fast path)

### Implementation for User Story 1

- [X] T010 [US1] Verify/wire `ResolutionService.serve()` concurrently gathers the runtime, intake, result, billing-result, and risk-result loops so a ticket flows ticket → classified → dual A2A delegation → aggregation → `customer.resolution.decided` → `customer-response.drafted`; fix any wiring gaps in `apps/agents/customer_resolution/agent.py`
- [X] T011 [US1] Verify the choreography topology against `contracts/choreography.md`: emitters/consumers and topic constants for steps 1–7 resolve correctly via `packages/contracts/topics.py` (and `dev_publish_ticket.py` publishes the root ticket on `support.ticket.created.v1`); reconcile any constant mismatch in `packages/contracts/topics.py`

**Checkpoint**: A single ticket produces a justified terminal decision end-to-end — MVP is demonstrable.

---

## Phase 4: User Story 2 - Correlated, async aggregation of independent opinions (Priority: P2)

**Goal**: Billing and risk opinions arrive independently, in any order; the resolution stage holds each case open until both belong-to-the-same-case opinions are present, then combines exactly those two — never mixing opinions across concurrent cases.

**Independent Test**: Run ≥10 refund cases concurrently with billing/risk results delivered in shuffled order; confirm every case's decision combines exactly its own two opinions and no others.

### Tests for User Story 2 ⚠️

- [X] T012 [P] [US2] Integration test: risk result arrives **before** billing result → case still produces the correct decision once both are present (arrival order irrelevant) (US2 AC1), in `tests/integration/test_workflow_choreography.py`
- [X] T013 [P] [US2] Integration test: ≥10 concurrent cases with interleaved/shuffled results across the shared result stream → each decision is composed of only its own two correlation-matched opinions (US2 AC2, SC-002), in `tests/integration/test_workflow_choreography.py`
- [X] T014 [P] [US2] Integration test: a decided case's audit trail links both contributing opinions and the originating ticket via the single shared `correlation_id` (US2 AC3, FR-005/FR-007), in `tests/integration/test_workflow_choreography.py`

### Implementation for User Story 2

- [ ] T015 [US2] Verify per-case attribution holds under concurrency: results matched by `correlation_id` + slot, no cross-case bleed in the billing/risk/result handlers (`apps/agents/customer_resolution/event_handlers.py`), and `task_id = uuid5(correlation_id, capability)` is stable per (case, capability) in `apps/agents/customer_resolution/a2a_handlers.py`; close any gap found

**Checkpoint**: Out-of-order, interleaved, many-in-flight aggregation is provably correct — the flow is genuinely decentralized, not a disguised synchronous chain.

---

## Phase 5: User Story 3 - Deterministic failure paths (Priority: P2)

**Goal**: Every failure mode resolves a case to a bounded, documented terminal state — never hanging, never deciding unsafely. This phase introduces the only meaningful new agent logic: the **timeout reaper**.

**Independent Test**: For each failure mode (no response within deadline, rejected/failed request, conflicting high-risk opinion, malformed ticket) drive a case and confirm it reaches its documented terminal outcome with the reason recorded and no case left open.

### Tests for User Story 3 ⚠️

- [X] T016 [P] [US3] Reaper unit tests (injected clock, no Kafka): a non-terminal past-deadline case escalates with `escalate_human`/`analysis_timeout`; an already-`DECIDED` case is skipped under the guard; escalation occurs within `deadline + ≤ REAPER_TICK_SECONDS`, in `apps/agents/customer_resolution/tests/test_reaper.py`
- [X] T017 [P] [US3] Integration test: a peer stays silent past `CASE_DEADLINE_SECONDS` → reaper escalates the case (`analysis_timeout`), case is not left open (US3 AC1, FR-017, SC-004), in `tests/integration/test_workflow_choreography.py`
- [X] T018 [P] [US3] Integration test: a peer returns a `failed`/`rejected` TaskResult → `escalate_human` with reason `peer_failure` (US3 AC2, FR-018, SC-007), in `tests/integration/test_workflow_choreography.py`
- [X] T019 [P] [US3] Integration test: eligible + high risk (conflict) → `escalate_human`; ineligible + high risk → `deny_refund` **plus** a separate risk/escalation flag that does not change the deny outcome (US3 AC3/AC4, FR-010/FR-024, SC-007), in `tests/integration/test_workflow_choreography.py`
- [X] T020 [P] [US3] Integration test: malformed/un-triageable ticket → escalation (never silently dropped, FR-020); and a late opinion arriving **after** terminal is recorded in audit but does not flip/duplicate the decision (Edge case, FR-019), in `tests/integration/test_workflow_choreography.py`

### Implementation for User Story 3

- [X] T021 [US3] Implement the timeout reaper in new file `apps/agents/customer_resolution/reaper.py`: loop every `REAPER_TICK_SECONDS` until a stop event; query `store.list_timed_out_cases(now)`; for each, re-check the `DECIDED`/terminal guard, build `TimeoutStatus(any_missing=True, deadline_exceeded=True, missing_reviews=…)` via the existing `build_timeout_status`, and resolve through the existing `_apply_decision` path (→ `escalate_human`/`analysis_timeout`); accept an injectable `now: Callable[[], datetime]` defaulting to `lambda: datetime.now(UTC)` (data-model D2, timeout contract)
- [X] T022 [US3] Add the reaper as a 5th concurrently-gathered task in `ResolutionService.serve()` with graceful stop-event shutdown, in `apps/agents/customer_resolution/agent.py`
- [X] T023 [US3] Verify failure-path handlers map to the documented `escalation_reason`s per `contracts/timeout-and-failure-paths.md` — `mark_slot_failed` → `peer_failure`, peer-undiscoverable intake branch → `peer_failure`, malformed-ticket validation → `malformed_ticket`, conflict rows → `conflicting_analyses`/`elevated_risk` — across `apps/agents/customer_resolution/event_handlers.py` and `apps/agents/customer_resolution/decision_engine.py`; close any gap found

**Checkpoint**: All failure modes terminate deterministically and boundedly; no case can hang.

---

## Phase 6: User Story 4 - Idempotent, replay-safe processing (Priority: P3)

**Goal**: Re-delivery of identical events causes no duplicate side effects, and replaying a recorded scenario reproduces the identical decision with zero extra side-effect events.

**Independent Test**: Process a recorded refund-case stream once, capture the decision and emitted-event set; replay from the beginning and confirm the decision is identical and no additional side-effect events were produced.

### Tests for User Story 4 ⚠️

- [X] T024 [P] [US4] Integration test: re-deliver the complete event set for an already-decided case → zero duplicate opinions/requests/decisions; a repeated `task_id` returns the stored result without re-running analysis (US4 AC1/AC3, FR-011/FR-012/FR-013, SC-006), asserted via audit `duplicate_skipped` outcomes, in `tests/integration/test_workflow_choreography.py`
- [X] T025 [P] [US4] Replay test: replay a recorded end-to-end scenario from the beginning → re-derived `customer.resolution.decided` payload (outcome + explanation) **equals** the original and exactly one decided event exists (US4 AC2, FR-014/FR-015, SC-003), in `tests/integration/test_workflow_choreography.py`
- [X] T026 [P] [US4] Replay test: replaying a partially-completed stream reproduces the same in-flight state and yields **no** spurious decision (reaper neutralized for completed-run replay) (Edge case), in `tests/integration/test_workflow_choreography.py`

### Implementation for User Story 4

- [ ] T027 [US4] Implement the replay harness: re-feed recorded input events (ticket + peer results) into a **fresh** `ResolutionService` with a fresh `InMemoryCaseStateStore`, using `Consumer.seek_to_beginning()` on uniquely-named consumer groups (offsets at zero, empty `IdempotencyTracker`) and the reaper disabled / given an effectively-infinite deadline, per `contracts/replay-and-trace.md`; place as `tests/integration/replay_harness.py` (reusable by T024–T026)

### Duplicate-event acceptance criteria (explicit per-event coverage) ⚠️

> Targeted, handler-level duplicate-handling proofs for the four named event types and the three
> acceptance criteria from the request. These complement the broader US4 work: T024 (re-deliver full set),
> T044 (`duplicate_ticket_event` fixture), and T045 (`duplicate_peer_result_event`/billing fixture) — these
> tasks add the **missing risk-result and decided-event duplicate coverage** plus fast unit-level guards
> (no broker), and map each acceptance criterion to a concrete assertion. The three idempotency layers
> already exist (event-level `IdempotencyTracker` via `idempotent=True` consumers; task-level stable
> `uuid5` `task_id` + `apply_result` → `AttachOutcome.DUPLICATE`; case-level `DECIDED`/terminal guard), so
> most of these are verify/regression-guard tasks; keep any change additive (Constitution V).

**Event → handler → acceptance-criterion map** (topic constants in `packages/contracts/topics.py`):
`support.ticket.created` → `intake_handler` → **AC1** (no duplicate peer tasks);
`billing.refund-analysis.completed` (`TOPIC_BILLING_RESULT`) & `risk.review.completed` (`TOPIC_RISK_RESULT`)
→ `billing_result_handler`/`risk_result_handler` → **AC2** (no decision change);
`customer.resolution.decided` (`TOPIC_RESOLUTION_DECIDED`) → `_apply_decision`/`_emit_decision_and_draft`
→ **AC3** (case not closed twice).

- [ ] T116 [P] [US4] **AC1** unit (no broker): in `apps/agents/customer_resolution/tests/test_duplicate_intake.py`, call `intake_handler` twice for the same ticket (both same-`event_id` and same-`correlation_id`/new-`event_id`) against one shared `InMemoryCaseStateStore`; assert exactly two `agent.task_request.v1` publishes total, the second pass writes an `agent.audit.v1` `duplicate_skipped` (`event_handlers.py:290`), `delegate` runs once, and `case.billing_task_id`/`case.risk_task_id` are unchanged stable `uuid5` values — "duplicate support ticket does not create duplicate peer tasks"
- [ ] T117 [P] [US4] **AC2** unit (no broker, billing): in `apps/agents/customer_resolution/tests/test_duplicate_results.py`, drive a case to a decision, then redeliver the `billing.refund-analysis.completed` result; assert `billing_result_handler` emits no second decision (`count(TOPIC_RESOLUTION_DECIDED) == 1`), `store.apply_result` returns `AttachOutcome.DUPLICATE` for the absent-from-`pending_tasks`/terminal cases (`state_store.py:210-225`), and a `write_task_audit` DUPLICATE/`duplicate_skipped` record is produced — "duplicate peer result does not change final decision"
- [ ] T118 [P] [US4] **AC2** unit (no broker, **risk — the gap T045 omits**): in the same `test_duplicate_results.py`, redeliver a `risk.review.completed` result, covering BOTH the normal-aggregation path and the high-risk-escalation branch (`event_handlers.py:631-655`); assert a duplicate high-risk result arriving after the case is `ESCALATED` is short-circuited by the `_decidable`/terminal guard and emits no second decision, and a late risk result after terminal hits `late_result_recorded_not_applied`/`DUPLICATE` (recorded, not applied — FR-019)
- [ ] T119 [P] [US4] **AC3** unit (no broker): in `apps/agents/customer_resolution/tests/test_duplicate_decision.py`, invoke `_apply_decision` twice for the same `READY_FOR_DECISION` case and assert exactly one `TOPIC_RESOLUTION_DECIDED` + one `TOPIC_RESPONSE_DRAFTED` publish and that the second call is a guarded no-op via the `status == DECIDED or is_terminal(...)` guard (`event_handlers.py:469-470`) with no status regression; add a both-results-race variant (`asyncio.gather` two ready-making result handlers) asserting a single decision — "duplicate final decision does not close case twice" (FR-013)
- [ ] T120 [US4] Verify/harden duplicate observability: confirm every duplicate path is auditable — `intake_handler` `duplicate_skipped` (`event_handlers.py:290`), `result_handler` late-result branch (`event_handlers.py:410`), and the `DUPLICATE` outcome reaching `write_task_audit` in `billing_result_handler`/`risk_result_handler` (`event_handlers.py:565,659`); add the missing `write_task_audit(..., "duplicate_skipped", ...)` only where a duplicate path currently returns without an audit record, keeping the change additive (FR-022, SC-006)
- [ ] T121 [P] [US4] End-to-end duplicate sweep (live broker): in `tests/integration/test_duplicate_events.py`, redeliver each of the four event types against the running agents and assert SC-006 globally for one `correlation_id` — at most one `customer.resolution.decided`, one `customer-response.drafted`, two `agent.task_request.v1`, each peer result applied once, and a redelivered terminal `customer.resolution.decided` re-opens/re-closes nothing; reuse the `KafkaContainer` fixture pattern from `tests/integration/test_idempotency.py`

**Checkpoint**: The system is provably idempotent and deterministically replayable; the three named
duplicate-event acceptance criteria (AC1 no duplicate peer tasks, AC2 no decision change, AC3 no
double-close) are proven per event type.

---

## Phase 7: User Story 5 - Trace any case from a single identifier (Priority: P3)

**Goal**: From one `correlation_id`, an operator reconstructs the entire case journey in causal order — ticket, triage, both requests, both opinions, aggregation, decision — without reading code.

**Independent Test**: Take the `correlation_id` of a completed case and retrieve, in causal order, every step that contributed to its decision.

### Tests for User Story 5 ⚠️

- [X] T028 [P] [US5] Integration test: tracing a completed case by `correlation_id` reconstructs 100% of workflow steps in causation order from ticket → decision (US5 AC1, SC-005); and an escalated case's trail makes the escalation reason and the missing/failed contributor identifiable from the trail alone (US5 AC2), in `tests/integration/test_workflow_choreography.py`

### Implementation for User Story 5

- [X] T029 [US5] Implement the reusable causal-trace function over `agent_foundation.audit.store.query_by_correlation`: build the `event_id → causation_id` map, root at the `support.ticket.created` event (`causation_id is None`), topologically order by causation (ties broken by timestamp then offset), and emit per-step `TraceStep{seq, actor, correlation_id, event_type/action, outcome, task_id?, timestamp, caused_by}` (data-model D3); place in `apps/agents/customer_resolution/` (or a foundation helper)
- [X] T030 [US5] Implement the `apps/api/trace_case.py` CLI accepting `correlation_id` (+ `--json`, `--broker`) that prints the ordered steps and surfaces the escalation reason / missing-or-failed contributor for escalated cases (FR-023)

**Checkpoint**: Any case is fully reconstructable from a single id, code-free.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Decentralization proof (SC-009), demo wiring, and full quickstart validation.

- [X] T031 [P] Verify/extend the structural decentralization guards so they stay green and assert the reaper, replay harness, and trace tool issue no task requests and direct no agents (FR-021, SC-009a), in `apps/agents/customer_resolution/tests/test_no_supervisor.py` and `tests/integration/test_no_router.py`
- [X] T032 [P] Add the audit-trail decentralization proof: for a sample case, assert the final decision emerges purely from peer result events with no central dispatcher (FR-021, SC-009b), in `tests/integration/test_workflow_choreography.py`
- [X] T033 [P] Verify the demo entrypoints (`uv run demo-customer-resolution`, `demo-billing-entitlement`, `demo-risk-fraud`), `apps/api/dev_publish_ticket.py`, and `apps/api/trace_case.py` run end-to-end and the happy path completes ticket → decision under 30s on a single broker (SC-008), per `specs/006-workflow-choreography/quickstart.md`; fix entrypoint/script gaps
- [X] T034 Run full quickstart validation — §A `pytest tests/integration/test_workflow_choreography.py -m integration`, the no-supervisor/no-router guards, §C unit/contract suites — and confirm every acceptance box in `quickstart.md`

---

## Phase 9: User Story 6 - Run the whole system locally with one command (Priority: P2)

**Goal**: Formalize quickstart §B's manual three-terminal demo wiring into two scripts —
`scripts/start-local-system.sh` brings up Redpanda/Kafka + Kafka UI and launches the three agents as
**independent peer processes** (no supervisor), each exposing its own A2A endpoint, with Kafka topics
consistently created; `scripts/stop-local-system.sh` tears it all down. This is the runnable-demo wiring
called out in `plan.md` (gap 5, "Runnable demo wiring", SC-008) and makes T033's manual steps one command.

**Acceptance criteria** (from the request, each mapped to a verification task):
- **AC1** — the start script does **not** start a supervisor (it backgrounds peers and exits) → T056, T062
- **AC2** — agents run as **independent OS processes** (distinct PIDs/logfiles) → T055, T062
- **AC3** — each agent exposes **its own A2A endpoint** (per-agent AgentCard + `task.requested` inbox; optional HTTP surface) → T057, T058
- **AC4** — Kafka topics are **created or auto-created consistently** on a cold start → T053, T054

**Independent Test**: On a clean checkout run `scripts/start-local-system.sh`; confirm `docker compose ps`
shows `redpanda` + `kafka-ui` healthy and three distinct agent PIDs; confirm each agent's
`task.requested` inbox topic exists; publish a ticket (`uv run python apps/api/dev_publish_ticket.py`) and
observe a terminal `customer.resolution.decided` within the SC-008 budget; run
`scripts/stop-local-system.sh` and confirm no agent process or container remains. No supervisor/coordinator
process is ever started.

### Scaffolding & shared shell helpers (blocking prerequisites for both scripts)

- [X] T050 [US6] Create the `scripts/` tree and `scripts/lib/common.sh` shared helper: `set -euo pipefail`;
  env defaults `AGENT_BROKER_URL=localhost:9092` and `AGENT_ENVIRONMENT=local` (overridable); a `.local-run/{pids,logs}`
  runtime-state convention; `log_info`/`log_warn`/`log_err` helpers; and a port-assignment block that reserves
  **8080 for Kafka UI** and assigns the HTTP A2A surfaces **billing=8101, risk=8103** to resolve the existing
  Kafka-UI↔billing-HTTP `:8080` collision. Add `.local-run/` to `.gitignore`. Files: `scripts/lib/common.sh`, `.gitignore`
- [X] T051 [US6] Add `wait_for_kafka()` to `scripts/lib/common.sh`: poll `docker compose -f infra/local/docker-compose.yml exec -T redpanda rpk cluster health` (fall back to a TCP probe of `localhost:9092`) until ready or a bounded timeout, with a clear failure message. File: `scripts/lib/common.sh`
- [X] T052 [US6] Add `start_agent()` / `stop_agent()` to `scripts/lib/common.sh`: `start_agent` runs `uv run <console-script>` via `nohup … &`, writes `.local-run/pids/<name>.pid`, and redirects stdout/stderr to `.local-run/logs/<name>.log`; `stop_agent` reads the pidfile → `SIGTERM` → bounded wait → `SIGKILL` fallback → removes the pidfile; both tolerate missing/stale state. File: `scripts/lib/common.sh`

### AC4 — consistent Kafka topic creation

- [X] T053 [P] [US6] Add `resolve_topics()` to `scripts/lib/common.sh` that prints every resolved topic name for `AGENT_ENVIRONMENT=local` by importing `packages/contracts/topics.py` (domain topics + the three `local.agent.<agent>.task.requested.v1` inboxes) via `uv run python -c …`, so the script and the agents share one source of truth. File: `scripts/lib/common.sh`
- [ ] T054 [US6] Add `ensure_topics()` to `scripts/start-local-system.sh`: after `wait_for_kafka`, idempotently pre-create each `resolve_topics()` entry via `docker compose -f infra/local/docker-compose.yml exec -T redpanda rpk topic create <topic> -p 1 -r 1` tolerating "already exists" (Redpanda's `enable_auto_create_topics=true` in `infra/local/docker-compose.yml` remains the fallback), then print `rpk topic list` for verification (AC4). File: `scripts/start-local-system.sh`

### AC2 + AC1 — start script: independent processes, no supervisor

- [X] T055 [US6] Implement `scripts/start-local-system.sh`: source `scripts/lib/common.sh`; `docker compose -f infra/local/docker-compose.yml up -d` (starts `redpanda` + `kafka-ui`); `wait_for_kafka`; `ensure_topics`; then `start_agent` the three **Kafka mains** as independent background processes — `demo-billing-entitlement`, `demo-risk-fraud`, `demo-customer-resolution` (the authoritative 006 run path, quickstart §B) — each with its own pidfile + logfile; print a status summary (per-agent PID + log path, Kafka UI at `http://localhost:8080`) (AC2). File: `scripts/start-local-system.sh`
- [X] T056 [US6] Guarantee the start script is **not a supervisor** (AC1): after launching, it disowns the background agents and **exits**, returning control to the operator. It MUST NOT contain any `wait`, monitor, or restart/while-true loop that directs the agents. Add an inline comment documenting this and a final assertion that the script reaches a clean `exit 0` without blocking. File: `scripts/start-local-system.sh`

### AC3 — each agent exposes its own A2A endpoint

- [ ] T057 [US6] Add a `--verify` mode to `scripts/start-local-system.sh` proving each agent exposes its own A2A endpoint (AC3): each `AgentRuntime` publishes its AgentCard to `local.agent.agent-card.published.v1` and owns its `local.agent.<agent>.task.requested.v1` inbox; the verify step confirms (via `rpk topic list` / a short consume of the agent-card topic) that all three inbox topics and three AgentCards are present, and prints each agent's endpoint identity. File: `scripts/start-local-system.sh`
- [ ] T058 [P] [US6] Add an optional `--with-http` flag to `scripts/start-local-system.sh` that additionally launches the HTTP A2A surfaces for operators who want HTTP discovery: `start_agent` `demo-billing-entitlement-http` with `PORT=8101` and `demo-risk-fraud-http` with `A2A_ENDPOINT_PORT=8103` (8080 stays reserved for Kafka UI); each serves `GET /.well-known/agent.json` + `POST /a2a/tasks`. Document that customer-resolution is Kafka-only (no HTTP surface) and exposes its endpoint via its AgentCard/inbox topic. File: `scripts/start-local-system.sh`

### stop script + ergonomics

- [X] T059 [US6] Implement `scripts/stop-local-system.sh`: source `scripts/lib/common.sh`; `stop_agent` each agent by pidfile (reverse start order), then `docker compose -f infra/local/docker-compose.yml down`; tolerate already-stopped agents / absent containers (idempotent); support a `--keep-kafka` flag that stops only the agents and leaves Redpanda + Kafka UI up. File: `scripts/stop-local-system.sh`
- [X] T060 [US6] Make both scripts `chmod +x`, re-run safe (start skips agents whose pidfile PID is already alive; stop tolerates missing state), and add `--help`/usage plus a `--status` mode (list running agent PIDs + `docker compose ps`). Files: `scripts/start-local-system.sh`, `scripts/stop-local-system.sh`

### Validation & docs

- [ ] T061 [P] [US6] Run `shellcheck` over `scripts/start-local-system.sh`, `scripts/stop-local-system.sh`, and `scripts/lib/common.sh`; fix all findings and confirm `set -euo pipefail`, quoted expansions, and clean exit codes. Files: `scripts/start-local-system.sh`, `scripts/stop-local-system.sh`, `scripts/lib/common.sh`
- [ ] T062 [US6] End-to-end smoke validation of all four acceptance criteria: on a clean checkout run `scripts/start-local-system.sh`; assert `redpanda` + `kafka-ui` healthy, three distinct agent PIDs (AC2), no supervisor process started (AC1), all three `task.requested` inboxes present (AC3, AC4); publish a ticket and confirm a terminal `customer.resolution.decided` within the SC-008 budget; then `scripts/stop-local-system.sh` and confirm no agent process or container remains. Record results against `specs/006-workflow-choreography/quickstart.md` §B
- [ ] T063 [P] [US6] Document the one-command workflow in `README.md` and update `specs/006-workflow-choreography/quickstart.md` §B to reference `scripts/start-local-system.sh` / `scripts/stop-local-system.sh` (with the manual three-terminal steps kept as the underlying detail). Files: `README.md`, `specs/006-workflow-choreography/quickstart.md`

**Checkpoint**: One command brings the full system up as independent peer processes (no supervisor) with
each agent exposing its own A2A endpoint and topics consistently created; one command tears it down.

---

## Phase 10: User Story 7 - Correlation tracking & causal integrity (Priority: P2)

**Goal**: Every event a case produces carries the five correlation components — `correlation_id`, `causation_id`, `case_id` (≡ `correlation_id` in this system), `task_id` where applicable, and `producer_agent_id` (≡ the envelope `agent_id`) — so all events in one case share one `correlation_id`, each `causation_id` points at the event/task that triggered it, the terminal decision references the Billing and Risk **result event IDs**, and the full audit timeline reconstructs from events alone.

**Independent Test**: Drive one refund case end-to-end; collect every emitted envelope across all case topics plus the audit records; assert (1) all share exactly one `correlation_id` and every `case_id`-bearing payload equals it; (2) every non-root `causation_id` resolves to its triggering `event_id`/`task_id`, forming one connected DAG rooted at the ticket; (3) the `customer.resolution.decided` payload's `billing_result_event_id`/`risk_result_event_id` equal the real emitted result envelopes' ids; (4) the entire timeline rebuilds in causal order from the audit topic alone.

> **ID note**: Added after the T001–T072 list; numbered T073+ to avoid renumbering existing IDs other work references. Maps the user request ("every event includes `correlation_id`, `causation_id`, `case_id`, `task_id` where applicable, `producer_agent_id`") onto the **existing** envelope — decision taken: `correlation_id` IS `case_id`, envelope `agent_id` IS `producer_agent_id`, and `task_id` lives in the A2A task payloads / `AuditPayload.task_id`. The only contract change is therefore the **additive** decision-payload result-event-id references (T079); everything else is assertion, threading already-captured case state, and a trace extension. No new event contract, no new topic, no new dependency (Constitution V).
>
> **Reuse (don't reinvent)**: builds on the Phase 2B `WorkflowHarness` (`packages/testing/workflow_harness.py`) — `collect_events(correlation_id)`, `wait_for_decision(...)`, and `assert_causal_order(...)` (T067/T069) already provide event collection and the non-root-causation check; the US7 tests *consume* them rather than re-collecting. Within-story order: tests T073–T078 (write first, must fail) → implementation T079–T082; T079 precedes T080; T082 extends the US5 trace function (T029) and `trace_case.py` (T030), so it lands after Phase 7; the integration tests depend on the Phase 2B harness (T064–T072) and the Phase 2 multi-agent fixture (T006).

### Tests for User Story 7 ⚠️ (write first; must fail before implementation)

- [ ] T073 [P] [US7] Contract test: `CustomerResponseDecisionPayload` accepts optional `billing_result_event_id`/`risk_result_event_id` (`UUID | None`, default `None`), JSON round-trips them, and a payload omitting them still validates (backward-compatible field expansion); extend `apps/agents/customer_resolution/tests/test_resolution_schemas.py`
- [ ] T074 [P] [US7] Integration test (criterion 1 — shared correlation_id): for one refund case, `harness.collect_events(correlation_id)` and assert every emitted envelope shares exactly one `correlation_id`, and every payload carrying a `case_id` field (`CustomerIssueClassifiedPayload`, `RefundReviewRequestedPayload`, `CustomerResponseDecisionPayload`, `CustomerResponseDraftedPayload`, `BillingRefundAnalysisCompletedPayload`, `RiskReviewCompletedPayload`) has `case_id == envelope.correlation_id` (FR-005), in `tests/integration/test_correlation_tracking.py`
- [ ] T075 [P] [US7] Integration test (criterion 2 — causation): exercise `harness.assert_causal_order(correlation_id)` and additionally assert every non-root event's `causation_id` resolves to the `event_id` (or A2A `task_id`) of an earlier event for the same case, forming a single connected DAG rooted at the `support.ticket.created` event (`causation_id is None`) — no orphan and no cross-case link (FR-006/FR-007), in `tests/integration/test_correlation_tracking.py`
- [ ] T076 [P] [US7] Integration test (criterion 3 — decision references results): the terminal `customer.resolution.decided` payload's `billing_result_event_id` and `risk_result_event_id` equal the `event_id`s of the actual emitted `billing.refund-analysis.completed` and `risk.review.completed` envelopes for that case, and both referenced ids appear earlier in the collected envelope set (FR-007), in `tests/integration/test_correlation_tracking.py`
- [ ] T077 [P] [US7] Integration test (criterion 4 — timeline from events alone): reconstruct the case timeline from the **audit topic alone** (no case-store access) via the US5 trace function; assert every workflow step (ticket → classified → both `task.requested` → refund-review.requested → both `*.completed` → decided → drafted) is present in causal order and each step exposes the five correlation components (`correlation_id`≡case_id, `causation_id`, producer `agent_id`, `task_id` where applicable), and that the decided step's `billing_result_event_id`/`risk_result_event_id` reference steps already present in the timeline (FR-022/FR-023, SC-005), in `tests/integration/test_correlation_tracking.py`
- [ ] T078 [P] [US7] Integration test (producer identity): each agent stamps itself as the producer — `billing.refund-analysis.completed` carries `agent_id == "billing-entitlement-agent"`, `risk.review.completed` carries `agent_id == "risk-fraud-agent"`, and the classified / refund-review-requested / decided / drafted + audit envelopes carry `agent_id == "customer-resolution-agent"` (producer_agent_id ≡ envelope `agent_id`), in `tests/integration/test_correlation_tracking.py`

### Implementation for User Story 7

- [ ] T079 [US7] Add additive optional references `billing_result_event_id: UUID | None = None` and `risk_result_event_id: UUID | None = None` to `CustomerResponseDecisionPayload` (frozen, `extra="forbid"`; safe defaults mirroring the backward-compatible field expansion already done on `BillingRefundAnalysisCompletedPayload`); no new topic/contract, in `packages/contracts/events/payloads.py`
- [ ] T080 [US7] Thread the already-captured `case.billing_result_event_id` / `case.risk_result_event_id` (set on result arrival in `event_handlers.py`, fields at `apps/agents/customer_resolution/models.py:283-284`) into the emitted decision: extend `decide(...)` and the `CustomerResponseDecisionPayload` builders in `apps/agents/customer_resolution/decision_engine.py` to accept the two optional result event ids and set them on the returned payload, and pass `case.billing_result_event_id`/`case.risk_result_event_id` at each decided-emit site in `apps/agents/customer_resolution/event_handlers.py` — leaving each `None` when its opinion is missing/timed-out so the reaper/timeout path stays valid (FR-007)
- [ ] T081 [US7] Add an emit-time `case_id == correlation_id` consistency guard in the resolution agent's publish path: before publishing any payload exposing a `case_id`, assert `payload.case_id == correlation_id` (raise in tests/debug, structured-log otherwise) so a mis-keyed case can never reach a topic, centralized in `apps/agents/customer_resolution/event_handlers.py` (and any shared publish helper); no schema change (criterion 1, FR-005)
- [ ] T082 [US7] Extend the US5 causal-trace function (T029) and `apps/api/trace_case.py` (T030) so each `TraceStep` surfaces the five correlation components explicitly — `correlation_id` (labelled as the case id), `causation_id` (`caused_by`), producer `agent_id`, and `task_id` where applicable — and the decided step additionally renders its `billing_result_event_id`/`risk_result_event_id`, all reconstructed from `agent.audit.v1` records alone (FR-022/FR-023, SC-005)

**Checkpoint**: Every case event carries the five correlation components, all events in a case share one `correlation_id`, the terminal decision references the Billing and Risk result event ids, and the full audit timeline reconstructs from events alone.

---

## Phase 11: User Story 8 - One-command portfolio demo (`make demo-refundops`) (Priority: P2)

**Goal**: A single `make demo-refundops` command stands up local infrastructure, starts the three
autonomous agents, **automatically** publishes one sample refund ticket (no manual Kafka publishing),
then prints the case's **causal audit timeline** and the **final decision** in a polished,
portfolio-friendly format — visibly proving distributed, orchestrator-free agent collaboration
end-to-end. This is the operator-facing capstone of `plan.md` gap 5 ("Runnable demo wiring", SC-008): it
reuses the US6 lifecycle scripts (T055/T059), the US5 trace tool (T029/T030), the Phase 2C audit-timeline
builder (T110–T113), and `dev_publish_ticket.py` rather than introducing new agent code or any new
contract/topic/dependency (Constitution V).

> **ID note**: Numbered **T200+** to clear the concurrently-grabbed front of the list (current max `T121`,
> with `T110`–`T121` already taken by the Phase 2C audit-timeline and US4 duplicate-test work). These IDs
> are intentionally jumped high to avoid colliding with parallel sessions; the Dependencies section records
> US8's logical placement (operational tooling, buildable after US1 is green).

**Acceptance criteria** (from the request, each mapped to a verification task):
- **AC1 — Demo proves distributed collaboration**: the printed timeline shows contributions from all three
  independent agents (`billing-entitlement-agent`, `risk-fraud-agent`, `customer-resolution-agent`) and an
  explicit "no orchestrator" line, sourced from the audit actors → T207, T200, T208
- **AC2 — No manual Kafka publishing required**: the operator runs exactly one `make` target; the sample
  ticket is published programmatically by the driver, never by a hand-run `kafka`/`rpk`/publish command → T203, T210
- **AC3 — Output is portfolio-friendly**: a banner, aligned per-step timeline (actor → action → outcome),
  and a final-decision block (outcome + explanation + contributing opinions), with a `--json` escape hatch → T204, T201

**Independent Test**: On a clean checkout run `make demo-refundops`; confirm it brings up Redpanda + the
three agents, publishes one sample ticket with no manual Kafka step, and prints both a causally-ordered
audit timeline spanning all three agents and a single terminal `customer.resolution.decided` outcome with
explanation — all within the SC-008 30s budget — then tears the stack down cleanly.

### Tests for User Story 8 ⚠️ (write first; must fail before implementation)

- [X] T200 [P] [US8] Demo smoke integration test in `tests/integration/test_demo_refundops.py`: drive the
  demo driver (T203) against the testcontainers multi-agent harness (T006); assert it publishes **exactly
  one** `support.ticket.created` event, reaches a single terminal `customer.resolution.decided` within the
  SC-008 budget, the reconstructed timeline contains all three agent actors (AC1 distributed
  collaboration), and the rendered final-decision block is present — and that the test itself performs **no
  manual Kafka publish** (AC2). (US8 AC1/AC2, SC-008)
- [X] T201 [P] [US8] Formatter unit test in `tests/unit/test_demo_render.py` (no broker): feed synthetic
  `TraceStep`s (T029 model) plus a `CustomerResponseDecisionPayload` into `format_timeline()` /
  `format_decision()` and assert the portfolio layout (banner, aligned actor → action → outcome rows, final
  decision block with explanation + contributing opinions), the explicit 3-agent / no-orchestrator
  collaboration line, and a valid `--json` form (AC3).

### Implementation for User Story 8

- [X] T202 [US8] Create the repo-root `Makefile` with a `.PHONY` `demo-refundops` target plus supporting
  targets (`demo-infra-up`, `demo-agents-up`, `demo-agents-down`, `demo-infra-down`, `demo-clean`);
  `demo-refundops` chains: `demo-infra-up` → `demo-agents-up` → readiness wait → demo driver (T203) →
  `demo-agents-down` → (optional) `demo-infra-down`. Each target is a thin wrapper over existing tooling
  (no agent source). File: `Makefile`
- [ ] T203 [US8] Implement the demo driver `apps/api/run_demo.py`: reuse the `dev_publish_ticket.py` publish
  path to emit **one** sample refund ticket programmatically (no manual Kafka, AC2) and capture its
  `correlation_id`; poll the `customer.resolution.decided` topic / audit for the terminal decision bounded
  by the SC-008 30s budget; then render the banner, the causal audit timeline (via the US5 trace function
  T029 / Phase 2C audit-timeline builder T110–T113), and the final-decision block. File: `apps/api/run_demo.py`
- [ ] T204 [US8] Portfolio-friendly formatting in `apps/api/run_demo.py`: `format_timeline(steps)` and
  `format_decision(payload)` producing a banner + aligned, labeled (optionally ANSI-colored) rows
  (actor → action → outcome per `TraceStep`) and a final-decision block (outcome + human-readable
  explanation + contributing billing/risk opinions), with a `--json` escape hatch; reuse the US5 `TraceStep`
  model (T029) and `apps/api/trace_case.py` (T030) rendering rather than reinventing (AC3). File: `apps/api/run_demo.py`
- [ ] T205 [US8] Wire the Makefile lifecycle targets to the **existing** scripts: `demo-agents-up` /
  `demo-agents-down` invoke `scripts/start-local-system.sh` / `scripts/stop-local-system.sh` (US6
  T055/T059) when present, else fall back to `infra/local/run-demo-agents.sh`; `demo-infra-up` runs
  `docker compose -f infra/local/docker-compose.yml up -d`; `demo-infra-down` runs the matching `down`. No
  new supervisor process is introduced (Constitution I, FR-021). File: `Makefile`
- [ ] T206 [US8] Readiness gating before publish in `apps/api/run_demo.py` (and the Makefile wait step):
  wait for Kafka health (reuse US6 `wait_for_kafka`, T051, or a TCP probe of `localhost:9092`) **and** for
  all three AgentCards on `local.agent.agent-card.published.v1` so the ticket is never published before the
  agents subscribe — eliminating a flaky cold-start demo. Files: `apps/api/run_demo.py`, `Makefile`
- [ ] T207 [US8] Distributed-collaboration proof line in `apps/api/run_demo.py`: from the audit actors in
  the reconstructed timeline, assert and print that all three **independent** agents participated
  (`billing-entitlement-agent`, `risk-fraud-agent`, `customer-resolution-agent`) and emit an explicit
  "distributed collaboration verified: 3 autonomous agents, no orchestrator" summary line — the visible
  proof of AC1 (FR-021, SC-009b). File: `apps/api/run_demo.py`

### Polish & docs for User Story 8

- [ ] T208 [US8] Verify `make demo-refundops` is **not** a supervisor (Constitution I / FR-021): the
  Makefile + driver only sequence setup → publish-one-ticket → observe → teardown and direct no agent's
  decisioning; extend `tests/integration/test_no_router.py` (or its guard list) to assert the demo
  driver/Makefile issue no `task.requested` and centrally dispatch no agent. File: `tests/integration/test_no_router.py`
- [ ] T209 [P] [US8] Document the one-command portfolio demo in `README.md` and
  `specs/006-workflow-choreography/quickstart.md` §B: `make demo-refundops` as the canonical entry point
  (one sample ticket → audit timeline → final decision), keeping the manual three-terminal steps as the
  underlying detail. Files: `README.md`, `specs/006-workflow-choreography/quickstart.md`
- [ ] T210 [US8] End-to-end acceptance validation: on a clean checkout run `make demo-refundops`; confirm
  it (1) starts local infrastructure, (2) starts the three agents, (3) publishes the sample ticket with
  **no manual Kafka step** (AC2), (4) prints the causal audit timeline spanning all three agents (AC1),
  (5) prints the final decision, all portfolio-friendly (AC3) and within the SC-008 30s budget; record
  results against `specs/006-workflow-choreography/quickstart.md` §B.

**Checkpoint**: One command — `make demo-refundops` — proves the entire decentralized workflow to a
stakeholder: infra up, three autonomous agents, an auto-published ticket, a causally-ordered audit timeline
across all three agents, and a justified final decision, with no manual Kafka publishing and no
orchestrator.

---

## Phase 12: Architecture Documentation (Cross-Cutting)

**Goal**: Capture the decentralized choreography as durable, code-free architecture documentation under `docs/architecture/` (siblings to the existing `adding-new-agent.md`, `event-contracts.md`, `topic-naming.md`). Each doc distills already-decided behaviour from the spec/plan/contracts into operator- and reviewer-facing narrative; it adds **no new design decisions** (Constitution V) and **references, never re-derives** the authoritative artifacts.

**Independent Test**: A reader who has not seen the code can, from these five docs alone, (a) explain how a ticket becomes a decision with no central orchestrator, (b) name every topic / emitter / consumer and the correlation rules, (c) describe the three idempotency layers and how replay proves determinism, (d) state the terminal outcome of every failure mode, and (e) describe how the absence of a supervisor is verified.

> **Scope note**: Pure documentation phase — touches only `docs/architecture/*.md` and the repo `README.md`. No agent source, no new contract/topic/dependency. The five docs are independently authorable (`[P]`, separate files); T225 cross-links/indexes them and therefore runs last. The docs describe the as-built choreography, so they are most accurate authored after the flow they describe is green (Phases 3-11), but drafting can begin from the spec/plan/contracts at any time. IDs jumped to **T220+** to clear the concurrently-grabbed front of the list (current max ~T210).

- [X] T220 [P] Create `docs/architecture/decentralized-workflow.md`: narrate the end-to-end refund flow (ticket -> triage -> parallel billing + risk opinions -> async aggregation -> single terminal decision) with **no central orchestrator**. Cover the four participants and their roles (dev intake, Customer Resolution, Billing Entitlement, Risk & Fraud) and the non-refund direct-response path. Include a Mermaid sequence diagram of the happy path. Source: `specs/006-workflow-choreography/spec.md` (Overview, US1), `plan.md` (Summary), `contracts/choreography.md` (Participants, Event flow, Non-refund path), Constitution Principle I (Agent Autonomy). Cross-link the other four architecture docs.

- [X] T221 [P] Create `docs/architecture/event-choreography.md`: document the event topology — the topic / emitter / consumer table, how topic names resolve via `packages/contracts/topics.py` + `AGENT_ENVIRONMENT`, the correlation/causation propagation rules (FR-005/FR-006/FR-007), and async result aggregation/correlation across the shared `task.result` stream (FR-008/FR-009). Reproduce the topic table and add a Mermaid diagram of the correlation/causation DAG. Source: `contracts/choreography.md` (Event flow table + Correlation & causation rules); link to (do not duplicate) the existing `docs/architecture/event-contracts.md` and `docs/architecture/topic-naming.md`.

- [X] T222 [P] Create `docs/architecture/replay-and-idempotency.md`: document the **three idempotency layers** (event-level `IdempotencyTracker` per consumer group; task-level stable `task_id = uuid5(correlation_id, capability)`; case-level `DECIDED`/terminal guard => exactly one decision) and the **replay harness** (fresh in-memory store + uniquely-named consumer groups + `Consumer.seek_to_beginning()`, reaper neutralized for completed-run replay) with its assertions and determinism basis. State explicitly why `decide()` purity is what makes replay deterministic. Source: `plan.md` (Constitution Check, Principle III), `contracts/replay-and-trace.md` Section 1, FR-011-FR-016, SC-003/SC-006.

- [X] T223 [P] Create `docs/architecture/failure-handling.md`: reproduce the **failure-mode -> terminal-outcome table** (both/one peer silent past deadline, peer failed/rejected, unparseable result, undiscoverable peer, conflicting opinions, peer-requested review, malformed ticket, late-opinion-after-terminal), document the **timeout reaper** enforcement loop (sweep cadence, `deadline + <= REAPER_TICK_SECONDS` grace, no-double-decision guard via shared `_apply_decision`, injectable clock), the combined decision rule, and the `CASE_DEADLINE_SECONDS` / `REAPER_TICK_SECONDS` config knobs. Source: `contracts/timeout-and-failure-paths.md`, `contracts/decision-rule.md`, FR-017-FR-020/FR-024, SC-004/SC-007, spec Edge Cases.

- [X] T224 [P] Create `docs/architecture/no-supervisor-verification.md`: document how the absence of a supervisor/router/orchestrator is **proven** — (a) the automated structural guards `apps/agents/customer_resolution/tests/test_no_supervisor.py` and `tests/integration/test_no_router.py`, and (b) the correlation-id audit trail showing the decision emerges purely from peer events via the causal trace tool `apps/api/trace_case.py`. Cover the decentralization invariants (no agent consumes a peer's endpoint topic to direct it; reaper/replay/trace are read-only and direct no agent). Source: `contracts/choreography.md` (Decentralization invariants), `contracts/replay-and-trace.md` Section 2, FR-021/FR-023, SC-005/SC-009, Constitution Principles I & IV.

- [X] T225 Cross-link and index the five new architecture docs: ensure each of T220-T224 links to the others where relevant, and register all five in any docs index (the repo `README.md` and the `docs/architecture/` sibling set with `adding-new-agent.md`, `event-contracts.md`, `topic-naming.md`) so they are discoverable; verify every internal link and source-artifact reference resolves. Files: `docs/architecture/*.md`, `README.md`.

---

## Phase 11: Billing-ineligible + low-risk conflict golden E2E test (added per request)

**Purpose**: Cover the requested scenario — *customer requests refund → billing says **ineligible** →
risk says **low***. Per the authoritative decision engine (`decision_engine.py`) and
`contracts/decision-rule.md`, this combination is **not** `deny_refund`: `deny_refund` is **Row 5**
(`ineligible` + risk `elevated`/`high`), while `ineligible` + `low` is a **residual conflict → Row 8 →
`escalate_human`/`conflicting_analyses`**. This phase asserts the engine's real terminal outcome for the
requested inputs and corrects the pre-existing fixtures (T040/T008) that wrongly assumed
`ineligible`+`low` → `deny_refund`. It is the sibling of T100 (full-refund approve), T101 (partial credit),
and T102 (eligible+high escalation) for the **ineligible+low conflict** path; it reuses the black-box
`WorkflowHarness` (Phase 2B) and adds **no** agent code, contract, topic, or dependency (Constitution V).

> **ID note**: Added after the existing list; numbered **T230+** to clear the current max (`T225`) and
> avoid the concurrently-grabbed low-ID bands (parallel-writers convention used by Phases 2A/2B/2C/US8).
>
> **Decision-rule reconciliation** (request → engine ground truth): the request's *expected
> `deny_refund`* does not hold for `ineligible`+`low`. The engine returns `escalate_human` with
> `escalation_reason="conflicting_analyses"` (decision-rule **Row 8**); a genuine `deny_refund` needs
> `ineligible`+`elevated`/`high` (**Row 5**). T230/T231 assert the true outcome for the requested inputs;
> T232 fixes T040/T008.
>
> **Event-name reconciliation**: `customer.resolution.decided.v1` (`TOPIC_RESOLUTION_DECIDED`,
> `outcome == escalate_human`); the request's terminal "case escalated" maps to the terminal **case state**
> `CaseStatus.ESCALATED` (no `case.escalated` topic exists or is added, Principle V); escalated terminals do
> **not** emit a closing `customer-response.drafted`.

- [X] T230 [P] [US3] New scenario fixture `billing_ineligible_low_conflict` in
  `tests/integration/fixtures/workflow_scenarios/billing_ineligible_low_conflict.py`: refund ticket; billing
  profile mirroring `PR-WINDOW-EXPIRED` (**ineligible**, RP-001); risk profile mirroring `CUS-CLEAN`
  (**low**); `expected_events` = ticket → classified → both `task.requested` → refund-review.requested →
  both `*.completed` → `decided(escalate_human)` (+ audit at each; **no** closing `customer-response.drafted`
  entry — escalated terminals don't draft a closing response); `expected_final_state` =
  `CaseStatus.ESCALATED`, `ResolutionOutcome.ESCALATE_HUMAN`, `escalation_reason="conflicting_analyses"`
  (decision-rule **Row 8**: `ineligible`+`low` residual conflict, FR-010). Register it in
  `tests/integration/fixtures/workflow_scenarios/__init__.py` (`ALL_SCENARIOS`) and bump the
  expected-scenario count in T047 (registry assertion) and T048 (fixture self-validation) accordingly.

- [X] T231 [P] [US3] Billing-ineligible + low-risk conflict golden E2E test in
  `tests/integration/test_workflow_choreography.py`: seed the `billing_ineligible_low_conflict` fixture
  (T230) into the **real** billing/risk agents via the harness; `harness.publish_ticket(...)` the refund
  ticket; then assert end-to-end through **Kafka only** (no internal agent method): (1) exactly one
  `TOPIC_RESOLUTION_DECIDED` event whose `CustomerResponseDecisionPayload.outcome ==
  ResolutionOutcome.ESCALATE_HUMAN` and `escalation_reason == "conflicting_analyses"`; (2) the case reaches
  terminal `CaseStatus.ESCALATED` (asserted from observed events/audit, no `case.escalated` topic) and **no**
  closing `TOPIC_RESPONSE_DRAFTED` is emitted (escalation lifecycle, per
  `WorkflowHarness.assert_final_state`); (3) **no** `approve_refund`/`deny_refund`/`offer_partial_credit`
  outcome is produced; (4) `assert_causal_order(correlation_id)` holds across the full chain (ticket →
  classified → both `task.requested` → refund-review.requested → both `*.completed` → decided), and the
  billing & risk capabilities were each invoked exactly once. **Depends on**: T230 (fixture), T006
  (multi-agent harness), T098/T093–T095 (`WorkflowHarness` publish/wait/assert primitives). (US3 AC3/AC4,
  FR-010, SC-007, decision-rule Row 8)

- [X] T232 [US3] Fix-up — align the pre-existing `billing_denied` fixture and ineligible smoke test with the
  engine: correct **T040** (`billing_denied` fixture) and **T008** (ineligible smoke test) so they assert a
  **genuine** `deny_refund`, which per decision-rule **Row 5** requires billing `ineligible` **AND** risk
  `elevated`/`high` (not `low`). Change T040's `mock_risk_profile` from `CUS-CLEAN` (low) to an
  **elevated**-band profile mirroring `CUS-VELOCITY` so `ineligible`+`elevated` → `deny_refund` (Row 5) with
  **no** high-risk flag (keeping it distinct from T019's `ineligible`+`high`+flag case), leaving
  `expected_final_state` = `CaseStatus.CLOSED`, `ResolutionOutcome.DENY_REFUND`, `escalation_reason=None`;
  and update T008's inputs/description to use `elevated`/`high` risk for the `deny_refund` assertion. Add a
  regression guard asserting **both** Row 5 (`ineligible`+`elevated`/`high` → `deny_refund`) and Row 8
  (`ineligible`+`low` → `escalate_human`/`conflicting_analyses`) hold across the real agents, in
  `tests/integration/test_workflow_choreography.py` (or the existing decision-table test). No new
  contract/topic/dependency (Constitution V).

**Checkpoint**: The requested *ineligible + low-risk* scenario is asserted to its true terminal outcome
(`escalate_human`/`conflicting_analyses`, Row 8), and the inconsistent `billing_denied` fixture/smoke
(T040/T008) is corrected to a genuine `deny_refund` (Row 5).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Foundational (Phase 2)**: Depends on Setup (T002 config used by T005/T021). **Blocks all user stories** — T006 harness is required by every integration test; T003 store query is required by the reaper.
- **Workflow Scenario Fixtures (Phase 2A, T035–T049)**: Logically foundational test data (numbered T035+ only to preserve existing IDs). Scaffolding T035→T036→T037 is sequential; the nine scenario modules T038–T046 are fully parallel `[P]`; T047 registry depends on all nine; T048 validation depends on T047; T049 wiring depends on T047 **and** the Phase 2 harness (T006). **Phase 2A prerequisites the integration/replay tests** T007–T009, T017–T020, T024–T026, which consume the fixtures via `get_scenario(...)`.
- **Reusable Workflow Test Harness (Phase 2B, T090–T098)**: Logically foundational test infrastructure (numbered T090+ to clear the concurrently-added Phase 9 IDs T050–T063). Scaffold T090 → collector T091 → driver/asserts T092–T096 are sequential (same file `packages/testing/workflow_harness.py`); T097 unit test is `[P]`; T098 wires the harness into the US1–US5 integration tests and depends on the Phase 2 harness fixture (T006) and the Phase 2A fixtures (T047/T049). **Phase 2B is the Kafka/A2A-only interaction layer required by** T007–T009, T012–T014, T017–T020, T024–T026, T028 (acceptance: tests call no internal agent method).
- **Audit Timeline Builder (Phase 2C, T110–T115)**: A read-only observability deliverable for US5 / Spec 007 feed (numbered T110+ to clear existing IDs). Within-block order: scaffold T110 → collect T111 → build/order T112 → render/serialize T113 are sequential (same file `packages/testing/audit_timeline.py`); T114 unit test is `[P]` (no broker); T115 integration test depends on the builder (T110–T113), the Phase 2 multi-agent harness (T006), the `happy_path_full_refund` fixture (T038), and the Phase 2B `WorkflowHarness` (T098). It reuses the US5 causal-ordering rule (T029) but adds no agent code and no new topic/contract/dependency.
- **User Stories (Phase 3–7)**: All depend on Foundational completion.
  - US1 (P1) → US2 (P2) → US3 (P2) → US4 (P3) → US5 (P3) in priority order, OR in parallel by file ownership (see below).
- **Polish (Phase 8)**: Depends on the user stories it validates (T031 after US3; T032 after US1/US5; T033/T034 after all).
- **US6 startup scripts (Phase 9)**: Internal order T050→T051→T052 (shell helpers) gate the rest; T053/T054 (topics), T055/T056 (start/no-supervisor), T057/T058 (A2A endpoint), T059/T060 (stop/ergonomics) build on the helpers; T061 (shellcheck) after the scripts exist; T062 (smoke) requires a working end-to-end flow (i.e. US1 green / Phase 3) since it publishes a ticket and expects a decision; T063 (docs) after T062. The scripts are pure operational tooling — they touch no agent source, so they can otherwise be built in parallel with Phases 3–8.
- **US8 portfolio demo (Phase 11)**: Operational tooling (a root `Makefile` + the `apps/api/run_demo.py` driver — no agent source). Internal order: T202 (Makefile) + T203/T204/T207 (driver) → T205/T206 (lifecycle + readiness wiring) → T200/T201 (tests) → T208 (no-supervisor guard) → T209/T210 (docs + e2e). Reuses US6 scripts (T055/T059), the US5 trace tool (T029/T030), and the Phase 2C audit-timeline builder (T110–T113); its smoke test (T200) and e2e validation (T210) require a working happy path (US1) and the multi-agent harness (T006). Buildable in parallel with Phases 3–10.

### User Story Dependencies

- **US1 (P1)**: After Foundational. No dependency on other stories — the MVP.
- **US2 (P2)**: After Foundational. Builds on the same handlers US1 exercises but is independently testable (concurrency/ordering).
- **US3 (P2)**: After Foundational (needs T003 store query + T002 config). Adds the reaper; independently testable.
- **US4 (P3)**: After Foundational. Independently testable; the replay harness reuses the agents but adds no agent code.
- **US5 (P3)**: After Foundational. Read-only over audit; fully independent.
- **US6 (P2)**: Operational tooling (shell scripts only — no agent source touched). Buildable in parallel with all other stories; only the end-to-end smoke (T062) depends on a working happy path (US1).
- **US8 (P2)**: One-command portfolio demo (`make demo-refundops`). Operational tooling only — no agent/contract/topic/dependency change. Independently testable; depends on US1 (happy path) for its end-to-end output and reuses the US5 trace tool + US6 lifecycle scripts.

### Within Each User Story

- Tests are written first and must FAIL before implementation.
- For US3: store query (T003, foundational) → reaper module (T021) → serve() wiring (T022).
- For US5: trace function (T029) → CLI (T030).

### Parallel Opportunities

- T002 ([P]) runs alongside T001.
- T004 ([P]) runs alongside T005 once T003 lands.
- **All `[P]`-marked test tasks within a story share one file** (`test_workflow_choreography.py`) — author them as separate test functions; they are logically parallel but coordinate on that file. The reaper unit tests (T016) and store-store unit test (T004) are in separate files and fully parallel.
- Across stories: once Foundational is done, US1, US2, US4, US5 touch largely disjoint code (handlers-verify vs. replay harness vs. trace tool) and can be staffed in parallel; US3 owns the new reaper + `agent.py`/`event_handlers.py` edits.

---

## Parallel Example: User Story 1

```bash
# Author the three US1 scenario tests together (separate test functions in one file):
Task: "Integration test eligible+low-risk → approve_refund in tests/integration/test_workflow_choreography.py"  (T007)
Task: "Integration test ineligible → deny_refund in tests/integration/test_workflow_choreography.py"             (T008)
Task: "Integration test non-refund → direct_response, peers not invoked in tests/integration/test_workflow_choreography.py" (T009)
Task: "Full happy-path golden E2E test (approve_refund, exact decided→drafted→CLOSED sequence) in tests/integration/test_workflow_choreography.py" (T100)
Task: "Partial-refund golden E2E test (partial billing + low/elevated risk → offer_partial_credit) in tests/integration/test_workflow_choreography.py" (T101)
```

## Parallel Example: User Story 3 (post-foundational)

```bash
# Unit tests (own file) parallel with integration scenario tests:
Task: "Reaper clock-injected unit tests in apps/agents/customer_resolution/tests/test_reaper.py"   (T016)
Task: "Timeout-escalation integration test in tests/integration/test_workflow_choreography.py"      (T017)
# then implement:
Task: "Reaper loop in apps/agents/customer_resolution/reaper.py"                                     (T021)
```

---

## Parallel Example: Workflow Scenario Fixtures (Phase 2A)

```bash
# After scaffolding (T035→T036→T037), author all nine scenario modules in parallel — each is its own file:
Task: "happy_path_full_refund fixture in tests/integration/fixtures/workflow_scenarios/happy_path_full_refund.py"   (T038)
Task: "partial_refund fixture in tests/integration/fixtures/workflow_scenarios/partial_refund.py"                   (T039)
Task: "billing_denied fixture in tests/integration/fixtures/workflow_scenarios/billing_denied.py"                   (T040)
Task: "high_risk_escalation fixture in tests/integration/fixtures/workflow_scenarios/high_risk_escalation.py"       (T041)
Task: "billing_timeout fixture in tests/integration/fixtures/workflow_scenarios/billing_timeout.py"                 (T042)
Task: "risk_timeout fixture in tests/integration/fixtures/workflow_scenarios/risk_timeout.py"                       (T043)
Task: "duplicate_ticket_event fixture in tests/integration/fixtures/workflow_scenarios/duplicate_ticket_event.py"   (T044)
Task: "duplicate_peer_result_event fixture in .../duplicate_peer_result_event.py"                                   (T045)
Task: "unknown_case_result fixture in tests/integration/fixtures/workflow_scenarios/unknown_case_result.py"         (T046)
# then T047 registry → T048 validation (both gate on the nine landing).
```

---

## Parallel Example: User Story 6 (startup scripts)

```bash
# After the shell helpers land (T050→T051→T052), these touch disjoint concerns and run in parallel:
Task: "resolve_topics() topic resolver in scripts/lib/common.sh"                         (T053)
Task: "--with-http optional HTTP A2A surfaces in scripts/start-local-system.sh"          (T058)
Task: "shellcheck all three scripts"                                                     (T061)
Task: "Document one-command workflow in README.md + quickstart §B"                        (T063)
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1 Setup → Phase 2 Foundational (config, store query, deadline rooting, multi-agent harness).
2. Phase 3 US1 → ticket → terminal decision end-to-end with audit trail.
3. **STOP and VALIDATE**: run T007–T009; demo a single ticket → `approve_refund`.

### Incremental Delivery

1. Foundation ready → 2. US1 (MVP, headline path) → 3. US2 (correlated async aggregation) →
4. US3 (failure paths + reaper — the only new agent logic) → 5. US4 (replay/idempotency) →
6. US5 (trace tool) → 7. Polish (decentralization proof + quickstart/SC-008).

### Parallel Team Strategy

After Foundational: Dev A on US1/US2 (handler verification + scenario tests), Dev B on US3 (reaper),
Dev C on US4 (replay harness) and US5 (trace tool). US3 owns the `agent.py`/`reaper.py` edits to avoid
file conflicts.

---

## Notes

- This feature adds **no new event contract, no new topic, no new dependency** (plan + Constitution V) — most tasks verify/wire reused 003/004/005 components; new code is the reaper (T021), store query (T003), config (T002), replay harness (T027), trace tool (T029/T030), and the orchestration-free startup/stop scripts (US6, T050–T063).
- **US6 startup scripts (T050–T063)** are pure operational tooling under `scripts/` — they launch the existing `demo-*` console entrypoints over `infra/local/docker-compose.yml`, introduce **no supervisor/orchestrator process** (Constitution I, FR-021), and add no agent source. They reserve `:8080` for Kafka UI and assign HTTP A2A ports billing=`8101`/risk=`8103` to resolve the existing `:8080` collision.
- **US8 portfolio demo (T200–T210)** adds a root `Makefile` `demo-refundops` target + an `apps/api/run_demo.py` driver that auto-publishes one sample ticket (no manual Kafka) and prints the causal audit timeline + final decision in a portfolio-friendly format; it introduces **no supervisor/orchestrator** (Constitution I, FR-021) and reuses US6 scripts, the US5 trace tool, and the Phase 2C audit-timeline builder.
- `[P]` = different files, no incomplete dependencies. Same-file `[P]` test tasks = separate functions in `test_workflow_choreography.py`.
- Verify each test FAILS before implementing the code it covers.
- Commit after each task or logical group; stop at any checkpoint to validate a story independently.
