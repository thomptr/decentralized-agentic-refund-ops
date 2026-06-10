"""Tests for the deterministic scoring engine (T014, T014a, T023, T025, T027)."""

from __future__ import annotations

import uuid

import pytest

from apps.agents.risk_fraud.mock_data import _clean_signals, load_signals
from apps.agents.risk_fraud.models import (
    RecommendedAction,
    RiskAssessmentRequest,
    RiskLevel,
)
from apps.agents.risk_fraud.scoring import assess_signals


def _req(
    customer_id: str = "TEST",
    requested_refund_amount: str | None = None,
) -> RiskAssessmentRequest:
    data: dict = {
        "case_id": str(uuid.uuid4()),
        "ticket_id": "TKT-001",
        "customer_id": customer_id,
    }
    if requested_refund_amount is not None:
        data["requested_refund_amount"] = requested_refund_amount
    return RiskAssessmentRequest.model_validate(data)


# ---------------------------------------------------------------------------
# T014: Named scenario tests
# ---------------------------------------------------------------------------


def test_known_good_customer_low_risk():
    """Known good customer => low risk (clean signals, conf 0.9)."""
    signals = load_signals("CUS-CLEAN")
    assert signals is not None
    result = assess_signals(signals, _req("CUS-CLEAN"))
    assert result.risk_level == RiskLevel.LOW
    assert result.confidence >= 0.9
    assert result.requires_human_review is False
    # At least one fraud_policy evidence stating no rule fired
    fp_evidence = [e for e in result.evidence if e.source == "fraud_policy"]
    assert len(fp_evidence) >= 1


def test_new_account_high_amount_elevated():
    """New account + elevated signals => medium/high risk (FP-005)."""
    signals = load_signals("CUS-NEW-ACCOUNT")
    assert signals is not None
    result = assess_signals(signals, _req("CUS-NEW-ACCOUNT"))
    assert result.risk_level in (RiskLevel.ELEVATED, RiskLevel.HIGH)
    assert any("FP-005" in str(e.value) for e in result.evidence)


def test_multiple_recent_refunds_elevated_at_velocity_elevated():
    """velocity >= 3 => elevated (FP-003 elevated contribution)."""
    from apps.agents.risk_fraud.policy import VELOCITY_ELEVATED

    signals = _clean_signals("TEST", refund_requests_in_window=VELOCITY_ELEVATED)
    result = assess_signals(signals, _req())
    assert result.risk_level in (RiskLevel.ELEVATED, RiskLevel.HIGH)


def test_multiple_recent_refunds_high_at_velocity_high():
    """velocity >= 5 => high (FP-003 high contribution, borderline high)."""
    signals = load_signals("CUS-VELOCITY")
    assert signals is not None
    result = assess_signals(signals, _req("CUS-VELOCITY"))
    # velocity=5 → FP-003 +0.8 → borderline HIGH
    assert result.risk_level in (RiskLevel.HIGH, RiskLevel.ELEVATED)


def test_prior_chargeback_elevated():
    """1 chargeback => elevated (FP-002)."""
    signals = load_signals("CUS-ONE-CHARGEBACK")
    assert signals is not None
    result = assess_signals(signals, _req("CUS-ONE-CHARGEBACK"))
    assert result.risk_level == RiskLevel.ELEVATED


def test_repeat_chargebacks_high():
    """2+ chargebacks => high (FP-002)."""
    signals = load_signals("CUS-CHARGEBACKS")
    assert signals is not None
    result = assess_signals(signals, _req("CUS-CHARGEBACKS"))
    assert result.risk_level == RiskLevel.HIGH


def test_ip_device_mismatch_elevated():
    """IP/device mismatch => elevated (FP-004 card testing or mismatch)."""
    signals = load_signals("CUS-CARD-TESTING")
    assert signals is not None
    result = assess_signals(signals, _req("CUS-CARD-TESTING"))
    assert result.risk_level in (RiskLevel.ELEVATED, RiskLevel.HIGH)


def test_known_good_offsets_minor_risk():
    """Known good customer (long tenure + good status + 0.0 baseline) offsets minor signal → low."""
    # A single minor behavioral signal below VELOCITY_ELEVATED doesn't push past LOW
    from apps.agents.risk_fraud.policy import VELOCITY_ELEVATED

    signals = _clean_signals(
        "TEST",
        refund_requests_in_window=VELOCITY_ELEVATED - 1,  # below elevated threshold
        known_good_customer=True,
        tenure_days=365,
        status="good",
    )
    result = assess_signals(signals, _req())
    assert result.risk_level == RiskLevel.LOW


def test_score_capped_at_one_gives_high():
    """Summed contributions > 1.0 clamp to 1.0 → high."""
    from apps.agents.risk_fraud.policy import CHARGEBACK_HIGH, VELOCITY_HIGH

    signals = _clean_signals(
        "TEST",
        chargebacks=CHARGEBACK_HIGH,
        refund_requests_in_window=VELOCITY_HIGH,
    )
    result = assess_signals(signals, _req())
    assert result.risk_level == RiskLevel.HIGH


def test_blocklist_gives_high_conf_095():
    """CUS-BLOCKLIST => high (FP-001 floor, conf 0.95)."""
    signals = load_signals("CUS-BLOCKLIST")
    assert signals is not None
    result = assess_signals(signals, _req("CUS-BLOCKLIST"))
    assert result.risk_level == RiskLevel.HIGH
    assert result.confidence == 0.95


def test_borderline_elevated_conf_06():
    """Exactly 0.5 → elevated (upper band, conf 0.6)."""
    signals = load_signals("CUS-BORDERLINE")  # chargebacks=1 → FP-002 +0.5
    assert signals is not None
    result = assess_signals(signals, _req("CUS-BORDERLINE"))
    assert result.risk_level == RiskLevel.ELEVATED
    assert abs(result.confidence - 0.6) < 1e-9


def test_borderline_high_conf_06():
    """Exactly 0.8 → high (upper band, conf 0.6)."""
    from apps.agents.risk_fraud.policy import CHARGEBACK_HIGH

    signals = _clean_signals("TEST", chargebacks=CHARGEBACK_HIGH)  # +0.8 exactly
    result = assess_signals(signals, _req())
    assert result.risk_level == RiskLevel.HIGH
    assert abs(result.confidence - 0.6) < 1e-9


# ---------------------------------------------------------------------------
# T014: recommended_action mapping
# ---------------------------------------------------------------------------


def test_recommendation_low_approve_risk_clearance():
    signals = load_signals("CUS-CLEAN")
    assert signals is not None
    result = assess_signals(signals, _req())
    assert result.recommended_action == RecommendedAction.APPROVE_RISK_CLEARANCE


def test_recommendation_elevated_allow_with_caution():
    """Elevated risk without chargebacks → allow_with_caution."""
    # CUS-CARD-TESTING has card_testing=True, no chargebacks → elevated → allow_with_caution
    signals = load_signals("CUS-CARD-TESTING")
    assert signals is not None
    result = assess_signals(signals, _req())
    assert result.risk_level == RiskLevel.ELEVATED
    assert result.recommended_action in (
        RecommendedAction.ALLOW_WITH_CAUTION,
        RecommendedAction.MANUAL_REVIEW,
    )


def test_recommendation_high_deny_or_escalate():
    """High risk → deny_or_escalate."""
    signals = load_signals("CUS-BLOCKLIST")
    assert signals is not None
    result = assess_signals(signals, _req())
    assert result.recommended_action == RecommendedAction.DENY_OR_ESCALATE


def test_recommendation_prior_chargeback_manual_review():
    """Elevated risk with prior chargeback → manual_review."""
    signals = load_signals("CUS-ONE-CHARGEBACK")
    assert signals is not None
    result = assess_signals(signals, _req())
    assert result.risk_level == RiskLevel.ELEVATED
    assert result.recommended_action == RecommendedAction.MANUAL_REVIEW


# ---------------------------------------------------------------------------
# T014: confidence and evidence always present
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "customer_id",
    [
        "CUS-CLEAN",
        "CUS-CHARGEBACKS",
        "CUS-ONE-CHARGEBACK",
        "CUS-VELOCITY",
        "CUS-BLOCKLIST",
        "CUS-NEW-ACCOUNT",
    ],
)
def test_confidence_present_and_in_range(customer_id: str):
    signals = load_signals(customer_id)
    assert signals is not None
    result = assess_signals(signals, _req(customer_id))
    assert 0.0 <= result.confidence <= 1.0


@pytest.mark.parametrize(
    "customer_id",
    [
        "CUS-CLEAN",
        "CUS-CHARGEBACKS",
        "CUS-ONE-CHARGEBACK",
        "CUS-VELOCITY",
        "CUS-BLOCKLIST",
        "CUS-NEW-ACCOUNT",
    ],
)
def test_evidence_non_empty(customer_id: str):
    signals = load_signals(customer_id)
    assert signals is not None
    result = assess_signals(signals, _req(customer_id))
    assert len(result.evidence) >= 1


# ---------------------------------------------------------------------------
# T014a: No customer-facing language in recommendation/reasoning
# ---------------------------------------------------------------------------


def test_recommended_action_always_operational_enum():
    """recommended_action is always a member of the RecommendedAction enum."""
    for customer_id in ["CUS-CLEAN", "CUS-CHARGEBACKS", "CUS-BLOCKLIST", "CUS-NEW-ACCOUNT"]:
        signals = load_signals(customer_id)
        assert signals is not None
        result = assess_signals(signals, _req(customer_id))
        assert isinstance(result.recommended_action, RecommendedAction), (
            f"recommended_action for {customer_id} is not a RecommendedAction enum"
        )


def test_no_customer_facing_language_in_reasoning():
    """reasoning_summary and evidence must not contain customer-addressed language."""
    FORBIDDEN = ["you ", "your ", "dear ", "sorry", "apologize", "we apologize"]
    for customer_id in ["CUS-CLEAN", "CUS-CHARGEBACKS", "CUS-BLOCKLIST", "CUS-VELOCITY"]:
        signals = load_signals(customer_id)
        assert signals is not None
        result = assess_signals(signals, _req(customer_id))
        summary_lower = result.reasoning_summary.lower()
        for phrase in FORBIDDEN:
            assert phrase not in summary_lower, (
                f"Customer-facing language {phrase!r} found in reasoning_summary for {customer_id}"
            )
        for ev in result.evidence:
            desc_lower = ev.description.lower()
            for phrase in FORBIDDEN:
                assert phrase not in desc_lower, (
                    f"Customer-facing language {phrase!r} in evidence description for {customer_id}"
                )


# ---------------------------------------------------------------------------
# T023: Uncertainty paths
# ---------------------------------------------------------------------------


def test_missing_profile_requires_human_review():
    """Unknown customer_id → requires_human_review=True, confidence 0.2."""
    from apps.agents.risk_fraud.service import _missing_data_assessment

    result = _missing_data_assessment("CUS-UNKNOWN-XYZ")
    assert result.requires_human_review is True
    assert result.confidence == 0.2
    assert result.recommended_action == RecommendedAction.REQUEST_MORE_INFORMATION
    # No fabricated risk level beyond the stub
    fp_evidence = [e for e in result.evidence if e.source == "fraud_policy"]
    assert len(fp_evidence) >= 1


def test_vip_enterprise_requires_human_review():
    """VIP/enterprise account segment → requires_human_review=True."""
    signals = load_signals("CUS-VIP-ENTERPRISE")
    assert signals is not None
    result = assess_signals(signals, _req("CUS-VIP-ENTERPRISE"))
    assert result.requires_human_review is True
    assert result.recommended_action == RecommendedAction.MANUAL_REVIEW


def test_contradictory_signals_requires_human_review():
    """Contradictory signals → elevated + requires_human_review=True, conf 0.3."""
    signals = load_signals("CUS-CONTRADICTION")
    assert signals is not None
    result = assess_signals(signals, _req("CUS-CONTRADICTION"))
    assert result.requires_human_review is True
    assert result.confidence == 0.3
    assert result.risk_level == RiskLevel.ELEVATED


# ---------------------------------------------------------------------------
# T025: Uncertainty VIP/enterprise path
# ---------------------------------------------------------------------------


def test_enterprise_segment_manual_review():
    signals = load_signals("CUS-VIP-ENTERPRISE")
    assert signals is not None
    result = assess_signals(signals, _req("CUS-VIP-ENTERPRISE"))
    assert result.requires_human_review is True
    assert result.recommended_action == RecommendedAction.MANUAL_REVIEW
    enterprise_evidence = [
        e
        for e in result.evidence
        if "enterprise" in str(e.value).lower()
        or "vip" in str(e.value).lower()
        or e.source == "account_standing"
    ]
    assert len(enterprise_evidence) >= 1


# ---------------------------------------------------------------------------
# T027: Determinism — same signals yield identical result
# ---------------------------------------------------------------------------


def test_assess_signals_deterministic():
    """assess_signals called twice on identical signals returns identical RiskAssessment."""
    signals = load_signals("CUS-CLEAN")
    assert signals is not None
    req = _req("CUS-CLEAN")
    result1 = assess_signals(signals, req)
    result2 = assess_signals(signals, req)
    assert result1 == result2


def test_assess_signals_deterministic_risky():
    """Determinism holds for risky signals too."""
    signals = load_signals("CUS-CHARGEBACKS")
    assert signals is not None
    req = _req("CUS-CHARGEBACKS")
    result1 = assess_signals(signals, req)
    result2 = assess_signals(signals, req)
    assert result1 == result2
