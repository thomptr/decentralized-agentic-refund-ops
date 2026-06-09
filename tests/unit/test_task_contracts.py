"""Unit tests for TaskRequest, TaskResult, TaskError, Capability, AgentCard (T018)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from agent_foundation.a2a import A2AMessage, A2APart
from agent_foundation.payloads.task import TaskError, TaskRequest, TaskResult
from agent_foundation.runtime.agent_card import AgentCard, Capability

# ── helpers ──────────────────────────────────────────────────────────────────


def _msg(text: str = "hello") -> A2AMessage:
    return A2AMessage(role="agent", parts=[A2APart(type="text", text=text)])


def _cap(cap_id: str = "do.something") -> Capability:
    return Capability(id=cap_id, name="Do Something", description="A capability for testing")


def _card(agent_id: str = "test.agent", caps: list[Capability] | None = None) -> AgentCard:
    from packages.contracts.topics import endpoint_topic

    return AgentCard(
        agent_id=agent_id,
        name="Test Agent",
        description="An agent for testing",
        version="1.0.0",
        endpoint_topic=endpoint_topic(agent_id),
        capabilities=[_cap()] if caps is None else caps,
    )


# ── TaskError ─────────────────────────────────────────────────────────────────


def test_task_error_valid_categories() -> None:
    for cat in ("validation", "unsupported_capability", "handler_error", "duplicate", "internal"):
        e = TaskError(category=cat, message="msg")  # type: ignore[arg-type]
        assert e.category == cat


def test_task_error_invalid_category() -> None:
    with pytest.raises(ValidationError):
        TaskError(category="unknown", message="msg")  # type: ignore[arg-type]


# ── TaskRequest round-trip ────────────────────────────────────────────────────


def test_task_request_round_trip() -> None:
    req = TaskRequest(
        task_id=uuid4(),
        capability="do.something",
        requester_agent_id="requester.agent",
        target_agent_id="target.agent",
        input=_msg(),
    )
    restored = TaskRequest.model_validate_json(req.model_dump_json())
    assert restored == req


# ── TaskResult validators ─────────────────────────────────────────────────────


def test_task_result_completed_requires_output() -> None:
    with pytest.raises(ValidationError, match="output must be set"):
        TaskResult(
            task_id=uuid4(),
            status="completed",
            performer_agent_id="test.agent",
            output=None,
        )


def test_task_result_completed_rejects_error() -> None:
    with pytest.raises(ValidationError, match="error must be null"):
        TaskResult(
            task_id=uuid4(),
            status="completed",
            performer_agent_id="test.agent",
            output=_msg(),
            error=TaskError(category="internal", message="oops"),
        )


def test_task_result_failed_requires_error() -> None:
    with pytest.raises(ValidationError, match="error must be set"):
        TaskResult(
            task_id=uuid4(),
            status="failed",
            performer_agent_id="test.agent",
        )


def test_task_result_failed_rejects_output() -> None:
    with pytest.raises(ValidationError, match="output must be null"):
        TaskResult(
            task_id=uuid4(),
            status="failed",
            performer_agent_id="test.agent",
            output=_msg(),
            error=TaskError(category="handler_error", message="boom"),
        )


def test_task_result_failed_wrong_error_category() -> None:
    with pytest.raises(ValidationError, match="handler_error or internal"):
        TaskResult(
            task_id=uuid4(),
            status="failed",
            performer_agent_id="test.agent",
            error=TaskError(category="validation", message="wrong"),
        )


def test_task_result_rejected_requires_error() -> None:
    with pytest.raises(ValidationError, match="error must be set"):
        TaskResult(
            task_id=uuid4(),
            status="rejected",
            performer_agent_id="test.agent",
        )


def test_task_result_rejected_wrong_error_category() -> None:
    with pytest.raises(ValidationError, match="validation/unsupported_capability/duplicate"):
        TaskResult(
            task_id=uuid4(),
            status="rejected",
            performer_agent_id="test.agent",
            error=TaskError(category="handler_error", message="wrong"),
        )


def test_task_result_completed_round_trip() -> None:
    result = TaskResult(
        task_id=uuid4(),
        status="completed",
        performer_agent_id="test.agent",
        output=_msg("done"),
    )
    restored = TaskResult.model_validate_json(result.model_dump_json())
    assert restored == result


def test_task_result_failed_round_trip() -> None:
    result = TaskResult(
        task_id=uuid4(),
        status="failed",
        performer_agent_id="test.agent",
        error=TaskError(category="handler_error", message="explosion"),
    )
    restored = TaskResult.model_validate_json(result.model_dump_json())
    assert restored == result


def test_task_result_rejected_round_trip() -> None:
    result = TaskResult(
        task_id=uuid4(),
        status="rejected",
        performer_agent_id="test.agent",
        error=TaskError(category="unsupported_capability", message="no such cap"),
    )
    restored = TaskResult.model_validate_json(result.model_dump_json())
    assert restored == result


# ── Capability ────────────────────────────────────────────────────────────────


def test_capability_valid() -> None:
    c = _cap("resolve.customer.case")
    assert c.id == "resolve.customer.case"


def test_capability_invalid_id_uppercase() -> None:
    with pytest.raises(ValidationError):
        Capability(id="BadId", name="X", description="Y")


def test_capability_invalid_id_starts_digit() -> None:
    with pytest.raises(ValidationError):
        Capability(id="1bad", name="X", description="Y")


# ── AgentCard ─────────────────────────────────────────────────────────────────


def test_agent_card_valid_round_trip() -> None:
    card = _card()
    restored = AgentCard.model_validate_json(card.model_dump_json())
    assert restored == card


def test_agent_card_empty_capabilities() -> None:
    with pytest.raises(ValidationError):
        _card(caps=[])


def test_agent_card_duplicate_capability_ids() -> None:
    with pytest.raises(ValidationError, match="unique ids"):
        _card(caps=[_cap("do.something"), _cap("do.something")])


def test_agent_card_invalid_semver() -> None:
    with pytest.raises(ValidationError, match="semver"):
        AgentCard(
            agent_id="test.agent",
            name="X",
            description="Y",
            version="1.0",
            endpoint_topic="local.agent.test.agent.task.requested.v1",
            capabilities=[_cap()],
        )


def test_agent_card_auth_metadata_default() -> None:
    card = _card()
    assert card.security == "none"
    data = card.model_dump()
    assert data["security"] == "none"
