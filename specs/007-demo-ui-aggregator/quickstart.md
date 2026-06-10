# Quickstart & Validation: Demo UI — A2A Card & Audit Aggregator

> **Stack note (reconciled — see plan.md banner):** the UI is implemented as a **Streamlit**
> app at `apps/demo_ui/` (per the tasks.md "Stack override"), **not** the FastAPI/`apps/ui`
> HTTP service the original plan/contracts describe. Navigation is a sidebar + query-param
> deep-links (`?view=case&case=<id>`), not HTTP routes. The scenarios and success criteria below
> are unchanged; only the access mechanics are Streamlit.

Runnable scenarios that prove the feature end-to-end. Commands target the local WSL/Linux environment
with Docker Redpanda. See [plan.md](./plan.md) for design and [data-model.md](./data-model.md) for shapes.

## Prerequisites

```bash
# from repo root
uv sync --extra dev --extra http --extra ui   # installs streamlit, httpx, test tooling
```

## Setup — bring up the system + UI

```bash
# Starts Redpanda + the three agents (HTTP surfaces) + the demo UI (port 8200) as a 4th observer.
bash scripts/start-local-system.sh --with-http --with-ui
# UI:        http://localhost:8200
# Kafka UI:  http://localhost:8080
```

Stop everything with `bash scripts/stop-local-system.sh`. The UI also runs standalone
(`uv run demo-ui`) with no broker/agents — it shows honest empty states, never crashes.

---

## Scenario 1 — Agent roster & capabilities (Story 1 / SC-001)

1. Open `http://localhost:8200` (the **Roster** view is the default landing page).
2. **Expect**: three agent cards — `customer-resolution-agent`, `billing-entitlement-agent`,
   `risk-fraud-agent` — each showing name, description, version, accepting-endpoint topic, and its
   advertised capabilities (name + description + tags). Billing and Risk show 🟢 **live**;
   Customer-Resolution shows ⚪ **unknown** (Kafka-only, no health endpoint).
3. **Missing-agent check**: stop one HTTP agent. Within one refresh, it flips to ⚪ `unknown`; an agent
   whose card never published shows ⚫ **not announced** rather than being omitted.
4. **No stale duplicates**: re-publishing a card (restarting an agent) shows only the latest version.

**Pass when**: a first-time viewer identifies all three agents + capabilities in ≤30 s with no code or
broker inspection (SC-001).

---

## Scenario 2 — Trace a single case end to end (Story 2 / SC-002, SC-004)

1. Start a case (use the UI's **Demo trigger** view — Scenario 4 — or the CLI):
   ```bash
   uv run python apps/api/dev_publish_ticket.py     # prints correlation_id
   ```
2. Open the **Case timeline** view and paste the `correlation_id` (or use the deep-link
   `http://localhost:8200/?view=case&case=<correlation_id>`).
3. **Expect** an ordered timeline in causal order: `support.ticket.created` →
   `customer-issue.classified` → `refund-review.requested` → (`billing.refund-analysis.completed`
   **and** `risk.review.completed` as branches of the same request) → `customer-resolution.decided`.
   Each row shows acting agent, event type, outcome, timestamp, and its `caused_by` link.
4. **Parity check**: compare with the CLI trace — they MUST match (same `trace_case` semantics):
   ```bash
   uv run python apps/api/trace_case.py <correlation_id>
   ```
5. **Failure/rejection row**: drive a case that fails a task; the failed/rejected row shows its reason.
6. **Empty case**: paste a random UUID → "no events found for this case" (not an error).

**Pass when**: the full intake→triage→two reviews→decision chain is reconstructed in correct causal
order, correctly attributed, entirely from the UI, matching the CLI (SC-002, SC-004).

---

## Scenario 3 — Live audit stream & filters (Story 3 / SC-003, SC-005)

1. Open the **Audit stream** view.
2. Trigger one or more cases (Scenario 4). **Expect** new audit rows appear within ≤5 s **without a
   manual full reload** (auto-refresh) (SC-003).
3. **Filter by agent**: select `risk-fraud-agent` → only its events remain; clear → full stream returns.
4. **Combine filters**: agent + event-type narrows further (AND).
5. **Dedup**: re-deliver/replay the same audit record → it appears **once** (SC-005).
6. **Deep-link**: click a row's **open** button → switches to the Case timeline for that
   `correlation_id` (Story 2).

**Pass when**: stream updates live within the refresh interval, dedups replays, and filters
narrow/restore correctly.

---

## Scenario 4 — Bounded demo trigger (the only write / SC-006)

1. Open the **Demo trigger** view, fill the form (amount, currency, reason, optional ids), and click
   **Publish ticket**.
2. **Expect**: the result shows the new `correlation_id` / `event_id` / `event_type`
   (`local.support.ticket.created.v1`) and offers **Open this case's timeline**.
3. **Read-only guarantee (SC-006)**: confirm the UI published *only* the root event — inspect the
   agent-task-request and result topics in Kafka UI and verify no UI-originated messages there. The UI
   process never produces a task-request or result event. (Asserted by
   `tests/unit/demo_ui/test_ticket_form.py`: exactly one publish, `causation_id is None`.)

**Pass when**: a presenter starts a case from the screen and the system proves the UI introduced zero
agent-coordination behavior beyond emitting the single root `support.ticket.created` event.

---

## Edge cases to spot-check

- **No data yet**: fresh system, no ticket → roster shows "waiting for agents"/announced agents only,
  stream and cases show empty states (no errors).
- **No broker at all**: `uv run demo-ui` with nothing else running → every view renders an honest
  empty/degraded state promptly (bounded read timeout), never a traceback.
- **Duplicate/replayed event**: re-deliver the same audit record → appears once in both timeline and
  stream (SC-005).
- **Out-of-order / orphan**: a result recorded after the decision, or referencing a missing parent →
  ordered by causal links first, time second; orphan flagged, not dropped; no crash.

## Automated validation

```bash
uv run pytest tests/unit/demo_ui -q                       # aggregator dedup/filter/ordering, trigger invariants, no-business-logic guard
uv run pytest tests/integration/demo_ui -q -m integration # testcontainers: one case end-to-end → build_timeline == trace_case, replay dedup
```

Reference: data shapes in [data-model.md](./data-model.md).
