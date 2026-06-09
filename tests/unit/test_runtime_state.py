"""Unit tests for the AgentRuntime lifecycle state machine (T019).

Verifies FR-009: exactly one of {rejected} or {accepted + one terminal} per task_id.
"""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from agent_foundation.a2a import A2AMessage, A2APart
from agent_foundation.envelope import AgentIdentity
from agent_foundation.payloads.task import TaskRequest, TaskResult
from agent_foundation.runtime.agent_card import AgentCard, Capability
from agent_foundation.runtime.runtime import AgentRuntime

# ── helpers ──────────────────────────────────────────────────────────────────


def _identity(agent_id: str = "test.runtime.agent") -> AgentIdentity:
    return AgentIdentity(agent_id=agent_id, display_name="Test", tenant_id="poc")


def _capability(cap_id: str = "do.something") -> Capability:
    return Capability(id=cap_id, name="Do Something", description="Test capability")


def _card(agent_id: str = "test.runtime.agent") -> AgentCard:
    from packages.contracts.topics import endpoint_topic

    return AgentCard(
        agent_id=agent_id,
        name="Test Runtime Agent",
        description="For state machine tests",
        version="1.0.0",
        endpoint_topic=endpoint_topic(agent_id),
        capabilities=[_capability()],
    )


def _msg(text: str = "input") -> A2AMessage:
    return A2AMessage(role="user", parts=[A2APart(type="text", text=text)])


def _make_request(
    agent_id: str,
    capability: str = "do.something",
    task_id: UUID | None = None,
) -> TaskRequest:
    return TaskRequest(
        task_id=task_id or uuid4(),
        capability=capability,
        requester_agent_id="requester.agent",
        target_agent_id=agent_id,
        input=_msg(),
    )


def _make_envelope(req: TaskRequest, agent_id: str) -> bytes:
    from datetime import UTC, datetime
    from uuid import uuid4

    from agent_foundation.envelope import EventEnvelope

    env = EventEnvelope(
        event_id=uuid4(),
        correlation_id=uuid4(),
        causation_id=uuid4(),  # task_request is non-root; synthetic causation
        agent_id="requester.agent",
        tenant_id="poc",
        timestamp=datetime.now(UTC),
        event_type="agent.task_request.v1",
        schema_version="1.0.0",
        payload=req.model_dump(mode="json"),
    )
    return env.model_dump_json().encode()


# ── stub infrastructure ───────────────────────────────────────────────────────


class _StubTracker:
    def __init__(self) -> None:
        self._seen: set[UUID] = set()

    async def is_duplicate(self, task_id: UUID) -> bool:
        return task_id in self._seen

    async def mark_processed(self, task_id: UUID) -> None:
        self._seen.add(task_id)


class _StubPublisher:
    def __init__(self) -> None:
        self.results: list[TaskResult] = []
        self.audits: list[tuple[str, UUID | None]] = []
        self._identity = AgentIdentity(
            agent_id="test.runtime.agent", display_name="Test", tenant_id="poc"
        )

    async def publish_raw(self, envelope: object, topic: str) -> None:
        from agent_foundation.envelope import EventEnvelope

        assert isinstance(envelope, EventEnvelope)
        if envelope.event_type == "agent.task_result.v1":
            self.results.append(TaskResult.model_validate(envelope.payload))
        elif envelope.event_type == "agent.audit.v1":
            from agent_foundation.payloads.sample import AuditPayload

            ap = AuditPayload.model_validate(envelope.payload)
            task_id_val: UUID | None = ap.task_id
            self.audits.append((ap.outcome, task_id_val))


async def _drive(
    runtime: AgentRuntime,
    raw_msg: bytes,
    stub_tracker: _StubTracker,
    stub_publisher: _StubPublisher,
) -> None:
    from agent_foundation.audit.store import write_task_audit
    from agent_foundation.transport.topics import TOPIC_TASK_RESULT

    await runtime._handle_message(
        raw_msg,
        stub_publisher,
        stub_tracker,
        write_task_audit,
        TOPIC_TASK_RESULT,
    )


# ── test cases ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_validation_rejects_before_handler() -> None:
    """Unsupported capability → rejected, handler never runs."""
    agent_id = "test.runtime.agent"
    identity = _identity(agent_id)
    card = _card(agent_id)
    runtime = AgentRuntime(identity, card)

    handler_called = False

    @runtime.handler("do.something")
    async def _h(req: TaskRequest) -> A2AMessage:
        nonlocal handler_called
        handler_called = True
        return A2AMessage(role="agent", parts=[A2APart(type="text", text="done")])

    stub_tracker = _StubTracker()
    stub_publisher = _StubPublisher()

    req = _make_request(agent_id, capability="no.such.cap")
    raw = _make_envelope(req, agent_id)
    await _drive(runtime, raw, stub_tracker, stub_publisher)

    assert not handler_called
    assert len(stub_publisher.results) == 1
    assert stub_publisher.results[0].status == "rejected"
    assert stub_publisher.results[0].error is not None
    assert stub_publisher.results[0].error.category == "unsupported_capability"


@pytest.mark.asyncio
async def test_accepted_then_completed_on_success() -> None:
    """Valid task → accepted audit + completed result (exactly one terminal)."""
    agent_id = "test.runtime.agent"
    identity = _identity(agent_id)
    card = _card(agent_id)
    runtime = AgentRuntime(identity, card)

    @runtime.handler("do.something")
    async def _h(req: TaskRequest) -> A2AMessage:
        return A2AMessage(role="agent", parts=[A2APart(type="text", text="done")])

    stub_tracker = _StubTracker()
    stub_publisher = _StubPublisher()

    req = _make_request(agent_id)
    raw = _make_envelope(req, agent_id)
    await _drive(runtime, raw, stub_tracker, stub_publisher)

    assert len(stub_publisher.results) == 1
    assert stub_publisher.results[0].status == "completed"
    outcomes = [a[0] for a in stub_publisher.audits]
    assert "accepted" in outcomes
    assert "completed" in outcomes
    assert "rejected" not in outcomes
    assert "failed" not in outcomes


@pytest.mark.asyncio
async def test_accepted_then_failed_on_handler_exception() -> None:
    """Handler raises → accepted audit + failed result (exactly one terminal)."""
    agent_id = "test.runtime.agent"
    identity = _identity(agent_id)
    card = _card(agent_id)
    runtime = AgentRuntime(identity, card)

    @runtime.handler("do.something")
    async def _h(req: TaskRequest) -> A2AMessage:
        raise RuntimeError("handler blew up")

    stub_tracker = _StubTracker()
    stub_publisher = _StubPublisher()

    req = _make_request(agent_id)
    raw = _make_envelope(req, agent_id)
    await _drive(runtime, raw, stub_tracker, stub_publisher)

    assert len(stub_publisher.results) == 1
    assert stub_publisher.results[0].status == "failed"
    outcomes = [a[0] for a in stub_publisher.audits]
    assert "accepted" in outcomes
    assert "failed" in outcomes
    assert "completed" not in outcomes


@pytest.mark.asyncio
async def test_duplicate_task_id_short_circuits() -> None:
    """Duplicate task_id → duplicate_skipped audit, handler not re-run, no second result."""
    agent_id = "test.runtime.agent"
    identity = _identity(agent_id)
    card = _card(agent_id)
    runtime = AgentRuntime(identity, card)

    handler_call_count = 0

    @runtime.handler("do.something")
    async def _h(req: TaskRequest) -> A2AMessage:
        nonlocal handler_call_count
        handler_call_count += 1
        return A2AMessage(role="agent", parts=[A2APart(type="text", text="done")])

    stub_tracker = _StubTracker()
    stub_publisher = _StubPublisher()

    task_id = uuid4()
    req = _make_request(agent_id, task_id=task_id)
    raw = _make_envelope(req, agent_id)

    # First run — should complete normally
    await _drive(runtime, raw, stub_tracker, stub_publisher)
    assert handler_call_count == 1

    # Manually pre-seed tracker (simulate what mark_processed does)
    stub_tracker._seen.add(task_id)

    # Second run with same task_id — should be skipped
    stub_publisher.results.clear()
    stub_publisher.audits.clear()
    await _drive(runtime, raw, stub_tracker, stub_publisher)

    assert handler_call_count == 1, "Handler must not run a second time"
    assert len(stub_publisher.results) == 0, "No second result for duplicate task"
    outcomes = [a[0] for a in stub_publisher.audits]
    assert "duplicate_skipped" in outcomes


@pytest.mark.asyncio
async def test_wrong_target_rejected() -> None:
    """Request targeting wrong agent_id → rejected with validation error."""
    agent_id = "test.runtime.agent"
    identity = _identity(agent_id)
    card = _card(agent_id)
    runtime = AgentRuntime(identity, card)

    @runtime.handler("do.something")
    async def _h(req: TaskRequest) -> A2AMessage:
        return A2AMessage(role="agent", parts=[A2APart(type="text", text="done")])

    stub_tracker = _StubTracker()
    stub_publisher = _StubPublisher()

    req = _make_request("wrong.target.agent")
    raw = _make_envelope(req, agent_id)
    await _drive(runtime, raw, stub_tracker, stub_publisher)

    assert len(stub_publisher.results) == 1
    assert stub_publisher.results[0].status == "rejected"
    assert stub_publisher.results[0].error is not None
    assert stub_publisher.results[0].error.category == "validation"


def test_handler_decorator_rejects_undeclared_capability() -> None:
    """@runtime.handler raises ValueError for capabilities not on the card."""
    agent_id = "test.runtime.agent"
    identity = _identity(agent_id)
    card = _card(agent_id)
    runtime = AgentRuntime(identity, card)

    with pytest.raises(ValueError, match="not declared on the agent card"):

        @runtime.handler("not.declared")
        async def _h(req: TaskRequest) -> A2AMessage:
            return A2AMessage(role="agent", parts=[A2APart(type="text", text="x")])
