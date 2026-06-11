"""Deterministic offline stub model — the default provider (no AWS)."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from pydantic import BaseModel

from agent_foundation.llm.providers.base import RawCompletion
from agent_foundation.llm.result import TokenUsage


class StubProvider:
    """Returns deterministic, schema-shaped output derived from the prompt hash.

    Identical inputs yield identical output; meaningfully different grounding
    yields different output. No cloud access.
    """

    async def invoke(self, prompt: str, profile: object) -> RawCompletion:
        digest = hashlib.sha256(prompt.encode()).hexdigest()
        output = self._generate_from_schema(prompt, digest)
        text_len = len(output)
        return RawCompletion(
            text=output,
            token_usage=TokenUsage(
                input_tokens=len(prompt) // 4,
                output_tokens=text_len // 4,
                cache_read_tokens=0,
                cache_write_tokens=0,
            ),
            cache_hit=False,
            model_id="stub",
        )

    def _generate_from_schema(self, prompt: str, digest: str) -> str:
        schema_json = self._extract_schema_hint(prompt)
        if schema_json:
            return self._fill_schema(schema_json, digest)
        return json.dumps({"text": f"stub-response-{digest[:8]}"})

    def _extract_schema_hint(self, prompt: str) -> dict[str, Any] | None:
        match = re.search(r"OUTPUT_SCHEMA:\s*(\{.*?\})\s*(?:END_SCHEMA|$)", prompt, re.DOTALL)
        if match:
            try:
                parsed: dict[str, Any] = json.loads(match.group(1))
                return parsed
            except json.JSONDecodeError:
                pass
        return None

    def _fill_schema(self, schema: dict[str, Any], digest: str) -> str:
        properties = schema.get("properties", {})
        if not properties:
            return json.dumps({"text": f"stub-{digest[:8]}"})

        result: dict[str, Any] = {}
        for field_name, field_info in properties.items():
            result[field_name] = self._generate_field(field_name, field_info, digest)
        return json.dumps(result)

    def _generate_field(self, name: str, info: dict[str, Any], digest: str) -> Any:
        field_type = info.get("type", "string")
        if "enum" in info:
            values = info["enum"]
            idx = int(digest[:4], 16) % len(values)
            return values[idx]
        if field_type == "string":
            return f"stub-{name}-{digest[:8]}"
        if field_type == "number" or field_type == "integer":
            return int(digest[:4], 16) % 100
        if field_type == "boolean":
            return int(digest[0], 16) % 2 == 0
        if field_type == "array":
            return [f"stub-item-{digest[:6]}"]
        return f"stub-{name}-{digest[:8]}"


def _schema_to_json_schema(schema_cls: type[BaseModel]) -> dict[str, Any]:
    return schema_cls.model_json_schema()
