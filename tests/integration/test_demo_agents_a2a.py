"""Integration tests: US3 — Agent Card discovery and one-agent-calls-another via A2A.

Tests T030 (acceptance criteria 2 & 4).
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


def _make_runtime(agent_id: str, cap_id: str, broker: str):  # type: ignore[no-untyped-def]
    from agent_foundation.envelope import AgentIdentity
    from agent_foundation.runtime.agent_card import AgentCard, Capability
    from agent_foundation.runtime.runtime import AgentRuntime
    from packages.contracts.topics import endpoint_topic

    identity = AgentIdentity(agent_id=agent_id, display_name=agent_id, tenant_id="poc")
    card = AgentCard(
        agent_id=agent_id,
        name=agent_id,
        description=f"Test agent {agent_id}",
        version="1.0.0",
        endpoint_topic=endpoint_topic(agent_id),
        capabilities=[Capability(id=cap_id, name=cap_id, description="desc")],
    )
    return AgentRuntime(identity, card, broker_url=broker)


@pytest.mark.asyncio
async def test_discover_agents_returns_three_cards(kafka_bootstrap_servers: str) -> None:
    """discover_agents() returns the three expected cards (criterion 2)."""
    from agent_foundation.a2a import A2AMessage, A2APart
    from agent_foundation.payloads.task import TaskRequest
    from agent_foundation.runtime.discovery import discover_agents
    from agent_foundation.transport.topics import create_topics

    await create_topics(kafka_bootstrap_servers)

    suffix = uuid4().hex[:8]
    agents = [
        (f"customer-resolution.{suffix}", "resolve_customer_case"),
        (f"billing-entitlement.{suffix}", "analyze_refund_eligibility"),
        (f"risk-fraud.{suffix}", "assess_fraud_risk"),
    ]

    stop_events = [asyncio.Event() for _ in agents]
    runtimes = []
    for (aid, cap), stop in zip(agents, stop_events, strict=True):
        rt = _make_runtime(aid, cap, kafka_bootstrap_servers)

        @rt.handler(cap)
        async def _h(req: TaskRequest) -> A2AMessage:
            return A2AMessage(role="agent", parts=[A2APart(type="data", data={"mock": True})])

        runtimes.append((rt, stop))

    tasks = [
        asyncio.create_task(rt.serve(stop))
        for rt, stop in runtimes
    ]
    await asyncio.sleep(5.0)

    # Discover agents from compacted topic — no central registry
    cards = await discover_agents(kafka_bootstrap_servers)
    discovered_ids = {c.agent_id for c in cards}

    for aid, _ in agents:
        stop_events[agents.index((aid, next(cap for a, cap in agents if a == aid)))].set()

    for ev in stop_events:
        ev.set()
    await asyncio.wait(tasks, timeout=10.0)

    for aid, _ in agents:
        assert aid in discovered_ids, f"Expected agent {aid!r} in discovered cards"


@pytest.mark.asyncio
async def test_a2a_delegation_billing_to_customer(kafka_bootstrap_servers: str) -> None:
    """customer-resolution calls billing-entitlement via A2AClient (criterion 4)."""
    from agent_foundation.a2a import A2AMessage, A2APart
    from agent_foundation.envelope import AgentIdentity
    from agent_foundation.payloads.task import TaskRequest
    from agent_foundation.runtime import A2AClient, AgentCard, AgentRuntime, Capability
    from agent_foundation.transport.topics import create_topics
    from packages.contracts.topics import endpoint_topic

    await create_topics(kafka_bootstrap_servers)

    suffix = uuid4().hex[:8]
    billing_id = f"billing.{suffix}"
    customer_id = f"customer.{suffix}"

    # Billing agent
    billing_identity = AgentIdentity(
        agent_id=billing_id, display_name="Billing", tenant_id="poc"
    )
    billing_card = AgentCard(
        agent_id=billing_id,
        name="Billing",
        description="Billing test agent",
        version="1.0.0",
        endpoint_topic=endpoint_topic(billing_id),
        capabilities=[
            Capability(id="analyze_refund_eligibility", name="Analyze", description="desc")
        ],
    )
    billing_runtime = AgentRuntime(
        billing_identity, billing_card, broker_url=kafka_bootstrap_servers
    )

    @billing_runtime.handler("analyze_refund_eligibility")
    async def _billing(req: TaskRequest) -> A2AMessage:
        return A2AMessage(
            role="agent",
            parts=[A2APart(type="data", data={"eligible": True, "reason": "mock"})],
        )

    # Customer agent (delegates to billing via A2AClient)
    customer_identity = AgentIdentity(
        agent_id=customer_id, display_name="Customer", tenant_id="poc"
    )
    customer_card = AgentCard(
        agent_id=customer_id,
        name="Customer",
        description="Customer test agent",
        version="1.0.0",
        endpoint_topic=endpoint_topic(customer_id),
        capabilities=[Capability(id="resolve_customer_case", name="Resolve", description="desc")],
    )
    customer_runtime = AgentRuntime(
        customer_identity, customer_card, broker_url=kafka_bootstrap_servers
    )
    a2a_client = A2AClient(customer_identity, broker_url=kafka_bootstrap_servers)

    @customer_runtime.handler("resolve_customer_case")
    async def _customer(req: TaskRequest) -> A2AMessage:
        billing_result = await a2a_client.submit(
            billing_id,
            "analyze_refund_eligibility",
            A2AMessage(role="user", parts=[A2APart(type="text", text="check")]),
            timeout_s=10.0,
        )
        billing_data = (
            billing_result.output.parts[0].data
            if billing_result.output and billing_result.output.parts
            else {}
        )
        return A2AMessage(
            role="agent",
            parts=[A2APart(type="data", data={"resolved": True, "billing": billing_data})],
        )

    stop_billing = asyncio.Event()
    stop_customer = asyncio.Event()

    billing_task = asyncio.create_task(billing_runtime.serve(stop_billing))
    customer_task = asyncio.create_task(customer_runtime.serve(stop_customer))
    await asyncio.sleep(4.0)

    # Submit to customer agent from external client
    ext_identity = AgentIdentity(agent_id="ext.client", display_name="Ext", tenant_id="poc")
    ext_client = A2AClient(ext_identity, broker_url=kafka_bootstrap_servers)
    result = await ext_client.submit(
        customer_id,
        "resolve_customer_case",
        A2AMessage(role="user", parts=[A2APart(type="text", text="resolve this")]),
        timeout_s=20.0,
    )

    stop_billing.set()
    stop_customer.set()
    await asyncio.wait({billing_task, customer_task}, timeout=10.0)

    assert result.status == "completed"
    assert result.output is not None
    parts_data = result.output.parts[0].data
    assert parts_data is not None
    assert parts_data.get("resolved") is True
    # The billing verdict must be in the result (cross-agent delegation worked)
    assert "billing" in parts_data
    assert parts_data["billing"].get("eligible") is True
