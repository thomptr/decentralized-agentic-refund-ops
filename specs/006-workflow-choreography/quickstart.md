# Quickstart: Decentralized Workflow & Event Choreography (006)

Runnable validation that the full RefundOps workflow works end-to-end with **no orchestrator** — a ticket
enters, autonomous agents coordinate via events, and a justified terminal decision comes out with a
causally-ordered audit trail. Details live in `plan.md`, `data-model.md`, and `contracts/`.

## Prerequisites
- Python 3.12 + `uv` (deps already in `pyproject.toml`; **no new dependency** added by 006).
- Docker (local single-broker Kafka): `docker compose -f infra/local/docker-compose.yml up -d`.
- All commands run from the repo root inside WSL (`AGENT_ENVIRONMENT=local`, `KAFKA_BROKER_URL=localhost:9092`).

## A. Automated validation (primary — proves every user story & success criterion)

Run the choreography integration suite (live Kafka via testcontainers; starts the **real** billing, risk,
and resolution agents in-process). No local broker needed for this — testcontainers manages one.

```bash
uv run pytest tests/integration/test_workflow_choreography.py -m integration -v
```

Scenario → spec mapping the suite asserts:

| Scenario | Proves |
|---|---|
| Eligible + low-risk ticket → `approve_refund`, with explanation + causal audit trail | US1 AC1, SC-001 |
| Ineligible ticket → `deny_refund` (billing reason in explanation) | US1 AC2 |
| Non-refund ticket → `direct_response`, billing/risk never invoked | US1 AC3, FR-002 |
| Risk result before billing result → still correct once both present | US2 AC1 |
| ≥10 concurrent cases, interleaved results → each decision uses only its own two opinions | US2 AC2/AC3, SC-002 |
| Peer silent past `CASE_DEADLINE_SECONDS` → reaper escalates (`analysis_timeout`), case not left open | US3 AC1, FR-017, SC-004 |
| Peer returns failed/rejected → `escalate_human` (`peer_failure`) | US3 AC2, FR-018, SC-007 |
| Eligible + high risk (conflict) → `escalate_human` | US3 AC3, SC-007 |
| Malformed ticket → escalation, never dropped | FR-020 |
| Re-deliver full event set for a decided case → 0 duplicate opinions/requests/decisions | US4 AC1, SC-006 |
| Replay recorded scenario from the start → identical decision + explanation, 0 extra side-effects | US4 AC2, FR-014/015, SC-003 |
| Late opinion after terminal → recorded in audit, decision unchanged | Edge case, FR-019 |
| Trace by `correlation_id` → full causal journey reconstructed | US5 AC1, SC-005 |
| Escalated case trace shows reason + missing/failed contributor | US5 AC2 |

Also confirm the decentralization guards still pass:

```bash
uv run pytest apps/agents/customer_resolution/tests/test_no_supervisor.py tests/integration/test_no_router.py -v
```

## B. Live manual demo (proves SC-008: ticket → decision < 30s on one broker)

Terminal 1–3 — start the three autonomous agents (each is independent; order does not matter):

```bash
uv run demo-billing-entitlement      # billing-entitlement-agent
uv run demo-risk-fraud               # risk-fraud-agent
uv run demo-customer-resolution      # customer-resolution-agent (intake + aggregation + reaper)
```

Terminal 4 — inject one refund ticket (prints the `correlation_id`):

```bash
uv run python apps/api/dev_publish_ticket.py
# → {"event_id": "...", "correlation_id": "<CID>", "topic": "local.support.ticket.created.v1"}
```

Terminal 4 — reconstruct the case's causal journey from the single correlation id (US5/SC-005):

```bash
uv run python apps/api/trace_case.py <CID>
# Ordered steps: ticket received → classified → billing+risk requested → both opinions → decided → drafted
```

Expected: a terminal `customer.resolution.decided` event for `<CID>` (default sample ticket is
"charged twice" → refund path) within a few seconds, and a complete causal trace. To see the timeout
path, start only billing + resolution (leave risk down) and publish a ticket: the reaper escalates the
case (`analysis_timeout`) within `CASE_DEADLINE_SECONDS + REAPER_TICK_SECONDS`.

## C. Targeted unit/contract checks (fast, no broker)

```bash
uv run pytest apps/agents/customer_resolution/tests -q          # decision engine, state store, reaper unit tests
uv run pytest tests/unit tests/contract -q                      # envelope/A2A/payload contracts
```

## Done / acceptance
- [ ] `test_workflow_choreography.py` green — all rows in §A pass.
- [ ] No-supervisor / no-router guards green.
- [ ] Manual demo yields a terminal decision and a full causal trace from one correlation id (< 30s).
- [ ] Timeout demo escalates a stuck case within the bounded deadline + grace.
