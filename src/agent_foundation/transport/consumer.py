"""Async Kafka consumer with envelope validation, idempotency, and audit integration."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable, Coroutine
from typing import Any

import structlog
from pydantic import ValidationError

from agent_foundation.envelope import AgentIdentity, EventEnvelope
from agent_foundation.logging import (
    CONSUMER_ERROR,
    EVENT_DUPLICATE_SKIPPED,
    EVENT_RECEIVED,
    EVENT_REJECTED,
    get_logger,
)
from agent_foundation.observability.attributes import attrs_from_envelope
from agent_foundation.observability.propagation import extract
from agent_foundation.observability.tracing import span as obs_span
from agent_foundation.payloads import UnknownEventType, lookup

_log = get_logger(__name__)

Handler = Callable[[EventEnvelope], Coroutine[Any, Any, None]]


class Consumer:
    def __init__(
        self,
        broker_url: str,
        group_id: str,
        agent_identity: AgentIdentity,
        idempotent: bool = True,
    ) -> None:
        self._broker_url = broker_url
        self._group_id = group_id
        self._identity = agent_identity
        self._idempotent = idempotent
        self._topics: list[str] = []
        self._consumer: Any = None
        self._seek_to_beginning_flag = False
        self._seek_to_offset_val: int | None = None

    def subscribe(self, topics: list[str]) -> None:
        self._topics = topics

    def seek_to_beginning(self) -> None:
        self._seek_to_beginning_flag = True
        self._seek_to_offset_val = None

    def seek_to_offset(self, offset: int) -> None:
        self._seek_to_offset_val = offset
        self._seek_to_beginning_flag = False

    async def stop(self) -> None:
        if self._consumer is not None:
            await self._consumer.stop()
            self._consumer = None

    async def run(
        self,
        handler: Handler,
        stop_event: asyncio.Event | None = None,
        publisher: Any = None,
    ) -> None:
        """Consume messages, validate envelopes, call handler, write audit records."""
        from aiokafka import AIOKafkaConsumer  # type: ignore[import-untyped]

        from agent_foundation.audit.store import write_audit
        from agent_foundation.idempotency import IdempotencyTracker

        tracker: IdempotencyTracker | None = None
        if self._idempotent:
            tracker = IdempotencyTracker(self._group_id, self._broker_url)
            await tracker.initialize()

        self._consumer = AIOKafkaConsumer(
            *self._topics,
            bootstrap_servers=self._broker_url,
            group_id=self._group_id,
            auto_offset_reset="earliest" if self._seek_to_beginning_flag else "latest",
            enable_auto_commit=True,
            value_deserializer=lambda b: b,
        )
        await self._consumer.start()

        if self._seek_to_beginning_flag:
            partitions = self._consumer.assignment()
            await self._consumer.seek_to_beginning(*partitions)
        elif self._seek_to_offset_val is not None:
            partitions = self._consumer.assignment()
            for tp in partitions:
                self._consumer.seek(tp, self._seek_to_offset_val)

        try:
            while True:
                if stop_event is not None and stop_event.is_set():
                    break
                try:
                    msg = await asyncio.wait_for(self._consumer.getone(), timeout=0.5)
                except TimeoutError:
                    continue
                except Exception as exc:
                    _log.error(CONSUMER_ERROR, error=str(exc))
                    break

                raw = msg.value
                try:
                    envelope = EventEnvelope.model_validate_json(raw)
                except (ValidationError, Exception) as exc:
                    _log.warning(
                        EVENT_REJECTED,
                        reason="invalid_envelope",
                        error=str(exc),
                        topic=msg.topic,
                    )
                    if publisher:
                        try:
                            partial = _make_partial_envelope(raw)
                            if partial:
                                await write_audit(
                                    publisher, partial, "rejected", "invalid_envelope"
                                )
                        except Exception:
                            pass
                    continue

                # Idempotency check.
                if tracker is not None:
                    try:
                        if await tracker.is_duplicate(envelope.event_id):
                            _log.info(
                                EVENT_DUPLICATE_SKIPPED,
                                event_id=str(envelope.event_id),
                                event_type=envelope.event_type,
                            )
                            if publisher:
                                await write_audit(publisher, envelope, "duplicate_skipped", None)
                            continue
                    except Exception:
                        pass

                # Payload registry check.
                try:
                    model_cls = lookup(envelope.event_type)
                    model_cls.model_validate(envelope.payload)
                except (UnknownEventType, ValidationError) as exc:
                    reason = (
                        "unknown_schema_version"
                        if isinstance(exc, UnknownEventType)
                        else "payload_invalid"
                    )
                    _log.warning(
                        EVENT_REJECTED,
                        event_id=str(envelope.event_id),
                        event_type=envelope.event_type,
                        reason=reason,
                        error=str(exc),
                    )
                    if publisher:
                        await write_audit(publisher, envelope, "rejected", reason)
                    continue

                _log.info(
                    EVENT_RECEIVED,
                    event_id=str(envelope.event_id),
                    event_type=envelope.event_type,
                    correlation_id=str(envelope.correlation_id),
                )

                with contextlib.suppress(Exception):
                    extract(envelope.trace_context)

                with contextlib.suppress(Exception):
                    structlog.contextvars.bind_contextvars(
                        correlation_id=str(envelope.correlation_id)
                    )

                handler_error = False
                try:
                    with obs_span("event.consume", attrs=attrs_from_envelope(envelope)):
                        await handler(envelope)
                except Exception as exc:
                    _log.error(CONSUMER_ERROR, error=str(exc), event_id=str(envelope.event_id))
                    handler_error = True
                finally:
                    with contextlib.suppress(Exception):
                        structlog.contextvars.clear_contextvars()

                if handler_error:
                    continue

                if tracker is not None:
                    with contextlib.suppress(Exception):
                        await tracker.mark_processed(envelope.event_id)

                if publisher:
                    with contextlib.suppress(Exception):
                        await write_audit(publisher, envelope, "accepted", None)

        finally:
            await self._consumer.stop()
            self._consumer = None


def _make_partial_envelope(raw: bytes) -> EventEnvelope | None:
    """Attempt to extract a valid envelope from partially-valid bytes."""
    try:
        return EventEnvelope.model_validate_json(raw)
    except Exception:
        return None
