"""Test fallback on provider failure."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from agent_foundation.llm import (
    AssistiveRequest,
    FailureReason,
    ReasoningPath,
    RuntimeConfig,
    TaskKind,
)
from agent_foundation.llm.providers.base import ProviderError
from agent_foundation.llm.runtime import LLMRuntime
from agent_foundation.llm.store import AssistiveResultStore


class SampleResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    summary: str
    confidence: float = 0.5


def _make_request() -> AssistiveRequest:
    return AssistiveRequest(
        task_kind=TaskKind.classify,
        agent_id="test-agent",
        correlation_id=uuid4(),
        causation_id=uuid4(),
        instructions="Classify the ticket.",
        grounding_inputs={"ticket_text": "I want a refund"},
        output_schema=SampleResult,
        fallback=lambda: SampleResult(summary="fallback-value", confidence=0.0),
    )


async def test_provider_error_triggers_fallback():
    """ProviderError should yield a fallback result with failure_reason set."""
    provider = AsyncMock()
    provider.invoke = AsyncMock(side_effect=ProviderError("Connection refused"))

    config = RuntimeConfig(mode="stub")
    runtime = LLMRuntime(
        provider=provider,
        store=AssistiveResultStore(),
        config=config,
    )

    result = await runtime.reason(_make_request())

    assert result.reasoning_path == ReasoningPath.fallback
    assert result.failure_reason == FailureReason.model_unavailable
    assert result.value.summary == "fallback-value"


async def test_fallback_reasoning_path_is_fallback():
    """Verify reasoning_path string value is 'fallback'."""
    provider = AsyncMock()
    provider.invoke = AsyncMock(side_effect=ProviderError("Boom"))

    config = RuntimeConfig(mode="stub")
    runtime = LLMRuntime(
        provider=provider,
        store=AssistiveResultStore(),
        config=config,
    )

    result = await runtime.reason(_make_request())
    assert str(result.reasoning_path) == "fallback"
    assert result.failure_reason is not None


async def test_generic_exception_triggers_fallback():
    """Unexpected exceptions should also produce a fallback result."""
    provider = AsyncMock()
    provider.invoke = AsyncMock(side_effect=RuntimeError("Unexpected failure"))

    config = RuntimeConfig(mode="stub")
    runtime = LLMRuntime(
        provider=provider,
        store=AssistiveResultStore(),
        config=config,
    )

    result = await runtime.reason(_make_request())
    assert result.reasoning_path == ReasoningPath.fallback
    assert result.failure_reason == FailureReason.model_unavailable
