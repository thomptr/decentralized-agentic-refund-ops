"""AgentCore provider — call Bedrock under agentcore dev."""

from __future__ import annotations

from typing import Any, cast

from agent_foundation.llm.providers.base import (
    ProviderCredentialsError,
    ProviderError,
    RawCompletion,
)
from agent_foundation.logging import get_logger

_log = get_logger(__name__)


class AgentCoreProvider:
    """ModelProvider for local AgentCore dev runs against Bedrock."""

    def __init__(self, config: Any = None) -> None:
        self._config = config
        self._bedrock_provider: Any = None

    def _get_bedrock_provider(self) -> Any:
        if self._bedrock_provider is not None:
            return self._bedrock_provider
        try:
            from agent_foundation.llm.providers.bedrock import BedrockProvider

            self._bedrock_provider = BedrockProvider(self._config)
            return self._bedrock_provider
        except ImportError as exc:
            raise ProviderError(
                "AgentCore provider requires boto3. Install with: pip install -e '.[llm]'"
            ) from exc

    async def invoke(self, prompt: str, profile: Any) -> RawCompletion:
        provider = self._get_bedrock_provider()
        try:
            return cast(RawCompletion, await provider.invoke(prompt, profile))
        except ProviderCredentialsError:
            raise
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(f"AgentCore invocation failed: {exc}") from exc
