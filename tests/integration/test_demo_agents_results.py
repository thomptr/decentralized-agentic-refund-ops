"""Integration tests: US2 — structured mock results, success and failure.

Tests T027 (acceptance: completed/failed lifecycle, exactly one terminal per accepted task_id).
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def kafka_bootstrap_servers() -> str:
    from testcontainers.kafka import KafkaContainer  # type: ignore[import-untyped]

    with KafkaContainer(image="confluentinc/cp-kafka:7.6.0") as kafka:
        yield kafka.get_bootstrap_server()


@pytest.mark.asyncio
async def test_successful_task_returns_completed(kafka_bootstrap_servers: str) -> None:
    """Accepted task that succeeds → TaskResult(status='completed') with output."""
    from agent_foundation.a2a import A2AMessage, A2APart
    from agent_foundation.envelope import AgentIdentity
    from agent_foundation.runtime import A2AClient, AgentCard, AgentRuntime, Capability
    from agent_foundation.transport.topics import create_topics
    from packages.contracts.topics import endpoint_topic

    await create_topics(kafka_bootstrap_servers)

    agent_id = f"test.results.{uuid4().hex[:8]}"
    cap_id = "do.work"
    identity = AgentIdentity(agent_id=agent_id, display_name="Test", tenant_id="poc")
    card = AgentCard(
        agent_id=agent_id,
        name="Test",
        description="Test",
        version="1.0.0",
        endpoint_topic=endpoint_topic(agent_id),
        capabilities=[Capability(id=cap_id, name="Do Work", description="desc")],
    )
    runtime = AgentRuntime(identity, card, broker_url=kafka_bootstrap_servers)

    from agent_foundation.payloads.task import TaskRequest

    @runtime.handler(cap_id)
    async def _h(req: TaskRequest) -> A2AMessage:
        return A2AMessage(role="agent", parts=[A2APart(type="data", data={"status": "done"})])

    stop_event = asyncio.Event()
    task = asyncio.create_task(runtime.serve(stop_event))
    await asyncio.sleep(3.0)

    client_id = AgentIdentity(agent_id="test.client2", display_name="Client", tenant_id="poc")
    client = A2AClient(client_id, broker_url=kafka_bootstrap_servers)
    result = await client.submit(
        agent_id,
        cap_id,
        A2AMessage(role="user", parts=[A2APart(type="text", text="go")]),
        timeout_s=10.0,
    )

    stop_event.set()
    await asyncio.wait_for(task, timeout=5.0)

    assert result.status == "completed"
    assert result.output is not None
    assert result.error is None


@pytest.mark.asyncio
async def test_fail_sentinel_returns_failed(kafka_bootstrap_servers: str) -> None:
    """Billing agent FAIL sentinel → TaskResult(status='failed', category='handler_error')."""
    from agent_foundation.a2a import A2AMessage, A2APart
    from agent_foundation.envelope import AgentIdentity
    from agent_foundation.runtime import A2AClient, AgentCard, AgentRuntime, Capability
    from agent_foundation.transport.topics import create_topics
    from packages.contracts.topics import endpoint_topic

    await create_topics(kafka_bootstrap_servers)

    agent_id = f"billing-test.{uuid4().hex[:8]}"
    cap_id = "analyze_refund_eligibility"
    identity = AgentIdentity(agent_id=agent_id, display_name="Billing Test", tenant_id="poc")
    card = AgentCard(
        agent_id=agent_id,
        name="Billing Test",
        description="Test",
        version="1.0.0",
        endpoint_topic=endpoint_topic(agent_id),
        capabilities=[Capability(id=cap_id, name="Eligibility", description="desc")],
    )
    runtime = AgentRuntime(identity, card, broker_url=kafka_bootstrap_servers)

    from agent_foundation.payloads.task import TaskRequest

    @runtime.handler(cap_id)
    async def _h(req: TaskRequest) -> A2AMessage:
        for part in req.input.parts:
            if part.type == "text" and part.text == "FAIL":
                raise RuntimeError("Billing failure sentinel triggered")
        return A2AMessage(
            role="agent", parts=[A2APart(type="data", data={"eligible": True, "reason": "mock"})]
        )

    stop_event = asyncio.Event()
    task = asyncio.create_task(runtime.serve(stop_event))
    await asyncio.sleep(3.0)

    client_id = AgentIdentity(agent_id="test.client3", display_name="Client", tenant_id="poc")
    client = A2AClient(client_id, broker_url=kafka_bootstrap_servers)

    # Send the FAIL sentinel
    result = await client.submit(
        agent_id,
        cap_id,
        A2AMessage(role="user", parts=[A2APart(type="text", text="FAIL")]),
        timeout_s=10.0,
    )

    stop_event.set()
    await asyncio.wait_for(task, timeout=5.0)

    assert result.status == "failed"
    assert result.error is not None
    assert result.error.category == "handler_error"
    assert result.output is None


@pytest.mark.asyncio
async def test_failed_result_distinct_from_rejected(kafka_bootstrap_servers: str) -> None:
    """Confirms failed (handler raised) ≠ rejected (unsupported capability)."""
    from agent_foundation.a2a import A2AMessage, A2APart
    from agent_foundation.envelope import AgentIdentity
    from agent_foundation.runtime import A2AClient, AgentCard, AgentRuntime, Capability
    from agent_foundation.transport.topics import create_topics
    from packages.contracts.topics import endpoint_topic

    await create_topics(kafka_bootstrap_servers)

    agent_id = f"test.distinguish.{uuid4().hex[:8]}"
    cap_id = "work.cap"
    identity = AgentIdentity(agent_id=agent_id, display_name="Test", tenant_id="poc")
    card = AgentCard(
        agent_id=agent_id,
        name="Test",
        description="Test",
        version="1.0.0",
        endpoint_topic=endpoint_topic(agent_id),
        capabilities=[Capability(id=cap_id, name="Work Cap", description="desc")],
    )
    runtime = AgentRuntime(identity, card, broker_url=kafka_bootstrap_servers)

    from agent_foundation.payloads.task import TaskRequest

    @runtime.handler(cap_id)
    async def _h(req: TaskRequest) -> A2AMessage:
        raise ValueError("deliberate failure")

    stop_event = asyncio.Event()
    task = asyncio.create_task(runtime.serve(stop_event))
    await asyncio.sleep(3.0)

    client_id = AgentIdentity(agent_id="test.client4", display_name="Client", tenant_id="poc")
    client = A2AClient(client_id, broker_url=kafka_bootstrap_servers)

    failed_result = await client.submit(
        agent_id,
        cap_id,
        A2AMessage(role="user", parts=[A2APart(type="text", text="go")]),
        timeout_s=10.0,
    )
    rejected_result = await client.submit(
        agent_id,
        "no.such.cap",
        A2AMessage(role="user", parts=[A2APart(type="text", text="go")]),
        timeout_s=10.0,
    )

    stop_event.set()
    await asyncio.wait_for(task, timeout=5.0)

    assert failed_result.status == "failed"
    assert rejected_result.status == "rejected"
    assert failed_result.error is not None
    assert failed_result.error.category == "handler_error"
    assert rejected_result.error is not None
    assert rejected_result.error.category == "unsupported_capability"
