"""AgentLLM — thin, normalized Bedrock client wrapper."""

from __future__ import annotations

import json
import time
from typing import Any

from pydantic import BaseModel, ConfigDict

from agent_foundation.llm.result import TokenUsage
from agent_foundation.logging import get_logger

_log = get_logger(__name__)


class LLMClientError(Exception):
    pass


class LLMResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    model_id: str | None = None
    latency_ms: int = 0
    token_usage: TokenUsage | None = None
    cache_hit: bool = False
    stop_reason: str | None = None
    metadata: dict[str, Any] = {}


class StructuredLLMResponse(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    text: str = ""
    model_id: str | None = None
    latency_ms: int = 0
    token_usage: TokenUsage | None = None
    cache_hit: bool = False
    stop_reason: str | None = None
    metadata: dict[str, Any] = {}
    value: Any = None
    raw_json: dict[str, Any] | None = None
    parse_error: str | None = None


_SECRET_KEYS = {"token", "secret", "password", "key", "credential", "auth", "api_key", "apikey"}
_MAX_VALUE_LEN = 2000
_MAX_TOTAL_SIZE = 10000


def _safe_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if not metadata:
        return {}
    result: dict[str, Any] = {}
    total = 0
    for k, v in metadata.items():
        if any(s in k.lower() for s in _SECRET_KEYS):
            continue
        sv = str(v) if not isinstance(v, (str, int, float, bool, type(None))) else v
        if isinstance(sv, str) and len(sv) > _MAX_VALUE_LEN:
            sv = sv[:_MAX_VALUE_LEN] + "..."
        total += len(str(sv))
        if total > _MAX_TOTAL_SIZE:
            break
        result[k] = sv
    try:
        json.dumps(result, default=str)
    except (TypeError, ValueError):
        return {}
    return result


class AgentLLM:
    """Normalized Bedrock client wrapper — hides all boto3/Bedrock shapes."""

    def __init__(
        self,
        *,
        config: Any = None,
        profile: Any = None,
    ) -> None:
        self._config = config
        self._profile = profile
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from agent_foundation.llm.providers.bedrock import create_bedrock_client

            self._client = create_bedrock_client(self._config or self._profile)
            return self._client
        except ImportError as exc:
            raise LLMClientError(
                "boto3 is required. Install with: pip install -e '.[llm]'"
            ) from exc

    def invoke(
        self,
        messages: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
    ) -> LLMResponse:
        safe_meta = _safe_metadata(metadata)
        client = self._get_client()
        body = _build_request_body(
            messages,
            max_tokens=getattr(self._profile, "max_tokens", 1024),
            temperature=getattr(self._profile, "temperature", 0.0),
        )
        model_id = getattr(
            self._profile,
            "model_id",
            "anthropic.claude-3-5-sonnet-20241022-v2:0",
        )
        start = time.perf_counter()
        try:
            response = client.invoke_model(
                modelId=model_id,
                body=json.dumps(body),
                contentType="application/json",
                accept="application/json",
            )
        except Exception as exc:
            raise LLMClientError(f"Bedrock invocation failed: {exc}") from exc
        latency_ms = int((time.perf_counter() - start) * 1000)
        return _parse_response(response, latency_ms, safe_meta)

    def invoke_structured(
        self,
        messages: list[dict[str, Any]],
        output_schema: type[BaseModel],
        metadata: dict[str, Any] | None = None,
    ) -> StructuredLLMResponse:
        structured_messages = list(messages)
        schema_json = json.dumps(output_schema.model_json_schema(), indent=2)
        structured_messages.append(
            {
                "role": "user",
                "content": f"Respond with valid JSON matching this schema:\n{schema_json}",
            }
        )
        resp = self.invoke(structured_messages, metadata)
        try:
            raw = json.loads(resp.text)
            value = output_schema.model_validate(raw)
            return StructuredLLMResponse(
                text=resp.text,
                model_id=resp.model_id,
                latency_ms=resp.latency_ms,
                token_usage=resp.token_usage,
                cache_hit=resp.cache_hit,
                stop_reason=resp.stop_reason,
                metadata=resp.metadata,
                value=value,
                raw_json=raw,
            )
        except Exception as exc:
            return StructuredLLMResponse(
                text=resp.text,
                model_id=resp.model_id,
                latency_ms=resp.latency_ms,
                token_usage=resp.token_usage,
                cache_hit=resp.cache_hit,
                stop_reason=resp.stop_reason,
                metadata=resp.metadata,
                parse_error=str(exc),
            )


def _build_request_body(
    messages: list[dict[str, Any]],
    *,
    max_tokens: int = 1024,
    temperature: float = 0.0,
    top_p: float | None = None,
    system: str | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "anthropic_version": "bedrock-2023-05-31",
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if top_p is not None:
        body["top_p"] = top_p
    if system:
        body["system"] = system
    return body


def _parse_response(
    response: Any,
    latency_ms: int,
    metadata: dict[str, Any],
) -> LLMResponse:
    try:
        body = json.loads(response["body"].read())
    except Exception as exc:
        raise LLMClientError(f"Failed to parse Bedrock response: {exc}") from exc

    text_parts = []
    for block in body.get("content", []):
        if block.get("type") == "text":
            text_parts.append(block.get("text", ""))

    usage = body.get("usage", {})
    token_usage = TokenUsage(
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        cache_read_tokens=usage.get("cache_read_input_tokens", 0),
        cache_write_tokens=usage.get("cache_creation_input_tokens", 0),
    )
    cache_hit = token_usage.cache_read_tokens > 0

    return LLMResponse(
        text="".join(text_parts),
        model_id=body.get("model", None),
        latency_ms=latency_ms,
        token_usage=token_usage,
        cache_hit=cache_hit,
        stop_reason=body.get("stop_reason"),
        metadata=metadata,
    )
