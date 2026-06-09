"""Contract tests: round-trip serialization for all schema types."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from agent_foundation.a2a import A2AMessage, A2APart
from agent_foundation.envelope import EventEnvelope
from agent_foundation.payloads.sample import AuditPayload, SamplePayload


def _make_envelope(
    event_type: str = "agent.sample.v1", causation_id: uuid.UUID | None = None
) -> EventEnvelope:
    return EventEnvelope(
        event_id=uuid.uuid4(),
        correlation_id=uuid.uuid4(),
        causation_id=causation_id,
        agent_id="test.agent",
        tenant_id="poc",
        timestamp=datetime.now(UTC),
        event_type=event_type,
        schema_version="1.0.0",
        payload={"message": "round-trip"},
    )


class TestEventEnvelopeRoundTrip:
    def test_roundtrip(self) -> None:
        original = _make_envelope()
        json_str = original.model_dump_json()
        restored = EventEnvelope.model_validate_json(json_str)
        assert restored.event_id == original.event_id
        assert restored.correlation_id == original.correlation_id
        assert restored.agent_id == original.agent_id
        assert restored.tenant_id == original.tenant_id
        assert restored.event_type == original.event_type
        assert restored.schema_version == original.schema_version
        assert restored.payload == original.payload

    def test_timestamp_survives_roundtrip(self) -> None:
        original = _make_envelope()
        json_str = original.model_dump_json()
        restored = EventEnvelope.model_validate_json(json_str)
        assert restored.timestamp.tzinfo is not None


class TestA2AMessageRoundTrip:
    def test_text_part_roundtrip(self) -> None:
        part = A2APart(type="text", text="hello")
        msg = A2AMessage(role="agent", parts=[part])
        json_str = msg.model_dump_json()
        restored = A2AMessage.model_validate_json(json_str)
        assert restored.role == "agent"
        assert len(restored.parts) == 1
        assert restored.parts[0].text == "hello"

    def test_data_part_roundtrip(self) -> None:
        part = A2APart(type="data", data={"key": "value"})
        msg = A2AMessage(role="user", parts=[part], task_id=uuid.uuid4())
        json_str = msg.model_dump_json()
        restored = A2AMessage.model_validate_json(json_str)
        assert restored.task_id == msg.task_id

    def test_file_part_roundtrip(self) -> None:
        part = A2APart(type="file", file_uri="s3://bucket/key")
        msg = A2AMessage(role="agent", parts=[part])
        restored = A2AMessage.model_validate_json(msg.model_dump_json())
        assert restored.parts[0].file_uri == "s3://bucket/key"

    def test_missing_text_in_text_part_raises(self) -> None:
        with pytest.raises(ValidationError):
            A2APart(type="text")

    def test_empty_parts_raises(self) -> None:
        with pytest.raises(ValidationError):
            A2AMessage(role="agent", parts=[])


class TestSamplePayloadRoundTrip:
    def test_roundtrip(self) -> None:
        p = SamplePayload(message="hello world")
        restored = SamplePayload.model_validate_json(p.model_dump_json())
        assert restored.message == p.message


class TestAuditPayloadRoundTrip:
    def test_accepted_roundtrip(self) -> None:
        envelope = _make_envelope()
        audit = AuditPayload(
            original_envelope=envelope,
            outcome="accepted",
            reason=None,
            recorded_at=datetime.now(UTC),
        )
        json_str = audit.model_dump_json()
        restored = AuditPayload.model_validate_json(json_str)
        assert restored.outcome == "accepted"
        assert restored.original_envelope.event_id == envelope.event_id
        assert restored.reason is None

    def test_rejected_roundtrip(self) -> None:
        envelope = _make_envelope()
        audit = AuditPayload(
            original_envelope=envelope,
            outcome="rejected",
            reason="payload_invalid",
            recorded_at=datetime.now(UTC),
        )
        restored = AuditPayload.model_validate_json(audit.model_dump_json())
        assert restored.outcome == "rejected"
        assert restored.reason == "payload_invalid"

    def test_duplicate_skipped_roundtrip(self) -> None:
        envelope = _make_envelope()
        audit = AuditPayload(
            original_envelope=envelope,
            outcome="duplicate_skipped",
            reason=None,
            recorded_at=datetime.now(UTC),
        )
        restored = AuditPayload.model_validate_json(audit.model_dump_json())
        assert restored.outcome == "duplicate_skipped"
