"""Test offline default -- stub requires no cloud access."""

from __future__ import annotations

import os
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
from agent_foundation.llm.config import reset_yaml_cache


class SampleResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    summary: str
    confidence: float = 0.5


async def test_build_runtime_with_no_env():
    """With no env set, build_runtime completes on stub."""
    clean_env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("AGENT_LLM_") and not k.startswith("AWS_") and k != "BEDROCK_MODEL_ID"
    }
    with patch.dict(os.environ, clean_env, clear=True):
        reset_yaml_cache()
        cfg = RuntimeConfig.from_env()
        runtime = build_runtime(cfg)
        assert runtime is not None


async def test_no_cloud_access_required():
    """Stub mode completes a full reason call with no cloud access."""
    cfg = RuntimeConfig(mode="stub")
    runtime = build_runtime(cfg)

    request = AssistiveRequest(
        task_kind=TaskKind.classify,
        agent_id="test-agent",
        correlation_id=uuid4(),
        causation_id=uuid4(),
        instructions="Classify the ticket.",
        grounding_inputs={"ticket_text": "I want a refund"},
        output_schema=SampleResult,
        fallback=lambda: SampleResult(summary="fallback", confidence=0.0),
    )

    result = await runtime.reason(request)
    assert result.reasoning_path in (ReasoningPath.model, ReasoningPath.fallback)
    assert result.value is not None


async def test_stub_mode_default():
    """Default RuntimeConfig mode is stub."""
    cfg = RuntimeConfig()
    assert cfg.mode == "stub"
