"""Programmatic evaluation score helpers — write-only, non-binding (FR-016)."""
from __future__ import annotations

from typing import Any


def _write_score(client: Any, trace_id: str, name: str, value: float, comment: str = "") -> None:
    """Write a numeric score to LangFuse; silently no-op on any error."""
    try:
        if client is None:
            return
        client.score(
            trace_id=trace_id,
            name=name,
            value=value,
            comment=comment or None,
        )
    except Exception:
        pass


def score_schema_valid(client: Any, trace_id: str, *, valid: bool) -> None:
    _write_score(client, trace_id, "schema_valid", 1.0 if valid else 0.0)


def score_used_fallback(client: Any, trace_id: str, *, used: bool) -> None:
    _write_score(client, trace_id, "used_fallback", 1.0 if used else 0.0)


def score_cache_hit(client: Any, trace_id: str, *, hit: bool) -> None:
    _write_score(client, trace_id, "cache_hit", 1.0 if hit else 0.0)


def score_latency_ms(client: Any, trace_id: str, *, latency_ms: float) -> None:
    _write_score(client, trace_id, "latency_ms", latency_ms)
