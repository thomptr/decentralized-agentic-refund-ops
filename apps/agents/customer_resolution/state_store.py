"""Pluggable case state store (Phase 14 T090-T094 authoritative design).

CaseStateStore is an abstract async interface; InMemoryCaseStateStore is the PoC implementation.
A Postgres or DynamoDB backend can be dropped in by implementing the same Protocol.

Durability across restart is a documented PoC gap (research R6).
"""

from __future__ import annotations

import asyncio
from collections import deque
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

import structlog

from apps.agents.customer_resolution.models import (
    BillingFinding,
    CaseStatus,
    ResolutionCase,
    RiskFinding,
    assert_transition,
    is_terminal,
)

logger = structlog.get_logger(__name__)

_PARKED_BUFFER_MAX = 200


class AttachOutcome(str):
    ATTACHED = "attached"
    UNKNOWN_CASE = "unknown_case"
    DUPLICATE = "duplicate"


class CaseSaveConflict(Exception):
    """Raised when save() detects a stale expected_version."""


class CaseStateStore(Protocol):
    """Storage-agnostic async interface for resolution case state.

    Any persistent backend (Postgres, DynamoDB) satisfies this Protocol
    without changing the handlers.
    """

    async def get_or_create(
        self,
        case_id: UUID,
        *,
        ticket_id: str,
        customer_id: str,
        correlation_id: UUID,
        ticket_amount: float,
        ticket_currency: str,
        ticket_reason: str,
        created_at: datetime,
    ) -> ResolutionCase: ...

    async def get(self, case_id: UUID) -> ResolutionCase | None: ...

    async def get_by_correlation_id(self, correlation_id: UUID) -> ResolutionCase | None: ...

    async def get_by_task_id(self, task_id: UUID) -> ResolutionCase | None: ...

    async def save(
        self,
        case: ResolutionCase,
        *,
        expected_version: int | None = None,
    ) -> ResolutionCase: ...

    async def transition(self, case_id: UUID, to_status: CaseStatus) -> ResolutionCase: ...


class InMemoryCaseStateStore:
    """In-process CaseStateStore implementation (Phase 14 T091).

    Primary index: dict[UUID, ResolutionCase] keyed by case_id.
    Secondary indexes: correlation_id → case_id, task_id → case_id.
    All mutations are guarded by an asyncio.Lock.
    """

    def __init__(self) -> None:
        self._cases: dict[UUID, ResolutionCase] = {}
        self._by_correlation: dict[UUID, UUID] = {}
        self._by_task_id: dict[UUID, UUID] = {}
        self._lock = asyncio.Lock()
        # Bounded parking buffer for results with no matching case (research R6)
        self._parked_billing: deque[tuple[UUID, Any]] = deque(maxlen=_PARKED_BUFFER_MAX)
        self._parked_risk: deque[tuple[UUID, Any]] = deque(maxlen=_PARKED_BUFFER_MAX)

    async def get_or_create(
        self,
        case_id: UUID,
        *,
        ticket_id: str,
        customer_id: str,
        correlation_id: UUID,
        ticket_amount: float = 0.0,
        ticket_currency: str = "",
        ticket_reason: str = "",
        created_at: datetime,
    ) -> ResolutionCase:
        """Idempotent — returns existing case on re-delivery (FR-011)."""
        async with self._lock:
            existing_id = self._by_correlation.get(correlation_id)
            if existing_id is not None and existing_id in self._cases:
                return self._cases[existing_id]
            if case_id in self._cases:
                return self._cases[case_id]

            now = created_at
            case = ResolutionCase(
                case_id=case_id,
                ticket_id=ticket_id,
                customer_id=customer_id,
                correlation_id=correlation_id,
                ticket_amount=ticket_amount,
                ticket_currency=ticket_currency,
                ticket_reason=ticket_reason,
                status=CaseStatus.RECEIVED,
                created_at=now,
                updated_at=now,
            )
            self._cases[case_id] = case
            self._by_correlation[correlation_id] = case_id
            return case

    async def get(self, case_id: UUID) -> ResolutionCase | None:
        return self._cases.get(case_id)

    async def get_by_correlation_id(self, correlation_id: UUID) -> ResolutionCase | None:
        case_id = self._by_correlation.get(correlation_id)
        if case_id is None:
            return None
        return self._cases.get(case_id)

    async def get_by_task_id(self, task_id: UUID) -> ResolutionCase | None:
        case_id = self._by_task_id.get(task_id)
        if case_id is None:
            return None
        return self._cases.get(case_id)

    async def save(
        self,
        case: ResolutionCase,
        *,
        expected_version: int | None = None,
    ) -> ResolutionCase:
        """Persist an updated case. Raises CaseSaveConflict on stale version."""
        async with self._lock:
            existing = self._cases.get(case.case_id)
            if (
                existing is not None
                and expected_version is not None
                and existing.version != expected_version
            ):
                raise CaseSaveConflict(
                    f"case {case.case_id}: expected version {expected_version}, "
                    f"found {existing.version}"
                )
            case.version = (existing.version + 1) if existing else 0
            case.updated_at = datetime.now(UTC)
            self._cases[case.case_id] = case
            self._by_correlation[case.correlation_id] = case.case_id
            return case

    async def transition(self, case_id: UUID, to_status: CaseStatus) -> ResolutionCase:
        """Validate and apply a status transition (Phase 14 T089)."""
        async with self._lock:
            case = self._cases.get(case_id)
            if case is None:
                raise KeyError(f"Case not found: {case_id}")
            assert_transition(case.status, to_status)
            case.status = to_status
            case.version += 1
            case.updated_at = datetime.now(UTC)
            return case

    async def add_pending_task(self, case_id: UUID, task_id: UUID) -> None:
        """Register a pending task and update the secondary task_id index."""
        async with self._lock:
            case = self._cases.get(case_id)
            if case is None:
                raise KeyError(f"Case not found: {case_id}")
            case.pending_tasks.add(task_id)
            self._by_task_id[task_id] = case_id

    async def apply_result(
        self,
        case_id: UUID,
        task_id: UUID,
        finding: BillingFinding | RiskFinding,
    ) -> str:
        """Apply a peer result to the case (Phase 14 T092).

        Returns AttachOutcome.ATTACHED, .DUPLICATE, or .UNKNOWN_CASE.
        A task_id absent from pending_tasks is a logged no-op (T093).
        When pending_tasks becomes empty the case transitions to ready_for_decision.
        """
        async with self._lock:
            case = self._cases.get(case_id)
            if case is None:
                return AttachOutcome.UNKNOWN_CASE

            if is_terminal(case.status) or case.status == CaseStatus.DECIDED:
                logger.info(
                    "apply_result_after_terminal",
                    case_id=str(case_id),
                    task_id=str(task_id),
                    status=case.status.value,
                )
                return AttachOutcome.DUPLICATE

            if task_id not in case.pending_tasks:
                logger.info(
                    "apply_result_duplicate",
                    case_id=str(case_id),
                    task_id=str(task_id),
                )
                return AttachOutcome.DUPLICATE

            if isinstance(finding, BillingFinding):
                case.billing_result = finding
            else:
                case.risk_result = finding

            case.pending_tasks.discard(task_id)
            case.updated_at = datetime.now(UTC)
            case.version += 1

            # Both results received — advance to ready_for_decision
            if not case.pending_tasks and can_transition_to_ready(case.status):
                case.status = CaseStatus.READY_FOR_DECISION

            return AttachOutcome.ATTACHED

    async def mark_slot_failed(
        self,
        case_id: UUID,
        task_id: UUID,
        *,
        is_billing: bool,
        reason: str,
    ) -> None:
        """Record a failed/rejected peer result and advance state."""
        async with self._lock:
            case = self._cases.get(case_id)
            if case is None:
                return
            if is_terminal(case.status):
                return
            if is_billing:
                case.billing_slot_failed = True
                case.billing_failure_reason = reason
            else:
                case.risk_slot_failed = True
                case.risk_failure_reason = reason

            case.pending_tasks.discard(task_id)
            case.updated_at = datetime.now(UTC)
            case.version += 1

            # A failed slot short-circuits to ready_for_decision (decision-policy.md §C row 2)
            if can_transition_to_ready(case.status):
                case.status = CaseStatus.READY_FOR_DECISION

    def park_billing_result(self, correlation_id: UUID, payload: Any) -> None:
        """Park an unmatched billing result (AC2, Phase 15)."""
        logger.warning(
            "billing_result_unknown_case",
            correlation_id=str(correlation_id),
        )
        self._parked_billing.append((correlation_id, payload))

    def park_risk_result(self, correlation_id: UUID, payload: Any) -> None:
        """Park an unmatched risk result (AC2, Phase 16)."""
        logger.warning(
            "risk_result_unknown_case",
            correlation_id=str(correlation_id),
        )
        self._parked_risk.append((correlation_id, payload))

    def set_deadline(self, case_id: UUID, deadline_at: datetime) -> None:
        """Record delegation deadline (not enforced — research R6)."""
        case = self._cases.get(case_id)
        if case is not None:
            case.deadline_at = deadline_at


def can_transition_to_ready(status: CaseStatus) -> bool:
    from apps.agents.customer_resolution.models import CaseStatus

    return status in {
        CaseStatus.RECEIVED,
        CaseStatus.CLASSIFIED,
        CaseStatus.WAITING_FOR_PEER_REVIEWS,
        CaseStatus.READY_FOR_DECISION,
    }
