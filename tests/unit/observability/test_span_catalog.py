"""T018: Span catalog — the 8 named spans and their FR-014 attribute assembly."""
from __future__ import annotations

import pytest

from agent_foundation.observability.attributes import attrs_from_envelope, build_span_attrs

SPAN_NAMES = [
    "event.consume",
    "kafka.publish",
    "a2a.task.send",
    "a2a.task.receive",
    "llm.invoke",
    "ticket.classify",
    "policy.evaluate",
    "case.decision",
]


def test_all_eight_span_names_defined() -> None:
    assert len(SPAN_NAMES) == 8
    assert "event.consume" in SPAN_NAMES
    assert "kafka.publish" in SPAN_NAMES
    assert "a2a.task.send" in SPAN_NAMES
    assert "a2a.task.receive" in SPAN_NAMES
    assert "llm.invoke" in SPAN_NAMES
    assert "ticket.classify" in SPAN_NAMES
    assert "policy.evaluate" in SPAN_NAMES
    assert "case.decision" in SPAN_NAMES


def test_build_span_attrs_all_fields() -> None:
    attrs = build_span_attrs(
        correlation_id="corr-1",
        causation_id="cause-1",
        event_id="evt-1",
        case_id="case-1",
        ticket_id="tick-1",
        task_id="task-1",
        capability="billing",
        agent_id="customer-resolution",
        model_id="anthropic.claude-3",
        topic="local.support.ticket.created.v1",
    )
    assert attrs["correlation_id"] == "corr-1"
    assert attrs["causation_id"] == "cause-1"
    assert attrs["case_id"] == "case-1"
    assert attrs["agent_id"] == "customer-resolution"
    assert attrs["model_id"] == "anthropic.claude-3"
    assert attrs["topic"] == "local.support.ticket.created.v1"


def test_build_span_attrs_drops_none() -> None:
    attrs = build_span_attrs(correlation_id="c1", case_id=None, model_id=None)
    assert "case_id" not in attrs
    assert "model_id" not in attrs
    assert attrs["correlation_id"] == "c1"


def test_build_span_attrs_rejects_unknown_keys() -> None:
    attrs = build_span_attrs(correlation_id="c1", customer_name="Alice", email="a@b.com")
    assert "customer_name" not in attrs
    assert "email" not in attrs
    assert attrs["correlation_id"] == "c1"


class _FakeEnvelope:
    correlation_id = "corr-99"
    causation_id = "cause-99"
    event_id = "evt-99"
    agent_id = "risk-fraud"
    event_type = "local.risk.review.completed.v1"


def test_attrs_from_envelope() -> None:
    env = _FakeEnvelope()
    attrs = attrs_from_envelope(env)
    assert attrs["correlation_id"] == "corr-99"
    assert attrs["agent_id"] == "risk-fraud"
    assert attrs["topic"] == "local.risk.review.completed.v1"
