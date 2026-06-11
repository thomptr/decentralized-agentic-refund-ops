"""AssistiveResult, ReasoningPath, TokenUsage, TextResult — runtime return types."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict

from agent_foundation.llm.errors import FailureReason


class ReasoningPath(StrEnum):
    model = "model"
    cache = "cache"
    fallback = "fallback"


class TokenUsage(BaseModel):
    model_config = ConfigDict(frozen=True)

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


class TextResult(BaseModel):
    """Default output schema for unstructured (free-text) calls."""

    model_config = ConfigDict(frozen=True)

    text: str


class AssistiveResult(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    value: Any
    reasoning_path: ReasoningPath
    token_usage: TokenUsage | None = None
    cache_hit: bool = False
    failure_reason: FailureReason | None = None
    model_id: str | None = None
    latency_ms: int = 0
    prompt_ref: str | None = None
