from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


def _build_root_event_types() -> frozenset[str]:
    import os

    env = os.environ.get("AGENT_ENVIRONMENT", "local")
    return frozenset(
        {
            "agent.sample.v1",
            "agent.workflow_start.v1",
            "agent.agent_card.v1",
            f"{env}.support.ticket.created.v1",
        }
    )


ROOT_EVENT_TYPES: frozenset[str] = _build_root_event_types()

_AGENT_ID_RE = re.compile(r"^[a-z][a-z0-9_.-]{1,62}$")
_TENANT_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{1,62}$")
# Multi-segment dot-separated lowercase identifiers ending in .v<digits>
_EVENT_TYPE_RE = re.compile(r"^[a-z][a-z0-9_-]*(\.[a-z][a-z0-9_-]*)+\.v\d+$")
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


class MissingCausation(ValueError):
    """Raised when a non-root event is missing causation_id."""


class AgentIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    display_name: str
    tenant_id: str

    @field_validator("agent_id")
    @classmethod
    def validate_agent_id(cls, v: str) -> str:
        if not _AGENT_ID_RE.match(v):
            raise ValueError(f"agent_id must match {_AGENT_ID_RE.pattern!r}, got {v!r}")
        return v

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, v: str) -> str:
        if not (1 <= len(v) <= 80):
            raise ValueError("display_name must be 1–80 characters")
        return v

    @field_validator("tenant_id")
    @classmethod
    def validate_tenant_id(cls, v: str) -> str:
        if not _TENANT_ID_RE.match(v):
            raise ValueError(f"tenant_id must match {_TENANT_ID_RE.pattern!r}, got {v!r}")
        return v


class EventEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: UUID
    correlation_id: UUID
    causation_id: UUID | None
    agent_id: str
    tenant_id: str
    timestamp: datetime
    event_type: str
    schema_version: str
    payload: dict[str, Any]

    @field_validator("agent_id")
    @classmethod
    def validate_agent_id(cls, v: str) -> str:
        if not _AGENT_ID_RE.match(v):
            raise ValueError(f"agent_id must match {_AGENT_ID_RE.pattern!r}, got {v!r}")
        return v

    @field_validator("tenant_id")
    @classmethod
    def validate_tenant_id(cls, v: str) -> str:
        if not _TENANT_ID_RE.match(v):
            raise ValueError(f"tenant_id must match {_TENANT_ID_RE.pattern!r}, got {v!r}")
        return v

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, v: str) -> str:
        if not _EVENT_TYPE_RE.match(v):
            raise ValueError(f"event_type must match {_EVENT_TYPE_RE.pattern!r}, got {v!r}")
        return v

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, v: str) -> str:
        if not _SEMVER_RE.match(v):
            raise ValueError(f"schema_version must be MAJOR.MINOR.PATCH semver, got {v!r}")
        return v

    @model_validator(mode="after")
    def validate_causation_id(self) -> EventEnvelope:
        if self.causation_id is None and self.event_type not in ROOT_EVENT_TYPES:
            raise MissingCausation(
                f"causation_id is required for non-root event type {self.event_type!r}; "
                f"root event types: {sorted(ROOT_EVENT_TYPES)}"
            )
        return self
