"""Rules-engine tests — truth table, single-fact matrix, uncertainty, determinism (T009/T022)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from apps.agents.billing_entitlement.mock_data import load_facts
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


# ---------------------------------------------------------------------------
# Approve / deny / human-review truth table (SC-004)
# ---------------------------------------------------------------------------


def test_approve_case():
    facts = load_facts("PR-APPROVE", "any")
    assert facts is not None
    rec = evaluate(facts, _request("PR-APPROVE"), REFUND_POLICY)
    assert rec.recommendation == Recommendation.APPROVE_FULL_REFUND
    assert rec.confidence == 0.9
    assert rec.requires_human_review is False
    assert rec.eligible_refund_amount > Decimal("0")


def test_deny_window_expired():
    facts = load_facts("PR-WINDOW-EXPIRED", "any")
    assert facts is not None
    rec = evaluate(facts, _request("PR-WINDOW-EXPIRED"), REFUND_POLICY)
    assert rec.recommendation == Recommendation.DENY_REFUND
    assert rec.confidence == 0.9
    assert rec.requires_human_review is False
    assert "RP-001" in rec.policy_references


def test_deny_unpaid():
    facts = load_facts("PR-UNPAID", "any")
    assert facts is not None
    rec = evaluate(facts, _request("PR-UNPAID"), REFUND_POLICY)
    assert rec.recommendation == Recommendation.DENY_REFUND
    assert "RP-002" in rec.policy_references


def test_deny_already_refunded():
    facts = load_facts("PR-ALREADY-REFUNDED", "any")
    assert facts is not None
    rec = evaluate(facts, _request("PR-ALREADY-REFUNDED"), REFUND_POLICY)
    assert rec.recommendation == Recommendation.DENY_REFUND
    assert "RP-002" in rec.policy_references


def test_deny_heavy_usage():
    facts = load_facts("PR-HEAVY-USAGE", "any")
    assert facts is not None
    rec = evaluate(facts, _request("PR-HEAVY-USAGE"), REFUND_POLICY)
    assert rec.recommendation == Recommendation.DENY_REFUND
    assert rec.confidence == 0.9
    assert "RP-004" in rec.policy_references


def test_contradiction_manual_review():
    facts = load_facts("PR-CONTRADICTION", "any")
    assert facts is not None
    rec = evaluate(facts, _request("PR-CONTRADICTION"), REFUND_POLICY)
    assert rec.recommendation == Recommendation.MANUAL_REVIEW
    assert rec.confidence == 0.3
    assert rec.requires_human_review is True


def test_borderline_approve_with_lowered_confidence():
    facts = load_facts("PR-BORDERLINE", "any")
    assert facts is not None
    rec = evaluate(facts, _request("PR-BORDERLINE"), REFUND_POLICY)
    assert rec.recommendation == Recommendation.APPROVE_FULL_REFUND
    assert rec.confidence == 0.6  # borderline window


# ---------------------------------------------------------------------------
# Single-fact matrix off PR-APPROVE (SC-004) — vary one column at a time
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(UTC)


def _base_approve_facts(now: datetime) -> BillingFacts:
    return BillingFacts(
        subscription=Subscription(
            subscription_id="SUB-1",
            status="active",
            term="monthly",
            started_at=now - timedelta(days=90),
        ),
        invoice=Invoice(
            invoice_id="INV-1",
            purchase_reference="PR-APPROVE",
            amount=49.99,
            currency="USD",
            issued_at=now - timedelta(days=5),
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


def test_single_fact_flip_window_causes_deny():
    now = _now()
    facts = _base_approve_facts(now)
    assert facts.subscription is not None
    flipped = BillingFacts(
        subscription=facts.subscription,
        invoice=Invoice(
            invoice_id="INV-1",
            purchase_reference="PR-APPROVE",
            amount=49.99,
            currency="USD",
            issued_at=now - timedelta(days=45),  # outside window
            paid=True,
        ),
        payment=facts.payment,
        entitlement=facts.entitlement,
        usage=facts.usage,
    )
    rec = evaluate(flipped, _request(), REFUND_POLICY)
    assert rec.recommendation == Recommendation.DENY_REFUND
    assert "RP-001" in rec.policy_references


def test_single_fact_flip_paid_causes_deny():
    now = _now()
    facts = _base_approve_facts(now)
    flipped = BillingFacts(
        subscription=facts.subscription,
        invoice=Invoice(
            invoice_id="INV-1",
            purchase_reference="PR-APPROVE",
            amount=49.99,
            currency="USD",
            issued_at=now - timedelta(days=5),
            paid=False,  # unpaid
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
    rec = evaluate(flipped, _request(), REFUND_POLICY)
    assert rec.recommendation == Recommendation.DENY_REFUND
    assert "RP-002" in rec.policy_references


def test_single_fact_flip_usage_causes_deny():
    now = _now()
    facts = _base_approve_facts(now)
    flipped = BillingFacts(
        subscription=facts.subscription,
        invoice=facts.invoice,
        payment=facts.payment,
        entitlement=facts.entitlement,
        usage=ProductUsage(usage_units=4.75, allotment_units=5.0),  # heavy
    )
    rec = evaluate(flipped, _request(), REFUND_POLICY)
    assert rec.recommendation == Recommendation.DENY_REFUND
    assert "RP-004" in rec.policy_references


def test_single_fact_flip_reversal_causes_deny():
    now = _now()
    facts = _base_approve_facts(now)
    flipped = BillingFacts(
        subscription=facts.subscription,
        invoice=facts.invoice,
        payment=Payment(
            payment_id="PAY-1",
            invoice_id="INV-1",
            captured=True,
            amount=49.99,
            reversed_amount=49.99,  # fully reversed
        ),
        entitlement=facts.entitlement,
        usage=facts.usage,
    )
    rec = evaluate(flipped, _request(), REFUND_POLICY)
    assert rec.recommendation == Recommendation.DENY_REFUND


# ---------------------------------------------------------------------------
# Missing / contradictory paths — uncertainty (T022 — FR-010/FR-011/SC-005)
# ---------------------------------------------------------------------------


def test_missing_invoice_returns_request_more_information():
    now = _now()
    facts = BillingFacts(
        subscription=Subscription(
            subscription_id="SUB-1",
            status="active",
            term="monthly",
            started_at=now - timedelta(days=90),
        ),
        invoice=None,
        payment=None,
    )
    rec = evaluate(facts, _request(), REFUND_POLICY)
    assert rec.recommendation == Recommendation.REQUEST_MORE_INFORMATION
    assert rec.confidence == 0.2
    assert rec.requires_human_review is True


def test_missing_payment_returns_request_more_information():
    now = _now()
    facts = BillingFacts(
        invoice=Invoice(
            invoice_id="INV-1",
            purchase_reference="PR-X",
            amount=49.99,
            currency="USD",
            issued_at=now - timedelta(days=5),
            paid=True,
        ),
        payment=None,
    )
    rec = evaluate(facts, _request(), REFUND_POLICY)
    assert rec.recommendation == Recommendation.REQUEST_MORE_INFORMATION
    assert rec.confidence == 0.2
    assert rec.requires_human_review is True


def test_contradiction_path_has_low_confidence():
    facts = load_facts("PR-CONTRADICTION", "any")
    assert facts is not None
    rec = evaluate(facts, _request("PR-CONTRADICTION"), REFUND_POLICY)
    assert rec.confidence == 0.3
    assert rec.requires_human_review is True
    assert rec.recommendation == Recommendation.MANUAL_REVIEW


def test_no_fabricated_verdict_on_contradiction():
    """Contradiction → manual_review, never confident approve/deny (FR-010/SC-005)."""
    facts = load_facts("PR-CONTRADICTION", "any")
    assert facts is not None
    rec = evaluate(facts, _request("PR-CONTRADICTION"), REFUND_POLICY)
    assert rec.recommendation not in (
        Recommendation.APPROVE_FULL_REFUND,
        Recommendation.DENY_REFUND,
    )


def test_reason_recorded_on_manual_review():
    facts = load_facts("PR-CONTRADICTION", "any")
    assert facts is not None
    rec = evaluate(facts, _request("PR-CONTRADICTION"), REFUND_POLICY)
    assert len(rec.reasoning_summary) > 0
    assert len(rec.evidence) > 0


# ---------------------------------------------------------------------------
# Confidence schedule (research R6)
# ---------------------------------------------------------------------------


def test_confidence_09_on_clear_approve():
    facts = load_facts("PR-APPROVE", "any")
    assert facts is not None
    rec = evaluate(facts, _request("PR-APPROVE"), REFUND_POLICY)
    assert rec.confidence == 0.9


def test_confidence_09_on_clear_deny():
    facts = load_facts("PR-WINDOW-EXPIRED", "any")
    assert facts is not None
    rec = evaluate(facts, _request("PR-WINDOW-EXPIRED"), REFUND_POLICY)
    assert rec.confidence == 0.9


def test_confidence_06_on_borderline():
    facts = load_facts("PR-BORDERLINE", "any")
    assert facts is not None
    rec = evaluate(facts, _request("PR-BORDERLINE"), REFUND_POLICY)
    assert rec.confidence == 0.6


def test_confidence_03_on_contradiction():
    facts = load_facts("PR-CONTRADICTION", "any")
    assert facts is not None
    rec = evaluate(facts, _request("PR-CONTRADICTION"), REFUND_POLICY)
    assert rec.confidence == 0.3


def test_confidence_02_on_missing_data():
    facts = BillingFacts()
    rec = evaluate(facts, _request(), REFUND_POLICY)
    assert rec.confidence == 0.2


# ---------------------------------------------------------------------------
# Determinism — same inputs → same output (T024 — FR-012/SC-006)
# ---------------------------------------------------------------------------


def test_determinism_same_facts_same_output():
    """Evaluating the same (facts, request, policy) twice yields identical recommendations."""
    for ref in ("PR-APPROVE", "PR-WINDOW-EXPIRED", "PR-CONTRADICTION", "PR-BORDERLINE"):
        facts = load_facts(ref, "any")
        assert facts is not None
        req = _request(ref)
        rec1 = evaluate(facts, req, REFUND_POLICY)
        rec2 = evaluate(facts, req, REFUND_POLICY)
        assert rec1.recommendation == rec2.recommendation
        assert rec1.confidence == rec2.confidence
        assert rec1.requires_human_review == rec2.requires_human_review
        assert rec1.policy_references == rec2.policy_references
