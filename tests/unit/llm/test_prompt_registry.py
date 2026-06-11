"""Test prompt templates and registry."""

from __future__ import annotations

import pytest

from agent_foundation.llm import PromptRegistry, PromptTemplate


async def test_all_four_templates_load():
    """All four prompt templates should load from packages/llm-runtime/prompts/."""
    registry = PromptRegistry()
    registry.load()
    templates = registry.templates
    assert len(templates) >= 4


async def test_resolve_returns_expected_prompt_id():
    """resolve returns the template with the matching prompt_id."""
    registry = PromptRegistry()
    registry.load()

    classify_template = registry.resolve("classify", "customer-resolution-agent")
    assert classify_template.prompt_id == "customer_ticket_classification"

    draft_template = registry.resolve("draft_response", "customer-resolution-agent")
    assert draft_template.prompt_id == "customer_response_drafting"


async def test_billing_risk_templates_disallow_recommendation():
    """Billing/risk templates disallow final recommendation."""
    registry = PromptRegistry()
    registry.load()

    billing = registry.resolve("summarize_reasoning", "billing-entitlement-agent")
    assert billing.allows_final_recommendation is False

    risk = registry.resolve("summarize_reasoning", "risk-fraud-agent")
    assert risk.allows_final_recommendation is False


async def test_registry_rejects_summarize_with_recommendation():
    """Registry rejects summarize_reasoning with recommendation."""
    registry = PromptRegistry()

    bad_template = PromptTemplate(
        prompt_id="bad_template",
        version=1,
        task_kind="summarize_reasoning",
        agent_id="test-agent",
        allows_final_recommendation=True,
        body="You are a test.",
    )

    with pytest.raises(ValueError, match="allows_final_recommendation"):
        registry._register(bad_template)
