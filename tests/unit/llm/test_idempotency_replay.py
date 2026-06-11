"""Test idempotent replay - same request twice returns cached result."""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from agent_foundation.llm import (
    AssistiveRequest,
    ReasoningPath,
    RuntimeConfig,
    TaskKind,
    build_runtime,
)


class SampleResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    summary: str
    confidence: float = 0.5


def _make_request(idem_key: str = "test-idem-key-001") -> AssistiveRequest:
    cid = uuid4()
    return AssistiveRequest(
        task_kind=TaskKind.classify,
        agent_id="test-agent",
        correlation_id=cid,
        causation_id=cid,
        instructions="Classify the ticket.",
        grounding_inputs={"ticket_text": "I want a refund"},
        output_schema=SampleResult,
        idempotency_key=idem_key,
        fallback=lambda: SampleResult(summary="fallback", confidence=0.0),
    )


def _dump_value(value):
    """Normalize a result value to a dict for comparison."""
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return value
    return {"raw": value}


async def test_replay_returns_identical_output():
    """Same request twice should yield identical value from cache."""
    cfg = RuntimeConfig(mode="stub")
    runtime = build_runtime(cfg)
    request = _make_request()

    result1 = await runtime.reason(request)
    result2 = await runtime.reason(request)

    # The cached value may be deserialized as a dict rather than a SampleResult,
    # so compare the normalized dict form.
    assert _dump_value(result1.value) == _dump_value(result2.value)


async def test_replay_has_cache_reasoning_path():
    """Second call should have reasoning_path == cache."""
    cfg = RuntimeConfig(mode="stub")
    runtime = build_runtime(cfg)
    request = _make_request()

    await runtime.reason(request)
    result2 = await runtime.reason(request)

    assert result2.reasoning_path == ReasoningPath.cache


async def test_provider_invoked_only_once():
    """Provider.invoke should only be called on the first request."""
    cfg = RuntimeConfig(mode="stub")
    runtime = build_runtime(cfg)

    with patch.object(runtime._provider, "invoke", wraps=runtime._provider.invoke) as mock_invoke:
        request = _make_request(idem_key="unique-once-key")
        await runtime.reason(request)
        await runtime.reason(request)

        assert mock_invoke.call_count == 1
