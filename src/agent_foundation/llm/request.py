"""AssistiveRequest and TaskKind — the in-process call an agent makes to the runtime."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class TaskKind(StrEnum):
    classify = "classify"
    extract_intent = "extract_intent"
    draft_response = "draft_response"
    summarize_reasoning = "summarize_reasoning"


class AssistiveRequest(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    task_kind: TaskKind
    agent_id: str
    correlation_id: UUID
    causation_id: UUID
    instructions: str
    grounding_inputs: dict[str, Any]
    output_schema: type[BaseModel]
    examples: list[dict[str, Any]] | None = None
    idempotency_key: str = ""
    fallback: Callable[[], BaseModel]

    @field_validator("instructions")
    @classmethod
    def _instructions_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("instructions must be non-empty")
        return v

    @field_validator("output_schema")
    @classmethod
    def _output_schema_is_model(cls, v: type) -> type:
        if not (isinstance(v, type) and issubclass(v, BaseModel)):
            raise ValueError("output_schema must be a BaseModel subclass")
        return v

    @model_validator(mode="after")
    def _derive_idempotency_key(self) -> AssistiveRequest:
        if not self.idempotency_key:
            digest = hashlib.sha256(
                json.dumps(self.grounding_inputs, sort_keys=True, default=str).encode()
            ).hexdigest()[:16]
            key = f"{self.correlation_id}:{self.task_kind}:{digest}"
            object.__setattr__(self, "idempotency_key", key)
        return self

    @field_validator("grounding_inputs")
    @classmethod
    def _grounding_json_serializable(cls, v: dict[str, Any]) -> dict[str, Any]:
        try:
            json.dumps(v, default=str)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"grounding_inputs must be JSON-serializable: {exc}") from exc
        return v
