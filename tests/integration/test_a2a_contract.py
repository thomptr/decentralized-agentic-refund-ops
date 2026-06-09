"""Integration A2A contract tests (Phase 9, T045–T051).

Cases 4–10: server-side reject/accept/idempotency, client timeout, audit events.
Requires a live Kafka broker via testcontainers.
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


def _make_serving_agent(
    broker: str,
    cap_id: str = "analyze_refund_eligibility",
):  # type: ignore[no-untyped-def]
    from agent_foundation.a2a import A2AMessage, A2APart
    from agent_foundation.envelope import AgentIdentity
    from agent_foundation.payloads.task import TaskRequest
    from agent_foundation.runtime.agent_card import AgentCard, Capability
    from agent_foundation.runtime.runtime import AgentRuntime
    from packages.contracts.topics import endpoint_topic

    agent_id = f"billing.{uuid4().hex[:8]}"
    identity = AgentIdentity(agent_id=agent_id, display_name="Billing", tenant_id="poc")
    card = AgentCard(
        agent_id=agent_id,
        name="Billing",
        description="Test billing agent",
        version="1.0.0",
        endpoint_topic=endpoint_topic(agent_id),
        capabilities=[Capability(id=cap_id, name=cap_id, description="desc")],
    )
    runtime = AgentRuntime(identity, card, broker_url=broker)

    @runtime.handler(cap_id)
    async def _h(req: TaskRequest) -> A2AMessage:
        for part in req.input.parts:
            if part.type == "text" and part.text == "FAIL":
                raise RuntimeError("Billing failure sentinel triggered")
        return A2AMessage(
            role="agent",
            parts=[A2APart(type="data", data={"eligible": True, "reason": "mock"})],
        )

    return agent_id, runtime


@pytest.mark.asyncio
async def test_case4_server_rejects_unknown_capability(kafka_bootstrap_servers: str) -> None:
    """Case 4: Server rejects task for undeclared capability with 'unsupported_capability'."""
    from agent_foundation.a2a import A2AMessage, A2APart
    from agent_foundation.envelope import AgentIdentity
    from agent_foundation.runtime import A2AClient
    from agent_foundation.transport.topics import create_topics

    await create_topics(kafka_bootstrap_servers)
    agent_id, runtime = _make_serving_agent(kafka_bootstrap_servers)

    stop = asyncio.Event()
    task = asyncio.create_task(runtime.serve(stop))
    await asyncio.sleep(3.0)

    client = A2AClient(
        AgentIdentity(agent_id="test.client", display_name="C", tenant_id="poc"),
        broker_url=kafka_bootstrap_servers,
    )
    result = await client.submit(
        agent_id,
        "no.such.cap",
        A2AMessage(role="user", parts=[A2APart(type="text", text="go")]),
        timeout_s=10.0,
    )

    stop.set()
    await asyncio.wait_for(task, timeout=5.0)

    assert result.status == "rejected"
    assert result.error is not None
    assert result.error.category == "unsupported_capability"


@pytest.mark.asyncio
async def test_case5_server_rejects_wrong_target_agent_id(kafka_bootstrap_servers: str) -> None:
    """Case 5: Request with wrong target_agent_id → rejected (validation)."""
    from agent_foundation.a2a import A2AMessage, A2APart
    from agent_foundation.envelope import AgentIdentity
    from agent_foundation.runtime import A2AClient
    from agent_foundation.transport.topics import create_topics

    await create_topics(kafka_bootstrap_servers)
    agent_id, runtime = _make_serving_agent(kafka_bootstrap_servers)

    stop = asyncio.Event()
    task = asyncio.create_task(runtime.serve(stop))
    await asyncio.sleep(3.0)

    # Submit to the correct endpoint topic but with wrong target_agent_id in payload

    from agent_foundation.payloads.task import TaskRequest
    from agent_foundation.transport.publisher import Publisher
    from packages.contracts.topics import endpoint_topic

    client_id = AgentIdentity(agent_id="test.client", display_name="C", tenant_id="poc")

    # Manually build a TaskRequest addressed to wrong agent
    req = TaskRequest(
        task_id=uuid4(),
        capability="analyze_refund_eligibility",
        requester_agent_id="test.client",
        target_agent_id="completely.wrong.agent",  # wrong!
        input=A2AMessage(role="user", parts=[A2APart(type="text", text="go")]),
    )

    corr_id = uuid4()
    async with Publisher(client_id, kafka_bootstrap_servers) as pub:
        await pub.publish(
            req,
            "agent.task_request.v1",
            corr_id,
            uuid4(),
            topic=endpoint_topic(agent_id),  # send to the right topic but wrong agent_id
        )

    # Listen for result
    client = A2AClient(client_id, broker_url=kafka_bootstrap_servers)
    result = await client._await_result(req.task_id, timeout_s=10.0)

    stop.set()
    await asyncio.wait_for(task, timeout=5.0)

    assert result.status == "rejected"
    assert result.error is not None
    assert result.error.category == "validation"


@pytest.mark.asyncio
async def test_case6_valid_task_executes_handler(kafka_bootstrap_servers: str) -> None:
    """Case 6: Valid task → handler runs, TaskResult(status='completed') with output."""
    from agent_foundation.a2a import A2AMessage, A2APart
    from agent_foundation.envelope import AgentIdentity
    from agent_foundation.runtime import A2AClient
    from agent_foundation.transport.topics import create_topics

    await create_topics(kafka_bootstrap_servers)
    agent_id, runtime = _make_serving_agent(kafka_bootstrap_servers)

    stop = asyncio.Event()
    task = asyncio.create_task(runtime.serve(stop))
    await asyncio.sleep(3.0)

    client = A2AClient(
        AgentIdentity(agent_id="test.client", display_name="C", tenant_id="poc"),
        broker_url=kafka_bootstrap_servers,
    )
    result = await client.submit(
        agent_id,
        "analyze_refund_eligibility",
        A2AMessage(role="user", parts=[A2APart(type="text", text="go")]),
        timeout_s=10.0,
    )

    stop.set()
    await asyncio.wait_for(task, timeout=5.0)

    assert result.status == "completed"
    assert result.output is not None
    assert result.performer_agent_id == agent_id


@pytest.mark.asyncio
async def test_case7_duplicate_idempotency_key_no_re_execute(
    kafka_bootstrap_servers: str,
) -> None:
    """Case 7: Duplicate task_id → handler invoked exactly once, second is duplicate_skipped."""
    from agent_foundation.a2a import A2AMessage, A2APart
    from agent_foundation.payloads.task import TaskRequest
    from agent_foundation.runtime import A2AClient
    from agent_foundation.runtime.agent_card import AgentCard, Capability
    from agent_foundation.runtime.runtime import AgentRuntime
    from agent_foundation.transport.topics import create_topics
    from packages.contracts.topics import endpoint_topic

    await create_topics(kafka_bootstrap_servers)

    agent_id = f"idem.{uuid4().hex[:8]}"
    from agent_foundation.envelope import AgentIdentity as AI

    identity = AI(agent_id=agent_id, display_name="Idempotent", tenant_id="poc")
    card = AgentCard(
        agent_id=agent_id,
        name="Idem",
        description="Idempotency test agent",
        version="1.0.0",
        endpoint_topic=endpoint_topic(agent_id),
        capabilities=[Capability(id="do.work", name="Do Work", description="desc")],
    )
    runtime = AgentRuntime(identity, card, broker_url=kafka_bootstrap_servers)

    call_count = 0

    @runtime.handler("do.work")
    async def _h(req: TaskRequest) -> A2AMessage:
        nonlocal call_count
        call_count += 1
        return A2AMessage(role="agent", parts=[A2APart(type="data", data={"n": call_count})])

    stop = asyncio.Event()
    task = asyncio.create_task(runtime.serve(stop))
    await asyncio.sleep(3.0)

    client = A2AClient(
        AI(agent_id="test.client", display_name="C", tenant_id="poc"),
        broker_url=kafka_bootstrap_servers,
    )
    shared_task_id = uuid4()

    # First submission
    result1 = await client.submit(
        agent_id,
        "do.work",
        A2AMessage(role="user", parts=[A2APart(type="text", text="first")]),
        task_id=shared_task_id,
        timeout_s=10.0,
    )
    await asyncio.sleep(1.0)

    # Second submission with SAME task_id (replay)
    from agent_foundation.transport.publisher import Publisher
    from packages.contracts.topics import endpoint_topic

    req2 = TaskRequest(
        task_id=shared_task_id,
        capability="do.work",
        requester_agent_id="test.client",
        target_agent_id=agent_id,
        input=A2AMessage(role="user", parts=[A2APart(type="text", text="replay")]),
    )
    async with Publisher(
        AI(agent_id="test.client", display_name="C", tenant_id="poc"),
        kafka_bootstrap_servers,
    ) as pub:
        await pub.publish(
            req2,
            "agent.task_request.v1",
            uuid4(),
            uuid4(),
            topic=endpoint_topic(agent_id),
        )

    await asyncio.sleep(2.0)
    stop.set()
    await asyncio.wait_for(task, timeout=5.0)

    assert result1.status == "completed"
    assert call_count == 1, f"Handler must run exactly once; ran {call_count} times"


@pytest.mark.asyncio
async def test_case8_timeout_raises_structured_error(kafka_bootstrap_servers: str) -> None:
    """Case 8: Client-side timeout raises TimeoutError when no agent serves the target.

    Note: This tests client await-timeout only. Server-side handler liveness/deadline
    detection is out of scope per spec Assumptions.
    """
    from agent_foundation.a2a import A2AMessage, A2APart
    from agent_foundation.envelope import AgentIdentity
    from agent_foundation.runtime import A2AClient
    from agent_foundation.transport.topics import create_topics

    await create_topics(kafka_bootstrap_servers)

    client = A2AClient(
        AgentIdentity(agent_id="test.client", display_name="C", tenant_id="poc"),
        broker_url=kafka_bootstrap_servers,
    )

    with pytest.raises(TimeoutError):
        await client.submit(
            "nonexistent.agent.never.starts",
            "some.capability",
            A2AMessage(role="user", parts=[A2APart(type="text", text="go")]),
            timeout_s=2.0,
        )


@pytest.mark.asyncio
async def test_case9_failure_emits_audit_event(kafka_bootstrap_servers: str) -> None:
    """Case 9: FAIL sentinel → TaskResult(failed) + audit sequence accepted→failed."""
    from agent_foundation.a2a import A2AMessage, A2APart
    from agent_foundation.audit.store import query_by_task_id
    from agent_foundation.envelope import AgentIdentity
    from agent_foundation.runtime import A2AClient
    from agent_foundation.transport.topics import create_topics

    await create_topics(kafka_bootstrap_servers)
    agent_id, runtime = _make_serving_agent(kafka_bootstrap_servers)

    stop = asyncio.Event()
    task = asyncio.create_task(runtime.serve(stop))
    await asyncio.sleep(3.0)

    task_id = uuid4()
    client = A2AClient(
        AgentIdentity(agent_id="test.client", display_name="C", tenant_id="poc"),
        broker_url=kafka_bootstrap_servers,
    )
    result = await client.submit(
        agent_id,
        "analyze_refund_eligibility",
        A2AMessage(role="user", parts=[A2APart(type="text", text="FAIL")]),
        task_id=task_id,
        timeout_s=10.0,
    )

    await asyncio.sleep(1.0)
    stop.set()
    await asyncio.wait_for(task, timeout=5.0)

    assert result.status == "failed"
    assert result.error is not None
    assert result.error.category == "handler_error"

    records = await query_by_task_id(kafka_bootstrap_servers, task_id)
    outcomes = [r.outcome for r in records]
    assert "accepted" in outcomes
    assert "failed" in outcomes
    assert "completed" not in outcomes
    # Verify reason is non-null for failed audit
    failed_rec = next(r for r in records if r.outcome == "failed")
    assert failed_rec.reason is not None


@pytest.mark.asyncio
async def test_case10_completed_task_emits_audit_event(kafka_bootstrap_servers: str) -> None:
    """Case 10: Successful task → audit sequence exactly accepted→completed, never both terminal."""
    from agent_foundation.a2a import A2AMessage, A2APart
    from agent_foundation.audit.store import query_by_task_id
    from agent_foundation.envelope import AgentIdentity
    from agent_foundation.runtime import A2AClient
    from agent_foundation.transport.topics import create_topics

    await create_topics(kafka_bootstrap_servers)
    agent_id, runtime = _make_serving_agent(kafka_bootstrap_servers)

    stop = asyncio.Event()
    task = asyncio.create_task(runtime.serve(stop))
    await asyncio.sleep(3.0)

    task_id = uuid4()
    client = A2AClient(
        AgentIdentity(agent_id="test.client", display_name="C", tenant_id="poc"),
        broker_url=kafka_bootstrap_servers,
    )
    result = await client.submit(
        agent_id,
        "analyze_refund_eligibility",
        A2AMessage(role="user", parts=[A2APart(type="text", text="go")]),
        task_id=task_id,
        timeout_s=10.0,
    )

    await asyncio.sleep(1.0)
    stop.set()
    await asyncio.wait_for(task, timeout=5.0)

    assert result.status == "completed"

    records = await query_by_task_id(kafka_bootstrap_servers, task_id)
    outcomes = [r.outcome for r in records]
    assert "accepted" in outcomes
    assert "completed" in outcomes
    assert "failed" not in outcomes
    # Exactly one terminal outcome (completed) — never both completed and failed
    terminal = [o for o in outcomes if o in ("completed", "failed")]
    assert len(terminal) == 1
