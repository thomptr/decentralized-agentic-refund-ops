"""Optional LLM audit events — observability-only, disabled by default."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from agent_foundation.llm.config import _parse_bool
from agent_foundation.logging import get_logger

_log = get_logger(__name__)


class LlmInvocationCompletedPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    model_id: str | None = None
    prompt_id: str
    task_kind: str
    correlation_id: UUID
    causation_id: UUID
    latency_ms: int
    token_usage: dict[str, Any] | None = None
    cache_hit: bool = False
    reasoning_path: str
    recorded_at: datetime
    raw_prompt: str | None = None


class LlmInvocationFailedPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    model_id: str | None = None
    prompt_id: str
    task_kind: str
    correlation_id: UUID
    causation_id: UUID
    latency_ms: int
    token_usage: dict[str, Any] | None = None
    cache_hit: bool = False
    reasoning_path: str
    recorded_at: datetime
    raw_prompt: str | None = None
    failure_reason: str


class LlmAuditEventConfig:
    def __init__(self) -> None:
        self.events_enabled = _parse_bool(os.environ.get("AGENT_LLM_AUDIT_EVENTS_ENABLED", "false"))
        self.log_raw_prompts = _parse_bool(
            os.environ.get("AGENT_LLM_AUDIT_LOG_RAW_PROMPTS", "false")
        )


async def emit_llm_invocation_event(
    publisher: Any,
    request: Any,
    result: Any,
    *,
    config: LlmAuditEventConfig | None = None,
    rendered_prompt: str = "",
) -> None:
    cfg = config or LlmAuditEventConfig()
    if not cfg.events_enabled:
        return

    from datetime import UTC
    from uuid import uuid4

    from agent_foundation.llm.result import ReasoningPath

    prompt_id = result.prompt_ref or ""
    raw_prompt = rendered_prompt if cfg.log_raw_prompts else None
    token_usage_dict = result.token_usage.model_dump() if result.token_usage else None
    recorded_at = datetime.now(UTC)

    is_failure = (
        result.reasoning_path in (ReasoningPath.fallback,) and result.failure_reason is not None
    )

    try:
        from agent_foundation.envelope import EventEnvelope
        from packages.contracts.topics import topic_for

        payload: LlmInvocationCompletedPayload | LlmInvocationFailedPayload
        if is_failure:
            payload = LlmInvocationFailedPayload(
                agent_id=request.agent_id,
                model_id=result.model_id,
                prompt_id=prompt_id,
                task_kind=str(request.task_kind),
                correlation_id=request.correlation_id,
                causation_id=request.causation_id,
                latency_ms=result.latency_ms,
                token_usage=token_usage_dict,
                cache_hit=result.cache_hit,
                reasoning_path=str(result.reasoning_path),
                recorded_at=recorded_at,
                raw_prompt=raw_prompt,
                failure_reason=str(result.failure_reason),
            )
            topic = topic_for("audit", "llm.invocation", "failed")
            event_type = "audit.llm.invocation.failed"
        else:
            payload = LlmInvocationCompletedPayload(
                agent_id=request.agent_id,
                model_id=result.model_id,
                prompt_id=prompt_id,
                task_kind=str(request.task_kind),
                correlation_id=request.correlation_id,
                causation_id=request.causation_id,
                latency_ms=result.latency_ms,
                token_usage=token_usage_dict,
                cache_hit=result.cache_hit,
                reasoning_path=str(result.reasoning_path),
                recorded_at=recorded_at,
                raw_prompt=raw_prompt,
            )
            topic = topic_for("audit", "llm.invocation", "completed")
            event_type = "audit.llm.invocation.completed"

        envelope = EventEnvelope(
            event_id=uuid4(),
            correlation_id=request.correlation_id,
            causation_id=request.causation_id,
            agent_id=request.agent_id,
            tenant_id="default",
            timestamp=recorded_at,
            event_type=event_type,
            schema_version="1.0.0",
            payload=payload.model_dump(mode="json"),
        )
        await publisher.publish_raw(envelope, topic)
    except Exception as exc:
        _log.warning("llm_audit_event.emit_failed", error=str(exc))
