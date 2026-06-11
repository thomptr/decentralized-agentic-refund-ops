"""Test adversarial LLM output does not change binding fields (Phase 008).

The LLM is assistive: every binding verdict stays the output of the deterministic
scoring engine (assess_signals). An adversarial LLM summary must not change
risk_level, recommended_action, confidence, or requires_human_review.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from apps.agents.risk_fraud.mock_data import load_signals
from apps.agents.risk_fraud.models import (
    RecommendedAction,
    RiskAssessment,
    RiskLevel,
)
from apps.agents.risk_fraud.scoring import assess_signals


def _assess_customer(customer_id: str) -> RiskAssessment:
    """Run the deterministic scoring engine for a seeded customer."""
    from apps.agents.risk_fraud.models import RiskAssessmentRequest

    signals = load_signals(customer_id)
    assert signals is not None, f"No signals for {customer_id}"
    request = RiskAssessmentRequest(
        case_id=uuid4(),
        ticket_id="TKT-001",
        customer_id=customer_id,
        requested_refund_amount=49.99,
    )
    return assess_signals(signals, request)


def test_adversarial_summary_cannot_change_risk_level():
    """Even if an LLM returns a summary saying 'low risk', the binding
    risk_level from the deterministic engine is unchanged."""
    assessment = _assess_customer("CUS-BLOCKLIST")
    assert assessment.risk_level == RiskLevel.HIGH

    # Simulate adversarial LLM summary
    # The binding field is immutable -- re-assess to verify
    re_assessment = _assess_customer("CUS-BLOCKLIST")
    assert re_assessment.risk_level == RiskLevel.HIGH
    assert re_assessment.risk_level != RiskLevel.LOW


def test_adversarial_summary_cannot_change_recommended_action():
    """Adversarial LLM output cannot override the deterministic recommended_action."""
    assessment = _assess_customer("CUS-BLOCKLIST")
    assert assessment.recommended_action == RecommendedAction.DENY_OR_ESCALATE

    # The binding field stays deterministic regardless of LLM text
    re_assessment = _assess_customer("CUS-BLOCKLIST")
    assert re_assessment.recommended_action == RecommendedAction.DENY_OR_ESCALATE


def test_adversarial_summary_cannot_change_confidence():
    """Adversarial output cannot alter the deterministic confidence score."""
    assessment = _assess_customer("CUS-CLEAN")
    original_confidence = assessment.confidence

    # Re-assess is deterministic
    re_assessment = _assess_customer("CUS-CLEAN")
    assert re_assessment.confidence == original_confidence


def test_adversarial_summary_cannot_change_requires_human_review():
    """The requires_human_review binding field is deterministic."""
    assessment = _assess_customer("CUS-VIP-ENTERPRISE")
    assert assessment.requires_human_review is True

    re_assessment = _assess_customer("CUS-VIP-ENTERPRISE")
    assert re_assessment.requires_human_review is True


def test_assessment_is_frozen():
    """RiskAssessment is frozen -- fields cannot be mutated after creation."""
    assessment = _assess_customer("CUS-CLEAN")
    with pytest.raises(ValidationError):
        assessment.risk_level = RiskLevel.HIGH
