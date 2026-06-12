# RefundOps Demo UI — View Guide

A companion to [`README.md`](./README.md) (which covers running and configuration).
This document explains **what each view is for** and **how it works** mechanically:
where its data comes from, which module renders it, and the behaviours worth knowing.

The UI is a **read-only observer** of the decentralized system. It never routes work,
requests A2A tasks, or supervises agents. The single exception is the Demo trigger,
which publishes exactly one root event to *start* a case (intake, not orchestration).

## Navigation

`app.py` is a thin Streamlit shell. The sidebar radio picks one of four views, and the
URL stays in sync via query params so views are deep-linkable:

- `?view=roster | stream | trigger`
- `?case=<correlation_id>` → opens the Case timeline for that case (takes precedence).

All live views re-render on a timer (`@st.fragment(run_every=REFRESH_SECONDS)`, default 5s).
If the broker or agents are down, every view degrades to an honest empty/"waiting" state
rather than crashing (FR-016).

## How the UI reads data (shared mechanics)

Each view is **pure presentation** over a `build_*()` function in a sibling data module —
the views contain no business logic (enforced by `tests/unit/demo_ui/test_no_business_logic.py`).

| View | Renders | Data module / entry point | Source |
|------|---------|---------------------------|--------|
| Roster | `roster_view.py` | `agent_cards.build_roster()` | compacted discovery topic + HTTP `/ping` |
| Case timeline | `case_view.py` | `timeline.build_timeline()` → `trace_case()` | audit topic, by `correlation_id` |
| Audit stream | `stream_view.py` | `event_stream.build_stream()` | audit topic, all cases |
| Demo trigger | `trigger_view.py` | `ticket_form.publish_demo_ticket()` | **writes** one ticket event |

Two shared helpers in `config.py` make the async Kafka reads usable from synchronous
Streamlit code:

- **`run_async(coro, timeout=READ_TIMEOUT_SECONDS)`** — runs an async read to completion
  in a fresh event loop, bounded so a dead broker degrades promptly instead of hanging.
- **`cached_call(key, factory, ttl=REFRESH_SECONDS)`** — a short-TTL in-process cache so
  multiple reruns within one refresh window reuse the last read. The Roster opts into
  `stale_while_revalidate=True`: it serves the last-good value instantly and refreshes in
  a background thread, so a slow read never blocks the refresh.

---

## 1. Roster

**Purpose.** Show the three peer agents *as they advertise themselves* — proving discovery
works without a central registry. For each expected agent: identity, version, the endpoint
topic it accepts work on, its declared capabilities, and a liveness badge.

**How it works.**
- `build_roster()` reads the **compacted** discovery topic (`local.agent.agent-card.published.v1`)
  in a single pass and keeps the latest Agent Card per `agent_id` (latest-wins compaction).
- It then probes each agent's HTTP `/ping` for liveness. Customer-resolution is Kafka-only
  (no HTTP surface) so it is never "live", only "unknown"/"not announced".
- The roster is anchored to `config.EXPECTED_AGENT_IDS`: a missing agent appears as
  **⚫ not announced** rather than being omitted. Badges: **🟢 live / ⚪ unknown / ⚫ not announced**.

**Good to know.** Agents publish their card once at startup (plus periodic re-announcement) on
a compacted topic, so a restarted UI still reconstructs the full roster by replaying the topic.
"Waiting for agents to announce their cards…" means no card is on the topic yet.

---

## 2. Case timeline

**Purpose.** For one `correlation_id`, tell the full causal story of a case:
intake → triage → review requests → Billing & Risk results → decision — in the same order as
the `trace_case.py` CLI (UI == CLI, SC-002). Failures show their reason; nothing is dropped.

**How it works.**
- `build_timeline()` reads the audit topic for that `correlation_id` (`query_by_correlation`),
  then delegates ordering to **`trace_case()`** (`apps/agents/customer_resolution/trace.py`).
- `trace_case` builds the causal tree by linking each event's `causation_id` to its parent's
  `event_id`, BFS-ordered from the root (`causation_id is None`, e.g. `support.ticket.created`).
- A peer's domain result (e.g. `billing.refund-analysis.completed`) records its cause as the
  A2A **`task_id`**, not the request's `event_id`; `trace_case` resolves those task-ids back to
  the triggering `agent.task_request` so they link instead of showing as false orphans.
- Each row shows `#`, actor, event (+ "orphan (parent not found)" when its cause truly isn't in
  the case), outcome, reason (on `failed`/`rejected`), timestamp, and `caused_by`.
- LLM reasoning records (`agent.llm.reasoning.v1`) are surfaced in a separate **redacted**
  expander — assistive summaries only, never raw prompts or PII.

**Good to know.** Open a case quickly via the "open" button in the Audit stream, or paste a
`correlation_id` (the Demo trigger prints one on submit). "No events found" means nothing has
been audited for that id yet.

---

## 3. Audit stream

**Purpose.** A single newest-first feed of every audited event across *all* cases — the live
pulse of the system, for spotting activity and jumping into a specific case.

**How it works.**
- `build_stream()` consumes the whole audit topic and **dedupes by `event_id`**, so replays
  appear once. Sorted newest-first.
- Three filters (Agent / Event type / Case) are **AND-combined** and applied in-memory over the
  cached stream, so changing a filter is instant (no re-read). The Agent and Event-type option
  lists are derived from the current stream.
- Each row has an **"open"** button that deep-links into the Case timeline for that
  `correlation_id` (`?case=…`, app-scoped rerun).

---

## 4. Demo trigger

**Purpose.** Start a case from the screen. This is the UI's **only write**: it publishes exactly
one root `support.ticket.created` envelope (`causation_id = None`) and constructs no other payload
type. The agents then react on their own — the UI issues no task requests and routes nothing.

**How it works.**
- The form collects amount, currency, reason, and optional `ticket_id` / `customer_id`, mapped
  1:1 onto `SupportTicketCreatedPayload` by `DemoTriggerRequest.to_payload()` (minting random
  `TKT-…`/`CUST-…` ids when blank).
- On submit, `publish_demo_ticket()` publishes the single envelope and returns its
  `correlation_id` / `event_id`, with a button to open the new case's timeline.

### The "Scenario (seeded billing data)" dropdown

**Why it exists.** The Billing agent only runs its rules engine for purchases it has data for.
Its `service.analyze()` calls `load_facts(purchase_reference, customer_id)`; if that returns
`None` it **short-circuits to "request more information" before the rules engine runs** — so the
interesting spans/outcomes (`policy.evaluate`, a clean `case.decision`) never happen. A ticket
with random ids has no matching record, so it always takes that short path.

The dropdown lets you publish a ticket whose ids **match seeded billing data**, so the full path
runs and you get a real approve/deny/manual-review outcome.

**How it works (mechanically).**
- The selectbox is rendered **outside** the `st.form`, so changing it triggers a rerun that
  updates the `ticket_id` / `customer_id` fields below (widgets inside a form don't update until
  submit). Picking a scenario pre-fills those fields from `_SCENARIOS`; you can still type over them.
- When Customer-resolution delegates, `build_billing_request_input()` sets
  **`purchase_reference = ticket_id`** (`a2a_handlers.py`). Billing's `load_facts()` then looks the
  ticket up in its seeded dataset — `_DATASET[purchase_reference]`, falling back to
  `_CUSTOMER_INDEX[customer_id]` (`apps/agents/billing_entitlement/mock_data.py`).
- A match → facts are found → `rules_engine.evaluate()` runs and produces a real recommendation;
  no match ("Custom") → the short-circuit above.
- The dropdown changes **nothing** about the write itself — it still publishes one
  `support.ticket.created` event; it only pre-fills which ids that ticket carries.

**Scenarios.** (`ticket_id` is the seeded purchase reference; outcomes come from the billing
rules in `mock_data.py` / `refund-policy.md`.)

| Scenario | ticket_id / customer_id | Expected billing outcome |
|----------|-------------------------|--------------------------|
| Custom (random ids) | *(blank → random)* | request more information (short-circuits before rules engine) |
| Approve — in window, paid, light usage | `PR-APPROVE` / `CUS-APPROVE` | **approve** |
| Approve — borderline (exactly 30 days) | `PR-BORDERLINE` / `CUS-BORDERLINE` | **approve** (lower confidence) |
| Deny — outside 30-day window | `PR-WINDOW-EXPIRED` | **deny** (RP-001) |
| Deny — invoice not paid | `PR-UNPAID` | **deny** (RP-002) |
| Deny — already fully refunded | `PR-ALREADY-REFUNDED` | **deny** (RP-002) |
| Deny — heavy usage | `PR-HEAVY-USAGE` | **deny** (RP-004) |
| Manual review — contradiction gate | `PR-CONTRADICTION` | **manual review** |

After publishing a seeded scenario, open the case timeline to watch the full causal chain, or
check LangFuse for the `policy.evaluate` and `case.decision` spans that the short-circuit path
skips.

---

## Read-only guarantees (summary)

- **One bounded write.** Only the Demo trigger writes, and only one root `support.ticket.created`
  envelope per submit.
- **No business logic in the UI.** Views display recorded outcomes; they never re-derive a
  decision or score.
- **UI == CLI.** The timeline reuses `trace_case` verbatim.
- **Never crashes on bad data.** Malformed / late / duplicate / orphaned events and broker
  outages degrade to honest empty states.

See [`README.md`](./README.md) for run commands, env configuration, and the module layout.
