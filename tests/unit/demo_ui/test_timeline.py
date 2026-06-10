"""Unit tests for timeline aggregation (T010) — no broker required."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from uuid import UUID

from agent_foundation.envelope import EventEnvelope
from agent_foundation.payloads.sample import AuditPayload
from apps.agents.customer_resolution.trace import trace_case
from apps.demo_ui.timeline import build_timeline_from_records

_BASE = datetime(2026, 1, 1, tzinfo=UTC)


def _env(
    event_type: str,
    *,
    correlation_id: UUID,
    causation_id: UUID | None,
    agent_id: str = "customer-resolution-agent",
    ms: int = 0,
) -> EventEnvelope:
    return EventEnvelope(
        event_id=uuid.uuid4(),
        correlation_id=correlation_id,
        causation_id=causation_id,
        agent_id=agent_id,
        tenant_id="poc",
        timestamp=_BASE + timedelta(milliseconds=ms),
        event_type=event_type,
        schema_version="1.0.0",
        payload={},
    )


def _audit(
    env: EventEnvelope, *, outcome: str = "accepted", reason: str | None = None
) -> AuditPayload:
    return AuditPayload(
        original_envelope=env,
        outcome=outcome,  # type: ignore[arg-type]
        reason=reason,
        recorded_at=env.timestamp,
    )


def _happy_records(cid: UUID) -> tuple[list[AuditPayload], list[EventEnvelope]]:
    e0 = _env("local.support.ticket.created.v1", correlation_id=cid, causation_id=None, ms=0)
    e1 = _env(
        "local.customer.issue.classified.v1",
        correlation_id=cid,
        causation_id=e0.event_id,
        ms=100,
    )
    e2 = _env(
        "local.resolution.refund-review.requested.v1",
        correlation_id=cid,
        causation_id=e1.event_id,
        ms=200,
    )
    e3 = _env(
        "local.billing.refund-analysis.completed.v1",
        correlation_id=cid,
        causation_id=e2.event_id,
        agent_id="billing-entitlement-agent",
        ms=300,
    )
    e4 = _env(
        "local.customer.resolution.decided.v1",
        correlation_id=cid,
        causation_id=e3.event_id,
        ms=400,
    )
    envs = [e0, e1, e2, e3, e4]
    records = [_audit(e) for e in envs]
    return records, envs


def test_empty_input_found_false() -> None:
    cid = uuid.uuid4()
    view = build_timeline_from_records(cid, [])
    assert view.found is False
    assert view.entries == []


def test_ordering_equals_trace_case() -> None:
    cid = uuid.uuid4()
    records, envs = _happy_records(cid)
    view = build_timeline_from_records(cid, records)
    expected = [s.event_type for s in trace_case(cid, envs)]
    assert [e.event_type for e in view.entries] == expected
    assert view.found is True
    # seq is contiguous and 1-indexed.
    assert [e.seq for e in view.entries] == list(range(1, len(view.entries) + 1))


def test_outcome_and_reason_joined_by_event_id() -> None:
    cid = uuid.uuid4()
    records, envs = _happy_records(cid)
    # Mark the billing result as failed with a reason.
    billing_env = envs[3]
    records[3] = _audit(billing_env, outcome="failed", reason="entitlement check failed")
    view = build_timeline_from_records(cid, records)
    billing_entry = next(
        e for e in view.entries if e.event_type == "local.billing.refund-analysis.completed.v1"
    )
    assert billing_entry.outcome == "failed"
    assert billing_entry.reason == "entitlement check failed"


def test_orphan_flagged_not_dropped() -> None:
    cid = uuid.uuid4()
    records, envs = _happy_records(cid)
    # An event whose parent is absent from the case.
    orphan = _env(
        "local.risk.review.completed.v1",
        correlation_id=cid,
        causation_id=uuid.uuid4(),  # references a missing event
        agent_id="risk-fraud-agent",
        ms=500,
    )
    records.append(_audit(orphan))
    view = build_timeline_from_records(cid, records)
    orphan_entries = [e for e in view.entries if e.event_type == "local.risk.review.completed.v1"]
    assert len(orphan_entries) == 1  # not dropped
    assert orphan_entries[0].is_orphan is True
    # Root and well-parented events are not orphans.
    root = next(e for e in view.entries if e.event_type == "local.support.ticket.created.v1")
    assert root.is_orphan is False


def test_duplicate_event_id_collapses() -> None:
    cid = uuid.uuid4()
    records, _ = _happy_records(cid)
    # Replay the whole case (same event_ids) — entries must not double up.
    view = build_timeline_from_records(cid, records + records)
    assert len(view.entries) == 5
