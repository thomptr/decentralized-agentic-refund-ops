# Implementation Plan: Decentralized Workflow & Event Choreography

**Branch**: `006-workflow-choreography` | **Date**: 2026-06-10 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/006-workflow-choreography/spec.md`

## Summary

Make the whole RefundOps system run **end-to-end with no central orchestrator**: a
`support.ticket.created` event triggers the Customer Resolution Agent, which independently requests a
billing-eligibility opinion and a fraud-risk opinion via A2A; the Billing and Risk agents publish their
own result events to Kafka; the resolution agent correlates the asynchronous results by `correlation_id`
(case) and `task_id` (slot), applies the existing deterministic decision rule, and emits exactly one
terminal decision plus the case-lifecycle events — and the case is replay-safe, idempotent, bounded by a
deadline, and traceable from a single correlation id.

A code walk of 003–005 shows the choreography is **~90% already implemented** (intake → triage →
delegation → dual-path result aggregation → deterministic decision → exactly-one-decision guards →
per-step audit → event/task/case idempotency). This feature is **integration and choreography, not new
domain logic** (spec Assumption "Reuse, not rebuild"; Constitution Principle V). It closes five concrete
gaps:

1. **Timeout reaper** — `ResolutionCase.deadline_at` is currently *recorded but not enforced*; add a
   fourth concurrent loop in `ResolutionService` that escalates cases past their deadline (FR-017,
   SC-004). This is the only meaningful new agent logic.
2. **Replay harness + replay tests** — re-process a recorded scenario into a fresh store/consumer-groups
   and assert an identical decision with zero extra side-effects (FR-014–016, SC-003/006).
3. **End-to-end multi-agent integration tests** — drive the three real agents over a testcontainers
   broker across every user story and success criterion (US1–US5, SC-001/002/007/008).
4. **Causal trace tool** — reconstruct a case's journey in causation order from one correlation id
   (FR-023, US5, SC-005).
5. **Runnable demo wiring** — quickstart that starts the three agents, injects a ticket, and traces it
   (SC-008).

No new event contract, no new topic, and **no new dependency** are introduced.

## Technical Context

**Language/Version**: Python 3.12 (single version per constitution; matches 001–005).

**Primary Dependencies** (all already present — **no new dependency**): `pydantic` v2 (reused
payloads/case models), `aiokafka` (via the existing `Publisher`/`Consumer`), `structlog` (per-step
logging), `agent_foundation.runtime` (`AgentRuntime`, `A2AClient`, discovery), `pytest`,
`pytest-asyncio`, `testcontainers[kafka]`.

**Reasoning approach**: Deterministic, rule-based throughout (existing `decide()` truth table). No LLM /
Bedrock is introduced; replay determinism depends on this purity (research R2/R3).

**Storage**: Kafka for transport/audit/replay (reused). Resolution case working state is the existing
in-process `InMemoryCaseStateStore` keyed by `correlation_id`; durability across restart remains a
documented PoC gap. 006 adds one read query (`list_timed_out_cases`) behind the same `CaseStateStore`
Protocol.

**Testing**: `pytest` + `pytest-asyncio`; live Kafka via `testcontainers` following the existing
`tests/integration/test_demo_agents_*.py` harness pattern. New: reaper unit tests (clock-injected),
`test_workflow_choreography.py` end-to-end suite, and replay/trace assertions.

**Target Platform**: Local developer workstation, Docker single-broker Kafka. AWS Bedrock AgentCore
remains a forward-compatible future target (out of scope).

**Project Type**: Single Python project. Changes are confined to
`apps/agents/customer_resolution/` (reaper + store query + config), two read-only tools under
`apps/api/`, and `tests/`. The `src/agent_foundation` library and the billing/risk agents are reused
**unchanged**.

**Performance Goals**: PoC/demo scale. Happy path ticket → decision well under the SC-008 30s budget on a
single broker (two concurrent A2A round-trips). Concurrency target: tens of in-flight cases (SC-002 uses
≥10).

**Constraints**: Local-only; single broker; no auth/TLS/HA. A missing opinion escalates rather than
deciding on partial info (refund-safety default). The reaper introduces a wall-clock dependency confined
to the timeout path; completed-run replay neutralizes it for determinism (research R2). New config knobs:
`CASE_DEADLINE_SECONDS`, `REAPER_TICK_SECONDS` (both with defaults, both test-overridable).

**Scale/Scope**: 1 new store query + 1 reaper loop + 2 config constants in the resolution agent; 2
read-only operator tools (`trace_case.py`, replay helper); 1 end-to-end integration test module + reaper
unit tests. Zero new contracts/topics/dependencies.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Agent Autonomy | ✅ PASS | **No new agent, no supervisor, no router, no orchestrator** is introduced (FR-021). The timeout reaper is an internal loop of the resolution agent acting only on **its own** cases — the same agent that opened them — not a separate coordinator. The replay harness and trace tool are **read-only** utilities that consume recorded events and direct nothing. Domain isolation is untouched: billing/risk logic stays in their agents; the resolution agent still reads no billing/fraud store and learns facts only via peer results. Existing `test_no_supervisor.py` / `test_no_router.py` guards remain authoritative. |
| II. Event-Driven Coordination | ✅ PASS | All coordination remains Kafka events (ticket intake, A2A task requests to peer endpoint topics, peers' own result events, the shared `task.result` topic, decision + lifecycle events, audit). The reaper triggers off **internal case state + a clock**, not a back-channel call, and resolves by emitting the same Kafka decision event. No synchronous agent-to-agent invocation is added. |
| III. Idempotency & Safety | ✅ PASS | Re-processing yields the same outcome with no duplicate side effects via three reused layers — event-level (`IdempotencyTracker` per group), task-level (stable `uuid5` `task_id`), and case-level (`DECIDED`/terminal guard ⇒ exactly one decision). The reaper routes through the same `_apply_decision` guard, so it cannot double-decide (FR-013/FR-019). Replay tests *prove* SC-006 ("zero duplicate opinions/requests/decisions"). |
| IV. Observability-First | ✅ PASS | Every step already emits a structured log + `agent.audit.v1` record (actor, event id, correlation, causation, outcome). 006 adds the **operator-facing causal trace** that turns this trail into a one-command, code-free reconstruction of a case (FR-022/FR-023, SC-005), and audits the reaper's timeout escalation with reason `analysis_timeout`. |
| V. PoC Scope Discipline | ✅ PASS | **No new dependency, no new transport, no new event contract, no new topic.** The feature is the minimum integration needed to prove the hypothesis end-to-end: one enforcement loop, one store query, two read-only tools, and tests. Simpler-but-insufficient alternatives (per-case timers, offset-ordered trace, blocking aggregation) are rejected with rationale in `research.md`. No Complexity Tracking violations. |

**Re-check after Phase 1 design**: ✅ PASS — Phase 1 adds no third-party dependency, no new transport,
no second audit path, and no new event schema. The only code deltas are an additive store query, an
internal reaper loop with injectable clock/config, and two read-only utilities. All five principles
remain satisfied; Complexity Tracking stays empty.

## Project Structure

### Documentation (this feature)

```text
specs/006-workflow-choreography/
├── plan.md              # This file (/speckit-plan output)
├── research.md          # Phase 0 output — reuse audit + R1–R8 decisions
├── data-model.md        # Phase 1 output — entity mapping + additive deltas (D1–D3)
├── quickstart.md        # Phase 1 output — automated + manual end-to-end validation
├── contracts/           # Phase 1 output
│   ├── choreography.md                 # end-to-end topic/emitter/consumer + correlation rules
│   ├── timeout-and-failure-paths.md    # reaper behaviour + failure→terminal-outcome table
│   ├── replay-and-trace.md             # replay harness + causal trace tool contracts
│   └── decision-rule.md                # combined decision rule (reuses 003 decision-policy.md)
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
src/agent_foundation/                 # REUSED UNCHANGED (001 + 002)
├── envelope.py                        # EventEnvelope (correlation_id, causation_id, event_id)
├── idempotency.py                     # IdempotencyTracker (event-level dedup)
├── transport/{publisher,consumer}.py  # publish/consume; Consumer.seek_to_beginning() drives replay
├── runtime/{runtime,client,discovery,agent_card}.py   # A2A peer delegation + discovery
├── payloads/task.py                   # TaskRequest / TaskResult / TaskError
└── audit/store.py                     # write_audit / query_by_correlation (trace tool builds on this)

packages/contracts/                    # REUSED UNCHANGED — no new payload/topic
├── topics.py                          # existing topic constants (choreography.md references them)
└── events/payloads.py                 # SupportTicket / Billing / Risk / Decision / Drafted payloads

apps/agents/customer_resolution/       # the only agent modified
├── config.py                          # (modified) + CASE_DEADLINE_SECONDS, REAPER_TICK_SECONDS
├── models.py                          # REUSED (deadline_at, TimeoutStatus, build_timeout_status)
├── state_store.py                     # (modified) + list_timed_out_cases() on Protocol + impl (D1)
├── reaper.py                          # (new) timeout sweep loop; injectable clock; routes via _apply_decision
├── event_handlers.py                  # REUSED (intake/result/billing/risk handlers, _apply_decision)
├── decision_engine.py                 # REUSED UNCHANGED (Row 1 analysis_timeout already supported)
├── a2a_handlers.py                    # REUSED UNCHANGED (delegation, stable uuid5 task_id)
└── agent.py                           # (modified) add reaper as a 5th gathered task in serve()

apps/agents/billing_entitlement/  apps/agents/risk_fraud/    # REUSED UNCHANGED (peers + their result publishes)

apps/api/
├── dev_publish_ticket.py              # REUSED — ticket intake for the demo
├── dev_consume_events.py              # REUSED — raw event observation
└── trace_case.py                      # (new) causal-ordered trace from one correlation_id (D3, FR-023)

tests/
├── integration/
│   ├── test_workflow_choreography.py  # (new) end-to-end across the 3 real agents (US1–US5, SC-001/002/007/008)
│   └── test_no_router.py              # REUSED guard (no orchestrator emerges)
└── (resolution unit tests) apps/agents/customer_resolution/tests/
    ├── test_reaper.py                 # (new) clock-injected timeout-sweep unit tests
    └── test_no_supervisor.py          # REUSED guard
```

**Structure Decision**: Keep all change inside the resolution agent (it owns case liveness) plus two
read-only `apps/api` utilities and tests. The `agent_foundation` library, the billing/risk agents, and
every event contract are reused **unchanged**, honoring Principle V (no library/contract growth) and the
spec's "Reuse, not rebuild" assumption. The reaper is isolated in its own module so its clock-driven
logic is unit-testable without Kafka.

## Architecture Decision: Timeout enforcement as an internal reaper loop

003 shipped the case deadline as *recorded but not enforced*. 006 makes it enforceable by adding a fourth
concurrent task to `ResolutionService.serve` (alongside the runtime, intake, result, billing, and risk
loops). The reaper periodically queries `store.list_timed_out_cases(now)` and resolves each stuck case
through the **existing** `_apply_decision` path with `TimeoutStatus(any_missing=True,
deadline_exceeded=True)`, yielding `escalate_human` / `analysis_timeout`. Because it reuses the
`DECIDED`/terminal guard and the store's `asyncio.Lock`, it cannot double-decide a case that just received
its final result. The clock and deadline are injectable so timeouts are deterministic in tests and
neutralizable for completed-run replay. Rejected alternatives (per-case `asyncio.sleep` timers; a
standalone "timeout service"; deciding on partial info) are recorded in `research.md` R1/R8.

## Complexity Tracking

> No Constitution Check violations. 006 adds no new dependency, no new transport, no new event contract,
> and no new topic; it closes integration gaps with one enforcement loop, one store query, two read-only
> tools, and tests. Table intentionally empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |
