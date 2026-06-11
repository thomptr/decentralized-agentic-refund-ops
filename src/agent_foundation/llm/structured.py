"""Schema validate-and-repair loop for structured LLM output."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict

from agent_foundation.llm.errors import FailureReason
from agent_foundation.logging import get_logger

_log = get_logger(__name__)


class StructuredError(BaseModel):
    model_config = ConfigDict(frozen=True)

    failure_reason: FailureReason = FailureReason.invalid_output
    attempts: int = 0
    error_messages: list[str] = []


class StructuredOutcome(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    ok: bool
    value: Any = None
    error: StructuredError | None = None


async def invoke_structured(
    messages: str,
    output_schema: type[BaseModel],
    *,
    provider: Any,
    profile: Any,
    grounding_inputs: dict[str, Any] | None = None,
    max_repairs: int = 1,
) -> StructuredOutcome:
    errors: list[str] = []
    attempts = 0

    for attempt in range(1 + max_repairs):
        attempts = attempt + 1
        prompt = messages
        if attempt > 0 and errors:
            prompt += (
                f"\n\nPrevious output was invalid: {errors[-1]}\n"
                f"Please fix the JSON output to match this schema:\n"
                f"{json.dumps(output_schema.model_json_schema(), indent=2)}"
            )

        raw = await provider.invoke(prompt, profile)

        try:
            parsed = _parse_json(raw.text)
        except json.JSONDecodeError as exc:
            errors.append(f"JSON parse error: {exc}")
            continue

        try:
            value = output_schema.model_validate(parsed)
        except Exception as exc:
            errors.append(f"Schema validation error: {exc}")
            continue

        if grounding_inputs and not _grounding_check(value, grounding_inputs):
            errors.append("Output asserts facts not present in grounding inputs")
            continue

        return StructuredOutcome(ok=True, value=value)

    return StructuredOutcome(
        ok=False,
        error=StructuredError(
            failure_reason=FailureReason.invalid_output,
            attempts=attempts,
            error_messages=errors,
        ),
    )


def _parse_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    parsed: dict[str, Any] = json.loads(text.strip())
    return parsed


def _grounding_check(value: BaseModel, grounding_inputs: dict[str, Any]) -> bool:
    """Reject a schema-valid result that asserts facts absent from grounding."""
    value_data = value.model_dump(mode="json")
    grounding_str = json.dumps(grounding_inputs, default=str).lower()

    for field_name, field_value in value_data.items():
        if not isinstance(field_value, str):
            continue
        if len(field_value) < 20:
            continue
        tokens = field_value.lower().split()
        numeric_claims = [t for t in tokens if any(c.isdigit() for c in t) and len(t) > 3]
        for claim in numeric_claims:
            if (
                claim not in grounding_str
                and claim.replace("$", "").replace(",", "") not in grounding_str
            ):
                _log.debug("grounding_check.rejected", claim=claim, field=field_name)
                return False
    return True
