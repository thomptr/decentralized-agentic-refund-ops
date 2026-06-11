"""build_runtime — the single assembly point for LLMRuntime."""

from __future__ import annotations

from agent_foundation.llm.config import RuntimeConfig
from agent_foundation.llm.providers import select_provider
from agent_foundation.llm.runtime import LLMRuntime
from agent_foundation.llm.store import AssistiveResultStore


def build_runtime(
    config: RuntimeConfig | None = None,
    *,
    publisher: object | None = None,
) -> LLMRuntime:
    cfg = config or RuntimeConfig.from_env()
    provider = select_provider(cfg.mode)
    store = AssistiveResultStore(bootstrap_servers=cfg.bootstrap_servers)
    return LLMRuntime(
        provider=provider,
        store=store,
        config=cfg,
        publisher=publisher,
    )
