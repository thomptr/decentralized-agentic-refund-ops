"""Tests for domain isolation — evidence only from owned signals, no peer calls (T021, T022)."""

from __future__ import annotations

import uuid

import pytest

from apps.agents.risk_fraud.mock_data import load_signals
from apps.agents.risk_fraud.models import RiskAssessmentRequest
from apps.agents.risk_fraud.scoring import assess_signals

_OWNED_SOURCES = frozenset(
    {
        "account_standing",
        "refund_history",
        "payment_instrument",
        "behavioral",
        "known_fraud",
        "fraud_policy",
    }
)


def _req(customer_id: str = "CUS-CLEAN") -> RiskAssessmentRequest:
    return RiskAssessmentRequest(
        case_id=uuid.uuid4(),
        ticket_id="TKT-001",
        customer_id=customer_id,
    )


# ---------------------------------------------------------------------------
# T021: Every EvidenceItem.source is in the owned signal set
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "customer_id",
    [
        "CUS-CLEAN",
        "CUS-CHARGEBACKS",
        "CUS-BLOCKLIST",
        "CUS-NEW-ACCOUNT",
        "CUS-VELOCITY",
        "CUS-CARD-TESTING",
    ],
)
def test_evidence_sources_owned_only(customer_id: str):
    """All EvidenceItem.source values are in the owned signal/policy set (SC-003/FR-009)."""
    signals = load_signals(customer_id)
    assert signals is not None
    result = assess_signals(signals, _req(customer_id))
    for ev in result.evidence:
        assert ev.source in _OWNED_SOURCES, (
            f"Non-owned evidence source {ev.source!r} for customer {customer_id}"
        )


# ---------------------------------------------------------------------------
# T021: Verdict reads no billing/foreign fields
# ---------------------------------------------------------------------------


def test_verdict_no_billing_foreign_fields():
    """The verdict/assessment contains no billing-eligibility or customer-resolution fields."""
    signals = load_signals("CUS-CLEAN")
    assert signals is not None
    result = assess_signals(signals, _req())

    forbidden = [
        "subscription",
        "invoice",
        "payment_id",
        "entitlement",
        "billing_account_id",
        "eligible_refund_amount",
        "refund_window_status",
        "subscription_status",
    ]
    for field in forbidden:
        assert not hasattr(result, field), f"RiskAssessment should not have field {field!r}"


# ---------------------------------------------------------------------------
# T021: No peer/runtime client constructed
# ---------------------------------------------------------------------------


def test_service_assess_makes_no_peer_call(monkeypatch):
    """service.assess constructs no peer/runtime client (SC-003/FR-009)."""
    from apps.agents.risk_fraud import service

    # Patch AgentRuntime and any client-like class to detect if they are constructed
    call_log: list[str] = []

    class SentinelRuntime:
        def __init__(self, *args, **kwargs):
            call_log.append("AgentRuntime constructed")

    try:
        from agent_foundation import runtime as rt_module

        monkeypatch.setattr(rt_module, "AgentRuntime", SentinelRuntime)
    except (ImportError, AttributeError):
        pass

    from agent_foundation.a2a import A2APart

    parts = [
        A2APart(
            type="data",
            data={
                "case_id": str(uuid.uuid4()),
                "ticket_id": "TKT-001",
                "customer_id": "CUS-CLEAN",
            },
        )
    ]
    service.assess(parts)
    assert call_log == [], f"Unexpected peer/runtime client construction: {call_log}"
