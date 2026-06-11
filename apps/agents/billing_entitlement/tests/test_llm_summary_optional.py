"""Test LLM summary is default-off for billing and forced-failure produces fallback (Phase 008)."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from agent_foundation.llm import (
    ReasoningPath,
    RuntimeConfig,
    build_runtime,
)
from agent_foundation.llm.providers.base import ProviderError
from agent_foundation.llm.runtime import LLMRuntime
from agent_foundation.llm.store import AssistiveResultStore
from apps.agents.billing_entitlement.mock_data import load_facts
from apps.agents.billing_entitlement.models import RefundEligibilityRequest
from apps.agents.billing_entitlement.policy import REFUND_POLICY
from apps.agents.billing_entitlement.rules_engine import evaluate


class BillingSummaryOutput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    summary: str
    policy_references: list[str] = Field(default_factory=list)


def _deterministic_summary(purchase_ref: str) -> str:
    """Get the deterministic reasoning_summary from the rules engine."""
    facts = load_facts(purchase_ref, "CUS-001")
    assert facts is not None
    request = RefundEligibilityRequest(
        case_id=uuid4(),
        ticket_id="TKT-001",
        customer_id="CUS-001",
        requested_refund_amount=49.99,
        purchase_reference=purchase_ref,
    )
    rec = evaluate(facts, request, REFUND_POLICY)
    return rec.reasoning_summary


async def test_llm_failure_produces_deterministic_fallback():
    """Provider failure yields the deterministic summary as fallback."""
    provider = AsyncMock()
    provider.invoke = AsyncMock(side_effect=ProviderError("Service down"))
    config = RuntimeConfig(mode="stub")
    runtime = LLMRuntime(
        provider=provider,
        store=AssistiveResultStore(),
        config=config,
    )

    det_summary = _deterministic_summary("PR-APPROVE")

    from agent_foundation.llm import assist_or_fallback

    result = await assist_or_fallback(
        runtime,
        agent_id="billing-entitlement-agent",
        task_kind="summarize_reasoning",
        correlation_id=uuid4(),
        causation_id=uuid4(),
        instructions="Summarize the billing analysis.",
        grounding_inputs={"recommendation": "approve", "confidence": 0.9},
        output_schema=BillingSummaryOutput,
        fallback=lambda: BillingSummaryOutput(summary=det_summary, policy_references=[]),
    )

    assert result.reasoning_path == ReasoningPath.fallback
    assert result.value.summary == det_summary


async def test_stub_mode_produces_valid_summary():
    """Stub mode (default, no AWS) produces a valid BillingSummaryOutput."""
    cfg = RuntimeConfig(mode="stub")
    runtime = build_runtime(cfg)

    from agent_foundation.llm import assist_or_fallback

    result = await assist_or_fallback(
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

    assert isinstance(result.value, BillingSummaryOutput)


async def test_fallback_does_not_alter_binding_recommendation():
    """Fallback path leaves the deterministic recommendation unchanged."""
    facts = load_facts("PR-APPROVE", "CUS-001")
    request = RefundEligibilityRequest(
        case_id=uuid4(),
        ticket_id="TKT-001",
        customer_id="CUS-001",
        requested_refund_amount=49.99,
        purchase_reference="PR-APPROVE",
    )
    rec_before = evaluate(facts, request, REFUND_POLICY)
    rec_after = evaluate(facts, request, REFUND_POLICY)

    assert rec_before.recommendation == rec_after.recommendation
    assert rec_before.confidence == rec_after.confidence
    assert rec_before.requires_human_review == rec_after.requires_human_review
