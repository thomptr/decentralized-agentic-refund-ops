from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator


class A2APart(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal["text", "data", "file"]
    text: str | None = None
    data: dict[str, Any] | None = None
    file_uri: str | None = None

    @model_validator(mode="after")
    def validate_conditional_fields(self) -> "A2APart":
        if self.type == "text" and self.text is None:
            raise ValueError("text is required when type is 'text'")
        if self.type == "data" and self.data is None:
            raise ValueError("data is required when type is 'data'")
        if self.type == "file" and self.file_uri is None:
            raise ValueError("file_uri is required when type is 'file'")
        return self


class A2AMessage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    role: Literal["user", "agent"]
    parts: list[A2APart]
    task_id: UUID | None = None

    @model_validator(mode="after")
    def validate_parts_nonempty(self) -> "A2AMessage":
        if not self.parts:
            raise ValueError("parts must be non-empty")
        return self


class A2ATask(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: UUID
    status: Literal["submitted", "working", "completed", "failed", "canceled"]
    messages: list[A2AMessage]
