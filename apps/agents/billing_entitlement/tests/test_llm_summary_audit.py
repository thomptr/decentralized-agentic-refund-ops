"""Test enrichment emits ReasoningAuditRecord for billing agent (Phase 008)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from agent_foundation.llm import (
    ReasoningAuditRecord,
    ReasoningPath,
    RuntimeConfig,
    TaskKind,
    build_runtime,
)
from agent_foundation.llm.audit import build_audit_record
from agent_foundation.llm.runtime import LLMRuntime


class BillingSummaryOutput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    summary: str
    policy_references: list[str] = Field(default_factory=list)


async def test_summarize_reasoning_emits_audit_record():
    """A summarize_reasoning call emits a ReasoningAuditRecord."""
    audit_records = []
    original_emit = LLMRuntime._emit_audit

    async def capture_audit(self, request, result, profile, **kwargs):
        record = build_audit_record(
            request=request,
            result=result,
            profile=profile,
            prompt_ref=kwargs.get("prompt_ref", ""),
        )
        audit_records.append(record)
        await original_emit(self, request, result, profile, **kwargs)

    cfg = RuntimeConfig(mode="stub")
    runtime = build_runtime(cfg)

    from agent_foundation.llm import assist_or_fallback

    with patch.object(LLMRuntime, "_emit_audit", capture_audit):
        await assist_or_fallback(
            runtime,
            agent_id="billing-entitlement-agent",
            task_kind="summarize_reasoning",
            correlation_id=uuid4(),
            causation_id=uuid4(),
            instructions="Summarize the billing analysis.",
            grounding_inputs={"recommendation": "approve", "confidence": 0.9},
            output_schema=BillingSummaryOutput,
            fallback=lambda: BillingSummaryOutput(summary="fallback", policy_references=[]),
        )

    assert len(audit_records) >= 1
    record = audit_records[0]
    assert isinstance(record, ReasoningAuditRecord)
    assert record.agent_id == "billing-entitlement-agent"
    assert record.task_kind == TaskKind.summarize_reasoning


async def test_audit_record_contains_reasoning_path():
    """Audit record reflects the reasoning path used."""
    audit_records = []
    original_emit = LLMRuntime._emit_audit

    async def capture_audit(self, request, result, profile, **kwargs):
        record = build_audit_record(
            request=request,
            result=result,
            profile=profile,
        )
        audit_records.append(record)
        await original_emit(self, request, result, profile, **kwargs)

    cfg = RuntimeConfig(mode="stub")
    runtime = build_runtime(cfg)

    from agent_foundation.llm import assist_or_fallback

    with patch.object(LLMRuntime, "_emit_audit", capture_audit):
        await assist_or_fallback(
            runtime,
            agent_id="billing-entitlement-agent",
            task_kind="summarize_reasoning",
            correlation_id=uuid4(),
            causation_id=uuid4(),
            instructions="Summarize.",
            grounding_inputs={"recommendation": "deny"},
            output_schema=BillingSummaryOutput,
            fallback=lambda: BillingSummaryOutput(summary="fb", policy_references=[]),
        )

    assert len(audit_records) >= 1
    assert audit_records[0].reasoning_path in (
        ReasoningPath.model,
        ReasoningPath.fallback,
        ReasoningPath.cache,
    )


async def test_audit_record_on_fallback_path():
    """Fallback path also emits an audit record with failure_reason."""
    from agent_foundation.llm.providers.base import ProviderError
    from agent_foundation.llm.store import AssistiveResultStore

    audit_records = []
    original_emit = LLMRuntime._emit_audit

    async def capture_audit(self, request, result, profile, **kwargs):
        record = build_audit_record(
            request=request,
            result=result,
            profile=profile,
        )
        audit_records.append(record)
        await original_emit(self, request, result, profile, **kwargs)

    provider = AsyncMock()
    provider.invoke = AsyncMock(side_effect=ProviderError("Boom"))
    config = RuntimeConfig(mode="stub")
    runtime = LLMRuntime(
        provider=provider,
        store=AssistiveResultStore(),
        config=config,
    )

    from agent_foundation.llm import assist_or_fallback

    with patch.object(LLMRuntime, "_emit_audit", capture_audit):
        await assist_or_fallback(
            runtime,
            agent_id="billing-entitlement-agent",
            task_kind="summarize_reasoning",
            correlation_id=uuid4(),
            causation_id=uuid4(),
            instructions="Summarize.",
            grounding_inputs={"recommendation": "deny"},
            output_schema=BillingSummaryOutput,
            fallback=lambda: BillingSummaryOutput(summary="det-fallback", policy_references=[]),
        )

    assert len(audit_records) >= 1
    assert audit_records[0].reasoning_path == ReasoningPath.fallback
    assert audit_records[0].failure_reason is not None
