# Phase 0 Research: Demo UI — A2A Card & Audit Aggregator

All "NEEDS CLARIFICATION" items from the Technical Context are resolved below. Each entry records the
decision, rationale, and rejected alternatives.

---

## R1. Agent roster source & "latest card" semantics

**Decision**: Read the roster with `agent_foundation.runtime.discovery.discover_agents(broker_url)`,
which consumes the compacted topic `local.agent.agent-card.published.v1` from earliest and returns the
latest `AgentCard` per `agent_id` (the topic is keyed by `agent_id`, latest-wins).

**Rationale**: FR-001/FR-003 require the most-recent card per agent with no stale duplicates — exactly
the compaction + latest-wins behavior `discover_agents` already implements. No new code or topic.

**Alternatives rejected**: HTTP-only discovery via `GET /.well-known/agent.json` was rejected as the
*primary* source because customer-resolution is Kafka-only (no HTTP surface), so a Kafka roster is the
one source covering all three agents. HTTP is reused only for liveness (R3).

---

## R2. "Last announced" timestamp (not on AgentCard)

**Decision**: `AgentCard` itself carries no announce time. The discovery **envelope** does
(`EventEnvelope.timestamp`). The UI aggregator runs a thin reader (same aiokafka pattern as
`discover_agents`) that keeps, per `agent_id`, both the latest `AgentCard` **and** the envelope
`timestamp` of that latest card → `last_announced`.

**Rationale**: The spec's Agent Card entity lists "the time it was last announced," and the edge case
"stale agent card" needs a last-seen signal. The envelope timestamp is the available, honest source.

**Alternatives rejected**: Adding a field to `AgentCard` (changes a frozen foundation contract for a
UI concern — violates "no new contract"); fabricating a timestamp at read time (dishonest, would reset
every poll).

---

## R3. Liveness / "currently live" vs. "last announced"

**Decision**: Surface two distinct signals and never present stale as live (FR / edge case
"stale agent card"):
- **Announced**: card present in the compacted topic + `last_announced` (R2). Always available.
- **Live (best-effort)**: for agents exposing HTTP (billing `:8101`, risk `:8103`), probe
  `GET /ping` (or `/.well-known/agent.json`) with `httpx` and a short timeout. Customer-resolution is
  Kafka-only → no live probe; its liveness is shown as "announced (no health endpoint)".

**Rationale**: The spec explicitly wants the UI to "distinguish last-announced cards from currently
live agents to the extent the available signals allow." HTTP `/ping` already exists on the two HTTP
agents (`apps/agents/*/http_app.py`). Probes are best-effort and failures degrade to "unknown," never
crash (FR-016).

**Alternatives rejected**: A heartbeat/liveness topic (new contract + agent change, out of scope);
treating card-presence as "live" (dishonest — a stopped agent's compacted card persists).

---

## R4. Case timeline — causal ordering reuse

**Decision**: Build the timeline by calling `query_by_correlation(broker, correlation_id)` →
`[r.original_envelope for r in records]` → `trace_case(correlation_id, envelopes)` from
`apps/agents/customer_resolution/trace.py`. Render the returned `TraceStep` list directly.

**Rationale**: FR-006 + Assumption "causal ordering reuses existing semantics" require UI and CLI to
tell the same story. `trace_case` already implements causation-then-time ordering, earliest-root
fallback, sibling tie-break by timestamp, and orphan append (root / "parent not found") — covering the
out-of-order and orphan edge cases for free. `apps/api/trace_case.py` uses the identical pipeline.

**Alternatives rejected**: Re-implementing ordering in the UI (divergence risk, duplicate logic);
ordering by timestamp only (fails the causal-order acceptance scenarios).

---

## R5. Audit stream source, dedup, and filtering

**Decision**: Source the cross-case stream from `consume_all_audit_records(broker)` (full audit topic).
The aggregator: (a) **dedups by `original_envelope.event_id`** keeping first-seen (FR-015, SC-005);
(b) sorts **newest-first** by `original_envelope.timestamp` (FR-010); (c) applies in-memory filters by
acting agent (`original_envelope.agent_id`), event type (`original_envelope.event_type`), and case
(`original_envelope.correlation_id`), individually or combined (FR-011); (d) exposes each row's
`correlation_id` so the UI can deep-link to the case timeline (FR-013).

**Rationale**: The audit topic is the system's authoritative, replay-safe record and is compacted, so a
full read yields one logical record per audit event. Dedup-by-event-id makes idempotent replays appear
once. Filters are cheap in-memory operations at demo volume.

**Alternatives rejected**: Subscribing to each domain topic separately (more topics, manual merge, no
single dedup key); a stateful incremental cursor (premature optimization — see R6).

---

## R6. "Live" refresh mechanism & polling cost

**Decision**: HTMX `hx-trigger="every 5s"` polling on the roster and stream partials (and on an open
case view). Each poll re-reads from Kafka via the aggregator and re-renders the partial. Target ≤5 s
(SC-003). A tiny in-process cache holds only the most recent poll result to smooth concurrent viewers.

**Rationale**: Assumption "Refresh over streaming" — periodic polling is explicitly acceptable; no hard
real-time push channel required. HTMX gives partial-refresh-without-full-reload using HTML attributes
only, keeping the stack Python-only (no JS framework/build). `consume_all_audit_records` re-reading the
whole compacted topic each poll is acceptable at demo volume.

**Alternatives rejected**: WebSocket/SSE push (more moving parts than SC-003 needs — Principle V);
full-page reload (fails FR-012 "without a manual full reload" intent and is jarring on a demo screen);
a persisted offset cursor (premature; documented as a future optimization, not needed for the PoC).

---

## R7. Robustness to malformed / late / duplicate / orphan events (FR-016)

**Decision**: The aggregator treats parsing defensively: records that fail `AuditPayload` validation
are skipped at the source helpers (already true in `consume_all_audit_records` /`discover_agents`,
which swallow per-record parse errors). `trace_case` already places missing-parent events as orphans
(root / "parent not found") and never raises on absent causal parents. The view layer renders an
explicit empty state when `query_by_correlation` returns `[]` (FR-009) and "waiting for agents" /
"no cases yet" when discovery/stream are empty (edge case "No data yet").

**Rationale**: Honest-but-degraded display is mandated by FR-016 and the edge cases. The reused helpers
already fail soft per-record; the UI's job is to surface absence/abnormality, not hide it.

**Alternatives rejected**: Hard validation that drops a whole case on one bad record (hides data);
crashing on missing causal parent (violates FR-016).

---

## R8. Bounded demo trigger — boundary & safety

**Decision**: Expose one write endpoint that publishes a single root `support.ticket.created`
`EventEnvelope` (fresh `correlation_id`, `causation_id=None`) using the existing publish path from
`apps/api/dev_publish_ticket.py` (`Publisher.publish` + `SupportTicketCreatedPayload` +
`topic_for("support","ticket","created")`). It accepts demo-friendly fields (amount, currency, reason,
optional ticket/customer ids) with sensible defaults, returns the new `correlation_id`, and the UI then
deep-links to that case's timeline. It publishes **nothing else** — no task-request, no result, no
routing.

**Rationale**: Resolves the spec/instruction divergence per the user's decision to include a bounded
trigger. Emitting a root domain event is intake, not orchestration; agents react autonomously exactly
as they do for the CLI tool, so Principles I/II hold (see Constitution Check + Complexity Tracking).

**Alternatives rejected**: Publishing a `refund-review.requested` / A2A task from the UI (would make the
UI a router — forbidden); no trigger at all (rejected by the user; harms the single-screen demo).

---

## R9. Packaging, port, and startup integration

**Decision**: New `apps/ui/` package with a `demo-ui` console script (`apps.ui.server:run`) on
**PORT 8200** (free: Kafka-UI 8080, billing 8101, risk 8103). Add a `ui` optional extra
(`fastapi`, `uvicorn[standard]`, `jinja2`, `httpx`). Extend `scripts/start-local-system.sh` to launch
it as a fourth background service via the existing `start_agent` helper (PID/log under `.local-run/`),
defaulting on or behind the existing pattern, with the broker URL inherited from `AGENT_BROKER_URL`.

**Rationale**: FR-017 ("runnable as part of the existing local-system startup"). Mirrors the existing
HTTP agent convention (`http_app.py` + uvicorn `run()` + console script) for consistency.

**Alternatives rejected**: A separate standalone launcher (fails the one-command-demo goal); reusing an
agent's port (collision).

---

## Summary of decisions

| # | Topic | Decision |
|---|-------|----------|
| R1 | Roster source | `discover_agents()` over compacted card topic; latest-per-agent |
| R2 | Last-announced | Thin reader keeps card + envelope `timestamp` |
| R3 | Liveness | HTTP `/ping` probe for billing/risk; announced-only for customer-resolution |
| R4 | Timeline order | Reuse `trace_case()` (causation-then-time) — UI == CLI |
| R5 | Stream | `consume_all_audit_records()`, dedup by `event_id`, newest-first, in-memory filters |
| R6 | Refresh | HTMX 5 s polling of partials; tiny last-poll cache |
| R7 | Robustness | Soft-fail per record; explicit empty/orphan states |
| R8 | Demo trigger | One POST → root `support.ticket.created` only; reuse existing publish path |
| R9 | Packaging | `apps/ui/`, `demo-ui` on :8200, `ui` extra (+Jinja2), wired into start script |
