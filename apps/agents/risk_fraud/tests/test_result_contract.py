"""Tests for the RiskReviewCompletedPayload contract (T018)."""

from __future__ import annotations

import uuid

from apps.agents.risk_fraud.mock_data import load_signals
from apps.agents.risk_fraud.models import RiskAssessmentRequest
from apps.agents.risk_fraud.scoring import assess_signals
from apps.agents.risk_fraud.service import to_result_payload
from packages.contracts.events.payloads import RiskReviewCompletedPayload


def _req(customer_id: str = "CUS-CLEAN") -> RiskAssessmentRequest:
    return RiskAssessmentRequest(
        case_id=uuid.uuid4(),
        ticket_id="TKT-001",
        customer_id=customer_id,
    )


# ---------------------------------------------------------------------------
# T018: RiskReviewCompletedPayload round-trip
# ---------------------------------------------------------------------------


def test_payload_roundtrip():
    """Payload serializes and deserializes without data loss."""
    signals = load_signals("CUS-CHARGEBACKS")
    assert signals is not None
    req = _req("CUS-CHARGEBACKS")
    assessment = assess_signals(signals, req)
    payload = to_result_payload(assessment, req)

    dumped = payload.model_dump(mode="json")
    restored = RiskReviewCompletedPayload.model_validate(dumped)

    assert restored.recommendation == payload.recommendation
    assert restored.confidence == payload.confidence
    assert restored.requires_human_review == payload.requires_human_review


def test_payload_registry_contains_risk_result_topic():
    """TOPIC_RISK_RESULT is registered in PAYLOAD_REGISTRY."""
    from agent_foundation.payloads import PAYLOAD_REGISTRY
    from packages.contracts.topics import TOPIC_RISK_RESULT

    assert TOPIC_RISK_RESULT in PAYLOAD_REGISTRY
    assert PAYLOAD_REGISTRY[TOPIC_RISK_RESULT] is RiskReviewCompletedPayload


def test_payload_recommendation_is_risk_level_value():
    """recommendation wire field is risk_level.value (SC-009/R5)."""
    signals = load_signals("CUS-CHARGEBACKS")
    assert signals is not None
    req = _req("CUS-CHARGEBACKS")
    assessment = assess_signals(signals, req)
    payload = to_result_payload(assessment, req)

    assert payload.recommendation == str(assessment.risk_level)
    assert payload.recommendation in ("low", "elevated", "high")


def test_payload_mapping_populates_all_fields():
    """All RiskReviewCompletedPayload fields are populated from RiskAssessment."""
    signals = load_signals("CUS-BLOCKLIST")
    assert signals is not None
    req = _req("CUS-BLOCKLIST")
    assessment = assess_signals(signals, req)
    payload = to_result_payload(assessment, req)

    assert payload.ticket_id == req.ticket_id
    assert payload.recommendation is not None
    assert 0.0 <= payload.confidence <= 1.0
    assert len(payload.evidence) >= 1
    assert payload.reasoning_summary
    assert isinstance(payload.requires_human_review, bool)


def test_at_least_one_fraud_policy_evidence_item():
    """At least one EvidenceItem has source='fraud_policy' (SC-002)."""
    signals = load_signals("CUS-CHARGEBACKS")
    assert signals is not None
    req = _req("CUS-CHARGEBACKS")
    assessment = assess_signals(signals, req)
    payload = to_result_payload(assessment, req)

    fp_items = [e for e in payload.evidence if e.source == "fraud_policy"]
    assert len(fp_items) >= 1


def test_a2a_output_shape_matches_normalize_risk_result():
    """A2A output data part carries the fields 003's normalize_risk_result consumes."""
    from apps.agents.risk_fraud.service import build_a2a_output

    signals = load_signals("CUS-CLEAN")
    assert signals is not None
    req = _req("CUS-CLEAN")
    assessment = assess_signals(signals, req)
    msg = build_a2a_output(assessment)

    assert len(msg.parts) == 1
    data = msg.parts[0].data
    assert "recommendation" in data
    assert data["recommendation"] in ("low", "elevated", "high")
    assert "confidence" in data
    assert "evidence" in data
    assert "reasoning_summary" in data
    assert "requires_human_review" in data
    # score field for backward compatibility with stub consumer
    assert "score" in data
