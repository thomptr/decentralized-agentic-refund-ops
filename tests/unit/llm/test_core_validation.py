"""Test validation rejects bad output and triggers fallback."""

from __future__ import annotations

import json
from enum import StrEnum
from unittest.mock import AsyncMock
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from agent_foundation.llm import (
    AssistiveRequest,
    ReasoningPath,
    RuntimeConfig,
    TaskKind,
)
from agent_foundation.llm.providers.base import RawCompletion
from agent_foundation.llm.result import TokenUsage
from agent_foundation.llm.runtime import LLMRuntime
from agent_foundation.llm.store import AssistiveResultStore


class Category(StrEnum):
    billing = "billing"
    shipping = "shipping"
    other = "other"


class CategorizedResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    category: Category
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
        output_schema=CategorizedResult,
        fallback=lambda: CategorizedResult(
            category=Category.other, summary="fallback", confidence=0.0
        ),
    )


async def test_out_of_enum_causes_fallback():
    """When model returns an out-of-enum value, the runtime should fall back."""
    bad_output = json.dumps(
        {
            "category": "INVALID_CATEGORY",
            "summary": "some text",
            "confidence": 0.9,
        }
    )
    provider = AsyncMock()
    provider.invoke = AsyncMock(
        return_value=RawCompletion(
            text=bad_output,
            token_usage=TokenUsage(input_tokens=10, output_tokens=10),
            model_id="stub",
        )
    )

    config = RuntimeConfig(mode="stub")
    runtime = LLMRuntime(
        provider=provider,
        store=AssistiveResultStore(),
        config=config,
    )

    result = await runtime.reason(_make_request())
    assert result.reasoning_path == ReasoningPath.fallback
    assert result.value.category == Category.other


async def test_malformed_json_causes_fallback():
    """When model returns non-JSON, the runtime should fall back."""
    provider = AsyncMock()
    provider.invoke = AsyncMock(
        return_value=RawCompletion(
            text="This is not JSON at all {{{",
            token_usage=TokenUsage(input_tokens=10, output_tokens=5),
            model_id="stub",
        )
    )

    config = RuntimeConfig(mode="stub")
    runtime = LLMRuntime(
        provider=provider,
        store=AssistiveResultStore(),
        config=config,
    )

    result = await runtime.reason(_make_request())
    assert result.reasoning_path == ReasoningPath.fallback
    assert result.value.summary == "fallback"
