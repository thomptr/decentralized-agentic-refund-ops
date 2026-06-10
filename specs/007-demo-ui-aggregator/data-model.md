# Phase 1 Data Model: Demo UI — A2A Card & Audit Aggregator

The UI introduces **no new persisted entities and no new event contracts**. It derives read-only *view
models* from existing foundation types and renders them. View models live in `apps/ui/viewmodels.py`
(Pydantic, for safe template rendering and JSON endpoints). The one write reuses the existing
`SupportTicketCreatedPayload` contract unchanged.

## Source (existing) types — reused, not modified

| Source type | Module | Key fields used |
|-------------|--------|-----------------|
| `AgentCard` | `agent_foundation.runtime.agent_card` | `agent_id, name, description, version, endpoint_topic, capabilities[], security` |
| `Capability` | `agent_foundation.runtime.agent_card` | `id, name, description, tags[]` |
| `EventEnvelope` | `agent_foundation.envelope` | `event_id, correlation_id, causation_id, agent_id, timestamp, event_type, payload` |
| `AuditPayload` | `agent_foundation.payloads.sample` | `original_envelope, outcome, reason, recorded_at, task_id` |
| `TraceStep` | `apps.agents.customer_resolution.trace` | `seq, actor, correlation_id, event_type, outcome, task_id, timestamp, caused_by` |
| `SupportTicketCreatedPayload` | `agent_foundation.payloads.support_ticket` | `ticket_id, customer_id, amount, currency, reason, created_at` |

---

## View models (NEW — `apps/ui/viewmodels.py`)

### RosterEntry  (Story 1 — FR-001..FR-004)
Latest card per expected agent, plus liveness.

| Field | Type | Source / Rule |
|-------|------|---------------|
| `agent_id` | `str` | `AgentCard.agent_id`, or the expected id when not yet announced |
| `name` | `str \| None` | `AgentCard.name` (None when not announced) |
| `description` | `str \| None` | `AgentCard.description` |
| `version` | `str \| None` | `AgentCard.version` |
| `endpoint_topic` | `str \| None` | `AgentCard.endpoint_topic` (the topic where it accepts work) |
| `capabilities` | `list[CapabilityView]` | mapped from `AgentCard.capabilities` |
| `announced` | `bool` | True iff a card exists in the compacted topic (FR-004) |
| `last_announced` | `datetime \| None` | envelope `timestamp` of the latest card (research R2) |
| `liveness` | `Literal["live","unknown","not_announced"]` | HTTP `/ping` probe result (R3); `not_announced` when `announced` is False |

**Rules**: Roster is anchored to the three expected agent ids (`customer-resolution-agent`,
`billing-entitlement-agent`, `risk-fraud-agent`). Each expected agent yields exactly one
`RosterEntry`; a missing agent is present with `announced=False` (never silently omitted). Only the
latest card is shown — no superseded duplicates (FR-003).

### CapabilityView
| Field | Type | Source |
|-------|------|--------|
| `id` | `str` | `Capability.id` |
| `name` | `str` | `Capability.name` |
| `description` | `str` | `Capability.description` |
| `tags` | `list[str]` | `Capability.tags` |

### TimelineEntry  (Story 2 — FR-005..FR-009)
One per `TraceStep`, enriched with the audit outcome/reason for that step's event.

| Field | Type | Source / Rule |
|-------|------|---------------|
| `seq` | `int` | `TraceStep.seq` (causal order position) |
| `actor` | `str` | `TraceStep.actor` (acting agent) |
| `event_type` | `str` | `TraceStep.event_type` |
| `outcome` | `str \| None` | `AuditPayload.outcome` for this event (accepted/completed/failed/rejected/duplicate_skipped) |
| `reason` | `str \| None` | `AuditPayload.reason` — shown for failed/rejected (FR-008) |
| `timestamp` | `datetime` | `TraceStep.timestamp` |
| `caused_by` | `UUID \| None` | `TraceStep.caused_by` (link to causing event) |
| `task_id` | `UUID \| None` | `TraceStep.task_id` (A2A task steps) |
| `is_orphan` | `bool` | True when `caused_by` references an event absent from the case (research R7) |

**State / ordering**: Order is whatever `trace_case` returns (causation-then-time; orphans last,
flagged). `outcome`/`reason` are joined from the `AuditPayload` whose `original_envelope.event_id`
matches the step's event. A failed or rejected step MUST display its `reason`.

### TimelineView
| Field | Type | Rule |
|-------|------|------|
| `correlation_id` | `UUID` | the requested case |
| `entries` | `list[TimelineEntry]` | empty list ⇒ render "no events found" (FR-009) |
| `found` | `bool` | False when no audit events exist for the id |

### StreamEvent  (Story 3 — FR-010..FR-013)
| Field | Type | Source |
|-------|------|--------|
| `event_id` | `UUID` | `original_envelope.event_id` (dedup key, FR-015) |
| `correlation_id` | `UUID` | `original_envelope.correlation_id` (deep-link target, FR-013) |
| `agent_id` | `str` | `original_envelope.agent_id` (acting-agent filter) |
| `event_type` | `str` | `original_envelope.event_type` (type filter) |
| `outcome` | `str \| None` | `AuditPayload.outcome` |
| `reason` | `str \| None` | `AuditPayload.reason` |
| `timestamp` | `datetime` | `original_envelope.timestamp` (newest-first sort key) |

### StreamView
| Field | Type | Rule |
|-------|------|------|
| `events` | `list[StreamEvent]` | deduped by `event_id`, sorted newest-first |
| `filter_agent` | `str \| None` | active acting-agent filter |
| `filter_event_type` | `str \| None` | active event-type filter |
| `filter_correlation_id` | `UUID \| None` | active case filter |

**Rules**: Filters combine with AND. Clearing a filter restores the full stream. Each distinct
`event_id` appears at most once across the whole view (FR-015 / SC-005).

---

## Demo trigger types (NEW — `apps/ui/demo_trigger.py`; the only write)

### DemoTriggerRequest
| Field | Type | Default | Rule |
|-------|------|---------|------|
| `amount` | `float` | `29.99` | > 0 |
| `currency` | `str` | `"USD"` | 3-letter code |
| `reason` | `str` | sample text | non-empty |
| `ticket_id` | `str \| None` | auto (`TKT-<short>`) | unique-ish for demo |
| `customer_id` | `str \| None` | auto (`CUST-<short>`) | — |

Maps directly to `SupportTicketCreatedPayload`. No other payload type may be constructed here.

### DemoTriggerResult
| Field | Type | Source |
|-------|------|--------|
| `correlation_id` | `UUID` | newly minted case id (UI deep-links to its timeline) |
| `event_id` | `UUID` | `EventEnvelope.event_id` of the published root event |
| `event_type` | `str` | `topic_for("support","ticket","created")` |

**Invariant**: `causation_id` is always `None` (root event). The trigger constructs and publishes
exactly one envelope of exactly this type — enforced by construction and asserted in tests (SC-006).

---

## Mapping summary

```text
discover_agents() ─┐
HTTP /ping probe  ─┼─► RosterEntry / CapabilityView            (Story 1)
last-announced    ─┘

query_by_correlation() ─► [original_envelope] ─► trace_case() ─► TraceStep
                                              └─ join AuditPayload(outcome,reason) ─► TimelineEntry → TimelineView   (Story 2)

consume_all_audit_records() ─► dedup(event_id) ─► sort(newest-first) ─► filter ─► StreamEvent → StreamView   (Story 3)

DemoTriggerRequest ─► SupportTicketCreatedPayload ─► Publisher.publish(causation_id=None) ─► DemoTriggerResult   (bounded write)
```
