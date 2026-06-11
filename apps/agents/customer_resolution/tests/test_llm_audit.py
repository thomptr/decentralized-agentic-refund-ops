"""Test each LLM call emits a ReasoningAuditRecord (Phase 008)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from agent_foundation.llm import (
    ReasoningAuditRecord,
    ReasoningPath,
    RuntimeConfig,
    TaskKind,
    build_runtime,
)
from agent_foundation.llm.audit import build_audit_record
from agent_foundation.llm.runtime import LLMRuntime
from agent_foundation.llm.store import AssistiveResultStore
from apps.agents.customer_resolution.response_drafter import (
    AllowedFacts,
    ToneConfig,
    draft_with_llm,
)
from apps.agents.customer_resolution.ticket_classifier import (
    classify_with_llm,
)
from packages.contracts.events.payloads import (
    ResolutionOutcome,
    SupportTicketCreatedPayload,
)


def _make_ticket() -> SupportTicketCreatedPayload:
    return SupportTicketCreatedPayload(
        ticket_id="TKT-AUDIT-001",
        customer_id="CUS-001",
        amount=49.99,
        currency="USD",
        reason="I want a refund",
        created_at=datetime.now(UTC),
    )


async def test_classify_with_llm_emits_audit_record():
    """classify_with_llm should trigger audit record emission through the runtime."""
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

    with patch.object(LLMRuntime, "_emit_audit", capture_audit):
        ticket = _make_ticket()
        await classify_with_llm(ticket, runtime)

    assert len(audit_records) >= 1
    record = audit_records[0]
    assert isinstance(record, ReasoningAuditRecord)
    assert record.agent_id == "customer-resolution-agent"
    assert record.task_kind == TaskKind.classify
    assert record.reasoning_path in (ReasoningPath.model, ReasoningPath.fallback)


async def test_draft_with_llm_emits_audit_record():
    """draft_with_llm should trigger audit record emission through the runtime."""
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

    with patch.object(LLMRuntime, "_emit_audit", capture_audit):
        facts = AllowedFacts(
            refund_amount=49.99,
            currency="USD",
            order_reference="TKT-001",
        )
        await draft_with_llm(
            ResolutionOutcome.APPROVE_REFUND,
            facts,
            ToneConfig(),
            runtime,
            ticket_summary="Customer wants refund",
        )

    assert len(audit_records) >= 1
    record = audit_records[0]
    assert isinstance(record, ReasoningAuditRecord)
    assert record.agent_id == "customer-resolution-agent"
    assert record.task_kind == TaskKind.draft_response


async def test_audit_record_contains_correlation_id():
    """Audit records carry the correlation_id from the request."""
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
    cid = uuid4()

    with patch.object(LLMRuntime, "_emit_audit", capture_audit):
        ticket = _make_ticket()
        await classify_with_llm(ticket, runtime, correlation_id=cid)

    assert len(audit_records) >= 1
    assert audit_records[0].correlation_id == cid


async def test_audit_record_on_fallback():
    """Even fallback paths emit an audit record."""
    from agent_foundation.llm.providers.base import ProviderError

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

    with patch.object(LLMRuntime, "_emit_audit", capture_audit):
        ticket = _make_ticket()
        await classify_with_llm(ticket, runtime)

    assert len(audit_records) >= 1
    assert audit_records[0].reasoning_path == ReasoningPath.fallback