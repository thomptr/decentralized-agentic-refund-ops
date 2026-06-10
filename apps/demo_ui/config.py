"""Configuration + async→sync bridge for the Streamlit demo UI (T003, T004).

Streamlit runs synchronously, but every foundation read-side helper
(``discover_agents``, ``query_by_correlation``, ``consume_all_audit_records``) is
``async``. ``run_async`` bridges the two, and ``cached_call`` gives a short-TTL
in-process cache so several reruns within one refresh interval reuse the last
Kafka read. Both are pure plumbing — no domain logic lives here.
"""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Awaitable, Callable
from typing import Any

# ---------------------------------------------------------------------------
# Static configuration
# ---------------------------------------------------------------------------

#: Kafka broker, shared with the agents and start-script (``AGENT_BROKER_URL``).
BROKER_URL: str = os.environ.get("AGENT_BROKER_URL", "localhost:9092")

#: Port the Streamlit app listens on (see scripts/start-local-system.sh --with-ui).
UI_PORT: int = int(os.environ.get("UI_PORT", "8200"))

#: Auto-refresh interval (seconds) for the live views — meets the ≤5 s "live" SC.
REFRESH_SECONDS: int = int(os.environ.get("REFRESH_SECONDS", "5"))

#: The three peer agents the roster is anchored to. A missing agent is shown as
#: ``announced=False`` rather than omitted (FR-004).
EXPECTED_AGENT_IDS: tuple[str, ...] = (
    "customer-resolution-agent",
    "billing-entitlement-agent",
    "risk-fraud-agent",
)

#: Per-agent HTTP ``/ping`` liveness endpoints (R3). ``None`` means the agent
#: exposes no HTTP surface (customer-resolution is Kafka-only) — it can never be
#: probed "live", only "unknown"/"not_announced". Env-overridable.
LIVENESS_ENDPOINTS: dict[str, str | None] = {
    "customer-resolution-agent": os.environ.get("CR_PING_URL") or None,
    "billing-entitlement-agent": os.environ.get("BILLING_PING_URL", "http://localhost:8101/ping"),
    "risk-fraud-agent": os.environ.get("RISK_PING_URL", "http://localhost:8103/ping"),
}

#: Timeout (seconds) for a single liveness probe — kept short so a dead agent
#: never stalls a refresh.
PROBE_TIMEOUT_SECONDS: float = float(os.environ.get("PROBE_TIMEOUT_SECONDS", "1.5"))

#: Upper bound (seconds) on any single Kafka read. A dead/unreachable broker makes
#: aiokafka's bootstrap retry for tens of seconds; bounding it here lets the UI
#: degrade to an honest empty state promptly instead of hanging (FR-016 / "runs
#: independently").
READ_TIMEOUT_SECONDS: float = float(os.environ.get("READ_TIMEOUT_SECONDS", "6.0"))


# ---------------------------------------------------------------------------
# Async → sync bridge
# ---------------------------------------------------------------------------


def run_async[T](coro: Awaitable[T], *, timeout: float | None = None) -> T:
    """Run an awaitable to completion from synchronous Streamlit code.

    A fresh event loop per call is correct here: each Kafka read opens and closes
    its own consumer/producer, so there is no loop state to preserve between calls.
    When ``timeout`` is set, a read that overruns it raises ``TimeoutError`` (the
    aggregators catch it and degrade to an empty state).
    """

    async def _runner() -> T:
        if timeout is None:
            return await coro
        return await asyncio.wait_for(coro, timeout)

    return asyncio.run(_runner())


# ---------------------------------------------------------------------------
# Short-TTL last-poll cache
# ---------------------------------------------------------------------------

_cache: dict[str, tuple[float, Any]] = {}


def cached_call[T](key: str, factory: Callable[[], T], ttl: float | None = None) -> T:
    """Return ``factory()``'s result, reusing a cached value within ``ttl`` seconds.

    Keyed by ``key`` so concurrent reruns inside one refresh interval reuse the
    last Kafka read instead of re-scanning the topic. Pure caching — no domain
    logic. ``ttl`` defaults to ``REFRESH_SECONDS``.
    """
    window = REFRESH_SECONDS if ttl is None else ttl
    now = time.monotonic()
    hit = _cache.get(key)
    if hit is not None and (now - hit[0]) < window:
        return hit[1]
    value = factory()
    _cache[key] = (now, value)
    return value


def clear_cache() -> None:
    """Drop all cached poll results (used by tests and manual refresh)."""
    _cache.clear()
