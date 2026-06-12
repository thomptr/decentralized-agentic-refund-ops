"""AgentRuntime: expose an A2A endpoint, serve tasks, and audit the lifecycle."""

from __future__ import annotations

import asyncio
import contextlib
import os
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

    def _start_background_tasks(
        self, publisher: Any, stop_event: asyncio.Event
    ) -> list[asyncio.Task[None]]:
        """Spawn the heartbeat emitter and periodic card-republish loops.

        Both are best-effort liveness/availability concerns kept out of task
        handling. The heartbeat honours the observability toggle/interval; the
        card republish honours ``AGENT_CARD_REPUBLISH_INTERVAL_S`` (0 disables).
        """
        from agent_foundation.observability.config import ObservabilityConfig
        from agent_foundation.observability.heartbeat import HeartbeatEmitter

        tasks: list[asyncio.Task[None]] = []

        obs = ObservabilityConfig.from_env(agent_id=self._identity.agent_id)
        hb_interval = obs.heartbeat_interval_s if obs.enabled else 0.0
        emitter = HeartbeatEmitter(
            agent_id=self._identity.agent_id,
            publisher=publisher,
            interval_s=hb_interval,
            tenant_id=self._identity.tenant_id,
        )
        if emitter.is_enabled:
            tasks.append(asyncio.create_task(emitter.run(stop_event)))

        try:
            card_interval = float(os.environ.get("AGENT_CARD_REPUBLISH_INTERVAL_S", "30"))
        except ValueError:
            card_interval = 30.0
        if card_interval > 0:
            tasks.append(
                asyncio.create_task(
                    self._republish_card_loop(publisher, card_interval, stop_event)
                )
            )
        return tasks

    async def _republish_card_loop(
        self, publisher: Any, interval_s: float, stop_event: asyncio.Event
    ) -> None:
        """Periodically re-publish the Agent Card on the compacted discovery topic.

        A card is otherwise published only once at startup, so the discovery
        registry never recovers if the topic is purged/recreated or the broker
        loses data — a long-running agent would silently vanish until its next
        restart. Re-publishing on an interval makes the registry self-healing
        and keeps ``last_announced`` fresh. The card is keyed by ``agent_id``,
        so compaction keeps exactly one record per agent no matter how often
        this runs.
        """
        if interval_s <= 0:
            return
        while True:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval_s)
                break  # stop requested
            except TimeoutError:
                pass  # interval elapsed → republish
            await self._publish_card(publisher)

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
            await publisher.publish_raw(
                card_envelope, TOPIC_AGENT_CARD, key=self._identity.agent_id
            )
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

            # Background liveness/availability tasks. They share a private stop
            # event so they shut down cleanly when serve() exits, independent of
            # whether the caller passed a stop_event.
            bg_stop = asyncio.Event()
            bg_tasks = self._start_background_tasks(publisher, bg_stop)

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
                bg_stop.set()
                for task in bg_tasks:
                    task.cancel()
                for task in bg_tasks:
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await task
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

        # Extract OTel parent context from envelope trace_context (fail-open)
        try:
            from agent_foundation.observability.propagation import extract as obs_extract

            _trace_ctx = getattr(req, "trace_context", None)
            obs_extract(_trace_ctx)
        except Exception:
            pass

        # Wrap handler dispatch with a2a.task.receive span (fail-open)
        try:
            from agent_foundation.observability.attributes import build_span_attrs
            from agent_foundation.observability.tracing import span as obs_span

            _span_attrs = build_span_attrs(
                capability=req.capability,
                task_id=str(task_id),
                agent_id=self._identity.agent_id,
            )
            _span_cm: contextlib.AbstractContextManager[Any] = obs_span(
                "a2a.task.receive", attrs=_span_attrs
            )
        except Exception:
            _span_cm = contextlib.nullcontext()

        try:
            with _span_cm:
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
                    await write_task_audit(
                        publisher, envelope, "failed", task_id, reason=str(exc)[:500]
                    )
        except Exception:
            pass

        # Mark task processed for idempotency
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
