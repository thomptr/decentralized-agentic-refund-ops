"""Entitlement checker tests — four-signal matrix, mismatch detection, evidence (T053/US3/US4)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from apps.agents.billing_entitlement.entitlement_checker import (
    build_entitlement_evidence,
    check_entitlement,
)
from apps.agents.billing_entitlement.mock_data import load_facts
from apps.agents.billing_entitlement.models import (
    BillingFacts,
    Entitlement,
    Recommendation,
    RefundEligibilityRequest,
    Subscription,
)
from apps.agents.billing_entitlement.policy import REFUND_POLICY
from apps.agents.billing_entitlement.rules_engine import evaluate


def _sub(status: str = "active") -> Subscription:
    now = datetime.now(UTC)
    return Subscription(
        subscription_id="SUB-1",
        status=status,  # type: ignore[arg-type]
        term="monthly",
        started_at=now - timedelta(days=90),
    )


def _ent(
    *,
    status: str = "active",
    delivered: bool = False,
    access_granted: bool = True,
    access_used: bool = False,
    feature_enabled: bool = True,
    account_active: bool = True,
) -> Entitlement:
    return Entitlement(
        entitlement_id="ENT-1",
        subscription_id="SUB-1",
        status=status,  # type: ignore[arg-type]
        delivered=delivered,
        access_granted=access_granted,
        access_used=access_used,
        feature_enabled=feature_enabled,
        account_active=account_active,
    )


def _facts(entitlement: Entitlement | None, sub_status: str = "active") -> BillingFacts:
    return BillingFacts(subscription=_sub(sub_status), entitlement=entitlement)


# ---------------------------------------------------------------------------
# Deterministic four-signal matrix (no clock, no random — FR-012)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("run", [1, 2])
def test_normal_granted_not_used(run: int):
    facts = _facts(_ent(access_granted=True, access_used=False))
    check = check_entitlement(facts)
    assert check.granted is True
    assert check.used is False
    assert check.mismatch is False


@pytest.mark.parametrize("run", [1, 2])
def test_normal_granted_and_used(run: int):
    facts = _facts(_ent(access_granted=True, access_used=True, delivered=True))
    check = check_entitlement(facts)
    assert check.granted is True
    assert check.used is True
    assert check.mismatch is False


@pytest.mark.parametrize("run", [1, 2])
def test_not_granted_not_used(run: int):
    facts = _facts(_ent(access_granted=False, access_used=False))
    check = check_entitlement(facts)
    assert check.granted is False
    assert check.used is False
    assert check.mismatch is False


# ---------------------------------------------------------------------------
# Mismatch detection (acceptance criteria 1 — T053/T055)
# ---------------------------------------------------------------------------

def test_mismatch_not_granted_but_used():
    """access_granted=False yet access_used=True → mismatch."""
    facts = _facts(_ent(access_granted=False, access_used=True))
    check = check_entitlement(facts)
    assert check.mismatch is True
    assert "access_granted=False" in check.summary
    assert "access_used=True" in check.summary


def test_mismatch_account_active_on_cancelled_sub():
    """account_active=True on a cancelled subscription → mismatch."""
    facts = _facts(_ent(account_active=True), sub_status="cancelled")
    check = check_entitlement(facts)
    assert check.mismatch is True
    assert "cancelled" in check.summary


def test_mismatch_revoked_with_feature_enabled():
    """status='revoked' while feature_enabled=True → mismatch."""
    facts = _facts(_ent(status="revoked", feature_enabled=True))
    check = check_entitlement(facts)
    assert check.mismatch is True
    assert "revoked" in check.summary


def test_mismatch_leads_to_manual_review_in_rules_engine():
    """Acceptance criterion 1: entitlement mismatch → manual_review, confidence≈0.3 (T055)."""
    facts = load_facts("PR-CONTRADICTION", "any")
    assert facts is not None
    req = RefundEligibilityRequest(
        case_id=uuid.uuid4(),
        ticket_id="TKT-001",
        customer_id="CUS-001",
        requested_refund_amount=49.99,
        purchase_reference="PR-CONTRADICTION",
    )
    rec = evaluate(facts, req, REFUND_POLICY)
    assert rec.recommendation == Recommendation.MANUAL_REVIEW
    assert rec.confidence == 0.3
    assert rec.requires_human_review is True


# ---------------------------------------------------------------------------
# No / absent entitlement → approve-supporting (acceptance criteria 2)
# ---------------------------------------------------------------------------

def test_no_entitlement_check_returns_no_mismatch():
    facts = _facts(None)
    check = check_entitlement(facts)
    assert check.mismatch is False
    assert check.granted is False
    assert check.used is False


# ---------------------------------------------------------------------------
# Active access + high usage (acceptance criteria 3)
# ---------------------------------------------------------------------------

def test_high_usage_with_active_access_via_mock():
    """PR-HEAVY-USAGE: active access + high usage → deny_refund (RP-003 + RP-004)."""
    facts = load_facts("PR-HEAVY-USAGE", "any")
    assert facts is not None
    assert facts.entitlement is not None
    check = check_entitlement(facts)
    assert check.mismatch is False
    assert check.used is True


# ---------------------------------------------------------------------------
# Evidence item format (source='entitlement', never raw internals)
# ---------------------------------------------------------------------------

def test_evidence_source_is_entitlement():
    facts = _facts(_ent())
    check = check_entitlement(facts)
    ev = build_entitlement_evidence(check)
    assert ev.source == "entitlement"


def test_evidence_description_is_concise_summary():
    facts = _facts(_ent())
    check = check_entitlement(facts)
    ev = build_entitlement_evidence(check)
    assert len(ev.description) > 0
    # Must not contain raw internal field names that aren't meaningful to consumers
    assert "subscription_id" not in ev.description.lower()
    assert "entitlement_id" not in ev.description.lower()


def test_evidence_value_contains_boolean_signals():
    facts = _facts(_ent(access_granted=True, access_used=False, feature_enabled=True, account_active=True))
    check = check_entitlement(facts)
    ev = build_entitlement_evidence(check)
    assert isinstance(ev.value, dict)
    assert "granted" in ev.value
    assert "used" in ev.value
    assert "mismatch" in ev.value
