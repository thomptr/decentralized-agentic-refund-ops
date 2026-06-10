"""Live audit stream for User Story 3 (T015).

Newest-first cross-case feed, deduped by ``event_id`` (so replayed records show
once — FR-015/SC-005), with AND-combined agent / event-type / case filters that
clear back to the full stream (FR-011). Read + filter only — no decisions.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from agent_foundation.audit.store import consume_all_audit_records
from agent_foundation.payloads.sample import AuditPayload
from apps.demo_ui import config


class StreamEvent(BaseModel):
    """One audit record projected for the stream (dedup key = ``event_id``)."""

    event_id: UUID
    correlation_id: UUID
    agent_id: str
    event_type: str
    outcome: str | None = None
    reason: str | None = None
    timestamp: datetime


class StreamView(BaseModel):
    """The deduped, newest-first, AND-filtered audit stream."""

    events: list[StreamEvent] = []
    filter_agent: str | None = None
    filter_event_type: str | None = None
    filter_correlation_id: UUID | None = None


def build_stream_from_records(
    records: list[AuditPayload],
    *,
    filter_agent: str | None = None,
    filter_event_type: str | None = None,
    filter_correlation_id: UUID | None = None,
) -> StreamView:
    """Dedup → newest-first → AND-filter already-read records (pure — testable)."""
    # Dedup by event_id, first-seen wins.
    seen: set[UUID] = set()
    events: list[StreamEvent] = []
    for rec in records:
        env = rec.original_envelope
        if env.event_id in seen:
            continue
        seen.add(env.event_id)
        events.append(
            StreamEvent(
                event_id=env.event_id,
                correlation_id=env.correlation_id,
                agent_id=env.agent_id,
                event_type=env.event_type,
                outcome=rec.outcome,
                reason=rec.reason,
                timestamp=env.timestamp,
            )
        )

    # Newest-first.
    events.sort(key=lambda e: e.timestamp, reverse=True)

    # AND-combined filters; a None filter is a no-op (clearing restores the set).
    if filter_agent:
        events = [e for e in events if e.agent_id == filter_agent]
    if filter_event_type:
        events = [e for e in events if e.event_type == filter_event_type]
    if filter_correlation_id is not None:
        events = [e for e in events if e.correlation_id == filter_correlation_id]

    return StreamView(
        events=events,
        filter_agent=filter_agent,
        filter_event_type=filter_event_type,
        filter_correlation_id=filter_correlation_id,
    )


def build_stream(
    broker_url: str = config.BROKER_URL,
    *,
    filter_agent: str | None = None,
    filter_event_type: str | None = None,
    filter_correlation_id: UUID | None = None,
) -> StreamView:
    """Consume the whole audit topic and build the filtered stream view.

    Best-effort: a broker outage yields an empty stream rather than raising (FR-016).
    """
    try:
        records = config.run_async(
            consume_all_audit_records(broker_url), timeout=config.READ_TIMEOUT_SECONDS
        )
    except Exception:
        records = []
    return build_stream_from_records(
        records,
        filter_agent=filter_agent,
        filter_event_type=filter_event_type,
        filter_correlation_id=filter_correlation_id,
    )
