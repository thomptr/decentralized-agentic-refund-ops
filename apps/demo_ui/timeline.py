"""Causal case timeline for User Story 2 (T011).

Delegates ordering to ``trace_case`` (so the UI timeline and the ``trace_case.py``
CLI tell the identical story — SC-002) and joins each step's audit outcome/reason
by ``event_id``. Read + map only — no re-implementation of ordering, no decisions.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from agent_foundation.audit.store import query_by_correlation
from agent_foundation.envelope import EventEnvelope
from agent_foundation.payloads.sample import AuditPayload
from apps.agents.customer_resolution.trace import TraceStep, trace_case
from apps.demo_ui import config


class TimelineEntry(BaseModel):
    """One causal step, enriched with the audit outcome/reason for that event."""

    seq: int
    actor: str
    event_type: str
    outcome: str | None = None
    reason: str | None = None
    timestamp: datetime
    caused_by: UUID | None = None
    task_id: UUID | None = None
    is_orphan: bool = False


class TimelineView(BaseModel):
    """The full ordered timeline for one case (empty ⇒ ``found=False``, FR-009)."""

    correlation_id: UUID
    entries: list[TimelineEntry] = []
    found: bool = False


def _step_key(
    event_type: str, timestamp: datetime, actor: str, caused_by: UUID | None
) -> tuple[str, datetime, str, UUID | None]:
    return (event_type, timestamp, actor, caused_by)


def build_timeline_from_records(correlation_id: UUID, records: list[AuditPayload]) -> TimelineView:
    """Build the timeline from already-read audit records (pure — unit-testable).

    ``trace_case`` returns ``TraceStep`` objects without an ``event_id``, so we
    reconstruct the step→event mapping from the envelope's stable identity
    (type, timestamp, actor, caused_by) to look up the matching ``AuditPayload``.
    """
    if not records:
        return TimelineView(correlation_id=correlation_id, entries=[], found=False)

    # Dedup by event_id; later records (higher offset) reflect later processing.
    env_by_id: dict[UUID, EventEnvelope] = {}
    audit_by_id: dict[UUID, AuditPayload] = {}
    for rec in records:
        env = rec.original_envelope
        env_by_id[env.event_id] = env
        audit_by_id[env.event_id] = rec

    envelopes = list(env_by_id.values())

    # Map a step back to its event_id via the envelope's stable identity.
    id_by_key: dict[tuple[str, datetime, str, UUID | None], UUID] = {
        _step_key(e.event_type, e.timestamp, e.agent_id, e.causation_id): e.event_id
        for e in envelopes
    }

    steps: list[TraceStep] = trace_case(correlation_id, envelopes)

    entries: list[TimelineEntry] = []
    for step in steps:
        event_id = id_by_key.get(
            _step_key(step.event_type, step.timestamp, step.actor, step.caused_by)
        )
        audit = audit_by_id.get(event_id) if event_id is not None else None
        entries.append(
            TimelineEntry(
                seq=step.seq,
                actor=step.actor,
                event_type=step.event_type,
                outcome=audit.outcome if audit is not None else step.outcome,
                reason=audit.reason if audit is not None else None,
                timestamp=step.timestamp,
                caused_by=step.caused_by,
                task_id=step.task_id,
                # Orphan only when the step has a cause that could not be
                # resolved to any event in the case — task_id-based causation
                # (peer domain results) is resolved by trace_case to the
                # triggering request, so those are no longer false orphans.
                is_orphan=step.caused_by is not None and step.parent_event_id is None,
            )
        )

    return TimelineView(correlation_id=correlation_id, entries=entries, found=True)


def build_timeline(broker_url: str, correlation_id: UUID) -> TimelineView:
    """Fetch the case's audit records and build its causal timeline.

    Best-effort: a broker outage yields ``found=False`` rather than raising (FR-016).
    """
    try:
        records = config.run_async(
            query_by_correlation(broker_url, correlation_id),
            timeout=config.READ_TIMEOUT_SECONDS,
        )
    except Exception:
        records = []
    return build_timeline_from_records(correlation_id, records)
