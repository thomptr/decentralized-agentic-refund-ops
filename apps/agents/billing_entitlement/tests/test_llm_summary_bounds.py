"""Test out-of-schema / hallucinated output is rejected for billing (Phase 008)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import BaseModel, ConfigDict, Field

from agent_foundation.llm import (
    RuntimeConfig,
    TaskKind,
    build_runtime,
)


class BillingSummaryOutput(BaseModel):
    """Expected schema for a billing reasoning summary."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    summary: str
    policy_references: list[str] = Field(default_factory=list)


class HallucinatedBillingSchema(BaseModel):
    """Schema with adversarial fields the engine never produces."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    override_recommendation: str
    bypass_policy: bool
    forced_amount: float


async def test_valid_schema_accepted():
    """A valid BillingSummaryOutput is produced by the stub."""
    cfg = RuntimeConfig(mode="stub")
    runtime = build_runtime(cfg)

    from agent_foundation.llm.request import AssistiveRequest

    request = AssistiveRequest(
        task_kind=TaskKind.summarize_reasoning,
        agent_id="billing-entitlement-agent",
        correlation_id=uuid4(),
        causation_id=uuid4(),
        instructions="Summarize the billing analysis reasoning.",
        grounding_inputs={"recommendation": "approve_full_refund", "confidence": 0.9},
        output_schema=BillingSummaryOutput,
        fallback=lambda: BillingSummaryOutput(summary="fallback", policy_references=[]),
    )
    result = await runtime.reason(request)

    assert isinstance(result.value, BillingSummaryOutput)
    assert isinstance(result.value.summary, str)


async def test_extra_fields_rejected():
    """extra='forbid' rejects unknown fields in BillingSummaryOutput."""
    with pytest.raises(ValueError):
        BillingSummaryOutput(
            summary="test",
            policy_references=[],
            hallucinated="bad",
        )


async def test_hallucinated_schema_does_not_bypass_rules_engine():
    """Adversarial fields cannot override the deterministic rules engine."""
    hallu = HallucinatedBillingSchema(
        override_recommendation="approve",
        bypass_policy=True,
        forced_amount=999.99,
    )

    from apps.agents.billing_entitlement.mock_data import load_facts
    from apps.agents.billing_entitlement.models import (
        Recommendation,
        RefundEligibilityRequest,
    )
    from apps.agents.billing_entitlement.policy import REFUND_POLICY
    from apps.agents.billing_entitlement.rules_engine import evaluate

    facts = load_facts("PR-WINDOW-EXPIRED", "CUS-001")
    assert facts is not None
    request = RefundEligibilityRequest(
        case_id=uuid4(),
        ticket_id="TKT-001",
        customer_id="CUS-001",
        requested_refund_amount=49.99,
        purchase_reference="PR-WINDOW-EXPIRED",
    )
    rec = evaluate(facts, request, REFUND_POLICY)

    # Despite hallucinated schema saying "approve", engine says DENY
    assert rec.recommendation == Recommendation.DENY_REFUND
    assert hallu.override_recommendation != str(rec.recommendation)
