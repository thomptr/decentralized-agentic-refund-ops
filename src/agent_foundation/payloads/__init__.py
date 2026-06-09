from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel

from agent_foundation.a2a import A2AMessage
from agent_foundation.payloads.sample import AuditPayload, SamplePayload
from agent_foundation.payloads.support_ticket import SupportTicketCreatedPayload
from packages.contracts.topics import topic_for

if TYPE_CHECKING:
    pass

_TICKET_CREATED_ET = topic_for("support", "ticket", "created")

PAYLOAD_REGISTRY: dict[str, type[BaseModel]] = {
    "agent.message.v1": A2AMessage,
    "agent.audit.v1": AuditPayload,
    "agent.sample.v1": SamplePayload,
    # Dev/demo domain event; included so Publisher can validate and send it.
    _TICKET_CREATED_ET: SupportTicketCreatedPayload,
}


class UnknownEventType(KeyError):
    def __init__(self, event_type: str) -> None:
        super().__init__(f"No payload model registered for event_type={event_type!r}")
        self.event_type = event_type


class PayloadValidationError(ValueError):
    def __init__(self, event_type: str, detail: str) -> None:
        super().__init__(f"Payload validation failed for event_type={event_type!r}: {detail}")
        self.event_type = event_type
        self.detail = detail


def lookup(event_type: str) -> type[BaseModel]:
    """Return the Pydantic model registered for the given event_type."""
    try:
        return PAYLOAD_REGISTRY[event_type]
    except KeyError:
        raise UnknownEventType(event_type)
