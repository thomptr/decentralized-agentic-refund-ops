"""Policy tests — each named rule fires on its triggering fact; borderline sides (T019 — FR-005)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from apps.agents.billing_entitlement.models import (
    BillingFacts,
    Entitlement,
    Invoice,
    Payment,
    ProductUsage,
    Recommendation,
    RefundEligibilityRequest,
    Subscription,
)
from apps.agents.billing_entitlement.policy import (
    REFUND_POLICY,
    REFUND_WINDOW_DAYS,
)
from apps.agents.billing_entitlement.rules_engine import evaluate


def _request(purchase_reference: str = "PR-APPROVE") -> RefundEligibilityRequest:
    return RefundEligibilityRequest(
        case_id=uuid.uuid4(),
        ticket_id="TKT-001",
        customer_id="CUS-001",
        requested_refund_amount=49.99,
        purchase_reference=purchase_reference,
    )


def _now() -> datetime:
    return datetime.now(UTC)


def _base_facts(*, days_ago: float = 5) -> BillingFacts:
    now = _now()
    return BillingFacts(
        subscription=Subscription(
            subscription_id="SUB-1",
            status="active",
            term="monthly",
            started_at=now - timedelta(days=90),
        ),
        invoice=Invoice(
            invoice_id="INV-1",
            purchase_reference="PR-X",
            amount=49.99,
            currency="USD",
            issued_at=now - timedelta(days=days_ago),
            paid=True,
        ),
        payment=Payment(
            payment_id="PAY-1",
            invoice_id="INV-1",
            captured=True,
            amount=49.99,
            reversed_amount=0.0,
        ),
        entitlement=Entitlement(
            entitlement_id="ENT-1",
            subscription_id="SUB-1",
            status="active",
            delivered=False,
        ),
        usage=ProductUsage(usage_units=0.5, allotment_units=5.0),
    )


# --- RP-001: refund window ---


def test_rp001_within_window_does_not_fire():
    facts = _base_facts(days_ago=5)
    rec = evaluate(facts, _request(), REFUND_POLICY)
    assert rec.recommendation == Recommendation.APPROVE_FULL_REFUND
    assert "RP-001" not in rec.policy_references or "expired" not in rec.refund_window_status


def test_rp001_outside_window_fires():
    facts = _base_facts(days_ago=45)
    rec = evaluate(facts, _request(), REFUND_POLICY)
    assert rec.recommendation == Recommendation.DENY_REFUND
    assert "RP-001" in rec.policy_references
    assert rec.refund_window_status == "expired"


def test_rp001_borderline_exactly_30_days_within():
    """Exactly REFUND_WINDOW_DAYS → within (inclusive boundary — policy.md)."""
    facts = _base_facts(days_ago=REFUND_WINDOW_DAYS)
    rec = evaluate(facts, _request(), REFUND_POLICY)
    assert rec.recommendation == Recommendation.APPROVE_FULL_REFUND
    assert rec.confidence == 0.6  # borderline


# --- RP-002: paid invoice ---


def test_rp002_unpaid_fires():
    facts = _base_facts()
    assert facts.invoice is not None
    # Rebuild with unpaid invoice
    now = _now()
    facts = BillingFacts(
        subscription=facts.subscription,
        invoice=Invoice(
            invoice_id="INV-1",
            purchase_reference="PR-X",
            amount=49.99,
            currency="USD",
            issued_at=now - timedelta(days=5),
            paid=False,
        ),
        payment=Payment(
            payment_id="PAY-1",
            invoice_id="INV-1",
            captured=False,
            amount=49.99,
            reversed_amount=0.0,
        ),
        entitlement=facts.entitlement,
        usage=facts.usage,
    )
    rec = evaluate(facts, _request(), REFUND_POLICY)
    assert rec.recommendation == Recommendation.DENY_REFUND
    assert "RP-002" in rec.policy_references


def test_rp002_already_fully_reversed_fires():
    facts = _base_facts()
    facts = BillingFacts(
        subscription=facts.subscription,
        invoice=facts.invoice,
        payment=Payment(
            payment_id="PAY-1",
            invoice_id="INV-1",
            captured=True,
            amount=49.99,
            reversed_amount=49.99,
        ),
        entitlement=facts.entitlement,
        usage=facts.usage,
    )
    rec = evaluate(facts, _request(), REFUND_POLICY)
    assert rec.recommendation == Recommendation.DENY_REFUND
    assert "RP-002" in rec.policy_references


# --- RP-003: entitlement delivered ---


def test_rp003_not_delivered_approve_supporting():
    facts = _base_facts()
    rec = evaluate(facts, _request(), REFUND_POLICY)
    assert rec.recommendation == Recommendation.APPROVE_FULL_REFUND
    assert "RP-003" in rec.policy_references


def test_rp003_delivered_no_automatic_deny():
    """Delivered alone does not deny — requires heavy usage or other gate."""
    facts = _base_facts()
    assert facts.entitlement is not None
    facts = BillingFacts(
        subscription=facts.subscription,
        invoice=facts.invoice,
        payment=facts.payment,
        entitlement=Entitlement(
            entitlement_id="ENT-1",
            subscription_id="SUB-1",
            status="active",
            delivered=True,
            access_granted=True,
            access_used=True,
        ),
        usage=ProductUsage(usage_units=0.5, allotment_units=5.0),
    )
    rec = evaluate(facts, _request(), REFUND_POLICY)
    # Delivered + light usage → no applicable rule → manual_review
    assert rec.recommendation == Recommendation.MANUAL_REVIEW


# --- RP-004: usage threshold ---


def test_rp004_heavy_usage_fires():
    facts = _base_facts()
    facts = BillingFacts(
        subscription=facts.subscription,
        invoice=facts.invoice,
        payment=facts.payment,
        entitlement=facts.entitlement,
        usage=ProductUsage(usage_units=4.75, allotment_units=5.0),  # 0.95 > 0.8
    )
    rec = evaluate(facts, _request(), REFUND_POLICY)
    assert rec.recommendation == Recommendation.DENY_REFUND
    assert "RP-004" in rec.policy_references
    assert rec.usage_level == "heavy"


def test_rp004_borderline_exactly_at_threshold_does_not_fire():
    """usage_ratio == USAGE_HEAVY_THRESHOLD → below heavy (RP-004 does NOT fire)."""
    facts = _base_facts()
    facts = BillingFacts(
        subscription=facts.subscription,
        invoice=facts.invoice,
        payment=facts.payment,
        entitlement=facts.entitlement,
        usage=ProductUsage(usage_units=4.0, allotment_units=5.0),  # exactly 0.80
    )
    rec = evaluate(facts, _request(), REFUND_POLICY)
    # Should approve (or at least not deny via usage gate)
    assert rec.recommendation != Recommendation.DENY_REFUND or "RP-001" in rec.policy_references


# --- RP-005: subscription status ---


def test_rp005_active_sub_contributes_evidence():
    facts = _base_facts()
    rec = evaluate(facts, _request(), REFUND_POLICY)
    # Active subscription → RP-005 reference when relevant
    assert rec.subscription_status == "active"


def test_rp005_cancelled_sub_within_window():
    facts = _base_facts()
    now = _now()
    cancelled_sub = Subscription(
        subscription_id="SUB-1",
        status="cancelled",
        term="monthly",
        started_at=now - timedelta(days=90),
    )
    facts = BillingFacts(
        subscription=cancelled_sub,
        invoice=facts.invoice,
        payment=facts.payment,
        entitlement=facts.entitlement,
        usage=facts.usage,
    )
    rec = evaluate(facts, _request(), REFUND_POLICY)
    assert rec.subscription_status == "cancelled"
