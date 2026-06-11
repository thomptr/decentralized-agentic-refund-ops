"""Test LangGraph node adapter."""

from __future__ import annotations

from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from agent_foundation.llm import (
    RuntimeConfig,
    build_runtime,
)
from agent_foundation.llm.langgraph import as_node


class SampleResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    summary: str
    confidence: float = 0.5


async def test_structured_call_returns_schema_in_state():
    """Structured call with output_schema returns schema instance in state."""
    cfg = RuntimeConfig(mode="stub")
    runtime = build_runtime(cfg)

    node = as_node(
        runtime,
        agent_id="test-agent",
        task_kind="classify",
        output_schema=SampleResult,
        instructions="Classify the ticket.",
        fallback=lambda: SampleResult(summary="fallback", confidence=0.0),
        state_key="llm_result",
    )

    cid = uuid4()
    state = {
        "correlation_id": str(cid),
        "causation_id": str(cid),
        "ticket_text": "I want a refund",
    }

    result_state = await node(state)
    assert "llm_result" in result_state
    assert "llm_result_reasoning_path" in result_state
    assert result_state["llm_result"] is not None


async def test_unstructured_call_returns_text_result():
    """Unstructured call with output_schema=None returns TextResult."""
    cfg = RuntimeConfig(mode="stub")
    runtime = build_runtime(cfg)

    node = as_node(
        runtime,
        agent_id="test-agent",
        task_kind="summarize_reasoning",
        output_schema=None,
        instructions="Summarize the reasoning.",
        state_key="llm_result",
    )

    cid = uuid4()
    state = {
        "correlation_id": str(cid),
        "causation_id": str(cid),
        "reasoning": "The customer was overcharged.",
    }

    result_state = await node(state)
    assert "llm_result" in result_state


async def test_trace_metadata_preserved_in_state():
    """correlation_id and causation_id should be preserved in output state."""
    cfg = RuntimeConfig(mode="stub")
    runtime = build_runtime(cfg)

    node = as_node(
        runtime,
        agent_id="test-agent",
        task_kind="classify",
        output_schema=SampleResult,
        instructions="Classify.",
        fallback=lambda: SampleResult(summary="fb", confidence=0.0),
    )

    cid = uuid4()
    causation = uuid4()
    state = {
        "correlation_id": str(cid),
        "causation_id": str(causation),
        "data": "test",
    }

    result_state = await node(state)
    assert result_state["correlation_id"] == str(cid)
    assert result_state["causation_id"] == str(causation)
