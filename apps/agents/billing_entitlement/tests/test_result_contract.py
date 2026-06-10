"""Result-contract tests — payload round-trip + registry (T013 — SC-009)."""

from __future__ import annotations

import uuid
from decimal import Decimal

from agent_foundation.payloads import PAYLOAD_REGISTRY
from packages.contracts.events.payloads import BillingRefundAnalysisCompletedPayload, EvidenceItem
from packages.contracts.topics import TOPIC_BILLING_RESULT


def _sample_payload(**overrides) -> BillingRefundAnalysisCompletedPayload:
    defaults = {
        "case_id": uuid.uuid4(),
        "ticket_id": "TKT-001",
        "customer_id": "CUS-001",
        "billing_account_id": "SUB-001",
        "subscription_status": "active",
        "invoice_status": "paid",
        "payment_status": "captured",
        "entitlement_status": "active",
        "usage_level": "light",
        "refund_window_status": "within",
        "recommendation": "approve_full_refund",
        "confidence": 0.9,
        "evidence": [
            EvidenceItem(source="invoice", description="Invoice paid", value={"paid": True})
        ],
        "reasoning_summary": "Within window, paid, not delivered.",
        "requires_human_review": False,
        "eligible_refund_amount": Decimal("49.99"),
    }
    defaults.update(overrides)
    return BillingRefundAnalysisCompletedPayload(**defaults)


def test_payload_constructs():
    p = _sample_payload()
    assert p.recommendation == "approve_full_refund"
    assert p.eligible_refund_amount == Decimal("49.99")


def test_payload_registry_resolves():
    model_cls = PAYLOAD_REGISTRY[TOPIC_BILLING_RESULT]
    assert model_cls is BillingRefundAnalysisCompletedPayload


def test_json_round_trip():
    p = _sample_payload()
    json_dict = p.model_dump(mode="json")
    assert isinstance(json_dict["eligible_refund_amount"], str)  # Decimal → str in JSON mode
    restored = BillingRefundAnalysisCompletedPayload.model_validate(json_dict)
    assert restored.eligible_refund_amount == Decimal("49.99")
    assert restored.recommendation == "approve_full_refund"


def test_decimal_zero_default():
    p = _sample_payload(eligible_refund_amount=Decimal("0.00"))
    data = p.model_dump(mode="json")
    restored = BillingRefundAnalysisCompletedPayload.model_validate(data)
    assert restored.eligible_refund_amount == Decimal("0.00")


def test_billing_account_id_optional():
    p = _sample_payload(billing_account_id=None)
    assert p.billing_account_id is None
    data = p.model_dump(mode="json")
    restored = BillingRefundAnalysisCompletedPayload.model_validate(data)
    assert restored.billing_account_id is None


def test_status_defaults_allow_backward_compat():
    """Older events without the new status fields can be deserialized using defaults."""
    minimal = {
        "case_id": str(uuid.uuid4()),
        "ticket_id": "TKT-X",
        "customer_id": "CUS-X",
        "recommendation": "deny_refund",
        "confidence": 0.9,
        "evidence": [],
        "reasoning_summary": "old format",
        "requires_human_review": False,
    }
    p = BillingRefundAnalysisCompletedPayload.model_validate(minimal)
    assert p.subscription_status == "unknown"
    assert p.invoice_status == "unknown"
    assert p.eligible_refund_amount == Decimal("0.00")


def test_a2a_data_part_shape_consumed_by_003_normalizer():
    """The A2A data part shape (recommendation + confidence + evidence + etc.) matches
    what 003's normalize_billing_result expects."""
    from apps.agents.customer_resolution.event_handlers import normalize_billing_result

    task_id = uuid.uuid4()
    performer = "billing-entitlement-agent"

    for rec_value, expected_eligibility in [
        ("approve_full_refund", "eligible"),
        ("approve_partial_refund", "partial"),
        ("deny_refund", "ineligible"),
        ("request_more_information", "indeterminate"),
        ("manual_review", "indeterminate"),
    ]:
        data = {
            "recommendation": rec_value,
            "confidence": 0.9,
            "evidence": [],
            "reasoning_summary": "test",
            "requires_human_review": False,
        }
        finding = normalize_billing_result(task_id, performer, data)
        assert finding is not None, f"normalize_billing_result returned None for {rec_value!r}"
        assert finding.eligibility == expected_eligibility, (
            f"recommendation={rec_value!r} → expected eligibility={expected_eligibility!r}, "
            f"got {finding.eligibility!r}"
        )
