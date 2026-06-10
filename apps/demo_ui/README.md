# Demo UI — A2A Card & Audit Aggregator

A **read-only** Streamlit dashboard that makes the decentralized RefundOps system
observable without code inspection or broker tailing. It is an *observer*: it never
routes work, requests A2A tasks, or supervises agents — preserving the
no-supervisor / no-central-router guarantee.

## Run

```bash
uv sync --extra ui
uv run demo-ui                       # serves on http://localhost:8200
# or, directly:
streamlit run apps/demo_ui/app.py --server.port 8200
```

As part of the full local stack (Redpanda + three agents + this UI):

```bash
bash scripts/start-local-system.sh --with-http --with-ui
# UI:        http://localhost:8200
# Kafka UI:  http://localhost:8080
bash scripts/stop-local-system.sh
```

The UI **runs independently** — start it with no broker or agents up and it shows
honest empty/degraded states rather than crashing.

## Views

| View | What it shows |
|------|---------------|
| **Roster** | The three peer agents as they advertise themselves over the discovery topic: identity, version, accepting endpoint, capabilities, and a liveness badge (🟢 live / ⚪ unknown / ⚫ not announced). A missing agent appears as *not announced* rather than being omitted; only the latest card per agent is shown. |
| **Case timeline** | For a `correlation_id`, the full causal timeline (intake → triage → review requests → Billing & Risk results → decision), ordered by reusing `trace_case` so the UI matches the `trace_case.py` CLI exactly. Failures show their reason; orphaned events are flagged, never dropped. |
| **Audit stream** | A newest-first, cross-case audit feed deduped by `event_id` (replays appear once), with AND-combined agent / event-type / case filters and a per-row deep-link into the case timeline. |
| **Demo trigger** | Starts a case from the screen — see below. |

All live views auto-refresh every `REFRESH_SECONDS` (default 5).

## Guarantees

- **Read-only, except one bounded write.** The *only* write is the demo trigger,
  which publishes exactly **one** root `support.ticket.created` envelope
  (`causation_id = None`). It constructs no other payload type and emits no
  task-request, result, audit, or agent-card event. Starting a case is intake,
  not orchestration.
- **No business decision logic.** The UI reads recorded outcomes and displays
  them; it never re-derives a decision or score. Enforced by the guard test
  `tests/unit/demo_ui/test_no_business_logic.py`.
- **UI == CLI.** The timeline reuses `trace_case` verbatim, so it tells the
  identical causal story as the CLI.
- **Never crashes on bad data.** Malformed / late / duplicate / orphaned events
  and broker outages degrade to honest empty states.

## Configuration (env)

| Variable | Default | Purpose |
|----------|---------|---------|
| `AGENT_BROKER_URL` | `localhost:9092` | Kafka broker (shared with the agents). |
| `UI_PORT` | `8200` | Streamlit port. |
| `REFRESH_SECONDS` | `5` | Live-view auto-refresh interval. |
| `BILLING_PING_URL` / `RISK_PING_URL` | `http://localhost:8101/ping` / `:8103/ping` | Per-agent liveness probe (customer-resolution is Kafka-only → never probed). |
| `READ_TIMEOUT_SECONDS` | `6.0` | Upper bound on a single Kafka read so a dead broker degrades promptly. |

## Layout

```
apps/demo_ui/
  app.py            # Streamlit shell + sidebar nav + query-param deep-links
  config.py         # config + async→sync bridge + short-TTL poll cache
  agent_cards.py    # build_roster()    — RosterEntry / CapabilityView (US1)
  timeline.py       # build_timeline()  — TimelineEntry / TimelineView (US2)
  event_stream.py   # build_stream()    — StreamEvent / StreamView (US3)
  ticket_form.py    # publish_demo_ticket() — the only write (bounded trigger)
  launcher.py       # `demo-ui` console-script entry point
  views/            # pure presentation (one render() per view)
```

Tests: `tests/unit/demo_ui/` (no broker required) and
`tests/integration/demo_ui/` (`-m integration`, testcontainers Kafka).
