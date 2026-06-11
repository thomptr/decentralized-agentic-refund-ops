"""Token usage tracking and cost estimation."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, field_serializer

from agent_foundation.llm.result import TokenUsage

_PRICING_TABLE: dict[str, tuple[Decimal, Decimal]] = {
    "anthropic.claude-3-5-sonnet-20241022-v2:0": (Decimal("0.003"), Decimal("0.015")),
    "anthropic.claude-3-haiku-20240307-v1:0": (Decimal("0.00025"), Decimal("0.00125")),
    "anthropic.claude-3-opus-20240229-v1:0": (Decimal("0.015"), Decimal("0.075")),
    "stub": (Decimal("0"), Decimal("0")),
}


class LLMUsage(BaseModel):
    model_config = ConfigDict(frozen=True)

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    estimated_cost_usd: Decimal | None = None
    model_id: str = ""
    agent_id: str = ""
    prompt_id: str | None = None

    @field_serializer("estimated_cost_usd")
    def _serialize_decimal(self, v: Decimal | None, _info: Any) -> str | None:
        return str(v) if v is not None else None


def estimate_cost(
    model_id: str,
    input_tokens: int | None,
    output_tokens: int | None,
) -> Decimal | None:
    if input_tokens is None or output_tokens is None:
        return None
    rates = _PRICING_TABLE.get(model_id)
    if rates is None:
        return None
    input_rate, output_rate = rates
    return (Decimal(input_tokens) * input_rate + Decimal(output_tokens) * output_rate) / Decimal(
        1000
    )


def build_llm_usage(
    token_usage: TokenUsage | None,
    *,
    model_id: str,
    agent_id: str,
    prompt_id: str | None = None,
) -> LLMUsage:
    if token_usage is None:
        return LLMUsage(model_id=model_id, agent_id=agent_id, prompt_id=prompt_id)

    input_t = token_usage.input_tokens if token_usage.input_tokens else None
    output_t = token_usage.output_tokens if token_usage.output_tokens else None
    total = (input_t + output_t) if (input_t is not None and output_t is not None) else None
    cost = estimate_cost(model_id, input_t, output_t)

    return LLMUsage(
        input_tokens=input_t,
        output_tokens=output_t,
        total_tokens=total,
        estimated_cost_usd=cost,
        model_id=model_id,
        agent_id=agent_id,
        prompt_id=prompt_id,
    )
