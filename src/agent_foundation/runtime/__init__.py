"""A2A runtime contract — expose endpoints, delegate tasks, discover peers."""
from __future__ import annotations

from agent_foundation.runtime.agent_card import AgentCard, Capability
from agent_foundation.runtime.client import A2AClient
from agent_foundation.runtime.discovery import discover_agents, find_capable, publish_card
from agent_foundation.runtime.errors import (
    DuplicateTask,
    TaskRejected,
    UnknownTask,
    UnsupportedCapability,
)
from agent_foundation.runtime.runtime import AgentRuntime

__all__ = [
    "AgentCard",
    "Capability",
    "A2AClient",
    "AgentRuntime",
    "discover_agents",
    "find_capable",
    "publish_card",
    "TaskRejected",
    "UnsupportedCapability",
    "DuplicateTask",
    "UnknownTask",
]
