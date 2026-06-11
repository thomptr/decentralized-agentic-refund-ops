"""Test classify failure triggers deterministic fallback (Phase 008)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

from agent_foundation.llm import (
    RuntimeConfig,
)
from agent_foundation.llm.providers.base import ProviderError
from agent_foundation.llm.runtime import LLMRuntime
from agent_foundation.llm.store import AssistiveResultStore
from apps.agents.customer_resolution.models import Triage
from apps.agents.customer_resolution.ticket_classifier import (
    classify,
    classify_with_llm,
)
from packages.contracts.events.payloads import SupportTicketCreatedPayload


def _make_ticket(reason: str = "I was charged twice") -> SupportTicketCreatedPayload:
    return SupportTicketCreatedPayload(
        ticket_id="TKT-FALLBACK-001",
        customer_id="CUS-001",
        amount=49.99,
        currency="USD",
        reason=reason,
        created_at=datetime.now(UTC),
    )


def _failing_runtime():
    """Build a runtime with a provider that always fails."""
    provider = AsyncMock()
    provider.invoke = AsyncMock(side_effect=ProviderError("Service unavailable"))
    config = RuntimeConfig(mode="stub")
    return LLMRuntime(
        provider=provider,
        store=AssistiveResultStore(),
        config=config,
    )


async def test_classify_with_llm_fallback_on_provider_error():
    """When provider fails, classify_with_llm falls back to deterministic classify."""
    runtime = _failing_runtime()
    ticket = _make_ticket()

    triage = await classify_with_llm(ticket, runtime)

    assert isinstance(triage, Triage)
    # Should match deterministic classify output
    det_triage = classify(ticket)
    assert triage.needs_refund_review == det_triage.needs_refund_review
    assert triage.issue_type == det_triage.issue_type


async def test_classify_with_llm_fallback_on_generic_exception():
    """Unexpected exception triggers deterministic fallback."""
    provider = AsyncMock()
    provider.invoke = AsyncMock(side_effect=RuntimeError("Unexpected"))
    config = RuntimeConfig(mode="stub")
    runtime = LLMRuntime(
        provider=provider,
        store=AssistiveResultStore(),
        config=config,
    )
    ticket = _make_ticket()

    triage = await classify_with_llm(ticket, runtime)

    assert isinstance(triage, Triage)
    det_triage = classify(ticket)
    assert triage.needs_refund_review == det_triage.needs_refund_review


async def test_classify_with_llm_fallback_preserves_binding_fields():
    """Fallback triage matches deterministic classify for binding fields.

    The LLM is assistive -- binding verdicts stay deterministic (FR-015).
    """
    runtime = _failing_runtime()
    ticket = _make_ticket("I want a refund")
    det_triage = classify(ticket)

    triage = await classify_with_llm(ticket, runtime)

    assert triage.needs_refund_review == det_triage.needs_refund_review
    assert triage.issue_type == det_triage.issue_type
    assert triage.confidence == det_triage.confidence


async def test_classify_with_llm_non_refund_ticket_fallback():
    """Non-refund ticket fallback produces correct non-refund Triage."""
    runtime = _failing_runtime()
    ticket = _make_ticket("How do I change my password?")

    triage = await classify_with_llm(ticket, runtime)

    assert isinstance(triage, Triage)
    det_triage = classify(ticket)
    assert triage.needs_refund_review == det_triage.needs_refund_review
