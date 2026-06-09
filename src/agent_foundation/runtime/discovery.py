"""Agent Card discovery over the compacted Kafka discovery topic. No central registry."""

from __future__ import annotations

from agent_foundation.logging import get_logger
from agent_foundation.runtime.agent_card import AgentCard

_log = get_logger(__name__)


async def publish_card(card: AgentCard, broker_url: str = "localhost:9092") -> None:
    """Publish an AgentCard to the compacted discovery topic (keyed by agent_id)."""
    from datetime import UTC, datetime
    from uuid import uuid4

    from aiokafka import AIOKafkaProducer  # type: ignore[import-untyped]

    from agent_foundation.envelope import EventEnvelope
    from agent_foundation.transport.topics import TOPIC_AGENT_CARD, create_topics

    await create_topics(broker_url)

    card_envelope = EventEnvelope(
        event_id=uuid4(),
        correlation_id=uuid4(),
        causation_id=None,
        agent_id=card.agent_id,
        tenant_id="poc",
        timestamp=datetime.now(UTC),
        event_type="agent.agent_card.v1",
        schema_version="1.0.0",
        payload=card.model_dump(mode="json"),
    )
    producer = AIOKafkaProducer(bootstrap_servers=broker_url)
    await producer.start()
    try:
        data = card_envelope.model_dump_json().encode("utf-8")
        await producer.send_and_wait(
            TOPIC_AGENT_CARD,
            value=data,
            key=card.agent_id.encode("utf-8"),
        )
        _log.info("discovery.card_published", agent_id=card.agent_id)
    finally:
        await producer.stop()


async def discover_agents(broker_url: str = "localhost:9092") -> list[AgentCard]:
    """Read the compacted TOPIC_AGENT_CARD from earliest; return latest card per agent_id."""
    from aiokafka import AIOKafkaConsumer  # type: ignore[import-untyped]

    from agent_foundation.envelope import EventEnvelope
    from agent_foundation.transport.topics import TOPIC_AGENT_CARD

    consumer = AIOKafkaConsumer(
        TOPIC_AGENT_CARD,
        bootstrap_servers=broker_url,
        group_id=None,
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        value_deserializer=lambda b: b,
    )
    await consumer.start()
    latest: dict[str, AgentCard] = {}
    try:
        while True:
            batches = await consumer.getmany(timeout_ms=1000)
            if not batches:
                break
            for records in batches.values():
                for msg in records:
                    try:
                        envelope = EventEnvelope.model_validate_json(msg.value)
                        card = AgentCard.model_validate(envelope.payload)
                        latest[card.agent_id] = card
                    except Exception:
                        pass
    except Exception:
        pass
    finally:
        await consumer.stop()
    return list(latest.values())


async def find_capable(
    capability_id: str,
    broker_url: str = "localhost:9092",
) -> list[AgentCard]:
    """Return all currently-published agents declaring the given capability_id."""
    cards = await discover_agents(broker_url)
    return [c for c in cards if any(cap.id == capability_id for cap in c.capabilities)]
