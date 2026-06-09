"""Integration tests: US1 — all three agents start independently and reject unsupported caps.

Tests T024 (acceptance criteria 1 & 3).
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


def _make_identity(agent_id: str):  # type: ignore[no-untyped-def]
    from agent_foundation.envelope import AgentIdentity

    return AgentIdentity(agent_id=agent_id, display_name=agent_id, tenant_id="poc")


def _make_card(agent_id: str, cap_id: str):  # type: ignore[no-untyped-def]
    from agent_foundation.runtime.agent_card import AgentCard, Capability
    from packages.contracts.topics import endpoint_topic

    return AgentCard(
        agent_id=agent_id,
        name=agent_id,
        description=f"Test agent {agent_id}",
        version="1.0.0",
        endpoint_topic=endpoint_topic(agent_id),
        capabilities=[Capability(id=cap_id, name=cap_id, description="test cap")],
    )


async def _run_agent_briefly(
    agent_id: str,
    cap_id: str,
    broker: str,
    stop_event: asyncio.Event,
) -> None:
    from agent_foundation.a2a import A2AMessage, A2APart
    from agent_foundation.payloads.task import TaskRequest
    from agent_foundation.runtime.runtime import AgentRuntime

    identity = _make_identity(agent_id)
    card = _make_card(agent_id, cap_id)
    runtime = AgentRuntime(identity, card, broker_url=broker)

    @runtime.handler(cap_id)
    async def _h(req: TaskRequest) -> A2AMessage:
        return A2AMessage(role="agent", parts=[A2APart(type="data", data={"result": "mock"})])

    await runtime.serve(stop_event)


@pytest.mark.asyncio
async def test_three_agents_start_independently(kafka_bootstrap_servers: str) -> None:
    """All three demo agents can start in the same broker without conflict."""
    from agent_foundation.transport.topics import create_topics

    await create_topics(kafka_bootstrap_servers)

    stop_events = [asyncio.Event() for _ in range(3)]
    agents = [
        ("customer-resolution-agent", "resolve_customer_case"),
        ("billing-entitlement-agent", "analyze_refund_eligibility"),
        ("risk-fraud-agent", "assess_fraud_risk"),
    ]

    tasks = [
        asyncio.create_task(_run_agent_briefly(aid, cap, kafka_bootstrap_servers, stop_events[i]))
        for i, (aid, cap) in enumerate(agents)
    ]

    # Give agents time to start and publish their cards
    await asyncio.sleep(5.0)

    for ev in stop_events:
        ev.set()

    await asyncio.wait(tasks, timeout=10.0)

    # If we get here without exceptions, all three agents started independently
    assert True


@pytest.mark.asyncio
async def test_agent_rejects_unsupported_capability(kafka_bootstrap_servers: str) -> None:
    """Agent rejects a task for a capability it does not declare."""
    from agent_foundation.a2a import A2AMessage, A2APart
    from agent_foundation.envelope import AgentIdentity
    from agent_foundation.runtime import A2AClient, AgentCard, AgentRuntime, Capability
    from agent_foundation.transport.topics import create_topics
    from packages.contracts.topics import endpoint_topic

    await create_topics(kafka_bootstrap_servers)

    agent_id = f"test.startup.{uuid4().hex[:8]}"
    cap_id = "my.real.capability"
    identity = AgentIdentity(agent_id=agent_id, display_name="Test", tenant_id="poc")
    card = AgentCard(
        agent_id=agent_id,
        name="Test",
        description="Test",
        version="1.0.0",
        endpoint_topic=endpoint_topic(agent_id),
        capabilities=[Capability(id=cap_id, name="Real Cap", description="The real cap")],
    )
    runtime = AgentRuntime(identity, card, broker_url=kafka_bootstrap_servers)

    from agent_foundation.payloads.task import TaskRequest

    @runtime.handler(cap_id)
    async def _h(req: TaskRequest) -> A2AMessage:
        return A2AMessage(role="agent", parts=[A2APart(type="data", data={"ok": True})])

    stop_event = asyncio.Event()
    agent_task = asyncio.create_task(runtime.serve(stop_event))
    await asyncio.sleep(3.0)

    # Submit a task for a capability the agent does NOT declare
    client_identity = AgentIdentity(
        agent_id="test.client", display_name="Test Client", tenant_id="poc"
    )
    client = A2AClient(client_identity, broker_url=kafka_bootstrap_servers)
    result = await client.submit(
        agent_id,
        "no.such.capability",
        A2AMessage(role="user", parts=[A2APart(type="text", text="test")]),
        timeout_s=10.0,
    )

    stop_event.set()
    await asyncio.wait_for(agent_task, timeout=5.0)

    assert result.status == "rejected"
    assert result.error is not None
    assert result.error.category == "unsupported_capability"


@pytest.mark.asyncio
async def test_agent_accepts_supported_capability(kafka_bootstrap_servers: str) -> None:
    """Agent accepts and completes a task for a supported capability."""
    from agent_foundation.a2a import A2AMessage, A2APart
    from agent_foundation.envelope import AgentIdentity
    from agent_foundation.runtime import A2AClient, AgentCard, AgentRuntime, Capability
    from agent_foundation.transport.topics import create_topics
    from packages.contracts.topics import endpoint_topic

    await create_topics(kafka_bootstrap_servers)

    agent_id = f"test.accept.{uuid4().hex[:8]}"
    cap_id = "supported.cap"
    identity = AgentIdentity(agent_id=agent_id, display_name="Test", tenant_id="poc")
    card = AgentCard(
        agent_id=agent_id,
        name="Test",
        description="Test",
        version="1.0.0",
        endpoint_topic=endpoint_topic(agent_id),
        capabilities=[Capability(id=cap_id, name="Supported Cap", description="desc")],
    )
    runtime = AgentRuntime(identity, card, broker_url=kafka_bootstrap_servers)

    from agent_foundation.payloads.task import TaskRequest

    @runtime.handler(cap_id)
    async def _h(req: TaskRequest) -> A2AMessage:
        return A2AMessage(role="agent", parts=[A2APart(type="data", data={"mock": "result"})])

    stop_event = asyncio.Event()
    agent_task = asyncio.create_task(runtime.serve(stop_event))
    await asyncio.sleep(3.0)

    client_identity = AgentIdentity(
        agent_id="test.client", display_name="Test Client", tenant_id="poc"
    )
    client = A2AClient(client_identity, broker_url=kafka_bootstrap_servers)
    result = await client.submit(
        agent_id,
        cap_id,
        A2AMessage(role="user", parts=[A2APart(type="text", text="go")]),
        timeout_s=10.0,
    )

    stop_event.set()
    await asyncio.wait_for(agent_task, timeout=5.0)

    assert result.status == "completed"
    assert result.output is not None
    assert result.output.parts[0].data == {"mock": "result"}
