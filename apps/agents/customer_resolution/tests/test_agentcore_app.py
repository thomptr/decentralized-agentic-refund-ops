"""Tests for the AgentCore app wrapper (demo/testing entrypoint).

No broker required — tests invoke the wrapper in-process. The wrapper reuses the same
classify + decide pipeline as the Kafka path but performs no peer delegation and no publish.
"""

from __future__ import annotations

import uuid


def _payload(reason: str = "I was double charged, please refund", **kwargs) -> dict:
    data: dict = {
        "ticket_id": "TKT-001",
        "customer_id": "CUS-001",
        "amount": 49.99,
        "currency": "USD",
        "reason": reason,
    }
    data.update(kwargs)
    return data


# ---------------------------------------------------------------------------
# Core invocation tests
# ---------------------------------------------------------------------------


def test_non_refund_ticket_returns_direct_response():
    from apps.agents.customer_resolution.agentcore_app import _invoke

    result = _invoke(_payload(reason="How do I reset my password?"))
    assert result["status"] == "completed"
    assert result["outcome"] == "direct_response"


def test_refund_ticket_without_peer_findings_escalates():
    """No billing/risk findings supplied → deterministic escalate_human (FR-005).

    The wrapper never fabricates a billing or risk verdict.
    """
    from apps.agents.customer_resolution.agentcore_app import _invoke

    result = _invoke(_payload())
    assert result["status"] == "completed"
    assert result["outcome"] == "escalate_human"
    assert result["escalation_reason"] == "missing_analysis"


def test_refund_ticket_approves_with_eligible_and_low_risk():
    from apps.agents.customer_resolution.agentcore_app import _invoke

    result = _invoke(
        _payload(
            billing_result={"recommendation": "approve_full_refund", "confidence": 0.9},
            risk_result={"recommendation": "low", "confidence": 0.9},
        )
    )
    assert result["status"] == "completed"
    assert result["outcome"] == "approve_refund"


def test_refund_ticket_denies_with_ineligible_and_elevated_risk():
    # risk "confidence" is the agent's certainty in its verdict (high == sure). A confident
    # elevated-risk read keeps decision-confidence above threshold, so an ineligible billing
    # opinion is corroborated and we land on the deny row, not a low_confidence escalation.
    from apps.agents.customer_resolution.agentcore_app import _invoke

    result = _invoke(
        _payload(
            billing_result={"recommendation": "deny_refund", "confidence": 0.9},
            risk_result={"recommendation": "elevated", "confidence": 0.9},
        )
    )
    assert result["status"] == "completed"
    assert result["outcome"] == "deny_refund"


def test_high_confidence_high_risk_escalates_to_human():
    # Eligible billing but a confident high-risk verdict is a genuine conflict (billing says
    # refund-worthy, risk says fraud), so the engine escalates to a human rather than approving.
    from apps.agents.customer_resolution.agentcore_app import _invoke

    result = _invoke(
        _payload(
            billing_result={"recommendation": "approve_full_refund", "confidence": 0.9},
            risk_result={"recommendation": "high", "confidence": 0.95},
        )
    )
    assert result["status"] == "completed"
    assert result["outcome"] == "escalate_human"


def test_malformed_payload_returns_failed():
    """Missing required fields → structured failure, no fabricated decision (FR-011)."""
    from apps.agents.customer_resolution.agentcore_app import _invoke

    result = _invoke({"reason": "refund please"})  # missing ticket_id and customer_id
    assert result["status"] == "failed"
    assert "error" in result


def test_invalid_json_string_returns_failed():
    from apps.agents.customer_resolution.agentcore_app import _invoke

    result = _invoke("not-valid-json{{{")
    assert result["status"] == "failed"


def test_json_string_payload_accepted():
    """JSON-string payload is accepted and decoded correctly."""
    import json

    from apps.agents.customer_resolution.agentcore_app import _invoke

    result = _invoke(json.dumps(_payload(reason="How do I reset my password?")))
    assert result["status"] == "completed"
    assert result["outcome"] == "direct_response"


def test_supplied_case_id_is_echoed():
    from apps.agents.customer_resolution.agentcore_app import _invoke

    case_id = str(uuid.uuid4())
    result = _invoke(_payload(case_id=case_id, reason="How do I reset my password?"))
    assert result["case_id"] == case_id


def test_no_publisher_constructed(monkeypatch):
    """Wrapper constructs no Publisher and publishes nothing to Kafka (FR-005)."""
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

    from apps.agents.customer_resolution.agentcore_app import _invoke

    _invoke(
        _payload(
            billing_result={"recommendation": "approve_full_refund", "confidence": 0.9},
            risk_result={"recommendation": "low", "confidence": 0.9},
        )
    )
    assert published == [], f"Unexpected Kafka activity: {published}"


def test_response_includes_required_decision_fields():
    from apps.agents.customer_resolution.agentcore_app import _invoke

    result = _invoke(
        _payload(
            billing_result={"recommendation": "approve_full_refund", "confidence": 0.9},
            risk_result={"recommendation": "low", "confidence": 0.9},
        )
    )
    assert result["status"] == "completed"
    assert "outcome" in result
    assert "customer_response" in result
    assert "rationale" in result
    assert "ticket_id" in result
    assert "customer_id" in result
