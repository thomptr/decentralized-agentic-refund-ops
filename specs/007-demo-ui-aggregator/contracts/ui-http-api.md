# Contract: Demo UI HTTP API

The UI exposes a small HTTP surface served by FastAPI at `apps/ui/server.py` (default `:8200`). Every
endpoint is **read-only** except the single, clearly-marked demo-trigger `POST /demo/ticket`. HTML
routes return server-rendered Jinja2 pages/partials; `/api/*` routes return JSON (same data, for tests
and integration). HTMX partials are returned by the `/partials/*` routes for polling refresh.

Source-of-truth types are defined in [data-model.md](../data-model.md). Underlying event/discovery
contracts are referenced in [references.md](./references.md) and are NOT redefined here.

---

## Read endpoints

### `GET /`  → HTML
Landing page: the agent roster (Story 1). Embeds an HTMX poll of `/partials/roster` every 5 s.

### `GET /api/roster`  → JSON
Returns the aggregated roster.

```json
{
  "agents": [
    {
      "agent_id": "billing-entitlement-agent",
      "name": "Billing Entitlement Agent",
      "description": "...",
      "version": "1.0.0",
      "endpoint_topic": "local.agent.billing-entitlement-agent.task.requested.v1",
      "capabilities": [
        {"id": "analyze_refund_eligibility", "name": "...", "description": "...", "tags": ["billing","refund"]}
      ],
      "announced": true,
      "last_announced": "2026-06-10T14:05:00Z",
      "liveness": "live"
    },
    {
      "agent_id": "customer-resolution-agent",
      "name": null, "description": null, "version": null, "endpoint_topic": null,
      "capabilities": [],
      "announced": false,
      "last_announced": null,
      "liveness": "not_announced"
    }
  ]
}
```
**Rules**: Exactly one entry per expected agent (`customer-resolution-agent`,
`billing-entitlement-agent`, `risk-fraud-agent`). Not-yet-announced agents appear with
`announced=false` (FR-004). Only the latest card per agent (FR-003). `liveness ∈ {live, unknown, not_announced}`.

### `GET /partials/roster`  → HTML fragment
The roster cards only (for HTMX polling). Same data as `/api/roster`.

### `GET /case/{correlation_id}`  → HTML
Case timeline page (Story 2). Empty/`found:false` ⇒ renders an explicit "no events found for this
case" panel (FR-009), not an error.

### `GET /api/case/{correlation_id}`  → JSON
```json
{
  "correlation_id": "f1e2...",
  "found": true,
  "entries": [
    {
      "seq": 1, "actor": "dev.ticket-producer",
      "event_type": "local.support.ticket.created.v1",
      "outcome": "accepted", "reason": null,
      "timestamp": "2026-06-10T14:00:00Z",
      "caused_by": null, "task_id": null, "is_orphan": false
    },
    {
      "seq": 4, "actor": "billing-entitlement-agent",
      "event_type": "local.billing.refund-analysis.completed.v1",
      "outcome": "completed", "reason": null,
      "timestamp": "2026-06-10T14:00:03Z",
      "caused_by": "a9...", "task_id": "77...", "is_orphan": false
    }
  ]
}
```
**Rules**: `entries` are in causal order (causation-then-time) produced by `trace_case` (FR-006).
Each entry carries acting agent, event type, outcome, timestamp, and `caused_by` link (FR-007).
Failed/rejected entries MUST include `reason` (FR-008). Unknown correlation id ⇒
`{"found": false, "entries": []}` (FR-009). Orphans (missing causal parent) are flagged
`is_orphan: true`, never dropped (FR-016).

### `GET /stream`  → HTML
Live audit stream page (Story 3) with agent / event-type / case filter controls. Embeds an HTMX poll
of `/partials/stream` every 5 s.

### `GET /api/stream`  → JSON
Query params (all optional, combine with AND): `agent`, `event_type`, `correlation_id`, `limit`.
```json
{
  "events": [
    {
      "event_id": "...", "correlation_id": "...",
      "agent_id": "risk-fraud-agent",
      "event_type": "local.risk.review.completed.v1",
      "outcome": "completed", "reason": null,
      "timestamp": "2026-06-10T14:00:04Z"
    }
  ],
  "filter_agent": "risk-fraud-agent",
  "filter_event_type": null,
  "filter_correlation_id": null
}
```
**Rules**: Newest-first by `timestamp` (FR-010). Deduplicated by `event_id` — each distinct event at
most once (FR-015 / SC-005). Filters narrow the list; absent params = unfiltered (FR-011). Each row's
`correlation_id` is the deep-link target for the case timeline (FR-013).

### `GET /partials/stream`  → HTML fragment
The stream rows only (for HTMX polling); accepts the same filter query params.

### `GET /healthz`  → JSON
`{"status": "ok"}` — UI process liveness (not an agent health endpoint).

---

## The single write endpoint (bounded demo trigger)

### `POST /demo/ticket`  → JSON / redirect
The ONLY state-changing endpoint. Publishes exactly one **root** `support.ticket.created`
`EventEnvelope` (see [data-model.md](../data-model.md) `DemoTriggerRequest`/`Result`).

Request (all fields optional; defaults applied):
```json
{ "amount": 29.99, "currency": "USD", "reason": "Charged twice", "ticket_id": null, "customer_id": null }
```
Response `200`:
```json
{
  "correlation_id": "9c...",
  "event_id": "3b...",
  "event_type": "local.support.ticket.created.v1"
}
```
(For the HTML form, responds with a redirect to `/case/{correlation_id}`.)

**Hard invariants (asserted in tests — SC-006)**:
- Publishes exactly ONE envelope, of `event_type == local.support.ticket.created.v1`, with
  `causation_id == null` (root).
- MUST NOT publish to any agent task-request topic, any result topic, the audit topic, or the
  agent-card topic. No A2A task is constructed. No routing/coordination occurs.
- Returns the new `correlation_id` so the UI deep-links to that case's timeline.

---

## Cross-cutting contract rules

- **Read-only guarantee (FR-014 / SC-006)**: Apart from `POST /demo/ticket`, the UI performs no
  publishes. A contract test asserts no producer is invoked during read flows and that the trigger
  emits only the single root event.
- **Robustness (FR-016)**: Malformed/late/duplicate/orphan source records never produce a 5xx; they
  render in degraded-but-honest form (orphan flagged, duplicate collapsed, empty state shown).
- **Refresh (FR-012 / SC-003)**: HTMX polls partials on a ≤5 s interval; no manual full reload needed.
