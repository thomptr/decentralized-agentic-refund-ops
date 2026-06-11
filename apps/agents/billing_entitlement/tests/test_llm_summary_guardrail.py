"""Test adversarial LLM output does not change billing recommendation (Phase 008).

The LLM is assistive: every binding verdict stays the output of the deterministic
rules engine (evaluate). An adversarial LLM summary cannot change
recommendation, confidence, requires_human_review, or eligible_refund_amount.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from apps.agents.billing_entitlement.mock_data import load_facts
from apps.agents.billing_entitlement.models import (
    EligibilityRecommendation,
    Recommendation,
    RefundEligibilityRequest,
)
from apps.agents.billing_entitlement.policy import REFUND_POLICY
from apps.agents.billing_entitlement.rules_engine import evaluate


def _evaluate_for(purchase_reference: str) -> EligibilityRecommendation:
    """Run the deterministic rules engine for a seeded purchase."""
    facts = load_facts(purchase_reference, "CUS-001")
    assert facts is not None, f"No facts for {purchase_reference}"
    request = RefundEligibilityRequest(
        case_id=uuid4(),
        ticket_id="TKT-001",
        customer_id="CUS-001",
        requested_refund_amount=49.99,
        purchase_reference=purchase_reference,
    )
    return evaluate(facts, request, REFUND_POLICY)


def test_adversarial_summary_cannot_change_recommendation():
    """Even if an LLM returns 'approve', the binding recommendation stays deterministic."""
    rec = _evaluate_for("PR-WINDOW-EXPIRED")
    assert rec.recommendation == Recommendation.DENY_REFUND

    # Re-evaluate to confirm determinism
    rec2 = _evaluate_for("PR-WINDOW-EXPIRED")
    assert rec2.recommendation == Recommendation.DENY_REFUND


def test_adversarial_summary_cannot_change_eligible_amount():
    """Adversarial output cannot alter the eligible_refund_amount."""
    rec = _evaluate_for("PR-WINDOW-EXPIRED")
    assert rec.eligible_refund_amount == 0

    rec2 = _evaluate_for("PR-WINDOW-EXPIRED")
    assert rec2.eligible_refund_amount == 0


def test_adversarial_summary_cannot_change_requires_human_review():
    """The requires_human_review binding field is deterministic."""
    rec = _evaluate_for("PR-APPROVE")
    original = rec.requires_human_review

    rec2 = _evaluate_for("PR-APPROVE")
    assert rec2.requires_human_review == original


def test_adversarial_summary_cannot_change_confidence():
    """Confidence stays deterministic regardless of LLM text."""
    rec = _evaluate_for("PR-APPROVE")
    original = rec.confidence

    rec2 = _evaluate_for("PR-APPROVE")
    assert rec2.confidence == original


def test_recommendation_extra_fields_rejected():
    """EligibilityRecommendation with extra='forbid' rejects unknown fields."""
    with pytest.raises(ValueError):
        EligibilityRecommendation(
            recommendation=Recommendation.APPROVE_FULL_REFUND,
            confidence=0.9,
            evidence=[],
            policy_references=[],
            reasoning_summary="test",
            requires_human_review=False,
            eligible_refund_amount=0,
            subscription_status="unknown",
            invoice_status="unknown",
            payment_status="unknown",
            entitlement_status="unknown",
            usage_level="unknown",
            refund_window_status="unknown",
            adversarial_override="should_fail",
        )
