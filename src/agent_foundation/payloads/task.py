from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

from agent_foundation.a2a import A2AMessage

TaskStatus = Literal["completed", "failed", "rejected"]


class TaskError(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    category: Literal[
        "validation", "unsupported_capability", "handler_error", "duplicate", "internal"
    ]
    message: str


class TaskRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: UUID
    capability: str
    requester_agent_id: str
    target_agent_id: str
    input: A2AMessage


class TaskResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: UUID
    status: TaskStatus
    performer_agent_id: str
    output: A2AMessage | None = None
    error: TaskError | None = None

    @model_validator(mode="after")
    def validate_status_fields(self) -> TaskResult:
        if self.status == "completed":
            if self.output is None:
                raise ValueError("output must be set when status is 'completed'")
            if self.error is not None:
                raise ValueError("error must be null when status is 'completed'")
        elif self.status == "failed":
            if self.error is None:
                raise ValueError("error must be set when status is 'failed'")
            if self.output is not None:
                raise ValueError("output must be null when status is 'failed'")
            if self.error.category not in ("handler_error", "internal"):
                raise ValueError(
                    f"error.category must be handler_error or internal for failed, "
                    f"got {self.error.category!r}"
                )
        elif self.status == "rejected":
            if self.error is None:
                raise ValueError("error must be set when status is 'rejected'")
            if self.output is not None:
                raise ValueError("output must be null when status is 'rejected'")
            if self.error.category not in (
                "validation",
                "unsupported_capability",
                "duplicate",
            ):
                raise ValueError(
                    f"error.category must be validation/unsupported_capability/duplicate "
                    f"for rejected, got {self.error.category!r}"
                )
        return self
