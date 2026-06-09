"""Shared bootstrap for demo agents."""
from __future__ import annotations

import asyncio
import os
import signal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_foundation.runtime.runtime import AgentRuntime

BROKER_URL: str = os.environ.get("AGENT_BROKER_URL", "localhost:9092")


def run_agent(runtime: AgentRuntime) -> None:
    """Configure structlog, install signal handlers, and run the runtime."""
    from agent_foundation.logging import configure_logging

    configure_logging()

    stop_event = asyncio.Event()

    def _handle_signal(*_: object) -> None:
        stop_event.set()

    import contextlib

    loop = asyncio.new_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError, RuntimeError):
            loop.add_signal_handler(sig, _handle_signal)

    try:
        loop.run_until_complete(runtime.serve(stop_event))
    finally:
        loop.close()
