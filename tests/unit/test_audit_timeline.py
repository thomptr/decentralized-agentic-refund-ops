"""Unit tests for AuditTimelineBuilder (no broker required)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from uuid import UUID

import pytest

from agent_foundation.envelope import EventEnvelope
from packages.contracts.topics import (
    TOPIC_BILLING_RESULT,
    TOPIC_ISSUE_CLASSIFIED,
    TOPIC_REFUND_REVIEW_REQUESTED,
    TOPIC_RESOLUTION_DECIDED,
    TOPIC_RESPONSE_DRAFTED,
    TOPIC_RISK_RESULT,
    endpoint_topic,
)
from packages.testing.audit_timeline import AuditTimelineBuilder, TimelineEntry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TICKET_TOPIC = "local.support.ticket.created.v1"
_BILLING_ENDPOINT = endpoint_topic("billing-entitlement-agent")
_RISK_ENDPOINT = endpoint_topic("risk-fraud-agent")


def _env(
    event_type: str,
    *,
    correlation_id: UUID,
    causation_id: UUID | None,
    agent_id: str = "customer-resolution-agent",
    payload: dict | None = None,
    ts_offset_ms: int = 0,
) -> EventEnvelope:
    """Build a minimal valid EventEnvelope for testing."""
    base_ts = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
    from datetime import timedelta

    return EventEnvelope(
        event_id=uuid.uuid4(),
        correlation_id=correlation_id,
        causation_id=causation_id,
        agent_id=agent_id,
        tenant_id="poc",
        timestamp=base_ts + timedelta(milliseconds=ts_offset_ms),
        event_type=event_type,
        schema_version="1.0.0",
        payload=payload or {},
    )


def _happy_path_envelopes(correlation_id: UUID) -> list[EventEnvelope]:
    """Build an ordered happy-path envelope chain for a refund case."""
    e0 = _env(_TICKET_TOPIC, correlation_id=correlation_id, causation_id=None, ts_offset_ms=0)
    e1 = _env(
        TOPIC_ISSUE_CLASSIFIED,
        correlation_id=correlation_id,
        causation_id=e0.event_id,
        ts_offset_ms=100,
    )
    e2 = _env(
        TOPIC_REFUND_REVIEW_REQUESTED,
        correlation_id=correlation_id,
        causation_id=e1.event_id,
        ts_offset_ms=200,
    )
    e3 = _env(
        _BILLING_ENDPOINT,
        correlation_id=correlation_id,
        causation_id=e2.event_id,
        agent_id="customer-resolution-agent",
        payload={"target_agent_id": "billing-entitlement-agent"},
        ts_offset_ms=300,
    )
    e4 = _env(
        _RISK_ENDPOINT,
        correlation_id=correlation_id,
        causation_id=e2.event_id,
        agent_id="customer-resolution-agent",
        payload={"target_agent_id": "risk-fraud-agent"},
        ts_offset_ms=310,
    )
    e5 = _env(
        TOPIC_BILLING_RESULT,
        correlation_id=correlation_id,
        causation_id=e3.event_id,
        agent_id="billing-entitlement-agent",
        ts_offset_ms=500,
    )
    e6 = _env(
        TOPIC_RISK_RESULT,
        correlation_id=correlation_id,
        causation_id=e4.event_id,
        agent_id="risk-fraud-agent",
        ts_offset_ms=510,
    )
    e7 = _env(
        TOPIC_RESOLUTION_DECIDED,
        correlation_id=correlation_id,
        causation_id=e5.event_id,
        ts_offset_ms=700,
    )
    e8 = _env(
        TOPIC_RESPONSE_DRAFTED,
        correlation_id=correlation_id,
        causation_id=e7.event_id,
        ts_offset_ms=800,
    )
    return [e0, e1, e2, e3, e4, e5, e6, e7, e8]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAuditTimelineBuilderBuild:
    def test_happy_path_ordered_sequence(self) -> None:
        """build() returns entries in causal order for a happy-path case."""
        cid = uuid.uuid4()
        envelopes = _happy_path_envelopes(cid)

        builder = AuditTimelineBuilder()
        entries = builder.build(envelopes)

        labels = [e.label for e in entries]
        # Root event first
        assert labels[0] == "support.ticket.created"
        assert labels[1] == "resolution.customer-issue.classified"
        assert labels[2] == "resolution.refund-review.requested"
        # Task requests after refund-review
        assert "audit.agent-task.requested billing-entitlement-agent" in labels
        assert "audit.agent-task.requested risk-fraud-agent" in labels
        # Billing result is causally upstream of decided (decided.causation = billing result)
        billing_idx = labels.index("billing.refund-analysis.completed")
        decided_idx = labels.index("resolution.customer-resolution.decided")
        assert billing_idx < decided_idx
        # Both results present in the timeline
        assert "billing.refund-analysis.completed" in labels
        assert "risk.review.completed" in labels
        # Drafted appears before the synthetic terminal
        drafted_idx = labels.index("resolution.customer-response.drafted")
        assert drafted_idx < len(labels) - 1  # terminal is last

    def test_sequence_numbers_are_contiguous(self) -> None:
        cid = uuid.uuid4()
        entries = AuditTimelineBuilder().build(_happy_path_envelopes(cid))
        seqs = [e.seq for e in entries]
        assert seqs == list(range(1, len(entries) + 1))

    def test_out_of_order_input_produces_causal_order(self) -> None:
        """build() sorts even when envelopes are submitted in reverse order."""
        cid = uuid.uuid4()
        ordered = _happy_path_envelopes(cid)
        # Reverse so input is out-of-causal-order
        reversed_envelopes = list(reversed(ordered))
        entries = AuditTimelineBuilder().build(reversed_envelopes)
        labels = [e.label for e in entries]
        assert labels[0] == "support.ticket.created"
        assert labels[1] == "resolution.customer-issue.classified"

    def test_synthetic_terminal_entry_appended(self) -> None:
        """build() appends a resolution.case.closed entry for decided+drafted."""
        cid = uuid.uuid4()
        entries = AuditTimelineBuilder().build(_happy_path_envelopes(cid))
        assert entries[-1].label == "resolution.case.closed"
        assert entries[-1].seq == len(entries)

    def test_cross_case_events_excluded(self) -> None:
        """build() only uses envelopes already filtered to one correlation_id."""
        cid_a = uuid.uuid4()
        cid_b = uuid.uuid4()
        envelopes_a = _happy_path_envelopes(cid_a)
        envelopes_b = _happy_path_envelopes(cid_b)

        # build() takes a flat list; caller is responsible for filtering.
        # AuditTimelineBuilder.collect() filters — test it here via collect.
        builder = AuditTimelineBuilder()

        import asyncio

        all_envelopes = envelopes_a + envelopes_b
        collected_a = asyncio.run(
            builder.collect(cid_a, envelopes=all_envelopes)
        )
        assert all(e.correlation_id == cid_a for e in collected_a)
        assert len(collected_a) == len(envelopes_a)

        entries_a = builder.build(collected_a)
        assert all(e.correlation_id == cid_a for e in entries_a if e.seq < len(entries_a))

    def test_empty_input_returns_empty(self) -> None:
        entries = AuditTimelineBuilder().build([])
        assert entries == []


class TestAuditTimelineBuilderRender:
    def test_render_produces_numbered_text(self) -> None:
        cid = uuid.uuid4()
        entries = AuditTimelineBuilder().build(_happy_path_envelopes(cid))
        rendered = AuditTimelineBuilder().render(entries)
        lines = rendered.splitlines()
        assert lines[0].startswith("1. ")
        assert lines[1].startswith("2. ")
        assert len(lines) == len(entries)
        assert "support.ticket.created" in lines[0]

    def test_render_labels_match_entries(self) -> None:
        cid = uuid.uuid4()
        entries = AuditTimelineBuilder().build(_happy_path_envelopes(cid))
        rendered = AuditTimelineBuilder().render(entries)
        for i, entry in enumerate(entries):
            expected_line = f"{entry.seq}. {entry.label}"
            assert rendered.splitlines()[i] == expected_line


class TestAuditTimelineBuilderJson:
    def test_to_json_round_trips(self) -> None:
        """to_json() produces valid JSON that round-trips to ordered structure."""
        cid = uuid.uuid4()
        builder = AuditTimelineBuilder()
        entries = builder.build(_happy_path_envelopes(cid))
        json_str = builder.to_json(entries)

        parsed = json.loads(json_str)
        assert isinstance(parsed, list)
        assert len(parsed) == len(entries)

        # Sequence numbers preserved
        seqs = [item["seq"] for item in parsed]
        assert seqs == list(range(1, len(entries) + 1))

        # Labels preserved
        labels = [item["label"] for item in parsed]
        assert labels[0] == "support.ticket.created"
        assert labels[-1] == "resolution.case.closed"

    def test_to_json_uuids_are_strings(self) -> None:
        cid = uuid.uuid4()
        builder = AuditTimelineBuilder()
        entries = builder.build(_happy_path_envelopes(cid))
        parsed = json.loads(builder.to_json(entries))
        for item in parsed:
            assert isinstance(item["correlation_id"], str)
            if item["causation_id"] is not None:
                assert isinstance(item["causation_id"], str)

    def test_to_dict_returns_list_of_dicts(self) -> None:
        cid = uuid.uuid4()
        builder = AuditTimelineBuilder()
        entries = builder.build(_happy_path_envelopes(cid))
        dicts = builder.to_dict(entries)
        assert isinstance(dicts, list)
        assert all(isinstance(d, dict) for d in dicts)


class TestTimelineEntryFields:
    def test_actor_populated_from_agent_id(self) -> None:
        cid = uuid.uuid4()
        entries = AuditTimelineBuilder().build(_happy_path_envelopes(cid))
        # First entry is the ticket (agent_id defaults to customer-resolution-agent)
        assert entries[0].actor == "customer-resolution-agent"

    def test_target_agent_populated_for_task_requests(self) -> None:
        cid = uuid.uuid4()
        entries = AuditTimelineBuilder().build(_happy_path_envelopes(cid))
        task_entries = [e for e in entries if "audit.agent-task.requested" in e.label]
        assert len(task_entries) >= 1
        for te in task_entries:
            assert te.target_agent is not None

    def test_correlation_id_matches_input(self) -> None:
        cid = uuid.uuid4()
        entries = AuditTimelineBuilder().build(_happy_path_envelopes(cid))
        # All real entries (not synthetic terminal) should have the same cid
        real_entries = [e for e in entries if e.event_type != "audit.synthetic.terminal.v1"]
        assert all(e.correlation_id == cid for e in real_entries)
