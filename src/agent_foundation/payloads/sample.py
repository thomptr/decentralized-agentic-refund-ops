from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent_foundation.envelope import EventEnvelope


class SamplePayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    message: str = Field(min_length=1, max_length=200)


class AuditPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    original_envelope: EventEnvelope
    outcome: Literal["accepted", "rejected", "duplicate_skipped", "completed", "failed"]
    reason: str | None = None
    recorded_at: datetime
    task_id: UUID | None = None

    @model_validator(mode="after")
    def validate_reason_required(self) -> AuditPayload:
        if self.outcome in ("rejected", "failed") and self.reason is None:
            raise ValueError(f"reason is required when outcome is {self.outcome!r}")
        return self
