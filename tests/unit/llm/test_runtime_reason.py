"""Test LLMRuntime.reason() happy path with stub provider."""

from __future__ import annotations

from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from agent_foundation.llm import (
    AssistiveRequest,
    AssistiveResult,
    ReasoningPath,
    RuntimeConfig,
    TaskKind,
    build_runtime,
)


class SampleResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    summary: str
    confidence: float = 0.5


def _make_request(
    grounding: dict | None = None,
    idem_key: str = "",
) -> AssistiveRequest:
    return AssistiveRequest(
        task_kind=TaskKind.classify,
        agent_id="test-agent",
        correlation_id=uuid4(),
        causation_id=uuid4(),
        instructions="Classify the ticket.",
        grounding_inputs=grounding or {"ticket_text": "I want a refund"},
        output_schema=SampleResult,
        idempotency_key=idem_key,
        fallback=lambda: SampleResult(summary="fallback", confidence=0.0),
    )


async def test_reason_returns_populated_result():
    """Build runtime with stub and verify reason() returns a schema-valid result."""
    cfg = RuntimeConfig(mode="stub")
    runtime = build_runtime(cfg)
    request = _make_request()
    result = await runtime.reason(request)

    assert isinstance(result, AssistiveResult)
    assert result.reasoning_path == ReasoningPath.model
    assert result.value is not None
    assert isinstance(result.value, SampleResult)
    assert isinstance(result.value.summary, str)
    assert len(result.value.summary) > 0
    assert result.latency_ms >= 0


async def test_reason_result_has_token_usage():
    """Stub provider returns synthetic token counts."""
    cfg = RuntimeConfig(mode="stub")
    runtime = build_runtime(cfg)
    request = _make_request()
    result = await runtime.reason(request)

    assert result.token_usage is not None
    assert result.token_usage.input_tokens > 0
    assert result.token_usage.output_tokens >= 0
    assert result.model_id == "stub"


async def test_different_grounding_yields_different_output():
    """Meaningfully different grounding should yield different stub output."""
    cfg = RuntimeConfig(mode="stub")
    runtime = build_runtime(cfg)

    req_a = _make_request(grounding={"ticket_text": "refund request for order ABC"})
    req_b = _make_request(grounding={"ticket_text": "billing inquiry for subscription XYZ"})

    result_a = await runtime.reason(req_a)
    result_b = await runtime.reason(req_b)

    assert result_a.value != result_b.value


async def test_reason_sets_prompt_ref():
    """Result should carry a non-empty prompt_ref string."""
    cfg = RuntimeConfig(mode="stub")
    runtime = build_runtime(cfg)
    request = _make_request()
    result = await runtime.reason(request)

    assert result.prompt_ref is not None
    assert len(result.prompt_ref) > 0
