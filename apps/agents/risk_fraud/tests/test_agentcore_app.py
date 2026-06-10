"""Tests for the AgentCore app wrapper (T119).

No broker required — tests invoke the wrapper in-process.
"""

from __future__ import annotations

import uuid


def _payload(customer_id: str = "CUS-BLOCKLIST", **kwargs) -> dict:
    data: dict = {
        "case_id": str(uuid.uuid4()),
        "ticket_id": "TKT-001",
        "customer_id": customer_id,
    }
    data.update(kwargs)
    return data


# ---------------------------------------------------------------------------
# T119: Core invocation tests
# ---------------------------------------------------------------------------


def test_blocklist_customer_returns_high():
    from apps.agents.risk_fraud.agentcore_app import _invoke

    result = _invoke(_payload("CUS-BLOCKLIST"))
    assert result["status"] == "completed"
    assert result["recommendation"] == "high"
    fp_evidence = [e for e in result["evidence"] if e.get("source") == "fraud_policy"]
    assert len(fp_evidence) >= 1


def test_clean_customer_returns_low():
    from apps.agents.risk_fraud.agentcore_app import _invoke

    result = _invoke(_payload("CUS-CLEAN"))
    assert result["status"] == "completed"
    assert result["recommendation"] == "low"


def test_malformed_payload_returns_failed():
    """Missing required fields → structured failure, no fabricated verdict (FR-011)."""
    from apps.agents.risk_fraud.agentcore_app import _invoke

    result = _invoke({"ticket_id": "TKT-001"})  # missing case_id and customer_id
    assert result["status"] == "failed"
    assert "error" in result


def test_invalid_json_string_returns_failed():
    from apps.agents.risk_fraud.agentcore_app import _invoke

    result = _invoke("not-valid-json{{{")
    assert result["status"] == "failed"


def test_json_string_payload_accepted():
    """JSON-string payload is accepted and decoded correctly."""
    import json

    from apps.agents.risk_fraud.agentcore_app import _invoke

    result = _invoke(json.dumps(_payload("CUS-CLEAN")))
    assert result["status"] == "completed"


def test_delegation_proof_same_as_service():
    """Entrypoint verdict equals service.assess_signals output for the same input."""
    import uuid as _uuid

    from apps.agents.risk_fraud.agentcore_app import _invoke
    from apps.agents.risk_fraud.mock_data import load_signals
    from apps.agents.risk_fraud.models import RiskAssessmentRequest
    from apps.agents.risk_fraud.scoring import assess_signals

    customer_id = "CUS-CHARGEBACKS"
    case_id = str(_uuid.uuid4())
    payload = {"case_id": case_id, "ticket_id": "TKT-001", "customer_id": customer_id}

    wrapper_result = _invoke(payload)

    signals = load_signals(customer_id)
    assert signals is not None
    req = RiskAssessmentRequest.model_validate(payload)
    direct_assessment = assess_signals(signals, req)

    assert wrapper_result["recommendation"] == str(direct_assessment.risk_level)
    assert abs(wrapper_result["confidence"] - direct_assessment.confidence) < 1e-9


def test_no_publisher_constructed(monkeypatch):
    """Wrapper constructs no Publisher and publishes nothing to Kafka (SC-008/FR-016)."""
    published: list = []

    class FakePublisher:
        def __init__(self, *args, **kwargs):
            published.append("constructed")

        async def publish(self, *args, **kwargs):
            published.append("published")

    try:
        from agent_foundation.transport import publisher as pub_module

        monkeypatch.setattr(pub_module, "Publisher", FakePublisher)
    except (ImportError, AttributeError):
        pass

    from apps.agents.risk_fraud.agentcore_app import _invoke

    _invoke(_payload("CUS-CLEAN"))
    assert published == [], f"Unexpected Kafka activity: {published}"


def test_response_includes_all_required_fields():
    """Response includes risk level, recommendation, confidence, and evidence."""
    from apps.agents.risk_fraud.agentcore_app import _invoke

    result = _invoke(_payload("CUS-CLEAN"))
    assert result["status"] == "completed"
    assert "recommendation" in result
    assert "confidence" in result
    assert "evidence" in result
    assert "reasoning_summary" in result
    assert "requires_human_review" in result
    assert "policy_references" in result
