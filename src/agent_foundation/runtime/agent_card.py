from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

_CAPABILITY_ID_RE = re.compile(r"^[a-z][a-z0-9_.-]{1,62}$")
_AGENT_ID_RE = re.compile(r"^[a-z][a-z0-9_.-]{1,62}$")
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


class Capability(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    name: str
    description: str
    tags: list[str] = []

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        if not _CAPABILITY_ID_RE.match(v):
            raise ValueError(f"Capability.id must match {_CAPABILITY_ID_RE.pattern!r}, got {v!r}")
        return v

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not (1 <= len(v) <= 80):
            raise ValueError("Capability.name must be 1–80 characters")
        return v

    @field_validator("description")
    @classmethod
    def validate_description(cls, v: str) -> str:
        if not (1 <= len(v) <= 280):
            raise ValueError("Capability.description must be 1–280 characters")
        return v


class AgentCard(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    name: str
    description: str
    version: str
    endpoint_topic: str
    capabilities: list[Capability]
    security: Literal["none"] = "none"

    @field_validator("agent_id")
    @classmethod
    def validate_agent_id(cls, v: str) -> str:
        if not _AGENT_ID_RE.match(v):
            raise ValueError(f"AgentCard.agent_id must match {_AGENT_ID_RE.pattern!r}, got {v!r}")
        return v

    @field_validator("version")
    @classmethod
    def validate_version(cls, v: str) -> str:
        if not _SEMVER_RE.match(v):
            raise ValueError(f"AgentCard.version must be semver MAJOR.MINOR.PATCH, got {v!r}")
        return v

    @model_validator(mode="after")
    def validate_capabilities(self) -> AgentCard:
        if not self.capabilities:
            raise ValueError("AgentCard.capabilities must be non-empty")
        ids = [c.id for c in self.capabilities]
        if len(ids) != len(set(ids)):
            raise ValueError("AgentCard.capabilities must have unique ids")
        return self
