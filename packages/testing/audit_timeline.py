"""AuditTimelineBuilder — causally-ordered timeline from EventEnvelopes.

Produces a human-readable (or JSON-serialisable) sequence of events for a
single correlation_id, ending with a synthetic terminal entry derived from
the outcome signals in the trace.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from agent_foundation.envelope import EventEnvelope
from packages.contracts.topics import (
    TOPIC_BILLING_RESULT,
    TOPIC_ISSUE_CLASSIFIED,
    TOPIC_REFUND_REVIEW_REQUESTED,
    TOPIC_RESOLUTION_DECIDED,
    TOPIC_RESPONSE_DRAFTED,
    TOPIC_RISK_RESULT,
    TOPIC_TASK_RESULT,
    endpoint_topic,
)

# ---------------------------------------------------------------------------
# Label map helpers
# ---------------------------------------------------------------------------

_TICKET_CREATED_SUFFIX = "support.ticket.created.v1"

# Static topic → label mapping (task.requested entries are handled dynamically)
_LABEL_MAP: dict[str, str] = {
    TOPIC_ISSUE_CLASSIFIED: "resolution.customer-issue.classified",
    TOPIC_REFUND_REVIEW_REQUESTED: "resolution.refund-review.requested",
    TOPIC_BILLING_RESULT: "billing.refund-analysis.completed",
    TOPIC_RISK_RESULT: "risk.review.completed",
    TOPIC_RESOLUTION_DECIDED: "resolution.customer-resolution.decided",
    TOPIC_RESPONSE_DRAFTED: "resolution.customer-response.drafted",
}


def _is_task_requested(event_type: str) -> bool:
    """Return True for any agent endpoint task.requested topic."""
    return event_type.endswith(".task.requested.v1")


def reconcile_label(envelope: EventEnvelope) -> str:
    """Map an envelope to its human-readable label string."""
    et = envelope.event_type

    # Ticket created (environment-prefixed, ends with the canonical suffix)
    if et.endswith(_TICKET_CREATED_SUFFIX):
        return "support.ticket.created"

    # Task-requested events carry target agent info in their topic
    if _is_task_requested(et) or et == TOPIC_TASK_RESULT:
        target = _extract_target_agent(envelope)
        return f"audit.agent-task.requested {target}" if target else "audit.agent-task.requested"

    return _LABEL_MAP.get(et, et)


def _extract_target_agent(envelope: EventEnvelope) -> str | None:
    """Best-effort extraction of the target agent from payload or topic."""
    payload = envelope.payload
    # Common A2A payload keys
    for key in ("target_agent_id", "agent_id", "target"):
        if key in payload:
            return str(payload[key])
    # Derive from endpoint topic pattern: <env>.agent.<agent-id>.task.requested.v1
    parts = envelope.event_type.split(".")
    # Pattern: env.agent.<agent-id-parts...>.task.requested.v1
    # Find "agent" segment and take everything after up to (but not incl.) "task"
    if "agent" in parts:
        idx = parts.index("agent")
        between = parts[idx + 1 :]
        try:
            task_idx = between.index("task")
            agent_parts = between[:task_idx]
            if agent_parts:
                return ".".join(agent_parts)
        except ValueError:
            pass
    return None


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


class TimelineEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    seq: int
    event_type: str
    label: str
    actor: str
    target_agent: str | None
    correlation_id: UUID
    causation_id: UUID | None
    task_id: UUID | None
    timestamp: datetime
    summary: str


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


class AuditTimelineBuilder:
    """Builds a causally-ordered audit timeline from EventEnvelopes."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def collect(
        self,
        correlation_id: UUID,
        *,
        broker_url: str | None = None,
        envelopes: list[EventEnvelope] | None = None,
    ) -> list[EventEnvelope]:
        """Return all envelopes belonging to *correlation_id*.

        If *broker_url* is provided the method replays from Kafka offset 0 on
        the workflow topics and filters by correlation_id.  Otherwise the
        optional *envelopes* list (injected by tests / callers) is filtered and
        returned; if neither is supplied an empty list is returned.
        """
        if broker_url is not None:
            return await self._collect_from_kafka(correlation_id, broker_url)

        if envelopes is not None:
            return [e for e in envelopes if e.correlation_id == correlation_id]

        return []

    def build(self, envelopes: list[EventEnvelope]) -> list[TimelineEntry]:
        """Causally order *envelopes* and append a synthetic terminal entry."""
        if not envelopes:
            return []

        ordered = _causal_sort(envelopes)

        entries: list[TimelineEntry] = []
        for seq, env in enumerate(ordered, start=1):
            target = _extract_target_agent(env) if _is_task_requested(env.event_type) else None
            task_id: UUID | None = _extract_task_id(env)
            entries.append(
                TimelineEntry(
                    seq=seq,
                    event_type=env.event_type,
                    label=reconcile_label(env),
                    actor=env.agent_id,
                    target_agent=target,
                    correlation_id=env.correlation_id,
                    causation_id=env.causation_id,
                    task_id=task_id,
                    timestamp=env.timestamp,
                    summary=_make_summary(env),
                )
            )

        # Synthetic terminal entry
        terminal = _make_terminal_entry(entries)
        if terminal is not None:
            entries.append(terminal)

        return entries

    def render(self, entries: list[TimelineEntry]) -> str:
        """Return a numbered text representation of the timeline."""
        return "\n".join(f"{e.seq}. {e.label}" for e in entries)

    def to_dict(self, entries: list[TimelineEntry]) -> list[dict[str, Any]]:
        """Return JSON-serialisable list of entry dicts."""
        result = []
        for e in entries:
            d = e.model_dump()
            # Convert UUID / datetime to strings for JSON serialisability
            d["correlation_id"] = str(d["correlation_id"])
            d["causation_id"] = str(d["causation_id"]) if d["causation_id"] else None
            d["task_id"] = str(d["task_id"]) if d["task_id"] else None
            d["timestamp"] = d["timestamp"].isoformat()
            result.append(d)
        return result

    def to_json(self, entries: list[TimelineEntry]) -> str:
        """Return JSON string of the timeline."""
        return json.dumps(self.to_dict(entries))

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _collect_from_kafka(
        self, correlation_id: UUID, broker_url: str
    ) -> list[EventEnvelope]:
        """Replay workflow topics from offset 0 and filter by correlation_id."""
        import asyncio

        from agent_foundation.transport.consumer import Consumer
        from agent_foundation.envelope import AgentIdentity

        workflow_topics = [
            TOPIC_ISSUE_CLASSIFIED,
            TOPIC_REFUND_REVIEW_REQUESTED,
            TOPIC_BILLING_RESULT,
            TOPIC_RISK_RESULT,
            TOPIC_RESOLUTION_DECIDED,
            TOPIC_RESPONSE_DRAFTED,
            TOPIC_TASK_RESULT,
        ]

        collected: list[EventEnvelope] = []
        stop_event = asyncio.Event()

        identity = AgentIdentity(
            agent_id="audit.timeline.builder",
            display_name="Audit Timeline Builder",
            tenant_id="poc",
        )

        consumer = Consumer(
            broker_url=broker_url,
            group_id="audit-timeline-builder",
            agent_identity=identity,
            idempotent=False,
        )
        consumer.subscribe(workflow_topics)
        consumer.seek_to_beginning()

        async def _handler(envelope: EventEnvelope) -> None:
            if envelope.correlation_id == correlation_id:
                collected.append(envelope)

        # Run until no new messages arrive within a short window
        try:
            await asyncio.wait_for(
                consumer.run(_handler, stop_event=stop_event),
                timeout=5.0,
            )
        except (TimeoutError, asyncio.TimeoutError):
            pass
        finally:
            await consumer.stop()

        return collected


# ---------------------------------------------------------------------------
# Internal sorting / synthesis helpers
# ---------------------------------------------------------------------------


def _causal_sort(envelopes: list[EventEnvelope]) -> list[EventEnvelope]:
    """Return envelopes in causal order (root first, children follow parent).

    Uses a topological walk: envelopes whose causation_id is None (or whose
    parent is not present in the set) are treated as roots and sorted by
    timestamp; their children follow recursively.  Ties among siblings are
    broken by timestamp.
    """
    by_id: dict[UUID, EventEnvelope] = {e.event_id: e for e in envelopes}
    children: dict[UUID | None, list[EventEnvelope]] = {}
    for env in envelopes:
        parent = env.causation_id if env.causation_id in by_id else None
        children.setdefault(parent, []).append(env)

    # Sort each sibling group by timestamp for determinism
    for siblings in children.values():
        siblings.sort(key=lambda e: e.timestamp)

    result: list[EventEnvelope] = []

    def _walk(parent_id: UUID | None) -> None:
        for env in children.get(parent_id, []):
            result.append(env)
            _walk(env.event_id)

    _walk(None)

    # Any envelopes not reached (disconnected) appended by timestamp
    seen = {e.event_id for e in result}
    stragglers = sorted(
        (e for e in envelopes if e.event_id not in seen), key=lambda e: e.timestamp
    )
    result.extend(stragglers)

    return result


def _extract_task_id(envelope: EventEnvelope) -> UUID | None:
    """Extract task_id from payload if present."""
    raw = envelope.payload.get("task_id")
    if raw is None:
        return None
    try:
        return UUID(str(raw))
    except (ValueError, AttributeError):
        return None


def _make_summary(envelope: EventEnvelope) -> str:
    """One-line description for an envelope."""
    label = reconcile_label(envelope)
    return f"{label} by {envelope.agent_id}"


def _make_terminal_entry(entries: list[TimelineEntry]) -> TimelineEntry | None:
    """Synthesise a case-closed / case-escalated terminal entry."""
    if not entries:
        return None

    labels = {e.label for e in entries}
    last = entries[-1]
    correlation_id = last.correlation_id

    decided = "resolution.customer-resolution.decided" in labels
    drafted = "resolution.customer-response.drafted" in labels

    # Determine outcome
    escalated = False
    for e in entries:
        if e.label == "resolution.customer-resolution.decided":
            outcome = e.event_type  # label alone doesn't carry outcome; check payload via seq
            # Check if any entry actor/summary hints at escalation
            _ = outcome  # outcome string not used directly here
        payload_outcome = _find_decided_outcome(entries)
        if payload_outcome in ("escalated", "escalate"):
            escalated = True
        break

    if escalated:
        terminal_label = "resolution.case.escalated"
        summary = "Case escalated"
    elif decided and drafted:
        terminal_label = "resolution.case.closed"
        summary = "Case closed"
    elif decided:
        terminal_label = "resolution.case.closed"
        summary = "Case closed (decision recorded)"
    else:
        return None

    return TimelineEntry(
        seq=last.seq + 1,
        event_type="audit.synthetic.terminal.v1",
        label=terminal_label,
        actor="audit-timeline-builder",
        target_agent=None,
        correlation_id=correlation_id,
        causation_id=None,
        task_id=None,
        timestamp=last.timestamp,
        summary=summary,
    )


def _find_decided_outcome(entries: list[TimelineEntry]) -> str | None:
    """Return the outcome string from the decided entry's summary if available."""
    for e in entries:
        if e.label == "resolution.customer-resolution.decided":
            summary_lower = e.summary.lower()
            if "escalat" in summary_lower:
                return "escalated"
    return None
