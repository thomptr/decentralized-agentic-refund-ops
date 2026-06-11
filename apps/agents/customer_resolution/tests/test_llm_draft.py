"""Test LLM-assisted draft rejects out-of-facts content (Phase 008)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from agent_foundation.llm import (
    AssistiveResult,
    ReasoningPath,
    RuntimeConfig,
    build_runtime,
)
from apps.agents.customer_resolution.response_drafter import (
    AllowedFacts,
    ResponseDraft,
    ToneConfig,
    _assert_no_internal_leak,
    draft_structured_response,
    draft_with_llm,
)
from packages.contracts.events.payloads import ResolutionOutcome


def _stub_runtime():
    cfg = RuntimeConfig(mode="stub")
    return build_runtime(cfg)


def _allowed_facts(**kwargs) -> AllowedFacts:
    defaults = {
        "refund_amount": 49.99,
        "currency": "USD",
        "order_reference": "TKT-001",
        "billing_outcome_summary": "Eligible for refund",
        "eligibility": True,
    }
    defaults.update(kwargs)
    return AllowedFacts(**defaults)


async def test_draft_with_llm_returns_response_draft():
    """draft_with_llm returns a ResponseDraft from the stub."""
    runtime = _stub_runtime()
    facts = _allowed_facts()

    draft = await draft_with_llm(
        ResolutionOutcome.APPROVE_REFUND,
        facts,
        ToneConfig(),
        runtime,
        correlation_id=uuid4(),
        causation_id=uuid4(),
        ticket_summary="Customer requested refund for double charge",
    )

    assert isinstance(draft, ResponseDraft)
    assert isinstance(draft.subject, str)
    assert isinstance(draft.body, str)
    assert len(draft.body) > 0


async def test_draft_with_llm_grounding_rejects_internal_leak():
    """Draft body containing internal fields triggers fallback with human approval."""
    # Create a mock runtime that produces a draft with leaked internal field
    mock_runtime = MagicMock()

    leaked_draft = ResponseDraft(
        subject="Your request",
        body="Based on our rationale analysis, your escalation_reason was reviewed",
        response_type="refund_confirmation",
        requires_human_approval=False,
    )
    mock_result = AssistiveResult(
        value=leaked_draft,
        reasoning_path=ReasoningPath.model,
    )
    mock_runtime.reason = AsyncMock(return_value=mock_result)

    facts = _allowed_facts()
    draft = await draft_with_llm(
        ResolutionOutcome.APPROVE_REFUND,
        facts,
        ToneConfig(),
        mock_runtime,
        ticket_summary="test",
    )

    # Should have fallen back and forced human approval
    assert draft.requires_human_approval is True


async def test_draft_with_llm_internal_leak_detection():
    """_assert_no_internal_leak raises on internal field names in body text."""
    safe_text = "We are happy to help with your refund request."
    _assert_no_internal_leak(safe_text)  # Should not raise

    with pytest.raises(ValueError, match="Internal field"):
        _assert_no_internal_leak("Here is the rationale for our decision")

    with pytest.raises(ValueError, match="Internal field"):
        _assert_no_internal_leak("The escalation_reason was clear")

    with pytest.raises(ValueError, match="Internal field"):
        _assert_no_internal_leak("billing_summary shows eligible")


async def test_draft_with_llm_fraud_field_leak_detection():
    """Fraud-scoring fields in body text are rejected."""
    with pytest.raises(ValueError, match="Fraud-scoring field"):
        _assert_no_internal_leak("Your risk_level is low")

    with pytest.raises(ValueError, match="Fraud-scoring field"):
        _assert_no_internal_leak("The confidence was 0.95")

    with pytest.raises(ValueError, match="Fraud-scoring field"):
        _assert_no_internal_leak("Based on evidence collected")


async def test_draft_structured_response_no_leak():
    """The deterministic drafter itself never leaks internal fields."""
    facts = _allowed_facts()
    for outcome in ResolutionOutcome:
        draft = draft_structured_response("test summary", outcome, facts)
        # Should not raise
        _assert_no_internal_leak(draft.body)