"""ReasoningAuditRecord — immutable, correlated record of one reasoning step."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from agent_foundation.llm.errors import FailureReason
from agent_foundation.llm.request import TaskKind
from agent_foundation.llm.result import ReasoningPath, TokenUsage
from agent_foundation.logging import get_logger

_log = get_logger(__name__)


class ReasoningAuditRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    agent_id: str
    correlation_id: UUID
    causation_id: UUID
    task_kind: TaskKind
    model_id: str | None = None
    model_params: dict[str, Any] = {}
    prompt_ref: str = ""
    grounding_digest: dict[str, Any] = {}
    reasoning_path: ReasoningPath
    result_summary: dict[str, Any] = {}
    token_usage: TokenUsage | None = None
    cache_hit: bool = False
    latency_ms: int = 0
    outcome: str = "produced"
    failure_reason: FailureReason | None = None
    recorded_at: datetime = datetime.now(UTC)


def build_audit_record(
    *,
    request: Any,
    result: Any,
    profile: Any,
    prompt_ref: str = "",
    redactor: Any = None,
) -> ReasoningAuditRecord:
    from agent_foundation.llm.result import ReasoningPath

    outcome_map = {
        ReasoningPath.model: "produced",
        ReasoningPath.cache: "served_from_cache",
        ReasoningPath.fallback: "fallback" if not result.failure_reason else "unable_to_produce",
    }

    grounding_digest = _compact_digest(request.grounding_inputs)
    result_summary = _compact_result(result)

    if redactor:
        grounding_digest = redactor.scrub(grounding_digest)
        result_summary = redactor.scrub(result_summary)

    return ReasoningAuditRecord(
        agent_id=request.agent_id,
        correlation_id=request.correlation_id,
        causation_id=request.causation_id,
        task_kind=request.task_kind,
        model_id=result.model_id,
        model_params={
            "temperature": getattr(profile, "temperature", 0.0),
            "max_tokens": getattr(profile, "max_tokens", 1024),
        },
        prompt_ref=prompt_ref or _hash_prompt(""),
        grounding_digest=grounding_digest,
        reasoning_path=result.reasoning_path,
        result_summary=result_summary,
        token_usage=result.token_usage,
        cache_hit=result.cache_hit,
        latency_ms=result.latency_ms,
        outcome=outcome_map.get(result.reasoning_path, "produced"),
        failure_reason=result.failure_reason,
        recorded_at=datetime.now(UTC),
    )


async def write_reasoning_audit(publisher: Any, record: ReasoningAuditRecord) -> None:
    try:
        from uuid import uuid4

        from agent_foundation.envelope import EventEnvelope
        from agent_foundation.payloads.sample import AuditPayload
        from agent_foundation.transport.topics import TOPIC_AUDIT

        audit_payload = AuditPayload(
            original_envelope=EventEnvelope(
                event_id=uuid4(),
                correlation_id=record.correlation_id,
                causation_id=record.causation_id,
                agent_id=record.agent_id,
                tenant_id="default",
                timestamp=record.recorded_at,
                event_type="agent.llm.reasoning.v1",
                schema_version="1.0.0",
                payload=record.model_dump(mode="json"),
            ),
            outcome=record.outcome,  # type: ignore[arg-type]
            reason=None,
            recorded_at=record.recorded_at,
        )

        envelope = EventEnvelope(
            event_id=uuid4(),
            correlation_id=record.correlation_id,
            causation_id=record.causation_id,
            agent_id=record.agent_id,
            tenant_id="default",
            timestamp=record.recorded_at,
            event_type="agent.audit.v1",
            schema_version="1.0.0",
            payload=audit_payload.model_dump(mode="json"),
        )
        await publisher.publish_raw(envelope, TOPIC_AUDIT)
    except Exception as exc:
        _log.warning("audit.write_failed", error=str(exc), agent_id=record.agent_id)


def _compact_digest(grounding: dict[str, Any]) -> dict[str, Any]:
    digest: dict[str, Any] = {}
    for k, v in grounding.items():
        if isinstance(v, str) and len(v) > 200:
            digest[k] = v[:200] + "..."
        else:
            digest[k] = v
    return digest


def _compact_result(result: Any) -> dict[str, Any]:
    try:
        if hasattr(result.value, "model_dump"):
            dumped: dict[str, Any] = result.value.model_dump(mode="json")
            return dumped
        return {"value": str(result.value)}
    except Exception:
        return {"value": "unable_to_serialize"}


def _hash_prompt(prompt: str) -> str:
    return hashlib.sha256(prompt.encode()).hexdigest()[:16]
