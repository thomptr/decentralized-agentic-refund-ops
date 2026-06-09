"""Integration tests: full publish/consume round-trip against a real Kafka broker."""
from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio

from agent_foundation.envelope import AgentIdentity, EventEnvelope
from agent_foundation.payloads.sample import SamplePayload

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def kafka_bootstrap_servers() -> str:
    from testcontainers.kafka import KafkaContainer  # type: ignore[import-untyped]

    with KafkaContainer(image="confluentinc/cp-kafka:7.6.0") as kafka:
        yield kafka.get_bootstrap_server()


@pytest.fixture
def agent_identity() -> AgentIdentity:
    return AgentIdentity(agent_id="test.integration", display_name="Integration Test", tenant_id="poc")


@pytest.mark.asyncio
async def test_publish_consume_roundtrip(kafka_bootstrap_servers: str, agent_identity: AgentIdentity) -> None:
    """Publish a sample event and consume it; verify all envelope fields survive."""
    from agent_foundation.transport.publisher import Publisher
    from agent_foundation.transport.consumer import Consumer
    from agent_foundation.transport.topics import create_topics, TOPIC_SAMPLE

    await create_topics(kafka_bootstrap_servers)

    received: list[EventEnvelope] = []
    stop_event = asyncio.Event()

    async def handler(envelope: EventEnvelope) -> None:
        received.append(envelope)
        stop_event.set()

    consumer = Consumer(
        broker_url=kafka_bootstrap_servers,
        group_id="test.roundtrip",
        agent_identity=agent_identity,
        idempotent=False,
    )
    consumer.subscribe([TOPIC_SAMPLE])

    async def consume_task() -> None:
        await consumer.run(handler, stop_event=stop_event)

    task = asyncio.create_task(consume_task())

    # Give consumer a moment to start
    await asyncio.sleep(1.0)

    corr_id = uuid.uuid4()
    payload = SamplePayload(message="integration test hello")

    async with Publisher(agent_identity, kafka_bootstrap_servers) as pub:
        sent = await pub.publish(payload, "agent.sample.v1", corr_id)

    # Wait for receipt
    try:
        await asyncio.wait_for(asyncio.shield(stop_event.wait()), timeout=10.0)
    except asyncio.TimeoutError:
        pass

    stop_event.set()
    await asyncio.wait_for(task, timeout=5.0)

    assert len(received) >= 1
    env = received[0]
    assert env.event_id == sent.event_id
    assert env.correlation_id == corr_id
    assert env.event_type == "agent.sample.v1"
    assert env.agent_id == agent_identity.agent_id


@pytest.mark.asyncio
async def test_schema_rejection_writes_audit(kafka_bootstrap_servers: str, agent_identity: AgentIdentity) -> None:
    """Publish an event with empty payload; consumer writes rejected audit record."""
    from aiokafka import AIOKafkaProducer  # type: ignore[import-untyped]
    from agent_foundation.transport.topics import create_topics, TOPIC_SAMPLE, TOPIC_AUDIT
    from agent_foundation.envelope import EventEnvelope
    from agent_foundation.transport.publisher import Publisher
    from agent_foundation.audit.store import consume_all_audit_records

    await create_topics(kafka_bootstrap_servers)

    corr_id = uuid.uuid4()
    # Build an envelope with wrong payload structure (missing required 'message' field)
    invalid_envelope = EventEnvelope.model_construct(
        event_id=uuid.uuid4(),
        correlation_id=corr_id,
        causation_id=None,
        agent_id=agent_identity.agent_id,
        tenant_id=agent_identity.tenant_id,
        timestamp=datetime.now(UTC),
        event_type="agent.sample.v1",
        schema_version="1.0.0",
        payload={},  # missing 'message' — invalid SamplePayload
    )

    producer = AIOKafkaProducer(bootstrap_servers=kafka_bootstrap_servers)
    await producer.start()
    try:
        await producer.send_and_wait(
            TOPIC_SAMPLE,
            value=invalid_envelope.model_dump_json().encode(),
            key=str(invalid_envelope.event_id).encode(),
        )
    finally:
        await producer.stop()

    stop_event = asyncio.Event()
    rejection_written = asyncio.Event()

    async with Publisher(agent_identity, kafka_bootstrap_servers) as pub:
        from agent_foundation.transport.consumer import Consumer

        consumer = Consumer(
            broker_url=kafka_bootstrap_servers,
            group_id="test.rejection",
            agent_identity=agent_identity,
            idempotent=False,
        )
        consumer.subscribe([TOPIC_SAMPLE])
        consumer.seek_to_beginning()

        processed: list[EventEnvelope] = []

        async def handler(envelope: EventEnvelope) -> None:
            processed.append(envelope)

        task = asyncio.create_task(consumer.run(handler, stop_event=stop_event, publisher=pub))
        await asyncio.sleep(5.0)
        stop_event.set()
        await asyncio.wait_for(task, timeout=5.0)

    # The invalid envelope should have been rejected; check audit topic
    audit_records = await consume_all_audit_records(kafka_bootstrap_servers)
    rejected = [r for r in audit_records if r.outcome == "rejected"]
    assert len(rejected) >= 1
