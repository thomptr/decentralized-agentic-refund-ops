"""Unit tests for stream aggregation (T014) — no broker required."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from uuid import UUID

from agent_foundation.envelope import EventEnvelope
from agent_foundation.payloads.sample import AuditPayload
from apps.demo_ui.event_stream import build_stream_from_records

_BASE = datetime(2026, 1, 1, tzinfo=UTC)


def _record(
    *,
    event_id: UUID | None = None,
    correlation_id: UUID | None = None,
    agent_id: str = "customer-resolution-agent",
    event_type: str = "local.support.ticket.created.v1",
    ms: int = 0,
    outcome: str = "accepted",
) -> AuditPayload:
    # Only the root ticket type may have a null causation_id; others need a parent.
    is_root = event_type == "local.support.ticket.created.v1"
    env = EventEnvelope(
        event_id=event_id or uuid.uuid4(),
        correlation_id=correlation_id or uuid.uuid4(),
        causation_id=None if is_root else uuid.uuid4(),
        agent_id=agent_id,
        tenant_id="poc",
        timestamp=_BASE + timedelta(milliseconds=ms),
        event_type=event_type,
        schema_version="1.0.0",
        payload={},
    )
    reason = "boom" if outcome in ("failed", "rejected") else None
    return AuditPayload(
        original_envelope=env,
        outcome=outcome,
        reason=reason,
        recorded_at=env.timestamp,  # type: ignore[arg-type]
    )


def test_dedup_by_event_id_keeps_one() -> None:
    eid = uuid.uuid4()
    r = _record(event_id=eid)
    view = build_stream_from_records([r, r, r])  # replayed three times
    assert len(view.events) == 1
    assert view.events[0].event_id == eid


def test_newest_first_sort() -> None:
    old = _record(ms=0)
    new = _record(ms=1000)
    mid = _record(ms=500)
    view = build_stream_from_records([old, new, mid])
    ts = [e.timestamp for e in view.events]
    assert ts == sorted(ts, reverse=True)
    assert view.events[0].timestamp == new.original_envelope.timestamp


def test_and_filters_and_clearing() -> None:
    cid = uuid.uuid4()
    billing = _record(
        agent_id="billing-entitlement-agent",
        event_type="local.billing.refund-analysis.completed.v1",
        correlation_id=cid,
        ms=10,
    )
    risk = _record(agent_id="risk-fraud-agent", event_type="local.risk.review.completed.v1", ms=20)
    cr = _record(agent_id="customer-resolution-agent", correlation_id=cid, ms=30)
    records = [billing, risk, cr]

    # No filters → full set.
    assert len(build_stream_from_records(records).events) == 3

    # Agent filter narrows.
    only_risk = build_stream_from_records(records, filter_agent="risk-fraud-agent")
    assert [e.agent_id for e in only_risk.events] == ["risk-fraud-agent"]

    # AND-combined: agent + event_type that don't co-occur → empty.
    none = build_stream_from_records(
        records,
        filter_agent="risk-fraud-agent",
        filter_event_type="local.billing.refund-analysis.completed.v1",
    )
    assert none.events == []

    # Correlation filter.
    by_case = build_stream_from_records(records, filter_correlation_id=cid)
    assert {e.agent_id for e in by_case.events} == {
        "billing-entitlement-agent",
        "customer-resolution-agent",
    }


def test_outcome_carried_through() -> None:
    r = _record(outcome="failed")
    view = build_stream_from_records([r])
    assert view.events[0].outcome == "failed"
