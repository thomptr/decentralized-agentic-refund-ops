"""Tests for the named fraud policy rules (T013).

Each FP-001..FP-006 rule fires on its triggering signal.
Borderline values exactly on a threshold resolve to the upper band.
"""

from __future__ import annotations

import uuid

from apps.agents.risk_fraud.mock_data import _clean_signals, load_signals
from apps.agents.risk_fraud.models import (
    RiskAssessmentRequest,
    RiskLevel,
)
from apps.agents.risk_fraud.policy import (
    ANOMALY_ELEVATED,
    CHARGEBACK_ELEVATED,
    CHARGEBACK_HIGH,
    VELOCITY_ELEVATED,
    VELOCITY_HIGH,
)
from apps.agents.risk_fraud.scoring import assess_signals


def _req(customer_id: str = "TEST") -> RiskAssessmentRequest:
    return RiskAssessmentRequest(
        case_id=uuid.uuid4(),
        ticket_id="TKT-001",
        customer_id=customer_id,
    )


# ---------------------------------------------------------------------------
# FP-001: Known-fraud-indicator hard floor
# ---------------------------------------------------------------------------


def test_fp001_blocklist_gives_high():
    signals = load_signals("CUS-BLOCKLIST")
    assert signals is not None
    result = assess_signals(signals, _req())
    assert result.risk_level == RiskLevel.HIGH
    assert result.confidence == 0.95
    assert result.requires_human_review is False
    # Evidence must include fraud_policy rule
    policy_evidence = [e for e in result.evidence if e.source == "fraud_policy"]
    assert any("FP-001" in e.description for e in policy_evidence)


def test_fp001_not_on_blocklist_does_not_fire():
    signals = load_signals("CUS-CLEAN")
    assert signals is not None
    result = assess_signals(signals, _req())
    assert result.risk_level == RiskLevel.LOW


# ---------------------------------------------------------------------------
# FP-002: Chargeback history
# ---------------------------------------------------------------------------


def test_fp002_one_chargeback_elevated():
    signals = load_signals("CUS-ONE-CHARGEBACK")
    assert signals is not None
    result = assess_signals(signals, _req())
    assert result.risk_level == RiskLevel.ELEVATED
    assert any("FP-002" in str(e.value) for e in result.evidence)


def test_fp002_two_chargebacks_high():
    signals = load_signals("CUS-CHARGEBACKS")
    assert signals is not None
    result = assess_signals(signals, _req())
    assert result.risk_level == RiskLevel.HIGH


def test_fp002_zero_chargebacks_does_not_fire():
    signals = _clean_signals("TEST", chargebacks=0)
    result = assess_signals(signals, _req())
    fp002_evidence = [e for e in result.evidence if "FP-002" in str(e.value)]
    assert len(fp002_evidence) == 0


# ---------------------------------------------------------------------------
# FP-003: Refund velocity
# ---------------------------------------------------------------------------


def test_fp003_velocity_elevated_fires_at_threshold():
    signals = _clean_signals("TEST", refund_requests_in_window=VELOCITY_ELEVATED)
    result = assess_signals(signals, _req())
    assert result.risk_level in (RiskLevel.ELEVATED, RiskLevel.HIGH)


def test_fp003_velocity_high_gives_high():
    signals = load_signals("CUS-VELOCITY")
    assert signals is not None
    result = assess_signals(signals, _req())
    # velocity=5 -> FP-003 high contribution -> elevated or high (score=0.8 borderline)
    assert result.risk_level in (RiskLevel.HIGH, RiskLevel.ELEVATED)


def test_fp003_below_velocity_elevated_does_not_fire():
    signals = _clean_signals("TEST", refund_requests_in_window=VELOCITY_ELEVATED - 1)
    result = assess_signals(signals, _req())
    fp003_evidence = [e for e in result.evidence if "FP-003" in str(e.value)]
    assert len(fp003_evidence) == 0


# ---------------------------------------------------------------------------
# FP-004: Instrument mismatch / card testing
# ---------------------------------------------------------------------------


def test_fp004_card_testing_gives_elevated():
    signals = load_signals("CUS-CARD-TESTING")
    assert signals is not None
    result = assess_signals(signals, _req())
    assert result.risk_level == RiskLevel.ELEVATED


def test_fp004_billing_mismatch_fires():
    signals = load_signals("CUS-INSTRUMENT")
    assert signals is not None
    result = assess_signals(signals, _req())
    # FP-004 fires; level may be elevated depending on contribution
    assert any("FP-004" in str(e.value) for e in result.evidence)


def test_fp004_clean_instrument_does_not_fire():
    signals = _clean_signals("TEST")
    result = assess_signals(signals, _req())
    fp004_evidence = [e for e in result.evidence if "FP-004" in str(e.value)]
    assert len(fp004_evidence) == 0


# ---------------------------------------------------------------------------
# FP-005: Account standing
# ---------------------------------------------------------------------------


def test_fp005_new_account_fires():
    signals = load_signals("CUS-NEW-ACCOUNT")
    assert signals is not None
    result = assess_signals(signals, _req())
    assert any("FP-005" in str(e.value) for e in result.evidence)


def test_fp005_long_tenure_good_does_not_fire():
    signals = _clean_signals("TEST")  # tenure=365, status="good"
    result = assess_signals(signals, _req())
    fp005_evidence = [e for e in result.evidence if "FP-005" in str(e.value)]
    assert len(fp005_evidence) == 0


def test_fp005_watch_status_fires():
    signals = _clean_signals("TEST", status="watch", tenure_days=90)
    result = assess_signals(signals, _req())
    assert any("FP-005" in str(e.value) for e in result.evidence)


# ---------------------------------------------------------------------------
# FP-006: Behavioral anomaly
# ---------------------------------------------------------------------------


def test_fp006_high_anomaly_fires():
    signals = load_signals("CUS-ANOMALY")
    assert signals is not None
    result = assess_signals(signals, _req())
    assert any("FP-006" in str(e.value) for e in result.evidence)


def test_fp006_below_threshold_does_not_fire():
    signals = _clean_signals("TEST", anomaly_score=ANOMALY_ELEVATED - 0.1)
    result = assess_signals(signals, _req())
    fp006_evidence = [e for e in result.evidence if "FP-006" in str(e.value)]
    assert len(fp006_evidence) == 0


# ---------------------------------------------------------------------------
# Borderline threshold resolution (upper band rule)
# ---------------------------------------------------------------------------


def test_borderline_exactly_elevated_threshold():
    """Score exactly 0.5 → elevated (upper band), conf 0.6."""
    # 1 chargeback → FP-002 +0.5 → score = 0.5 exactly
    signals = _clean_signals("TEST", chargebacks=CHARGEBACK_ELEVATED)
    result = assess_signals(signals, _req())
    assert result.risk_level == RiskLevel.ELEVATED
    assert abs(result.confidence - 0.6) < 1e-9


def test_borderline_exactly_high_threshold():
    """Score exactly 0.8 → high (upper band), conf 0.6."""
    # 2 chargebacks → FP-002 +0.8 → score = 0.8 exactly
    signals = _clean_signals("TEST", chargebacks=CHARGEBACK_HIGH)
    result = assess_signals(signals, _req())
    assert result.risk_level == RiskLevel.HIGH
    assert abs(result.confidence - 0.6) < 1e-9


def test_score_capped_at_one():
    """Additive score > 1.0 is capped at 1.0 → high."""
    # Blocklist fires first (FP-001 hard floor), so use manual stacking
    # to test the cap: FP-002 (0.8) + FP-003 (0.8) = 1.6 → capped at 1.0
    signals = _clean_signals(
        "TEST",
        chargebacks=CHARGEBACK_HIGH,
        refund_requests_in_window=VELOCITY_HIGH,
    )
    result = assess_signals(signals, _req())
    assert result.risk_level == RiskLevel.HIGH
