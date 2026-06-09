from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agent_foundation.envelope import EventEnvelope


class SamplePayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    message: str = Field(min_length=1, max_length=200)


class AuditPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    original_envelope: EventEnvelope
    outcome: Literal["accepted", "rejected", "duplicate_skipped"]
    reason: str | None = None
    recorded_at: datetime
