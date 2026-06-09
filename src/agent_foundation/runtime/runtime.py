"""AgentRuntime: expose an A2A endpoint, serve tasks, and audit the lifecycle."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import ValidationError

from agent_foundation.a2a import A2AMessage
from agent_foundation.envelope import AgentIdentity, EventEnvelope
from agent_foundation.logging import (
    TASK_ACCEPTED,
    TASK_CARD_PUBLISHED,
    TASK_COMPLETED,
    TASK_DUPLICATE_SKIPPED,
    TASK_ENDPOINT_SERVING,
    TASK_FAILED,
    TASK_REJECTED,
    get_logger,
)
from agent_foundation.payloads.task import TaskError, TaskRequest, TaskResult
from agent_foundation.runtime.agent_card import AgentCard

_log = get_logger(__name__)

TaskHandler = Callable[[TaskRequest], Coroutine[Any, Any, A2AMessage]]


class AgentRuntime:
    def __init__(
        self,
        identity: AgentIdentity,
        card: AgentCard,
        broker_url: str = "localhost:9092",
    ) -> None:
        self._identity = identity
        self._card = card
        self._broker_url = broker_url
        self._handlers: dict[str, TaskHandler] = {}
        self._capability_ids: set[str] = {c.id for c in card.capabilities}
        self._publisher: Any = None

    def handler(self, capability_id: str) -> Callable[[TaskHandler], TaskHandler]:
        """Decorator: register an async handler for one declared capability."""
        if capability_id not in self._capability_ids:
            raise ValueError(
                f"Capability {capability_id!r} is not declared on the agent card; "
                f"declared: {sorted(self._capability_ids)}"
            )

        def _decorator(fn: TaskHandler) -> TaskHandler:
            self._handlers[capability_id] = fn
            return fn

        return _decorator

    async def republish_card(self, card: AgentCard | None = None) -> None:
        """Publish an updated Agent Card (latest-wins by agent_id on the compacted topic)."""
        if card is not None:
            self._card = card
        if self._publisher is not None:
            await self._publish_card(self._publisher)

    async def _publish_card(self, publisher: Any) -> None:
        from agent_foundation.transport.topics import TOPIC_AGENT_CARD

        card_envelope = EventEnvelope(
            event_id=uuid4(),
            correlation_id=uuid4(),
            causation_id=None,
            agent_id=self._identity.agent_id,
            tenant_id=self._identity.tenant_id,
            timestamp=datetime.now(UTC),
            event_type="agent.agent_card.v1",
            schema_version="1.0.0",
            payload=self._card.model_dump(mode="json"),
        )
        try:
            await publisher.publish_raw(card_envelope, TOPIC_AGENT_CARD)
            _log.info(TASK_CARD_PUBLISHED, agent_id=self._identity.agent_id)
        except Exception as exc:
            _log.warning("card.publish_failed", error=str(exc))

    async def serve(self, stop_event: asyncio.Event | None = None) -> None:
        """Ensure topics, publish card, consume endpoint topic, drive the task lifecycle."""
        from aiokafka import AIOKafkaConsumer  # type: ignore[import-untyped]

        from agent_foundation.audit.store import write_task_audit
        from agent_foundation.idempotency import IdempotencyTracker
        from agent_foundation.transport.publisher import Publisher
        from agent_foundation.transport.topics import (
            TOPIC_TASK_RESULT,
            create_topics,
            endpoint_topic_new_topic,
        )
        from packages.contracts.topics import endpoint_topic

        ep_topic = endpoint_topic(self._identity.agent_id)

        async with Publisher(self._identity, self._broker_url) as publisher:
            self._publisher = publisher

            await create_topics(
                self._broker_url,
                extra_topics=[endpoint_topic_new_topic(self._identity.agent_id)],
            )
            await self._publish_card(publisher)

            tracker = IdempotencyTracker(f"{self._identity.agent_id}.tasks", self._broker_url)
            await tracker.initialize()

            _log.info(
                TASK_ENDPOINT_SERVING,
                agent_id=self._identity.agent_id,
                endpoint_topic=ep_topic,
            )

            consumer = AIOKafkaConsumer(
                ep_topic,
                bootstrap_servers=self._broker_url,
                group_id=f"{self._identity.agent_id}.runtime",
                auto_offset_reset="latest",
                enable_auto_commit=True,
                value_deserializer=lambda b: b,
            )
            await consumer.start()
            try:
                while True:
                    if stop_event is not None and stop_event.is_set():
                        break
                    try:
                        msg = await asyncio.wait_for(consumer.getone(), timeout=0.5)
                    except TimeoutError:
                        continue
                    except Exception as exc:
                        _log.error("runtime.consumer_error", error=str(exc))
                        break

                    await self._handle_message(
                        msg.value, publisher, tracker, write_task_audit, TOPIC_TASK_RESULT
                    )
            finally:
                await consumer.stop()
                self._publisher = None

    async def _handle_message(
        self,
        raw: bytes,
        publisher: Any,
        tracker: Any,
        write_task_audit: Any,
        result_topic: str,
    ) -> None:
        # Parse envelope
        try:
            envelope = EventEnvelope.model_validate_json(raw)
        except Exception as exc:
            _log.warning("runtime.invalid_envelope", error=str(exc))
            return

        # Parse TaskRequest payload
        try:
            req = TaskRequest.model_validate(envelope.payload)
        except (ValidationError, Exception) as exc:
            _log.warning(
                TASK_REJECTED,
                reason="invalid_payload",
                error=str(exc),
                event_id=str(envelope.event_id),
            )
            raw_task_id = envelope.payload.get("task_id")
            task_id_for_result: UUID = UUID(str(raw_task_id)) if raw_task_id else uuid4()
            result = TaskResult(
                task_id=task_id_for_result,
                status="rejected",
                performer_agent_id=self._identity.agent_id,
                error=TaskError(category="validation", message=str(exc)[:500]),
            )
            await self._publish_result(publisher, result, envelope)
            await write_task_audit(publisher, envelope, "rejected", None, reason=str(exc)[:500])
            return

        task_id = req.task_id

        # Validate target_agent_id
        if req.target_agent_id != self._identity.agent_id:
            _log.warning(
                TASK_REJECTED,
                reason="wrong_target",
                target=req.target_agent_id,
                our_id=self._identity.agent_id,
                task_id=str(task_id),
            )
            result = TaskResult(
                task_id=task_id,
                status="rejected",
                performer_agent_id=self._identity.agent_id,
                error=TaskError(
                    category="validation",
                    message=(
                        f"This agent is {self._identity.agent_id!r}, not {req.target_agent_id!r}"
                    ),
                ),
            )
            await self._publish_result(publisher, result, envelope)
            await write_task_audit(publisher, envelope, "rejected", task_id, reason="wrong_target")
            return

        # Validate capability
        if req.capability not in self._capability_ids:
            _log.warning(
                TASK_REJECTED,
                reason="unsupported_capability",
                capability=req.capability,
                task_id=str(task_id),
            )
            result = TaskResult(
                task_id=task_id,
                status="rejected",
                performer_agent_id=self._identity.agent_id,
                error=TaskError(
                    category="unsupported_capability",
                    message=f"Capability {req.capability!r} is not supported",
                ),
            )
            await self._publish_result(publisher, result, envelope)
            await write_task_audit(
                publisher,
                envelope,
                "rejected",
                task_id,
                reason="unsupported_capability",
            )
            return

        # Idempotency check by task_id
        try:
            if await tracker.is_duplicate(task_id):
                _log.info(
                    TASK_DUPLICATE_SKIPPED,
                    task_id=str(task_id),
                    capability=req.capability,
                )
                await write_task_audit(
                    publisher, envelope, "duplicate_skipped", task_id, reason=None
                )
                return
        except Exception:
            pass

        # Emit accepted audit (before running handler)
        await write_task_audit(publisher, envelope, "accepted", task_id)
        _log.info(TASK_ACCEPTED, task_id=str(task_id), capability=req.capability)

        # Run handler
        handler = self._handlers.get(req.capability)
        if handler is None:
            _log.error(
                "runtime.no_handler",
                capability=req.capability,
                task_id=str(task_id),
            )
            result = TaskResult(
                task_id=task_id,
                status="failed",
                performer_agent_id=self._identity.agent_id,
                error=TaskError(
                    category="internal",
                    message="No handler registered for this capability",
                ),
            )
            await self._publish_result(publisher, result, envelope)
            await write_task_audit(publisher, envelope, "failed", task_id, reason="no_handler")
            return

        try:
            output: A2AMessage = await handler(req)
            result = TaskResult(
                task_id=task_id,
                status="completed",
                performer_agent_id=self._identity.agent_id,
                output=output,
            )
            await self._publish_result(publisher, result, envelope)
            await write_task_audit(publisher, envelope, "completed", task_id)
            _log.info(TASK_COMPLETED, task_id=str(task_id), capability=req.capability)
        except Exception as exc:
            _log.error(
                TASK_FAILED,
                task_id=str(task_id),
                capability=req.capability,
                error=str(exc),
            )
            result = TaskResult(
                task_id=task_id,
                status="failed",
                performer_agent_id=self._identity.agent_id,
                error=TaskError(category="handler_error", message=str(exc)[:500]),
            )
            await self._publish_result(publisher, result, envelope)
            await write_task_audit(publisher, envelope, "failed", task_id, reason=str(exc)[:500])

        # Mark task processed for idempotency
        import contextlib

        with contextlib.suppress(Exception):
            await tracker.mark_processed(task_id)

    async def _publish_result(
        self,
        publisher: Any,
        result: TaskResult,
        request_envelope: EventEnvelope,
    ) -> None:
        from agent_foundation.transport.topics import TOPIC_TASK_RESULT

        result_envelope = EventEnvelope(
            event_id=uuid4(),
            correlation_id=request_envelope.correlation_id,
            causation_id=request_envelope.event_id,
            agent_id=self._identity.agent_id,
            tenant_id=self._identity.tenant_id,
            timestamp=datetime.now(UTC),
            event_type="agent.task_result.v1",
            schema_version="1.0.0",
            payload=result.model_dump(mode="json"),
        )
        try:
            await publisher.publish_raw(result_envelope, TOPIC_TASK_RESULT)
        except Exception as exc:
            _log.warning(
                "runtime.result_publish_failed",
                error=str(exc),
                task_id=str(result.task_id),
            )
