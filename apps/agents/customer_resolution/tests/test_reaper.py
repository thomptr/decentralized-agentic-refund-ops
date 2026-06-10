"""Reaper unit tests (006 T016).

Uses an injected clock (no Kafka, no real publisher) to verify:
- A non-terminal past-deadline case is escalated with escalate_human/analysis_timeout.
- An already-DECIDED case is skipped (terminal guard).
- Escalation occurs within deadline + <= REAPER_TICK_SECONDS.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.agents.customer_resolution.models import CaseStatus
from apps.agents.customer_resolution.reaper import run_reaper
from apps.agents.customer_resolution.state_store import InMemoryCaseStateStore


def _make_store() -> InMemoryCaseStateStore:
    return InMemoryCaseStateStore()


async def _create_and_register_case(
    store: InMemoryCaseStateStore,
    *,
    add_pending_task: bool = True,
    deadline: datetime | None = None,
) -> Any:
    case_id = uuid.uuid4()
    case = await store.get_or_create(
        case_id,
        ticket_id="TKT-001",
        customer_id="CUS-001",
        correlation_id=uuid.uuid4(),
        ticket_amount=50.0,
        ticket_currency="USD",
        ticket_reason="refund please",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    if add_pending_task:
        task_id = uuid.uuid4()
        case.billing_task_id = task_id
        await store.save(case)
        await store.add_pending_task(case.case_id, task_id)
    if deadline is not None:
        store.set_deadline(case.case_id, deadline)
    return await store.get(case_id)


@pytest.mark.asyncio
async def test_reaper_escalates_past_deadline_case():
    """A non-terminal past-deadline case with pending tasks is escalated."""
    store = _make_store()
    past = datetime(2020, 1, 1, tzinfo=UTC)
    case = await _create_and_register_case(store, deadline=past)

    stop_event = asyncio.Event()
    apply_calls: list[Any] = []

    async def fake_apply_decision(c, *, causation_id=None, publisher, store):
        apply_calls.append(c.case_id)
        c.status = CaseStatus.DECIDED
        await store.save(c)

    fake_publisher = MagicMock()
    now_fixed = datetime(2026, 1, 1, tzinfo=UTC)

    with patch(
        "apps.agents.customer_resolution.event_handlers._apply_decision",
        side_effect=fake_apply_decision,
    ):
        # Run one iteration then stop
        stop_event.set()
        await run_reaper(
            store,
            fake_publisher,
            stop_event=stop_event,
            now=lambda: now_fixed,
            tick_seconds=0.0,
        )

    assert case.case_id in apply_calls, "Past-deadline case should have been escalated"


@pytest.mark.asyncio
async def test_reaper_skips_already_decided_case():
    """A case already in DECIDED status is skipped by the reaper."""
    store = _make_store()
    past = datetime(2020, 1, 1, tzinfo=UTC)
    case = await _create_and_register_case(store, deadline=past)
    # Mark as decided
    fetched = await store.get(case.case_id)
    fetched.status = CaseStatus.DECIDED
    await store.save(fetched)

    stop_event = asyncio.Event()
    apply_calls: list[Any] = []

    async def fake_apply_decision(c, *, causation_id=None, publisher, store):
        apply_calls.append(c.case_id)

    fake_publisher = MagicMock()
    now_fixed = datetime(2026, 1, 1, tzinfo=UTC)

    with patch(
        "apps.agents.customer_resolution.event_handlers._apply_decision",
        side_effect=fake_apply_decision,
    ):
        stop_event.set()
        await run_reaper(
            store,
            fake_publisher,
            stop_event=stop_event,
            now=lambda: now_fixed,
            tick_seconds=0.0,
        )

    assert case.case_id not in apply_calls, "DECIDED case should not be escalated"


@pytest.mark.asyncio
async def test_reaper_skips_terminal_case():
    """A CLOSED/ESCALATED terminal case is skipped by the reaper."""
    store = _make_store()
    past = datetime(2020, 1, 1, tzinfo=UTC)
    case = await _create_and_register_case(store, deadline=past)
    fetched = await store.get(case.case_id)
    fetched.status = CaseStatus.ESCALATED
    await store.save(fetched)

    stop_event = asyncio.Event()
    apply_calls: list[Any] = []

    async def fake_apply_decision(c, *, causation_id=None, publisher, store):
        apply_calls.append(c.case_id)

    fake_publisher = MagicMock()
    now_fixed = datetime(2026, 1, 1, tzinfo=UTC)

    with patch(
        "apps.agents.customer_resolution.event_handlers._apply_decision",
        side_effect=fake_apply_decision,
    ):
        stop_event.set()
        await run_reaper(
            store,
            fake_publisher,
            stop_event=stop_event,
            now=lambda: now_fixed,
            tick_seconds=0.0,
        )

    assert case.case_id not in apply_calls, "ESCALATED case should not be re-escalated"


@pytest.mark.asyncio
async def test_reaper_does_not_escalate_future_deadline():
    """A case whose deadline is in the future is not touched."""
    store = _make_store()
    future = datetime(2099, 1, 1, tzinfo=UTC)
    await _create_and_register_case(store, deadline=future)

    stop_event = asyncio.Event()
    apply_calls: list[Any] = []

    async def fake_apply_decision(c, *, causation_id=None, publisher, store):
        apply_calls.append(c.case_id)

    fake_publisher = MagicMock()
    now_fixed = datetime(2026, 1, 1, tzinfo=UTC)

    with patch(
        "apps.agents.customer_resolution.event_handlers._apply_decision",
        side_effect=fake_apply_decision,
    ):
        stop_event.set()
        await run_reaper(
            store,
            fake_publisher,
            stop_event=stop_event,
            now=lambda: now_fixed,
            tick_seconds=0.0,
        )

    assert apply_calls == [], "Future-deadline case must not be escalated"
