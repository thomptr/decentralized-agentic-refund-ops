"""ModelProvider protocol and RawCompletion — the provider contract."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

from agent_foundation.llm.result import TokenUsage


class RawCompletion(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    token_usage: TokenUsage = TokenUsage()
    cache_hit: bool = False
    model_id: str = "unknown"


class ProviderError(Exception):
    pass


class ProviderCredentialsError(ProviderError):
    pass


@runtime_checkable
class ModelProvider(Protocol):
    async def invoke(self, prompt: str, profile: object) -> RawCompletion: ...
