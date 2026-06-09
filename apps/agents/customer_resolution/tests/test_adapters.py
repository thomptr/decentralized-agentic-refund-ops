"""Unit tests for the result normalization adapter (T028, T104, T118, T157, US3)."""

from __future__ import annotations

import uuid

from apps.agents.customer_resolution.event_handlers import (
    normalize_billing_result,
    normalize_risk_result,
)

_TASK_ID = uuid.uuid4()
_PERFORMER = "billing-entitlement-agent"


# --- Billing normalization ---

def test_billing_canonical_approve():
    data = {"recommendation": "approve", "confidence": 0.9, "requires_human_review": False,
            "evidence": [], "reasoning_summary": "ok"}
    finding = normalize_billing_result(_TASK_ID, _PERFORMER, data)
    assert finding is not None
    assert finding.eligibility == "eligible"
    assert finding.requires_human_review is False


def test_billing_canonical_deny():
    data = {"recommendation": "deny", "confidence": 0.8, "requires_human_review": False,
            "evidence": [], "reasoning_summary": "denied"}
    finding = normalize_billing_result(_TASK_ID, _PERFORMER, data)
    assert finding is not None
    assert finding.eligibility == "ineligible"


def test_billing_stub_eligible_true():
    data = {"eligible": True, "reason": "mock"}
    finding = normalize_billing_result(_TASK_ID, _PERFORMER, data)
    assert finding is not None
    assert finding.eligibility == "eligible"


def test_billing_stub_eligible_false():
    data = {"eligible": False, "reason": "not eligible"}
    finding = normalize_billing_result(_TASK_ID, _PERFORMER, data)
    assert finding is not None
    assert finding.eligibility == "ineligible"


def test_billing_partial_refund():
    data = {"recommendation": "partial_refund", "confidence": 0.7, "requires_human_review": False,
            "evidence": [], "reasoning_summary": "partial"}
    finding = normalize_billing_result(_TASK_ID, _PERFORMER, data)
    assert finding is not None
    assert finding.eligibility == "partial"


def test_billing_unparseable_returns_none():
    finding = normalize_billing_result(_TASK_ID, _PERFORMER, {"garbage": "data"})
    assert finding is None


# --- Risk normalization ---

_RISK_PERFORMER = "risk-fraud-agent"


def test_risk_canonical_low():
    data = {"recommendation": "low", "confidence": 0.1, "requires_human_review": False,
            "evidence": [], "reasoning_summary": "low risk"}
    finding = normalize_risk_result(_TASK_ID, _RISK_PERFORMER, data)
    assert finding is not None
    assert finding.level == "low"


def test_risk_canonical_high():
    data = {"recommendation": "high", "confidence": 0.95, "requires_human_review": False,
            "evidence": [], "reasoning_summary": "high risk"}
    finding = normalize_risk_result(_TASK_ID, _RISK_PERFORMER, data)
    assert finding is not None
    assert finding.level == "high"


def test_risk_stub_low():
    data = {"risk": "low", "score": 0.1}
    finding = normalize_risk_result(_TASK_ID, _RISK_PERFORMER, data)
    assert finding is not None
    assert finding.level == "low"


def test_risk_stub_elevated():
    data = {"risk": "elevated", "score": 0.6}
    finding = normalize_risk_result(_TASK_ID, _RISK_PERFORMER, data)
    assert finding is not None
    assert finding.level == "elevated"


def test_risk_stub_high():
    data = {"risk": "high", "score": 0.9}
    finding = normalize_risk_result(_TASK_ID, _RISK_PERFORMER, data)
    assert finding is not None
    assert finding.level == "high"


def test_risk_score_threshold_elevated():
    # score 0.6 → elevated
    data = {"recommendation": "unknown", "confidence": 0.6}
    finding = normalize_risk_result(
        _TASK_ID, _RISK_PERFORMER, data, elevated_threshold=0.5, high_threshold=0.8
    )
    assert finding is not None
    assert finding.level == "elevated"


def test_risk_score_threshold_high():
    data = {"recommendation": "unknown", "confidence": 0.9}
    finding = normalize_risk_result(
        _TASK_ID, _RISK_PERFORMER, data, elevated_threshold=0.5, high_threshold=0.8
    )
    assert finding is not None
    assert finding.level == "high"


def test_risk_unparseable_returns_none():
    finding = normalize_risk_result(_TASK_ID, _RISK_PERFORMER, {"garbage": "data"})
    assert finding is None
