"""Mock-data lookup tests (T018 — FR-003/FR-010)."""

from __future__ import annotations

from apps.agents.billing_entitlement.mock_data import load_facts


def test_pr_approve_resolves():
    facts = load_facts("PR-APPROVE", "CUS-001")
    assert facts is not None
    assert facts.invoice is not None
    assert facts.invoice.paid is True
    assert facts.payment is not None
    assert facts.payment.reversed_amount == 0.0


def test_pr_window_expired_resolves():
    facts = load_facts("PR-WINDOW-EXPIRED", "any")
    assert facts is not None
    assert facts.invoice is not None


def test_pr_unpaid_resolves():
    facts = load_facts("PR-UNPAID", "any")
    assert facts is not None
    assert facts.invoice is not None
    assert facts.invoice.paid is False


def test_pr_already_refunded_resolves():
    facts = load_facts("PR-ALREADY-REFUNDED", "any")
    assert facts is not None
    assert facts.payment is not None
    assert facts.payment.reversed_amount >= facts.payment.amount


def test_pr_heavy_usage_resolves():
    facts = load_facts("PR-HEAVY-USAGE", "any")
    assert facts is not None
    assert facts.usage is not None
    assert facts.usage.usage_ratio > 0.8


def test_pr_contradiction_resolves():
    facts = load_facts("PR-CONTRADICTION", "any")
    assert facts is not None
    assert facts.subscription is not None
    assert facts.subscription.status == "cancelled"
    assert facts.entitlement is not None
    assert facts.entitlement.status == "active"


def test_pr_borderline_resolves():
    facts = load_facts("PR-BORDERLINE", "any")
    assert facts is not None
    assert facts.usage is not None
    assert abs(facts.usage.usage_ratio - 0.80) < 1e-9


def test_unknown_reference_returns_none():
    facts = load_facts("PR-UNKNOWN-XYZ-DOESNOTEXIST", "UNKNOWN-CUS")
    assert facts is None


def test_customer_id_fallback():
    facts = load_facts("PR-NONEXISTENT", "CUS-APPROVE")
    assert facts is not None


def test_unknown_customer_returns_none():
    facts = load_facts("PR-NONEXISTENT", "CUS-NOBODY")
    assert facts is None
