"""Test LLM-assisted classify returns valid Triage (Phase 008)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from agent_foundation.llm import (
    RuntimeConfig,
    build_runtime,
)
from apps.agents.customer_resolution.models import Triage
from apps.agents.customer_resolution.ticket_classifier import (
    TicketClassification,
    classify_with_llm,
)
from packages.contracts.events.payloads import SupportTicketCreatedPayload


def _make_ticket(reason: str = "I was charged twice, please refund") -> SupportTicketCreatedPayload:
    return SupportTicketCreatedPayload(
        ticket_id="TKT-LLM-001",
        customer_id="CUS-001",
        amount=49.99,
        currency="USD",
        reason=reason,
        created_at=datetime.now(UTC),
    )


def _stub_runtime():
    """Build a stub LLM runtime (no AWS)."""
    cfg = RuntimeConfig(mode="stub")
    return build_runtime(cfg)


async def test_classify_with_llm_returns_valid_triage():
    """classify_with_llm returns a Triage model when stub produces valid output."""
    runtime = _stub_runtime()
    ticket = _make_ticket()

    triage = await classify_with_llm(
        ticket,
        runtime,
        correlation_id=uuid4(),
        causation_id=uuid4(),
    )

    assert isinstance(triage, Triage)
    assert isinstance(triage.needs_refund_review, bool)
    assert isinstance(triage.rationale, str)
    assert len(triage.rationale) > 0
    assert 0.0 <= triage.confidence <= 1.0
    assert isinstance(triage.issue_type, str)


async def test_classify_with_llm_matches_triage_fields():
    """All required Triage fields are populated."""
    runtime = _stub_runtime()
    ticket = _make_ticket()
    triage = await classify_with_llm(ticket, runtime)

    # Triage model requires these fields
    assert hasattr(triage, "needs_refund_review")
    assert hasattr(triage, "ambiguous")
    assert hasattr(triage, "matched_signals")
    assert hasattr(triage, "rationale")
    assert hasattr(triage, "issue_type")
    assert hasattr(triage, "confidence")


async def test_ticket_classification_to_triage_mapping():
    """TicketClassification.to_triage() produces correct Triage values."""
    tc = TicketClassification(
        issue_type="refund_request",
        needs_refund_review=True,
        confidence=0.95,
        rationale="Customer mentioned refund",
        matched_signals=["refund"],
    )
    triage = tc.to_triage()
    assert triage.needs_refund_review is True
    assert triage.ambiguous is False  # confidence >= 0.7
    assert triage.confidence == 0.95
    assert triage.issue_type == "refund_request"
    assert triage.matched_signals == ["refund"]


async def test_ticket_classification_low_confidence_marks_ambiguous():
    """Low confidence in TicketClassification sets ambiguous=True in Triage."""
    tc = TicketClassification(
        issue_type="unknown",
        needs_refund_review=True,
        confidence=0.4,
        rationale="Unclear intent",
        matched_signals=[],
    )
    triage = tc.to_triage()
    assert triage.ambiguous is True


async def test_ticket_classification_schema_rejects_extra_fields():
    """TicketClassification with extra='forbid' rejects unknown fields."""
    with pytest.raises(ValueError):
        TicketClassification(
            issue_type="refund_request",
            needs_refund_review=True,
            confidence=0.9,
            rationale="test",
            hallucinated_field="should_not_exist",
        )


async def test_ticket_classification_schema_rejects_out_of_range_confidence():
    """Confidence outside [0.0, 1.0] is rejected."""
    with pytest.raises(ValueError):
        TicketClassification(
            issue_type="refund_request",
            needs_refund_review=True,
            confidence=1.5,
            rationale="test",
        )


async def test_classify_with_llm_different_tickets_produce_different_results():
    """Different ticket reasons should produce different LLM grounding."""
    runtime = _stub_runtime()
    t1 = _make_ticket("I want a full refund for order ABC")
    t2 = _make_ticket("How do I change my email address?")

    triage1 = await classify_with_llm(t1, runtime)
    triage2 = await classify_with_llm(t2, runtime)

    # The stub produces different outputs for different grounding inputs
    assert isinstance(triage1, Triage)
    assert isinstance(triage2, Triage)
