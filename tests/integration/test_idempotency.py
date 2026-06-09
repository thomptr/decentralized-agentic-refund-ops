"""Integration tests: idempotency tracker with real Kafka broker."""

from __future__ import annotations

import asyncio
import uuid

import pytest

from agent_foundation.envelope import AgentIdentity
from agent_foundation.payloads.sample import SamplePayload

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def kafka_bootstrap_servers() -> str:
    from testcontainers.kafka import KafkaContainer  # type: ignore[import-untyped]

    with KafkaContainer(image="confluentinc/cp-kafka:7.6.0") as kafka:
        yield kafka.get_bootstrap_server()


@pytest.fixture
def agent_identity() -> AgentIdentity:
    return AgentIdentity(
        agent_id="test.idempotent", display_name="Idempotency Test", tenant_id="poc"
    )


@pytest.mark.asyncio
async def test_replay_deduplicates(
    kafka_bootstrap_servers: str, agent_identity: AgentIdentity
) -> None:
    """Publish one event; replay the same stream twice; handler called exactly once."""
    from agent_foundation.envelope import EventEnvelope
    from agent_foundation.transport.consumer import Consumer
    from agent_foundation.transport.publisher import Publisher
    from agent_foundation.transport.topics import TOPIC_SAMPLE, create_topics

    await create_topics(kafka_bootstrap_servers)

    # Publish one event
    async with Publisher(agent_identity, kafka_bootstrap_servers) as pub:
        await pub.publish(
            SamplePayload(message="deduplicate me"),
            "agent.sample.v1",
            uuid.uuid4(),
        )

    handler_calls: list[EventEnvelope] = []
    group_id = "test.idempotent.replay"

    async def run_consumer() -> None:
        stop = asyncio.Event()

        async def handler(env: EventEnvelope) -> None:
            handler_calls.append(env)

        consumer = Consumer(
            broker_url=kafka_bootstrap_servers,
            group_id=group_id,
            agent_identity=agent_identity,
            idempotent=True,
        )
        consumer.subscribe([TOPIC_SAMPLE])
        consumer.seek_to_beginning()
        task = asyncio.create_task(consumer.run(handler, stop_event=stop))
        await asyncio.sleep(4.0)
        stop.set()
        await asyncio.wait_for(task, timeout=5.0)

    # First pass — should process the event
    await run_consumer()
    first_pass_count = len(handler_calls)
    assert first_pass_count >= 1

    # Second pass with same group_id — IdempotencyTracker should skip all
    await run_consumer()
    second_pass_count = len(handler_calls) - first_pass_count
    assert second_pass_count == 0, f"Expected 0 handler calls on replay, got {second_pass_count}"


@pytest.mark.asyncio
async def test_idempotency_tracker_recovery(
    kafka_bootstrap_servers: str, agent_identity: AgentIdentity
) -> None:
    """IdempotencyTracker rebuilds its LRU from the compacted topic on restart."""
    from agent_foundation.idempotency import IdempotencyTracker
    from agent_foundation.transport.topics import create_topics

    await create_topics(kafka_bootstrap_servers)

    event_id = uuid.uuid4()
    consumer_name = f"test.recovery.{uuid.uuid4().hex[:8]}"

    tracker1 = IdempotencyTracker(consumer_name, kafka_bootstrap_servers)
    await tracker1.initialize()
    assert not await tracker1.is_duplicate(event_id)
    await tracker1.mark_processed(event_id)

    # Simulate restart: create a new tracker with the same consumer_name
    await asyncio.sleep(1.0)
    tracker2 = IdempotencyTracker(consumer_name, kafka_bootstrap_servers)
    await tracker2.initialize()
    assert await tracker2.is_duplicate(event_id), (
        "Tracker should recognise already-processed event after restart"
    )
