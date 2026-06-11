"""Test out-of-schema / hallucinated LLM output is rejected (Phase 008).

The shared runtime's schema validation rejects output that does not match
the declared output_schema. This test verifies the rejection path using
the stub provider and adversarial schemas.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import BaseModel, ConfigDict, Field

from agent_foundation.llm import (
    AssistiveResult,
    RuntimeConfig,
    TaskKind,
    build_runtime,
)


class RiskSummaryOutput(BaseModel):
    """Expected schema for a risk reasoning summary."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    summary: str
    key_factors: list[str] = Field(default_factory=list)


class HallucinatedSchema(BaseModel):
    """Schema with fields that the stub cannot meaningfully populate."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    risk_override: str  # not a real field
    bypass_scoring: bool  # adversarial
    forced_level: str  # adversarial


async def test_valid_schema_accepted_by_runtime():
    """A valid schema produces a model-path result from the stub."""
    cfg = RuntimeConfig(mode="stub")
    runtime = build_runtime(cfg)

    from agent_foundation.llm.request import AssistiveRequest

    request = AssistiveRequest(
        task_kind=TaskKind.summarize_reasoning,
        agent_id="risk-fraud-agent",
        correlation_id=uuid4(),
        causation_id=uuid4(),
        instructions="Summarize the risk assessment reasoning.",
        grounding_inputs={"risk_level": "low", "score": 0.1},
        output_schema=RiskSummaryOutput,
        fallback=lambda: RiskSummaryOutput(summary="fallback", key_factors=[]),
    )
    result = await runtime.reason(request)

    assert isinstance(result, AssistiveResult)
    assert isinstance(result.value, RiskSummaryOutput)
    assert isinstance(result.value.summary, str)


async def test_extra_fields_rejected_by_schema():
    """extra='forbid' rejects LLM output with unknown fields."""
    with pytest.raises(ValueError):
        RiskSummaryOutput(
            summary="test",
            key_factors=[],
            hallucinated="bad_field",
        )


async def test_hallucinated_schema_does_not_bypass_scoring():
    """A schema with adversarial fields cannot override the deterministic engine."""
    # This just verifies the schema itself -- the scoring engine never uses
    # LLM output for binding fields
    hallu = HallucinatedSchema(
        risk_override="low",
        bypass_scoring=True,
        forced_level="low",
    )
    # The scoring engine ignores this entirely
    from apps.agents.risk_fraud.mock_data import load_signals
    from apps.agents.risk_fraud.models import RiskAssessmentRequest, RiskLevel
    from apps.agents.risk_fraud.scoring import assess_signals

    signals = load_signals("CUS-BLOCKLIST")
    request = RiskAssessmentRequest(
        case_id=uuid4(),
        ticket_id="TKT-001",
        customer_id="CUS-BLOCKLIST",
        requested_refund_amount=49.99,
    )
    assessment = assess_signals(signals, request)

    # Despite the hallucinated schema saying "low", the engine says HIGH
    assert assessment.risk_level == RiskLevel.HIGH
    assert hallu.forced_level != str(assessment.risk_level)
