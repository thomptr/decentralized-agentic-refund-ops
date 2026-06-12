"""Customer Resolution Agent entrypoint.

Three concurrent loops (intake, result, runtime) share an in-process CaseStateStore.
No billing/risk business logic is implemented here — all such facts enter via peer TaskResult.

Usage:
    demo-customer-resolution           # via installed console script
    uv run python -m apps.agents.customer_resolution.main
"""

from __future__ import annotations


def run() -> None:
    """Entry point registered in pyproject.toml as demo-customer-resolution."""
    main()


def main() -> None:
    import asyncio
    import signal

    from agent_foundation.logging import configure_logging
    from agent_foundation.observability import configure_observability
    from apps.agents.common import BROKER_URL
    from apps.agents.customer_resolution.agent import ResolutionService

    configure_logging()
    configure_observability(agent_id="customer-resolution")

    service = ResolutionService(broker_url=BROKER_URL)
    stop_event = asyncio.Event()

    def _handle_signal(sig, frame) -> None:
        stop_event.set()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    asyncio.run(service.serve(stop_event))


if __name__ == "__main__":
    main()
