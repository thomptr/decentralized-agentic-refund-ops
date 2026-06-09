"""Unit tests for EventEnvelope, AgentIdentity, and payload registry."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from agent_foundation.envelope import (
    AgentIdentity,
    EventEnvelope,
    MissingCausation,
    ROOT_EVENT_TYPES,
)
from agent_foundation.payloads import (
    PAYLOAD_REGISTRY,
    PayloadValidationError,
    UnknownEventType,
    lookup,
)
from agent_foundation.payloads.sample import SamplePayload


def _base_envelope(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = dict(
        event_id=uuid.uuid4(),
        correlation_id=uuid.uuid4(),
        causation_id=None,
        agent_id="test.agent",
        tenant_id="poc",
        timestamp=datetime.now(UTC),
        event_type="agent.sample.v1",
        schema_version="1.0.0",
        payload={"message": "hello"},
    )
    base.update(overrides)
    return base


class TestEventEnvelopeValidation:
    def test_valid_root_event(self) -> None:
        e = EventEnvelope(**_base_envelope())  # type: ignore[arg-type]
        assert e.event_type == "agent.sample.v1"

    def test_missing_agent_id_raises(self) -> None:
        with pytest.raises(Exception):
            EventEnvelope(**_base_envelope(agent_id=""))  # type: ignore[arg-type]

    def test_bad_agent_id_pattern_raises(self) -> None:
        with pytest.raises(Exception):
            EventEnvelope(**_base_envelope(agent_id="BAD_ID"))  # type: ignore[arg-type]

    def test_bad_tenant_id_raises(self) -> None:
        with pytest.raises(Exception):
            EventEnvelope(**_base_envelope(tenant_id="BAD!"))  # type: ignore[arg-type]

    def test_non_root_without_causation_raises(self) -> None:
        # MissingCausation is raised inside a Pydantic model_validator, wrapped in ValidationError.
        with pytest.raises(Exception, match="causation_id is required"):
            EventEnvelope(**_base_envelope(event_type="agent.message.v1", causation_id=None))  # type: ignore[arg-type]

    def test_non_root_with_causation_ok(self) -> None:
        e = EventEnvelope(
            **_base_envelope(event_type="agent.message.v1", causation_id=uuid.uuid4())  # type: ignore[arg-type]
        )
        assert e.causation_id is not None

    def test_extra_fields_rejected(self) -> None:
        with pytest.raises(Exception):
            EventEnvelope(**_base_envelope(unexpected_field="x"))  # type: ignore[arg-type]

    def test_frozen_immutability(self) -> None:
        e = EventEnvelope(**_base_envelope())  # type: ignore[arg-type]
        with pytest.raises(Exception):
            e.agent_id = "changed"  # type: ignore[misc]

    def test_invalid_event_type_pattern(self) -> None:
        with pytest.raises(Exception):
            EventEnvelope(**_base_envelope(event_type="INVALID"))  # type: ignore[arg-type]

    def test_invalid_schema_version(self) -> None:
        with pytest.raises(Exception):
            EventEnvelope(**_base_envelope(schema_version="not-semver"))  # type: ignore[arg-type]

    def test_root_event_types_set(self) -> None:
        assert "agent.sample.v1" in ROOT_EVENT_TYPES

    def test_causation_id_none_allowed_for_root_type(self) -> None:
        e = EventEnvelope(**_base_envelope(event_type="agent.sample.v1", causation_id=None))  # type: ignore[arg-type]
        assert e.causation_id is None


class TestAgentIdentityValidation:
    def test_valid_identity(self) -> None:
        a = AgentIdentity(agent_id="billing.agent", display_name="Billing", tenant_id="poc")
        assert a.agent_id == "billing.agent"

    def test_display_name_too_long(self) -> None:
        with pytest.raises(Exception):
            AgentIdentity(agent_id="test.agent", display_name="x" * 81, tenant_id="poc")

    def test_display_name_empty(self) -> None:
        with pytest.raises(Exception):
            AgentIdentity(agent_id="test.agent", display_name="", tenant_id="poc")

    def test_frozen_immutability(self) -> None:
        a = AgentIdentity(agent_id="test.agent", display_name="Test", tenant_id="poc")
        with pytest.raises(Exception):
            a.agent_id = "other"  # type: ignore[misc]


class TestPayloadRegistry:
    def test_lookup_sample(self) -> None:
        model_cls = lookup("agent.sample.v1")
        assert model_cls is SamplePayload

    def test_lookup_unknown_raises(self) -> None:
        with pytest.raises(UnknownEventType):
            lookup("does.not.exist.v1")

    def test_registry_has_all_three(self) -> None:
        assert "agent.message.v1" in PAYLOAD_REGISTRY
        assert "agent.audit.v1" in PAYLOAD_REGISTRY
        assert "agent.sample.v1" in PAYLOAD_REGISTRY

    def test_sample_payload_validation(self) -> None:
        p = SamplePayload(message="hello")
        assert p.message == "hello"

    def test_sample_payload_empty_message(self) -> None:
        with pytest.raises(Exception):
            SamplePayload(message="")

    def test_sample_payload_too_long(self) -> None:
        with pytest.raises(Exception):
            SamplePayload(message="x" * 201)
