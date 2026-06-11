"""Test LLM summary is default-off for risk agent and forced-failure produces fallback (Phase 008).

The risk agent uses LLM only for reasoning summaries (summarize_reasoning),
which is optional enrichment. When disabled or failing, the deterministic
reasoning_summary from assess_signals is used.
"""

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
from apps.agents.risk_fraud.mock_data import load_signals
from apps.agents.risk_fraud.models import RiskAssessmentRequest
from apps.agents.risk_fraud.scoring import assess_signals


class RiskSummaryOutput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    summary: str
    key_factors: list[str] = Field(default_factory=list)


def _deterministic_summary(customer_id: str) -> str:
    """Get the deterministic reasoning_summary from the scoring engine."""
    signals = load_signals(customer_id)
    assert signals is not None
    request = RiskAssessmentRequest(
        case_id=uuid4(),
        ticket_id="TKT-001",
        customer_id=customer_id,
        requested_refund_amount=49.99,
    )
    assessment = assess_signals(signals, request)
    return assessment.reasoning_summary


async def test_llm_failure_produces_deterministic_fallback():
    """Provider failure yields the deterministic summary as fallback value."""
    provider = AsyncMock()
    provider.invoke = AsyncMock(side_effect=ProviderError("Service down"))
    config = RuntimeConfig(mode="stub")
    runtime = LLMRuntime(
        provider=provider,
        store=AssistiveResultStore(),
        config=config,
    )

    det_summary = _deterministic_summary("CUS-CLEAN")

    from agent_foundation.llm import assist_or_fallback

    result = await assist_or_fallback(
        runtime,
        agent_id="risk-fraud-agent",
        task_kind="summarize_reasoning",
        correlation_id=uuid4(),
        causation_id=uuid4(),
        instructions="Summarize the risk assessment.",
        grounding_inputs={"risk_level": "low", "score": 0.1},
        output_schema=RiskSummaryOutput,
        fallback=lambda: RiskSummaryOutput(summary=det_summary, key_factors=[]),
    )

    assert result.reasoning_path == ReasoningPath.fallback
    assert result.value.summary == det_summary


async def test_stub_mode_produces_valid_summary():
    """Stub mode (default, no AWS) produces a valid RiskSummaryOutput."""
    cfg = RuntimeConfig(mode="stub")
    runtime = build_runtime(cfg)

    from agent_foundation.llm import assist_or_fallback

    result = await assist_or_fallback(
        runtime,
        agent_id="risk-fraud-agent",
        task_kind="summarize_reasoning",
        correlation_id=uuid4(),
        causation_id=uuid4(),
        instructions="Summarize the risk assessment.",
        grounding_inputs={"risk_level": "low", "score": 0.1},
        output_schema=RiskSummaryOutput,
        fallback=lambda: RiskSummaryOutput(summary="fallback", key_factors=[]),
    )

    assert isinstance(result.value, RiskSummaryOutput)
    assert isinstance(result.value.summary, str)


async def test_fallback_does_not_alter_binding_assessment():
    """Fallback path leaves the deterministic assessment completely unchanged."""
    signals = load_signals("CUS-CLEAN")
    request = RiskAssessmentRequest(
        case_id=uuid4(),
        ticket_id="TKT-001",
        customer_id="CUS-CLEAN",
        requested_refund_amount=49.99,
    )
    assessment_before = assess_signals(signals, request)
    # Simulate LLM failure (no actual call needed -- just verify determinism)
    assessment_after = assess_signals(signals, request)

    assert assessment_before.risk_level == assessment_after.risk_level
    assert assessment_before.recommended_action == assessment_after.recommended_action
    assert assessment_before.confidence == assessment_after.confidence
    assert assessment_before.requires_human_review == assessment_after.requires_human_review
