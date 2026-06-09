"""Unit tests for triage rules (T012, US1)."""

from __future__ import annotations

from apps.agents.customer_resolution.tests.conftest import make_non_refund_ticket, make_ticket
from apps.agents.customer_resolution.ticket_classifier import classify


def test_refund_signal_hit():
    ticket = make_ticket(reason="I was charged twice please refund")
    triage = classify(ticket)
    assert triage.needs_refund_review is True
    assert triage.ambiguous is False
    assert len(triage.matched_signals) > 0


def test_clear_non_refund():
    ticket = make_non_refund_ticket()
    triage = classify(ticket)
    assert triage.needs_refund_review is False
    assert triage.ambiguous is False
    assert triage.matched_signals == []


def test_empty_reason_defaults_to_review():
    ticket = make_ticket(reason="")
    triage = classify(ticket)
    assert triage.needs_refund_review is True
    assert triage.ambiguous is True


def test_ambiguous_short_reason_defaults_to_review():
    ticket = make_ticket(reason="???")
    triage = classify(ticket)
    assert triage.needs_refund_review is True
    assert triage.ambiguous is True


def test_chargeback_signal():
    ticket = make_ticket(reason="I want to file a chargeback for this order")
    triage = classify(ticket)
    assert triage.needs_refund_review is True
    assert "chargeback" in triage.matched_signals


def test_rationale_always_present():
    for reason in ("refund please", "how do I change email", ""):
        ticket = make_ticket(reason=reason)
        triage = classify(ticket)
        assert triage.rationale


def test_case_insensitive_matching():
    ticket = make_ticket(reason="REFUND MY MONEY")
    triage = classify(ticket)
    assert triage.needs_refund_review is True


def test_multiple_signals_all_recorded():
    ticket = make_ticket(reason="I was charged and I want a refund and a reimbursement")
    triage = classify(ticket)
    assert len(triage.matched_signals) >= 2
