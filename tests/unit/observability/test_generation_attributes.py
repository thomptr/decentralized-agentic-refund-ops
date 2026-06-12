"""T028: LLM generation attribute mapping.

Model, token usage, cache hit, latency, provider_mode.
"""

from __future__ import annotations

from agent_foundation.observability.attributes import build_span_attrs


def test_model_id_in_attrs() -> None:
    attrs = build_span_attrs(model_id="anthropic.claude-3-5-sonnet-20241022-v2:0", agent_id="cr")
    assert attrs["model_id"] == "anthropic.claude-3-5-sonnet-20241022-v2:0"


def test_agent_id_in_attrs() -> None:
    attrs = build_span_attrs(agent_id="billing-entitlement")
    assert attrs["agent_id"] == "billing-entitlement"


def test_task_id_in_attrs() -> None:
    attrs = build_span_attrs(task_id="task-abc-123", agent_id="risk-fraud")
    assert attrs["task_id"] == "task-abc-123"


def test_none_values_dropped() -> None:
    attrs = build_span_attrs(model_id=None, agent_id="cr", task_id=None)
    assert "model_id" not in attrs
    assert "task_id" not in attrs
    assert attrs["agent_id"] == "cr"


def test_all_fr014_keys_allowed() -> None:
    attrs = build_span_attrs(
        correlation_id="c1",
        causation_id="ca1",
        event_id="e1",
        case_id="cs1",
        ticket_id="t1",
        task_id="tk1",
        capability="billing",
        agent_id="cr",
        model_id="stub",
        topic="agent.audit.v1",
    )
    assert len(attrs) == 10
