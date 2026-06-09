#!/usr/bin/env python3
"""Dev-only script: publishes a sample local.support.ticket.created.v1 event. Requires Kafka at localhost:9092 (docker compose -f infra/local/docker-compose.yml up -d)."""
from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime
from uuid import uuid4

from agent_foundation.envelope import AgentIdentity
from agent_foundation.logging import configure_logging, get_logger
from agent_foundation.payloads.support_ticket import SupportTicketCreatedPayload
from agent_foundation.transport.publisher import Publisher
from packages.contracts.topics import topic_for

TICKET_CREATED_EVENT_TYPE = topic_for("support", "ticket", "created")


async def main() -> None:
    configure_logging()
    get_logger("dev_publish_ticket")

    identity = AgentIdentity(
        agent_id="dev.ticket-producer",
        display_name="Dev Ticket Producer",
        tenant_id="local",
    )

    payload = SupportTicketCreatedPayload(
        ticket_id="TKT-001",
        customer_id="CUST-42",
        amount=29.99,
        currency="USD",
        reason="Charged twice for monthly subscription",
        created_at=datetime.now(UTC),
    )

    corr_id = uuid4()
    broker_url = os.getenv("KAFKA_BROKER_URL", "localhost:9092")

    async with Publisher(identity, broker_url) as pub:
        envelope = await pub.publish(
            payload=payload,
            event_type=TICKET_CREATED_EVENT_TYPE,
            correlation_id=corr_id,
            causation_id=None,
        )

    result = {
        "event_id": str(envelope.event_id),
        "correlation_id": str(envelope.correlation_id),
        "topic": TICKET_CREATED_EVENT_TYPE,
    }
    print(json.dumps(result))


if __name__ == "__main__":
    asyncio.run(main())
