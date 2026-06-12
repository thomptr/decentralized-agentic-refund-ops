"""build_runtime — the single assembly point for LLMRuntime."""

from __future__ import annotations

from typing import Any

from agent_foundation.llm.config import RuntimeConfig
from agent_foundation.llm.providers import select_provider
from agent_foundation.llm.runtime import LLMRuntime
from agent_foundation.llm.store import AssistiveResultStore

try:
    from agent_foundation.observability.config import ObservabilityConfig as _ObservabilityConfig
except Exception:  # observability package not installed
    _ObservabilityConfig = None  # type: ignore[assignment,misc]


def build_runtime(
    config: RuntimeConfig | None = None,
    *,
    publisher: object | None = None,
    obs_config: Any | None = None,
) -> LLMRuntime:
    cfg = config or RuntimeConfig.from_env()
    provider = select_provider(cfg.mode)
    store = AssistiveResultStore(bootstrap_servers=cfg.bootstrap_servers)
    return LLMRuntime(
        provider=provider,
        store=store,
        config=cfg,
        publisher=publisher,
        obs_config=obs_config,
    )
