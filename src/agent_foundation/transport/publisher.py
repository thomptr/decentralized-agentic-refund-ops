"""Async Kafka publisher with envelope construction, schema validation, and structlog."""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime
from types import TracebackType
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel

from agent_foundation.envelope import (
    AgentIdentity,
    EventEnvelope,
    MissingCausation,
)
from agent_foundation.logging import (
    EVENT_PUBLISH_FAILED,
    EVENT_PUBLISHED,
    get_logger,
)
from agent_foundation.observability import span
from agent_foundation.observability.attributes import attrs_from_envelope
from agent_foundation.observability.propagation import current_trace_context
from agent_foundation.payloads import PayloadValidationError, UnknownEventType, lookup

_log = get_logger(__name__)


class Publisher:
    """Async context manager that wraps AIOKafkaProducer with envelope building."""

    def __init__(
        self,
        agent_identity: AgentIdentity,
        bootstrap_servers: str = "localhost:9092",
    ) -> None:
        self._identity = agent_identity
        self._bootstrap_servers = bootstrap_servers
        self._producer: Any = None

    async def __aenter__(self) -> Publisher:
        from aiokafka import AIOKafkaProducer  # type: ignore[import-untyped]

        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._bootstrap_servers,
            enable_idempotence=True,
        )
        await self._producer.start()
        _log.bind(
            agent_id=self._identity.agent_id,
            tenant_id=self._identity.tenant_id,
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._producer is not None:
            await self._producer.stop()

    def _build_envelope(
        self,
        payload: BaseModel,
        event_type: str,
        correlation_id: UUID,
        causation_id: UUID | None = None,
    ) -> EventEnvelope:
        model_cls = lookup(event_type)  # raises UnknownEventType
        if not isinstance(payload, model_cls):
            raise PayloadValidationError(
                event_type,
                f"expected {model_cls.__name__}, got {type(payload).__name__}",
            )
        return EventEnvelope(
            event_id=uuid4(),
            correlation_id=correlation_id,
            causation_id=causation_id,
            agent_id=self._identity.agent_id,
            tenant_id=self._identity.tenant_id,
            timestamp=datetime.now(UTC),
            event_type=event_type,
            schema_version="1.0.0",
            payload=payload.model_dump(mode="json"),
        )

    def _resolve_topic(self, event_type: str) -> str:
        from agent_foundation.transport.topics import TOPIC_NAMES

        try:
            return TOPIC_NAMES[event_type]
        except KeyError as err:
            raise UnknownEventType(event_type) from err

    @staticmethod
    def _serialize(envelope: EventEnvelope) -> bytes:
        return envelope.model_dump_json().encode("utf-8")

    async def publish(
        self,
        payload: BaseModel,
        event_type: str,
        correlation_id: UUID,
        causation_id: UUID | None = None,
        *,
        topic: str | None = None,
    ) -> EventEnvelope:
        """Build, validate, serialize, and send an envelope. All exceptions propagate.

        topic: optional override; when set, bypasses registry topic resolution while
        keeping full payload validation (e.g. for dynamic per-agent endpoint topics).
        """
        try:
            envelope = self._build_envelope(payload, event_type, correlation_id, causation_id)
        except (UnknownEventType, PayloadValidationError, MissingCausation, ValueError) as exc:
            _log.error(
                EVENT_PUBLISH_FAILED,
                error=str(exc),
                event_type=event_type,
                correlation_id=str(correlation_id),
            )
            raise

        # Inject current trace context into the envelope before serialization
        ctx = current_trace_context()
        envelope = envelope.model_copy(update={"trace_context": ctx})

        resolved_topic = topic if topic is not None else self._resolve_topic(event_type)
        data = self._serialize(envelope)
        try:
            with span("kafka.publish", attrs=attrs_from_envelope(envelope)):
                await self._producer.send_and_wait(
                    resolved_topic,
                    value=data,
                    key=str(envelope.event_id).encode(),
                )
        except Exception as exc:
            _log.error(
                EVENT_PUBLISH_FAILED,
                error=str(exc),
                event_id=str(envelope.event_id),
                event_type=event_type,
                topic=resolved_topic,
            )
            raise

        _log.info(
            EVENT_PUBLISHED,
            event_id=str(envelope.event_id),
            correlation_id=str(correlation_id),
            event_type=event_type,
            topic=resolved_topic,
        )
        return envelope

    async def publish_raw(
        self,
        envelope: EventEnvelope,
        topic: str,
        *,
        key: str | None = None,
        trace: bool = True,
    ) -> None:
        """Publish a pre-built envelope directly (used by audit store).

        The Kafka message key defaults to the envelope's ``event_id``. Pass
        ``key`` to override it — compacted topics (e.g. agent-card discovery)
        must key by a stable identity such as ``agent_id`` so latest-wins
        compaction collapses to one record per agent instead of growing
        unbounded with a fresh ``event_id`` per publish.

        Set ``trace=False`` to skip the ``kafka.publish`` span for high-frequency
        operational publishes (e.g. liveness heartbeats) that would otherwise
        flood the trace backend with standalone, parent-less traces. Kafka stays
        the system of record regardless of whether the publish is traced.
        """
        # Inject current trace context into the envelope before serialization
        ctx = current_trace_context()
        envelope = envelope.model_copy(update={"trace_context": ctx})

        data = self._serialize(envelope)
        msg_key = (key if key is not None else str(envelope.event_id)).encode()
        publish_span = (
            span("kafka.publish", attrs=attrs_from_envelope(envelope))
            if trace
            else contextlib.nullcontext()
        )
        with publish_span:
            await self._producer.send_and_wait(
                topic,
                value=data,
                key=msg_key,
            )
