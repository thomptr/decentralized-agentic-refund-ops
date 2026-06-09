"""Audit write helper and correlation / window query helpers."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from agent_foundation.logging import get_logger
from agent_foundation.payloads.sample import AuditPayload

if TYPE_CHECKING:
    from agent_foundation.envelope import EventEnvelope
    from agent_foundation.transport.publisher import Publisher

_log = get_logger(__name__)


async def write_audit(
    publisher: Publisher,
    envelope: EventEnvelope,
    outcome: str,
    reason: str | None,
) -> None:
    """Publish an AuditPayload envelope to the audit topic."""
    from datetime import UTC
    from uuid import uuid4

    from agent_foundation.envelope import EventEnvelope as EE
    from agent_foundation.transport.topics import TOPIC_AUDIT

    recorded_at = datetime.now(UTC)
    audit_payload = AuditPayload(
        original_envelope=envelope,
        outcome=outcome,  # type: ignore[arg-type]
        reason=reason,
        recorded_at=recorded_at,
    )

    audit_event_type = "agent.audit.v1"
    audit_envelope = EE(
        event_id=uuid4(),
        correlation_id=envelope.correlation_id,
        causation_id=envelope.event_id,
        agent_id=publisher._identity.agent_id,
        tenant_id=publisher._identity.tenant_id,
        timestamp=recorded_at,
        event_type=audit_event_type,
        schema_version="1.0.0",
        payload=audit_payload.model_dump(mode="json"),
    )
    try:
        await publisher.publish_raw(audit_envelope, TOPIC_AUDIT)
    except Exception as exc:
        _log.warning("audit.write_failed", error=str(exc), event_id=str(envelope.event_id))


async def query_by_correlation(
    bootstrap_servers: str,
    correlation_id: UUID,
) -> list[AuditPayload]:
    """Return all AuditPayload records for a correlation_id, ordered by Kafka offset."""
    records = await consume_all_audit_records(bootstrap_servers)
    return [r for r in records if r.original_envelope.correlation_id == correlation_id]


async def query_by_window(
    bootstrap_servers: str,
    start_dt: datetime,
    end_dt: datetime,
) -> list[AuditPayload]:
    """Return all AuditPayload records whose recorded_at falls within [start_dt, end_dt]."""
    records = await consume_all_audit_records(bootstrap_servers)
    return [r for r in records if start_dt <= r.recorded_at <= end_dt]


async def consume_all_audit_records(bootstrap_servers: str) -> list[AuditPayload]:
    """Consume the entire audit topic from earliest and return parsed AuditPayload records."""
    from aiokafka import AIOKafkaConsumer  # type: ignore[import-untyped]

    from agent_foundation.envelope import EventEnvelope as EE
    from agent_foundation.transport.topics import TOPIC_AUDIT

    consumer = AIOKafkaConsumer(
        TOPIC_AUDIT,
        bootstrap_servers=bootstrap_servers,
        group_id=None,
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        consumer_timeout_ms=3000,
    )
    await consumer.start()
    results: list[AuditPayload] = []
    try:
        async for msg in consumer:
            try:
                raw_envelope = EE.model_validate_json(msg.value)
                audit = AuditPayload.model_validate(raw_envelope.payload)
                results.append(audit)
            except Exception:
                pass
    except Exception:
        pass
    finally:
        await consumer.stop()
    return results
