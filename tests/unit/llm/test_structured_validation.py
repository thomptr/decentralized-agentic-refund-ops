"""Test structured output validation and repair loop."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

from pydantic import BaseModel, ConfigDict

from agent_foundation.llm.providers.base import RawCompletion
from agent_foundation.llm.result import TokenUsage
from agent_foundation.llm.structured import invoke_structured


class SampleResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    summary: str
    confidence: float = 0.5


async def test_valid_output_returns_schema_instance():
    """Valid JSON matching the schema should return ok=True with parsed value."""
    valid_json = json.dumps({"summary": "test summary", "confidence": 0.9})
    provider = AsyncMock()
    provider.invoke = AsyncMock(
        return_value=RawCompletion(
            text=valid_json,
            token_usage=TokenUsage(input_tokens=10, output_tokens=10),
            model_id="stub",
        )
    )

    outcome = await invoke_structured(
        "Test prompt",
        SampleResult,
        provider=provider,
        profile=object(),
        max_repairs=1,
    )

    assert outcome.ok is True
    assert isinstance(outcome.value, SampleResult)
    assert outcome.value.summary == "test summary"
    assert outcome.value.confidence == 0.9


async def test_invalid_json_retries_then_errors():
    """Invalid JSON should retry once, then produce a StructuredError."""
    provider = AsyncMock()
    provider.invoke = AsyncMock(
        return_value=RawCompletion(
            text="not json {{{{",
            token_usage=TokenUsage(input_tokens=10, output_tokens=5),
            model_id="stub",
        )
    )

    outcome = await invoke_structured(
        "Test prompt",
        SampleResult,
        provider=provider,
        profile=object(),
        max_repairs=1,
    )

    assert outcome.ok is False
    assert outcome.error is not None
    assert outcome.error.attempts == 2  # initial + 1 repair


async def test_retry_budget_is_one_repair():
    """With max_repairs=1, provider should be invoked exactly 2 times on persistent failure."""
    provider = AsyncMock()
    provider.invoke = AsyncMock(
        return_value=RawCompletion(
            text="garbage",
            token_usage=TokenUsage(input_tokens=10, output_tokens=5),
            model_id="stub",
        )
    )

    outcome = await invoke_structured(
        "Test prompt",
        SampleResult,
        provider=provider,
        profile=object(),
        max_repairs=1,
    )

    assert outcome.ok is False
    assert provider.invoke.call_count == 2


async def test_repair_succeeds_on_second_attempt():
    """If first attempt fails but second succeeds, outcome should be ok."""
    valid_json = json.dumps({"summary": "repaired output", "confidence": 0.7})
    provider = AsyncMock()
    provider.invoke = AsyncMock(
        side_effect=[
            RawCompletion(text="bad json", model_id="stub"),
            RawCompletion(text=valid_json, model_id="stub"),
        ]
    )

    outcome = await invoke_structured(
        "Test prompt",
        SampleResult,
        provider=provider,
        profile=object(),
        max_repairs=1,
    )

    assert outcome.ok is True
    assert outcome.value.summary == "repaired output"
