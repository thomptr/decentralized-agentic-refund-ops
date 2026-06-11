"""Test draft failure triggers templated fallback with requires_human_approval (Phase 008)."""

from __future__ import annotations

from unittest.mock import AsyncMock

from agent_foundation.llm import (
    RuntimeConfig,
)
from agent_foundation.llm.providers.base import ProviderError
from agent_foundation.llm.runtime import LLMRuntime
from agent_foundation.llm.store import AssistiveResultStore
from apps.agents.customer_resolution.response_drafter import (
    AllowedFacts,
    ResponseDraft,
    ToneConfig,
    draft_structured_response,
    draft_with_llm,
)
from packages.contracts.events.payloads import ResolutionOutcome


def _allowed_facts() -> AllowedFacts:
    return AllowedFacts(
        refund_amount=49.99,
        currency="USD",
        order_reference="TKT-001",
        billing_outcome_summary="Eligible for refund",
        eligibility=True,
    )


def _failing_runtime():
    provider = AsyncMock()
    provider.invoke = AsyncMock(side_effect=ProviderError("Service unavailable"))
    config = RuntimeConfig(mode="stub")
    return LLMRuntime(
        provider=provider,
        store=AssistiveResultStore(),
        config=config,
    )


async def test_draft_with_llm_fallback_on_provider_error():
    """When provider fails, draft_with_llm falls back to templated draft."""
    runtime = _failing_runtime()

    draft = await draft_with_llm(
        ResolutionOutcome.APPROVE_REFUND,
        _allowed_facts(),
        ToneConfig(),
        runtime,
        ticket_summary="Customer wants refund",
    )

    assert isinstance(draft, ResponseDraft)
    # Fallback forces human approval
    assert draft.requires_human_approval is True
    assert len(draft.body) > 0
    assert len(draft.subject) > 0


async def test_draft_with_llm_fallback_on_generic_exception():
    """Unexpected exception triggers templated fallback with human approval."""
    provider = AsyncMock()
    provider.invoke = AsyncMock(side_effect=RuntimeError("Unexpected"))
    config = RuntimeConfig(mode="stub")
    runtime = LLMRuntime(
        provider=provider,
        store=AssistiveResultStore(),
        config=config,
    )

    draft = await draft_with_llm(
        ResolutionOutcome.DENY_REFUND,
        _allowed_facts(),
        ToneConfig(),
        runtime,
        ticket_summary="Test",
    )

    assert isinstance(draft, ResponseDraft)
    assert draft.requires_human_approval is True


async def test_draft_with_llm_fallback_matches_deterministic():
    """Fallback draft body matches deterministic draft_structured_response output."""
    runtime = _failing_runtime()
    facts = _allowed_facts()
    tone = ToneConfig()
    outcome = ResolutionOutcome.APPROVE_REFUND

    draft = await draft_with_llm(
        outcome, facts, tone, runtime, ticket_summary="test"
    )
    det_draft = draft_structured_response("test", outcome, facts, tone)

    # Body content should match the deterministic template
    assert isinstance(draft, ResponseDraft)
    assert det_draft.body in draft.body or draft.body == det_draft.body


async def test_draft_with_llm_fallback_for_each_outcome():
    """Every ResolutionOutcome produces a valid draft on fallback."""
    runtime = _failing_runtime()
    facts = _allowed_facts()

    for outcome in ResolutionOutcome:
        draft = await draft_with_llm(
            outcome, facts, ToneConfig(), runtime, ticket_summary="test"
        )
        assert isinstance(draft, ResponseDraft)
        assert draft.requires_human_approval is True
        assert len(draft.body) > 0