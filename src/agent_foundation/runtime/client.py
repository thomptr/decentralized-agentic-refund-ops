"""A2AClient: submit tasks to peer agents over Kafka (no router)."""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

from agent_foundation.a2a import A2AMessage
from agent_foundation.envelope import AgentIdentity
from agent_foundation.logging import get_logger
from agent_foundation.payloads.task import TaskRequest, TaskResult

_log = get_logger(__name__)


class A2AClient:
    def __init__(
        self,
        identity: AgentIdentity,
        broker_url: str = "localhost:9092",
    ) -> None:
        self._identity = identity
        self._broker_url = broker_url

    async def submit(
        self,
        target_agent_id: str,
        capability: str,
        input: A2AMessage,
        *,
        correlation_id: UUID | None = None,
        causation_id: UUID | None = None,
        task_id: UUID | None = None,
        timeout_s: float = 30.0,
    ) -> TaskResult:
        """Publish a TaskRequest to target_agent_id's endpoint topic, await correlated TaskResult.

        No supervisor or router is involved (FR-011). Raises TimeoutError if no result
        arrives within timeout_s (client-side await only; server-side handler liveness
        is out of scope per spec Assumptions).
        """
        from packages.contracts.topics import endpoint_topic

        resolved_task_id = task_id or uuid4()
        resolved_correlation_id = correlation_id or uuid4()
        # agent.task_request.v1 is a non-root event type, so the envelope requires a
        # causation_id. A client-initiated request has no upstream event, so it self-roots
        # against its own conversation (causation_id == correlation_id). Nested requests
        # pass an explicit causation_id (the parent request's event_id) and are unaffected.
        resolved_causation_id = causation_id or resolved_correlation_id
        target_topic = endpoint_topic(target_agent_id)

        req = TaskRequest(
            task_id=resolved_task_id,
            capability=capability,
            requester_agent_id=self._identity.agent_id,
            target_agent_id=target_agent_id,
            input=input,
        )

        # Propagate trace context into the TaskRequest if the field exists (fail-open).
        try:
            from agent_foundation.observability.propagation import current_trace_context

            tc = current_trace_context()
            if tc is not None and hasattr(req, "trace_context"):
                req.trace_context = tc
        except Exception:
            pass

        from agent_foundation.transport.publisher import Publisher

        # Wrap the publish + result-await with an a2a.task.send span (fail-open).
        try:
            from agent_foundation.observability.attributes import build_span_attrs
            from agent_foundation.observability.tracing import span as obs_span

            _span_ctx = obs_span(
                "a2a.task.send",
                attrs=build_span_attrs(
                    capability=capability,
                    task_id=str(resolved_task_id),
                    agent_id=self._identity.agent_id,
                ),
            )
        except Exception:
            _span_ctx = None

        async def _do_submit() -> TaskResult:
            async with Publisher(self._identity, self._broker_url) as publisher:
                await publisher.publish(
                    req,
                    "agent.task_request.v1",
                    resolved_correlation_id,
                    resolved_causation_id,
                    topic=target_topic,
                )
            return await self._await_result(resolved_task_id, timeout_s)

        if _span_ctx is not None:
            try:
                with _span_ctx:
                    return await _do_submit()
            except Exception:
                # If the span context itself raises on enter/exit, fall through to bare call.
                pass

        return await _do_submit()

    async def _await_result(self, task_id: UUID, timeout_s: float) -> TaskResult:
        from aiokafka import AIOKafkaConsumer  # type: ignore[import-untyped]

        from agent_foundation.envelope import EventEnvelope
        from agent_foundation.transport.topics import TOPIC_TASK_RESULT

        consumer = AIOKafkaConsumer(
            TOPIC_TASK_RESULT,
            bootstrap_servers=self._broker_url,
            group_id=None,
            auto_offset_reset="earliest",
            enable_auto_commit=False,
            value_deserializer=lambda b: b,
        )
        await consumer.start()
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout_s
        try:
            while True:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    raise TimeoutError(f"No result for task_id={task_id} within {timeout_s}s")
                try:
                    msg = await asyncio.wait_for(consumer.getone(), timeout=min(remaining, 1.0))
                except TimeoutError:
                    if loop.time() >= deadline:
                        raise TimeoutError(
                            f"No result for task_id={task_id} within {timeout_s}s"
                        ) from None
                    continue
                try:
                    envelope = EventEnvelope.model_validate_json(msg.value)
                    result = TaskResult.model_validate(envelope.payload)
                    if result.task_id == task_id:
                        return result
                except Exception:
                    continue
        finally:
            await consumer.stop()
