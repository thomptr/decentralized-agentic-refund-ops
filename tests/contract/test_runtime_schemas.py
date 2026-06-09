"""Contract tests: JSON-schema round-trips for the new A2A runtime payloads (T020)."""
from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from agent_foundation.a2a import A2AMessage, A2APart
from agent_foundation.payloads.sample import AuditPayload
from agent_foundation.payloads.task import TaskError, TaskRequest, TaskResult
from agent_foundation.runtime.agent_card import AgentCard, Capability

CONTRACTS = Path(__file__).parent.parent.parent / "specs" / "002-a2a-runtime-contract" / "contracts"


def _msg(text: str = "hello") -> A2AMessage:
    return A2AMessage(role="agent", parts=[A2APart(type="text", text=text)])


def _cap() -> Capability:
    return Capability(id="do.something", name="Do Something", description="A test capability")


def _card() -> AgentCard:
    from packages.contracts.topics import endpoint_topic

    return AgentCard(
        agent_id="test.agent",
        name="Test Agent",
        description="Agent for contract tests",
        version="1.0.0",
        endpoint_topic=endpoint_topic("test.agent"),
        capabilities=[_cap()],
    )


# ── AgentCard ─────────────────────────────────────────────────────────────────


def test_agent_card_json_round_trip() -> None:
    card = _card()
    serialized = card.model_dump_json()
    restored = AgentCard.model_validate_json(serialized)
    assert restored == card


def test_agent_card_schema_fields() -> None:
    schema_path = CONTRACTS / "agent-card.schema.json"
    if not schema_path.exists():
        pytest.skip("agent-card.schema.json not found")
    schema = json.loads(schema_path.read_text())
    required = schema.get("required", [])
    card = _card()
    data = card.model_dump()
    for field in required:
        assert field in data, f"Required field {field!r} missing from AgentCard dump"


# ── TaskRequest ───────────────────────────────────────────────────────────────


def test_task_request_json_round_trip() -> None:
    req = TaskRequest(
        task_id=uuid4(),
        capability="do.something",
        requester_agent_id="requester.agent",
        target_agent_id="target.agent",
        input=_msg(),
    )
    restored = TaskRequest.model_validate_json(req.model_dump_json())
    assert restored == req


def test_task_request_schema_required_fields() -> None:
    schema_path = CONTRACTS / "task-request.schema.json"
    if not schema_path.exists():
        pytest.skip("task-request.schema.json not found")
    schema = json.loads(schema_path.read_text())
    required = schema.get("required", [])
    req = TaskRequest(
        task_id=uuid4(),
        capability="do.something",
        requester_agent_id="requester.agent",
        target_agent_id="target.agent",
        input=_msg(),
    )
    data = req.model_dump(mode="json")
    data["task_id"] = str(data["task_id"])
    for field in required:
        assert field in data, f"Required field {field!r} missing from TaskRequest dump"


# ── TaskResult ────────────────────────────────────────────────────────────────


def test_task_result_completed_json_round_trip() -> None:
    result = TaskResult(
        task_id=uuid4(),
        status="completed",
        performer_agent_id="test.agent",
        output=_msg("done"),
    )
    restored = TaskResult.model_validate_json(result.model_dump_json())
    assert restored == result


def test_task_result_failed_json_round_trip() -> None:
    result = TaskResult(
        task_id=uuid4(),
        status="failed",
        performer_agent_id="test.agent",
        error=TaskError(category="handler_error", message="boom"),
    )
    restored = TaskResult.model_validate_json(result.model_dump_json())
    assert restored == result


def test_task_result_rejected_json_round_trip() -> None:
    result = TaskResult(
        task_id=uuid4(),
        status="rejected",
        performer_agent_id="test.agent",
        error=TaskError(category="unsupported_capability", message="no such cap"),
    )
    restored = TaskResult.model_validate_json(result.model_dump_json())
    assert restored == result


def test_task_result_schema_required_fields() -> None:
    schema_path = CONTRACTS / "task-result.schema.json"
    if not schema_path.exists():
        pytest.skip("task-result.schema.json not found")
    schema = json.loads(schema_path.read_text())
    required = schema.get("required", [])
    result = TaskResult(
        task_id=uuid4(),
        status="completed",
        performer_agent_id="test.agent",
        output=_msg(),
    )
    data = result.model_dump(mode="json")
    data["task_id"] = str(data["task_id"])
    for field in required:
        assert field in data, f"Required field {field!r} missing from TaskResult dump"


# ── AuditPayload task-lifecycle extension ─────────────────────────────────────


def test_audit_payload_task_lifecycle_round_trip() -> None:
    from datetime import UTC, datetime

    from agent_foundation.envelope import EventEnvelope

    task_id = uuid4()
    original = EventEnvelope(
        event_id=uuid4(),
        correlation_id=uuid4(),
        causation_id=uuid4(),
        agent_id="test.agent",
        tenant_id="poc",
        timestamp=datetime.now(UTC),
        event_type="agent.task_request.v1",
        schema_version="1.0.0",
        payload={},
    )
    ap = AuditPayload(
        original_envelope=original,
        outcome="completed",
        recorded_at=datetime.now(UTC),
        task_id=task_id,
    )
    restored = AuditPayload.model_validate_json(ap.model_dump_json())
    assert restored.task_id == task_id
    assert restored.outcome == "completed"


def test_audit_payload_task_audit_schema_fields() -> None:
    schema_path = CONTRACTS / "task-audit-payload.schema.json"
    if not schema_path.exists():
        pytest.skip("task-audit-payload.schema.json not found")
    schema = json.loads(schema_path.read_text())
    required = schema.get("required", [])
    from datetime import UTC, datetime

    from agent_foundation.envelope import EventEnvelope

    original = EventEnvelope(
        event_id=uuid4(),
        correlation_id=uuid4(),
        causation_id=uuid4(),
        agent_id="test.agent",
        tenant_id="poc",
        timestamp=datetime.now(UTC),
        event_type="agent.task_request.v1",
        schema_version="1.0.0",
        payload={},
    )
    ap = AuditPayload(
        original_envelope=original,
        outcome="accepted",
        recorded_at=datetime.now(UTC),
        task_id=uuid4(),
    )
    data = ap.model_dump(mode="json")
    for field in required:
        assert field in data, f"Required field {field!r} missing from AuditPayload dump"
