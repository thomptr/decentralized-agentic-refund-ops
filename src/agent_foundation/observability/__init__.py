"""Public surface for the observability package."""

from __future__ import annotations

from agent_foundation.observability.client import configure as _configure
from agent_foundation.observability.client import flush, get_client, get_config
from agent_foundation.observability.config import ObservabilityConfig
from agent_foundation.observability.decorators import traced
from agent_foundation.observability.propagation import current_trace_context, start_consumer_span
from agent_foundation.observability.scores import (
    score_cache_hit,
    score_latency_ms,
    score_schema_valid,
    score_used_fallback,
)
from agent_foundation.observability.tracing import generation, span


def configure_observability(
    *, agent_id: str = "agent", config: ObservabilityConfig | None = None
) -> None:
    """Bootstrap observability at agent startup. Call once beside configure_logging()."""
    cfg = config or ObservabilityConfig.from_env(agent_id=agent_id)
    _configure(cfg)


__all__ = [
    "configure_observability",
    "ObservabilityConfig",
    "span",
    "generation",
    "traced",
    "flush",
    "get_client",
    "get_config",
    "current_trace_context",
    "start_consumer_span",
    "score_schema_valid",
    "score_used_fallback",
    "score_cache_hit",
    "score_latency_ms",
]
