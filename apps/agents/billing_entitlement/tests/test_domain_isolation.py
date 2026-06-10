"""Domain isolation test — all EvidenceItem.source values are owned domains (T020 — SC-003/FR-009)."""

from __future__ import annotations

import uuid

import pytest

from apps.agents.billing_entitlement.mock_data import _DATASET, load_facts
from apps.agents.billing_entitlement.models import RefundEligibilityRequest
from apps.agents.billing_entitlement.policy import REFUND_POLICY
from apps.agents.billing_entitlement.rules_engine import evaluate

_ALLOWED_SOURCES = {
    "subscription",
    "invoice",
    "payment",
    "entitlement",
    "product_usage",
    "refund_policy",
}

_FORBIDDEN_KEYWORDS = {"risk", "fraud", "chargeback", "dispute", "customer_workflow"}


def _request(purchase_reference: str) -> RefundEligibilityRequest:
    return RefundEligibilityRequest(
        case_id=uuid.uuid4(),
        ticket_id="TKT-001",
        customer_id="CUS-001",
        requested_refund_amount=49.99,
        purchase_reference=purchase_reference,
    )


@pytest.mark.parametrize("ref", list(_DATASET.keys()))
def test_all_evidence_sources_are_owned(ref: str):
    facts = load_facts(ref, "any")
    assert facts is not None
    rec = evaluate(facts, _request(ref), REFUND_POLICY)
    for item in rec.evidence:
        assert item.source in _ALLOWED_SOURCES, (
            f"EvidenceItem.source={item.source!r} is not an owned domain "
            f"(ref={ref!r}). Allowed: {_ALLOWED_SOURCES}"
        )


@pytest.mark.parametrize("ref", list(_DATASET.keys()))
def test_no_foreign_domain_fields_in_evidence_values(ref: str):
    facts = load_facts(ref, "any")
    assert facts is not None
    rec = evaluate(facts, _request(ref), REFUND_POLICY)
    for item in rec.evidence:
        val_str = str(item.value).lower()
        for kw in _FORBIDDEN_KEYWORDS:
            assert kw not in val_str, (
                f"Forbidden keyword {kw!r} found in EvidenceItem.value (ref={ref!r})"
            )


def test_evidence_is_non_empty_for_all_cases(sc_002: None = None):
    """SC-002: evidence must be non-empty for every verdict."""
    for ref in _DATASET:
        facts = load_facts(ref, "any")
        assert facts is not None
        rec = evaluate(facts, _request(ref), REFUND_POLICY)
        assert len(rec.evidence) > 0, f"Evidence empty for ref={ref!r}"
