"""Timeout reaper for the Customer Resolution Agent (006 T021).

Loops every REAPER_TICK_SECONDS, queries the store for cases whose deadline has
passed and still have pending peer tasks, re-checks the terminal guard, and
escalates each via the existing _apply_decision path (escalate_human /
analysis_timeout).

Design constraints:
- Routes through _apply_decision so the DECIDED/terminal guard prevents double-decides.
- Injectable clock (now: Callable) for deterministic unit tests; neutralizable for
  completed-run replay by passing an effectively-infinite deadline.
- No new Kafka topic, no new dependency (Constitution V).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

import structlog

from apps.agents.customer_resolution.config import REAPER_TICK_SECONDS
from apps.agents.customer_resolution.models import CaseStatus, is_terminal
from apps.agents.customer_resolution.state_store import InMemoryCaseStateStore

logger = structlog.get_logger(__name__)


async def run_reaper(
    store: InMemoryCaseStateStore,
    publisher,  # agent_foundation.transport.publisher.Publisher
    *,
    stop_event: asyncio.Event | None = None,
    now: Callable[[], datetime] | None = None,
    tick_seconds: float | None = None,
) -> None:
    """Sweep for timed-out cases and escalate each via _apply_decision (T021).

    Args:
        store:        The shared case state store.
        publisher:    The shared publisher for emitting decision events.
        stop_event:   Signals graceful shutdown (same event used by other loops).
        now:          Clock factory; defaults to ``lambda: datetime.now(UTC)``.
                      Inject a fixed clock for unit tests / replay neutralisation.
        tick_seconds: Override loop cadence; defaults to ``REAPER_TICK_SECONDS``.
    """

    _now: Callable[[], datetime] = now or (lambda: datetime.now(UTC))
    _tick: float = tick_seconds if tick_seconds is not None else REAPER_TICK_SECONDS

    # Import the module (not the function) so test patches are respected at call time
    import apps.agents.customer_resolution.event_handlers as _event_handlers  # noqa: PLC0415

    logger.info("reaper_started", tick_seconds=_tick)

    while True:
        current_time = _now()
        try:
            timed_out = await store.list_timed_out_cases(current_time)
        except Exception:
            logger.exception("reaper_store_query_failed")
            timed_out = []

        for case in timed_out:
            # Re-check terminal guard (the case may have just been decided)
            if is_terminal(case.status) or case.status == CaseStatus.DECIDED:
                continue

            logger.info(
                "reaper_escalating",
                case_id=str(case.case_id),
                deadline_at=str(case.deadline_at),
                pending_tasks=len(case.pending_tasks),
            )

            try:
                await _event_handlers._apply_decision(
                    case,
                    causation_id=uuid4(),
                    publisher=publisher,
                    store=store,
                )
            except Exception:
                logger.exception("reaper_apply_decision_failed", case_id=str(case.case_id))

        # Check stop after sweep so at least one iteration runs
        if stop_event is not None and stop_event.is_set():
            break

        # Sleep interruptibly — check stop_event every second
        elapsed = 0.0
        interval = min(1.0, _tick)
        while elapsed < _tick:
            if stop_event is not None and stop_event.is_set():
                break
            await asyncio.sleep(interval)
            elapsed += interval

    logger.info("reaper_stopped")
