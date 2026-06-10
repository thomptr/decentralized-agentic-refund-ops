"""Bounded demo trigger — the only write in the UI (T019).

Publishes exactly one root ``support.ticket.created`` envelope (``causation_id=None``),
reusing the ``apps/api/dev_publish_ticket.py`` publish path. It may construct no
other payload type and emits no task-request, result, audit, or agent-card event
(FR-014, SC-006). Starting a case is intake, not orchestration.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from agent_foundation.envelope import AgentIdentity
from agent_foundation.payloads.support_ticket import SupportTicketCreatedPayload
from agent_foundation.transport.publisher import Publisher
from apps.demo_ui import config
from packages.contracts.topics import topic_for

#: The single event type the trigger is permitted to publish.
TICKET_CREATED_EVENT_TYPE: str = topic_for("support", "ticket", "created")

#: Identity used for the demo intake event (mirrors dev_publish_ticket.py).
_DEMO_IDENTITY = AgentIdentity(
    agent_id="demo-ui.ticket-producer",
    display_name="Demo UI Ticket Producer",
    tenant_id="local",
)


class DemoTriggerRequest(BaseModel):
    """Operator input for starting a demo case (data-model.md).

    Maps directly onto ``SupportTicketCreatedPayload``; no other payload type may
    be constructed from it.
    """

    amount: float = Field(default=29.99, gt=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    reason: str = Field(default="Charged twice for monthly subscription", min_length=1)
    ticket_id: str | None = None
    customer_id: str | None = None

    def to_payload(self) -> SupportTicketCreatedPayload:
        """Build the single root payload, minting demo ids when not supplied."""
        return SupportTicketCreatedPayload(
            ticket_id=self.ticket_id or f"TKT-{uuid4().hex[:8]}",
            customer_id=self.customer_id or f"CUST-{uuid4().hex[:8]}",
            amount=self.amount,
            currency=self.currency,
            reason=self.reason,
            created_at=datetime.now(UTC),
        )


class DemoTriggerResult(BaseModel):
    """Identifiers of the one published root event — the UI deep-links to its case."""

    correlation_id: UUID
    event_id: UUID
    event_type: str


async def _publish_async(req: DemoTriggerRequest, broker_url: str) -> DemoTriggerResult:
    payload = req.to_payload()
    correlation_id = uuid4()
    async with Publisher(_DEMO_IDENTITY, broker_url) as pub:
        envelope = await pub.publish(
            payload=payload,
            event_type=TICKET_CREATED_EVENT_TYPE,
            correlation_id=correlation_id,
            causation_id=None,
        )
    return DemoTriggerResult(
        correlation_id=envelope.correlation_id,
        event_id=envelope.event_id,
        event_type=TICKET_CREATED_EVENT_TYPE,
    )


def publish_demo_ticket(
    req: DemoTriggerRequest, broker_url: str = config.BROKER_URL
) -> DemoTriggerResult:
    """Publish the single root ``support.ticket.created`` event and return its ids."""
    return config.run_async(_publish_async(req, broker_url))
