"""Bedrock provider — boto3 bedrock-runtime + prompt-cache breakpoints."""

from __future__ import annotations

import json
import time
from typing import Any

from agent_foundation.llm.providers.base import (
    ProviderCredentialsError,
    ProviderError,
    RawCompletion,
)
from agent_foundation.llm.result import TokenUsage
from agent_foundation.logging import get_logger

_log = get_logger(__name__)


def create_bedrock_client(config: Any) -> Any:
    """Build a region-configured boto3 bedrock-runtime client.

    Model-agnostic: model_id is supplied per-call at invoke time, never baked in.
    No explicit credential kwargs — boto3 resolves the default provider chain.
    """
    try:
        import boto3
        import botocore.config
    except ImportError as exc:
        raise ProviderError(
            "boto3 is required for the Bedrock provider. Install with: pip install -e '.[llm]'"
        ) from exc

    region = getattr(config, "region", None) or "us-east-1"
    timeout = getattr(config, "timeout_seconds", 30)
    max_attempts = getattr(config, "retry_max_attempts", 3)

    boto_config = botocore.config.Config(
        connect_timeout=int(timeout),
        read_timeout=int(timeout),
        retries={"max_attempts": max_attempts, "mode": "standard"},
    )

    try:
        return boto3.client(
            "bedrock-runtime",
            region_name=region,
            config=boto_config,
        )
    except Exception as exc:
        _check_credentials_error(exc)
        raise ProviderError(f"Failed to create Bedrock client: {exc}") from exc


def _check_credentials_error(exc: Exception) -> None:
    try:
        from botocore.exceptions import (
            NoCredentialsError,
            NoRegionError,
            ProfileNotFound,
        )

        if isinstance(exc, (NoCredentialsError, ProfileNotFound, NoRegionError)):
            msg = str(exc)
            if isinstance(exc, NoCredentialsError):
                msg = (
                    "AWS credentials not found. Configure with: aws configure, "
                    "or set AWS_PROFILE / AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY"
                )
            elif isinstance(exc, ProfileNotFound):
                msg = f"AWS profile not found: {exc}. Run: aws configure --profile <name>"
            elif isinstance(exc, NoRegionError):
                msg = "AWS region not set. Set AWS_REGION or AGENT_LLM_REGION"
            raise ProviderCredentialsError(msg) from exc
    except ImportError:
        pass


class BedrockProvider:
    """ModelProvider implementation for AWS Bedrock."""

    def __init__(self, config: Any = None) -> None:
        self._config = config
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        self._client = create_bedrock_client(self._config)
        return self._client

    async def invoke(self, prompt: str, profile: Any) -> RawCompletion:
        client = self._get_client()
        model_id = getattr(profile, "model_id", "anthropic.claude-3-5-sonnet-20241022-v2:0")
        max_tokens = getattr(profile, "max_tokens", 1024)
        temperature = getattr(profile, "temperature", 0.0)

        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        start = time.perf_counter()
        try:
            response = client.invoke_model(
                modelId=model_id,
                body=json.dumps(body),
                contentType="application/json",
                accept="application/json",
            )
        except Exception as exc:
            _check_credentials_error(exc)
            raise ProviderError(f"Bedrock invocation failed: {exc}") from exc
        _ = time.perf_counter() - start

        resp_body = json.loads(response["body"].read())
        text_parts = []
        for block in resp_body.get("content", []):
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))

        usage = resp_body.get("usage", {})
        token_usage = TokenUsage(
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            cache_read_tokens=usage.get("cache_read_input_tokens", 0),
            cache_write_tokens=usage.get("cache_creation_input_tokens", 0),
        )

        return RawCompletion(
            text="".join(text_parts),
            token_usage=token_usage,
            cache_hit=token_usage.cache_read_tokens > 0,
            model_id=resp_body.get("model", model_id),
        )
