# Feature Specification: Demo UI — A2A Card & Audit Aggregator

**Feature Branch**: `007-demo-ui-aggregator`

**Created**: 2026-06-10

**Status**: Draft

**Input**: User description: "build a Demo UI that aggregates all three A2A cards and audit events."

## Overview

A read-only demo dashboard that makes the decentralized refund-operations system observable from a
single screen. It aggregates the published capability cards of all three peer agents (Customer
Resolution, Billing/Entitlement, Risk/Fraud) and the system's audit-event stream, so a viewer can
see *who the agents are*, *what they can do*, and *what happened during a refund case* — end to end,
without reading code or tailing a broker. This directly serves the project's Observability-First
principle: "a feature is not considered complete until its audit trail is readable and end-to-end
traceable without code inspection."

The UI is an **observer**, not a participant. It does not coordinate, route, or trigger agent work,
preserving the system's no-supervisor / no-central-orchestrator guarantee.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See the agent roster and their capabilities (Priority: P1)

A person demonstrating or operating the system opens the UI and immediately sees all three agents
that have announced themselves, each shown as a card listing its identity (name, description,
version), the endpoint where it accepts work, and the capabilities it advertises. If an agent has
not announced itself, that absence is visible too.

**Why this priority**: This is the smallest slice that delivers value on its own — it proves
peer-to-peer agent discovery is working and gives a viewer the "cast of characters" before any case
is examined. It is the foundation the rest of the UI builds on.

**Independent Test**: Start the local system, open the UI, and confirm three agent cards appear with
correct names, versions, and capability lists matching what each agent publishes. Stop one agent and
confirm the UI reflects that it is no longer current/announced.

**Acceptance Scenarios**:

1. **Given** all three agents have published their cards, **When** the viewer opens the UI, **Then**
   exactly three agent cards are displayed, one per agent, each showing name, description, version,
   accepting-endpoint, and the list of advertised capabilities (with capability names and tags).
2. **Given** only two of three agents have published cards, **When** the viewer opens the UI,
   **Then** the two announced agents are shown and the third is shown as not-yet-announced (or its
   absence is otherwise made obvious) rather than silently omitted.
3. **Given** an agent re-publishes an updated card (e.g., new version or added capability), **When**
   the viewer refreshes, **Then** the UI shows the latest card for that agent and does not show stale
   duplicates.

---

### User Story 2 - Trace a single refund case end to end (Priority: P2)

A viewer selects a refund case (identified by its correlation id) and sees the full ordered story of
that case: the support ticket that started it, the triage/classification, the review requests sent to
Billing and Risk, the results those agents published, and the final decision — each step showing
which agent acted, what kind of event it was, when it happened, its outcome, and how it links back to
the step that caused it.

**Why this priority**: This is the core observability payoff — it demonstrates that the entire causal
chain of a decentralized workflow can be reconstructed from the audit trail alone, with no hidden
orchestrator and no code inspection. It depends on the audit data the UI already ingests for the feed.

**Independent Test**: Drive one refund case through the system, copy its correlation id into the UI,
and confirm the displayed timeline matches the known sequence of events for that case in correct
causal order, with each event attributed to the correct agent.

**Acceptance Scenarios**:

1. **Given** a completed refund case, **When** the viewer opens that case by its correlation id,
   **Then** the UI shows all audit events for that case in causal order (a triggering event always
   appears before the events it caused; ties broken by time), each labeled with acting agent, event
   type, outcome, and timestamp.
2. **Given** a case where Billing and Risk both responded, **When** the viewer inspects the timeline,
   **Then** both the Billing result and the Risk result are shown as branches caused by the same
   review request, and the final decision is shown as caused by the agent results.
3. **Given** a case that ended in a failure or rejection on one of its tasks, **When** the viewer
   inspects the timeline, **Then** the failed/rejected step is clearly marked with its reason.
4. **Given** a correlation id that has no audit events, **When** the viewer opens it, **Then** the UI
   reports that no events were found rather than showing an empty or broken view.

---

### User Story 3 - Browse and filter the live audit stream across cases (Priority: P3)

A viewer watches a continuously updating list of audit events spanning all cases, newest first, and
can filter it (by agent, by event type, and/or by case) to focus on a slice of activity. From any
event in the stream the viewer can jump to the full timeline for its case.

**Why this priority**: This turns the UI from a per-case lookup tool into a live demo surface — useful
for showing the system "breathing" during a presentation — but it is additive on top of stories 1
and 2 rather than required for them.

**Independent Test**: With the system running, drive one or more cases and confirm new audit events
appear in the stream without a manual full reload, and that applying an agent or case filter narrows
the list to matching events.

**Acceptance Scenarios**:

1. **Given** the UI is open on the audit stream, **When** new audit events are recorded by the
   system, **Then** they appear in the stream automatically (within the configured refresh interval)
   without the viewer manually reloading the whole page.
2. **Given** the stream is showing many events, **When** the viewer filters by a specific agent,
   **Then** only events emitted by that agent remain visible, and clearing the filter restores the
   full stream.
3. **Given** an event in the stream, **When** the viewer selects it, **Then** the UI navigates to the
   case timeline (Story 2) for that event's correlation id.

---

### Edge Cases

- **No data yet**: System just started, no agents announced and no events recorded — the UI shows
  clear empty states ("waiting for agents", "no cases yet"), not errors or blank panels.
- **Out-of-order / late events**: An agent's result event is recorded after the final decision (clock
  skew or delayed delivery) — the timeline still orders by causal links first, time second, and does
  not crash on a missing causal parent.
- **Duplicate / replayed events**: The same event id is recorded more than once (idempotent replay) —
  the UI shows it once, not duplicated.
- **Unknown / orphan event**: An audit event references a causal parent that is not present — the UI
  shows it as a root or "parent not found" node rather than dropping it.
- **Stale agent card**: An agent that published a card earlier is no longer running — the UI
  distinguishes "last announced" cards from currently live agents to the extent the available signals
  allow, and never presents stale data as definitively live.
- **Large case**: A case with a very large number of events still renders in a usable, scrollable
  form without freezing the view.

## Requirements *(mandatory)*

### Functional Requirements

#### Agent roster (Story 1)

- **FR-001**: The UI MUST aggregate and display the most recently announced capability card for each
  of the three agents (Customer Resolution, Billing/Entitlement, Risk/Fraud) in a single view.
- **FR-002**: Each agent card MUST show the agent's identifier, name, description, version, the
  endpoint at which it accepts work, and its advertised capabilities (each with name, description,
  and tags).
- **FR-003**: When an agent has published more than one card over time, the UI MUST show only the
  latest card for that agent and MUST NOT display superseded duplicates.
- **FR-004**: When an expected agent has not announced a card, the UI MUST make that absence visible
  rather than silently omitting the agent.

#### Case timeline (Story 2)

- **FR-005**: The UI MUST let a viewer retrieve all audit events for a single case identified by its
  correlation id.
- **FR-006**: The UI MUST present a case's audit events in causal order — an event that caused other
  events appears before them — using recorded time only to break ties or order events with no causal
  link.
- **FR-007**: Each timeline entry MUST display the acting agent, the event type, the outcome
  (e.g., accepted / completed / failed / rejected where applicable), the timestamp, and its link to
  the causing event.
- **FR-008**: For failed or rejected steps, the UI MUST display the associated reason.
- **FR-009**: When a requested correlation id has no audit events, the UI MUST report "no events
  found" for that case rather than rendering an empty or broken timeline.

#### Audit stream (Story 3)

- **FR-010**: The UI MUST present a chronological (newest-first) stream of audit events across all
  cases.
- **FR-011**: The UI MUST allow filtering the audit stream by acting agent, by event type, and by
  case (correlation id), individually or in combination.
- **FR-012**: The UI MUST refresh aggregated data (roster and audit stream) on a recurring basis so
  newly recorded events and newly announced cards become visible without a manual full reload.
- **FR-013**: The UI MUST allow a viewer to navigate from any event in the stream to the full case
  timeline for that event's correlation id.

#### Cross-cutting

- **FR-014**: The UI MUST be observational with respect to the agent system: it MUST NOT publish task
  requests, route work between agents, or otherwise participate in coordination. The single permitted
  exception is a **bounded demo trigger** that publishes one *root* `support.ticket.created` domain
  event (case intake) — identical to the existing `dev_publish_ticket.py` tool — so a presenter can
  start a demo case from the screen. Apart from that one root-event write, the UI only reads
  already-recorded discovery and audit data, and it MUST NOT publish any task-request, result, audit,
  or agent-card event. (See plan.md Complexity Tracking for the rationale; the no-supervisor /
  no-central-router guarantee is preserved because intake is not delegation or routing.)
- **FR-015**: The UI MUST present each distinct audit event at most once, even when the underlying
  record has been delivered or replayed more than once (deduplicate by event identity).
- **FR-016**: The UI MUST not crash or hide data when encountering malformed, late, duplicate, or
  orphaned (missing-causal-parent) events; such events MUST be surfaced in a degraded-but-honest form.
- **FR-017**: The UI MUST be runnable as part of, or alongside, the existing local system startup so a
  demonstrator can bring up agents and the UI together.

### Key Entities *(include if feature involves data)*

- **Agent Card**: A peer agent's self-published identity and capability advertisement. Attributes:
  agent identifier, name, description, version, accepting endpoint, list of capabilities, and the time
  it was last announced. The roster holds the latest card per agent.
- **Capability**: A unit of advertised functionality on an agent card. Attributes: identifier, name,
  description, tags.
- **Audit Event**: One recorded fact in the system's audit trail. Attributes: event identifier,
  correlation identifier (the case it belongs to), causation identifier (the event that triggered it,
  if any), acting agent, event type, timestamp, outcome (where applicable), and a reason (for failures
  or rejections).
- **Case**: The full lifecycle of one refund, identified by a correlation id — the set of audit events
  sharing that correlation id, from support-ticket intake through to the final decision.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With the local system running and all agents announced, a first-time viewer can open the
  UI and identify all three agents and their advertised capabilities within 30 seconds, without
  reading any source code or broker output.
- **SC-002**: Given a completed refund case's identifier, a viewer can reconstruct that case's full
  end-to-end sequence — intake, triage, the two agent reviews, and the final decision — entirely from
  the UI, with steps in correct causal order and correctly attributed to acting agents, in 100% of
  test cases.
- **SC-003**: New audit events recorded by the system become visible in the UI within the configured
  refresh interval (target: 5 seconds or less) without the viewer performing a manual full reload.
- **SC-004**: The audit trail for any case is fully readable from the UI without code inspection,
  satisfying the project's Observability-First completeness bar for this feature.
- **SC-005**: Replayed or duplicated events appear exactly once in both the case timeline and the
  audit stream (zero visible duplicates across the test suite).
- **SC-006**: The UI introduces zero new agent-coordination behavior — observation only — verified by
  confirming it publishes no task-request or result events during operation.

## Assumptions

- **Observational scope with one bounded trigger**: The UI observes already-recorded discovery and
  audit data. It additionally provides a single bounded demo trigger that publishes one root
  `support.ticket.created` event to start a demo case (see FR-014); it does nothing else that mutates
  the system. The existing case-injection CLI (`dev_publish_ticket.py`) remains available and emits the
  identical root event.
- **Local demo target**: The UI targets the existing single-node local environment for demonstration,
  for a small number of concurrent viewers. Multi-tenant access, authentication, and production
  hardening are out of scope per PoC scope discipline.
- **Three known agents**: The roster is anchored to the three agents that exist today; the UI shows
  whatever cards have been announced and flags any of the three that are missing.
- **Existing audit and discovery data are authoritative**: The UI derives the roster from the agents'
  published cards and the timeline/stream from the recorded audit trail; it does not maintain its own
  separate source of truth.
- **Refresh over streaming**: Periodic refresh/polling at a short interval is acceptable for "live"
  behavior; a hard real-time push channel is not required to meet the success criteria.
- **Causal ordering reuses existing semantics**: Case ordering follows the same causation-then-time
  ordering the system's existing causal-trace tooling uses, so UI and CLI tell the same story.

## Out of Scope

- Approving, retrying, routing, or otherwise mutating in-flight refund cases from the UI. (Starting a
  new demo case via the single bounded `support.ticket.created` trigger is in scope per FR-014; nothing
  beyond that root-event intake is.)
- Authentication, authorization, multi-tenant isolation, and any production-hardening concerns.
- Persisting a separate UI-owned datastore or analytics warehouse beyond what is needed to render
  current discovery/audit data.
- Editing or annotating audit events.
- Deployment to AWS or any environment beyond the local demo system.

## Dependencies

- The three existing agents and their self-published capability cards (Customer Resolution,
  Billing/Entitlement, Risk/Fraud).
- The system's recorded audit trail and agent-discovery data.
- The existing local-system startup flow that brings up the broker and agents.
- The existing causal-ordering semantics used to reconstruct a case from its audit events.
