from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from agent_foundation.envelope import AgentIdentity, EventEnvelope


@pytest.fixture
def sample_agent_identity() -> AgentIdentity:
    return AgentIdentity(
        agent_id="test.agent",
        display_name="Test Agent",
        tenant_id="poc",
    )


@pytest.fixture
def correlation_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def make_envelope(sample_agent_identity: AgentIdentity):
    """Factory that produces a valid root EventEnvelope."""

    def _make(
        *,
        message: str = "test message",
        event_type: str = "agent.sample.v1",
        correlation_id: uuid.UUID | None = None,
        causation_id: uuid.UUID | None = None,
    ) -> EventEnvelope:
        from agent_foundation.payloads.sample import SamplePayload

        payload = SamplePayload(message=message)
        return EventEnvelope(
            event_id=uuid.uuid4(),
            correlation_id=correlation_id or uuid.uuid4(),
            causation_id=causation_id,
            agent_id=sample_agent_identity.agent_id,
            tenant_id=sample_agent_identity.tenant_id,
            timestamp=datetime.now(UTC),
            event_type=event_type,
            schema_version="1.0.0",
            payload=payload.model_dump(mode="json"),
        )

    return _make
