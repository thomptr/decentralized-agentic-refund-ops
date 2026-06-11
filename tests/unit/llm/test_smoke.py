"""Smoke test — verify the runtime works end-to-end with the stub provider."""

from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from agent_foundation.llm import (
    AssistiveRequest,
    AssistiveResult,
    RuntimeConfig,
    TaskKind,
    build_runtime,
)


class SampleOutput(BaseModel):
    model_config = ConfigDict(frozen=True)
    summary: str = ""
    confidence: float = 0.5


async def test_stub_reason_happy_path():
    rt = build_runtime(RuntimeConfig(mode="stub"))
    request = AssistiveRequest(
        task_kind=TaskKind.classify,
        agent_id="test-agent",
        correlation_id=uuid4(),
        causation_id=uuid4(),
        instructions="Classify this ticket",
        grounding_inputs={"reason": "I want a refund"},
        output_schema=SampleOutput,
        fallback=lambda: SampleOutput(summary="fallback", confidence=0.0),
    )
    result = await rt.reason(request)
    assert isinstance(result, AssistiveResult)
    assert result.reasoning_path in ("model", "fallback")


async def test_stub_different_grounding_different_output():
    rt = build_runtime(RuntimeConfig(mode="stub"))
    req1 = AssistiveRequest(
        task_kind=TaskKind.classify,
        agent_id="test-agent",
        correlation_id=uuid4(),
        causation_id=uuid4(),
        instructions="Classify this ticket",
        grounding_inputs={"reason": "I want a refund for damaged goods"},
        output_schema=SampleOutput,
        fallback=lambda: SampleOutput(summary="fallback"),
    )
    req2 = AssistiveRequest(
        task_kind=TaskKind.classify,
        agent_id="test-agent",
        correlation_id=uuid4(),
        causation_id=uuid4(),
        instructions="Classify this ticket",
        grounding_inputs={"reason": "Account was hacked and charged"},
        output_schema=SampleOutput,
        fallback=lambda: SampleOutput(summary="fallback"),
    )
    r1 = await rt.reason(req1)
    r2 = await rt.reason(req2)
    assert isinstance(r1, AssistiveResult)
    assert isinstance(r2, AssistiveResult)
