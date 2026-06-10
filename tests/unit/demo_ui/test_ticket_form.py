"""Unit tests for the bounded demo trigger (T018) — the only write.

Asserts the read-only guarantee (SC-006): exactly ONE root envelope is published,
of type ``support.ticket.created`` with ``causation_id is None``, and nothing else.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from agent_foundation.envelope import EventEnvelope
from apps.demo_ui import ticket_form
from apps.demo_ui.ticket_form import (
    TICKET_CREATED_EVENT_TYPE,
    DemoTriggerRequest,
    publish_demo_ticket,
)


class FakePublisher:
    """Records every publish call so the test can assert exactly one root event."""

    calls: list[dict] = []

    def __init__(self, identity, broker_url):  # noqa: ANN001
        self.identity = identity
        self.broker_url = broker_url

    async def __aenter__(self) -> FakePublisher:
        return self

    async def __aexit__(self, *exc) -> bool:  # noqa: ANN002
        return False

    async def publish(
        self,
        *,
        payload,  # noqa: ANN001
        event_type: str,
        correlation_id: UUID,
        causation_id: UUID | None = None,
        topic: str | None = None,
    ) -> EventEnvelope:
        envelope = EventEnvelope(
            event_id=uuid4(),
            correlation_id=correlation_id,
            causation_id=causation_id,
            agent_id=self.identity.agent_id,
            tenant_id=self.identity.tenant_id,
            timestamp=datetime.now(UTC),
            event_type=event_type,
            schema_version="1.0.0",
            payload=payload.model_dump(mode="json"),
        )
        FakePublisher.calls.append(
            {"event_type": event_type, "causation_id": causation_id, "topic": topic}
        )
        return envelope


@pytest.fixture(autouse=True)
def _patch_publisher(monkeypatch: pytest.MonkeyPatch) -> None:
    FakePublisher.calls = []
    monkeypatch.setattr(ticket_form, "Publisher", FakePublisher)


def test_request_defaults_map_to_payload() -> None:
    req = DemoTriggerRequest()
    payload = req.to_payload()
    assert payload.amount == 29.99
    assert payload.currency == "USD"
    assert payload.ticket_id.startswith("TKT-")
    assert payload.customer_id.startswith("CUST-")


def test_amount_must_be_positive() -> None:
    with pytest.raises(ValueError):
        DemoTriggerRequest(amount=0)


def test_currency_must_be_three_letters() -> None:
    with pytest.raises(ValueError):
        DemoTriggerRequest(currency="US")


def test_publishes_exactly_one_root_ticket_event() -> None:
    publish_demo_ticket(DemoTriggerRequest(amount=49.5), broker_url="dummy:9092")

    assert len(FakePublisher.calls) == 1
    call = FakePublisher.calls[0]
    assert call["event_type"] == TICKET_CREATED_EVENT_TYPE
    assert call["event_type"] == "local.support.ticket.created.v1"
    assert call["causation_id"] is None  # root event (SC-006)


def test_result_returns_new_correlation_and_event_ids() -> None:
    result = publish_demo_ticket(DemoTriggerRequest(), broker_url="dummy:9092")
    assert isinstance(result.correlation_id, UUID)
    assert isinstance(result.event_id, UUID)
    assert result.event_type == TICKET_CREATED_EVENT_TYPE
