"""Provider selection from config."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent_foundation.llm.providers.base import ModelProvider, ProviderError
from agent_foundation.llm.providers.stub import StubProvider

if TYPE_CHECKING:
    pass


def select_provider(mode: str = "stub") -> ModelProvider:
    if mode == "stub":
        return StubProvider()
    if mode == "bedrock":
        try:
            from agent_foundation.llm.providers.bedrock import BedrockProvider

            return BedrockProvider()
        except ImportError as exc:
            raise ProviderError(
                "Bedrock provider requires boto3. Install with: pip install -e '.[llm]'"
            ) from exc
    if mode == "agentcore":
        try:
            from agent_foundation.llm.providers.agentcore import AgentCoreProvider

            return AgentCoreProvider()
        except ImportError as exc:
            raise ProviderError(
                "AgentCore provider requires bedrock-agentcore. "
                "Install with: pip install bedrock-agentcore"
            ) from exc
    raise ProviderError(f"Unknown provider mode: {mode!r}. Use 'stub', 'bedrock', or 'agentcore'.")


__all__ = ["ModelProvider", "ProviderError", "StubProvider", "select_provider"]
