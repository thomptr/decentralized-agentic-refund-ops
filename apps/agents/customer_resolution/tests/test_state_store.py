"""Unit tests for InMemoryCaseStateStore (T021, T027, T096-T098, T102-T107, T116-T120)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from apps.agents.customer_resolution.models import (
    BillingFinding,
    CaseStatus,
    ResolutionCase,
    RiskFinding,
)
from apps.agents.customer_resolution.state_store import (
    AttachOutcome,
    CaseSaveConflict,
    InMemoryCaseStateStore,
)


def _make_store() -> InMemoryCaseStateStore:
    return InMemoryCaseStateStore()


async def _create_case(store: InMemoryCaseStateStore, **kwargs) -> ResolutionCase:
    case_id = kwargs.pop("case_id", uuid.uuid4())
    return await store.get_or_create(
        case_id,
        ticket_id=kwargs.get("ticket_id", "TKT-001"),
        customer_id=kwargs.get("customer_id", "CUS-001"),
        correlation_id=kwargs.get("correlation_id", uuid.uuid4()),
        ticket_amount=kwargs.get("ticket_amount", 49.99),
        ticket_currency=kwargs.get("ticket_currency", "USD"),
        ticket_reason=kwargs.get("ticket_reason", "refund please"),
        created_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_get_or_create_idempotent():
    store = _make_store()
    corr_id = uuid.uuid4()
    case1 = await _create_case(store, correlation_id=corr_id)
    case2 = await _create_case(store, correlation_id=corr_id)
    assert case1.case_id == case2.case_id
    assert case1.version == case2.version


@pytest.mark.asyncio
async def test_get_by_correlation_id():
    store = _make_store()
    corr_id = uuid.uuid4()
    case = await _create_case(store, correlation_id=corr_id)
    found = await store.get_by_correlation_id(corr_id)
    assert found is not None
    assert found.case_id == case.case_id


@pytest.mark.asyncio
async def test_get_by_task_id():
    store = _make_store()
    corr_id = uuid.uuid4()
    case = await _create_case(store, correlation_id=corr_id)
    task_id = uuid.uuid4()
    await store.add_pending_task(case.case_id, task_id)
    found = await store.get_by_task_id(task_id)
    assert found is not None
    assert found.case_id == case.case_id


@pytest.mark.asyncio
async def test_apply_result_billing():
    store = _make_store()
    case = await _create_case(store)
    task_id = uuid.uuid4()
    case.billing_task_id = task_id
    await store.save(case)
    await store.add_pending_task(case.case_id, task_id)

    finding = BillingFinding(eligibility="eligible", task_id=task_id)
    outcome = await store.apply_result(case.case_id, task_id, finding)
    assert outcome == AttachOutcome.ATTACHED

    case = await store.get(case.case_id)
    assert case.billing_result is not None
    assert task_id not in case.pending_tasks


@pytest.mark.asyncio
async def test_apply_result_duplicate_is_no_op():
    store = _make_store()
    case = await _create_case(store)
    task_id = uuid.uuid4()
    case.billing_task_id = task_id
    await store.save(case)
    await store.add_pending_task(case.case_id, task_id)

    finding = BillingFinding(eligibility="eligible", task_id=task_id)
    await store.apply_result(case.case_id, task_id, finding)
    # Second application — task_id no longer in pending_tasks
    outcome2 = await store.apply_result(case.case_id, task_id, finding)
    assert outcome2 == AttachOutcome.DUPLICATE


@pytest.mark.asyncio
async def test_case_ready_for_decision_when_both_results():
    store = _make_store()
    case = await _create_case(store)
    billing_tid = uuid.uuid4()
    risk_tid = uuid.uuid4()
    case.billing_task_id = billing_tid
    case.risk_task_id = risk_tid
    await store.save(case)
    await store.add_pending_task(case.case_id, billing_tid)
    await store.add_pending_task(case.case_id, risk_tid)

    await store.apply_result(
        case.case_id, billing_tid, BillingFinding(eligibility="eligible", task_id=billing_tid)
    )
    # One result: still waiting
    case = await store.get(case.case_id)
    assert case.status != CaseStatus.READY_FOR_DECISION

    await store.apply_result(case.case_id, risk_tid, RiskFinding(level="low", task_id=risk_tid))
    case = await store.get(case.case_id)
    assert case.status == CaseStatus.READY_FOR_DECISION


@pytest.mark.asyncio
async def test_mark_slot_failed_short_circuits():
    store = _make_store()
    case = await _create_case(store)
    task_id = uuid.uuid4()
    case.billing_task_id = task_id
    await store.save(case)
    await store.add_pending_task(case.case_id, task_id)

    await store.mark_slot_failed(case.case_id, task_id, is_billing=True, reason="test_fail")
    case = await store.get(case.case_id)
    assert case.billing_slot_failed is True
    assert case.status == CaseStatus.READY_FOR_DECISION


@pytest.mark.asyncio
async def test_illegal_transition_raises():
    store = _make_store()
    case = await _create_case(store)
    # closed → received is illegal
    case.status = CaseStatus.CLOSED
    await store.save(case)
    with pytest.raises(ValueError):
        await store.transition(case.case_id, CaseStatus.RECEIVED)


@pytest.mark.asyncio
async def test_save_with_stale_version_raises():
    store = _make_store()
    case = await _create_case(store)
    original_version = case.version
    await store.save(case)  # bumps version
    with pytest.raises(CaseSaveConflict):
        await store.save(case, expected_version=original_version)


@pytest.mark.asyncio
async def test_unknown_case_returns_none():
    store = _make_store()
    result = await store.get(uuid.uuid4())
    assert result is None
    result2 = await store.get_by_correlation_id(uuid.uuid4())
    assert result2 is None
    result3 = await store.get_by_task_id(uuid.uuid4())
    assert result3 is None


# ---------------------------------------------------------------------------
# T004: list_timed_out_cases unit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_timed_out_cases_past_deadline_with_pending():
    """A non-terminal case past its deadline with pending tasks is returned."""
    store = _make_store()
    case = await _create_case(store)
    task_id = uuid.uuid4()
    await store.add_pending_task(case.case_id, task_id)

    past = datetime(2020, 1, 1, tzinfo=UTC)
    store.set_deadline(case.case_id, past)

    now = datetime(2026, 1, 1, tzinfo=UTC)
    timed_out = await store.list_timed_out_cases(now)
    assert len(timed_out) == 1
    assert timed_out[0].case_id == case.case_id


@pytest.mark.asyncio
async def test_list_timed_out_cases_no_deadline_excluded():
    """A case without a deadline is not returned even if it has pending tasks."""
    store = _make_store()
    case = await _create_case(store)
    task_id = uuid.uuid4()
    await store.add_pending_task(case.case_id, task_id)
    # deadline_at stays None

    now = datetime(2026, 1, 1, tzinfo=UTC)
    timed_out = await store.list_timed_out_cases(now)
    assert timed_out == []


@pytest.mark.asyncio
async def test_list_timed_out_cases_future_deadline_excluded():
    """A case whose deadline is in the future is not returned."""
    store = _make_store()
    case = await _create_case(store)
    task_id = uuid.uuid4()
    await store.add_pending_task(case.case_id, task_id)

    future = datetime(2099, 1, 1, tzinfo=UTC)
    store.set_deadline(case.case_id, future)

    now = datetime(2026, 1, 1, tzinfo=UTC)
    timed_out = await store.list_timed_out_cases(now)
    assert timed_out == []


@pytest.mark.asyncio
async def test_list_timed_out_cases_empty_pending_excluded():
    """A past-deadline case with no pending tasks is not returned."""
    store = _make_store()
    case = await _create_case(store)
    # pending_tasks stays empty (never added a task)

    past = datetime(2020, 1, 1, tzinfo=UTC)
    store.set_deadline(case.case_id, past)

    now = datetime(2026, 1, 1, tzinfo=UTC)
    timed_out = await store.list_timed_out_cases(now)
    assert timed_out == []


@pytest.mark.asyncio
async def test_list_timed_out_cases_terminal_excluded():
    """A terminal (CLOSED/ESCALATED/DECIDED) case is not returned even if past deadline."""
    store = _make_store()
    for terminal_status in (CaseStatus.CLOSED, CaseStatus.ESCALATED, CaseStatus.DECIDED):
        case = await _create_case(store, case_id=uuid.uuid4(), correlation_id=uuid.uuid4())
        task_id = uuid.uuid4()
        await store.add_pending_task(case.case_id, task_id)
        past = datetime(2020, 1, 1, tzinfo=UTC)
        store.set_deadline(case.case_id, past)
        # Force terminal status directly
        live_case = await store.get(case.case_id)
        live_case.status = terminal_status
        await store.save(live_case)

    now = datetime(2026, 1, 1, tzinfo=UTC)
    timed_out = await store.list_timed_out_cases(now)
    assert timed_out == []
