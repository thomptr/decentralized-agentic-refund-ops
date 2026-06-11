"""Test LLMUsage token tracking and cost estimation."""

from __future__ import annotations

from decimal import Decimal

from agent_foundation.llm import LLMUsage, TokenUsage, build_llm_usage


async def test_build_llm_usage_full():
    """build_llm_usage with full TokenUsage populates total_tokens and estimated_cost_usd."""
    usage = TokenUsage(input_tokens=100, output_tokens=50)
    result = build_llm_usage(usage, model_id="stub", agent_id="test-agent")

    assert result.input_tokens == 100
    assert result.output_tokens == 50
    assert result.total_tokens == 150
    assert result.estimated_cost_usd is not None
    assert result.estimated_cost_usd == Decimal("0")


async def test_build_llm_usage_missing_tokens():
    """Missing/partial usage yields None tokens/cost without exception."""
    result = build_llm_usage(None, model_id="stub", agent_id="test-agent")

    assert result.input_tokens is None
    assert result.output_tokens is None
    assert result.total_tokens is None
    assert result.estimated_cost_usd is None


async def test_build_llm_usage_zero_tokens():
    """TokenUsage with zero tokens yields None tokens due to falsy check."""
    usage = TokenUsage(input_tokens=0, output_tokens=0)
    result = build_llm_usage(usage, model_id="stub", agent_id="test-agent")

    assert result.input_tokens is None
    assert result.output_tokens is None


async def test_llm_usage_round_trips_json():
    """LLMUsage round-trips through model_dump_json/model_validate_json."""
    usage = TokenUsage(input_tokens=200, output_tokens=100)
    original = build_llm_usage(
        usage, model_id="anthropic.claude-3-5-sonnet-20241022-v2:0", agent_id="cra"
    )

    json_str = original.model_dump_json()
    restored = LLMUsage.model_validate_json(json_str)

    assert restored.input_tokens == original.input_tokens
    assert restored.output_tokens == original.output_tokens
    assert restored.total_tokens == original.total_tokens
    assert restored.model_id == original.model_id
    assert restored.agent_id == original.agent_id
