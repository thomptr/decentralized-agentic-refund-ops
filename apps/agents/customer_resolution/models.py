"""Internal domain models for the Customer Resolution Agent.

Phase 14 (T087-T089) expanded CaseStatus to 9 states and ResolutionCase with richer fields.
This module is the authoritative case-state design — it supersedes the Phase 2 (T008) model.

Old 4-state mapping:
  INTAKE              → received
  AWAITING_ANALYSES   → waiting_for_peer_reviews
  DECIDED             → decided
  CLOSED_DIRECT       → closed

Phase 12 PENDING_RISK is kept as a sub-state of waiting_for_peer_reviews
(recorded in status_detail). Phase 12 ESCALATE_HUMAN case status folds into "escalated".
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CaseStatus(StrEnum):
    """9-state resolution case lifecycle.

    Terminal states: decided, response_drafted, closed, escalated, failed
    Active states: received, classified, waiting_for_peer_reviews, ready_for_decision
    """

    RECEIVED = "received"
    CLASSIFIED = "classified"
    WAITING_FOR_PEER_REVIEWS = "waiting_for_peer_reviews"
    READY_FOR_DECISION = "ready_for_decision"
    DECIDED = "decided"
    RESPONSE_DRAFTED = "response_drafted"
    CLOSED = "closed"
    ESCALATED = "escalated"
    FAILED = "failed"


# Monotonic allowed transitions (from → set of valid tos)
_ALLOWED_TRANSITIONS: dict[CaseStatus, frozenset[CaseStatus]] = {
    CaseStatus.RECEIVED: frozenset(
        {
            CaseStatus.CLASSIFIED,
            CaseStatus.READY_FOR_DECISION,
            CaseStatus.ESCALATED,
            CaseStatus.FAILED,
        }
    ),
    CaseStatus.CLASSIFIED: frozenset(
        {
            CaseStatus.WAITING_FOR_PEER_REVIEWS,
            CaseStatus.DECIDED,  # direct_response (no peers)
            CaseStatus.ESCALATED,
            CaseStatus.FAILED,
        }
    ),
    CaseStatus.WAITING_FOR_PEER_REVIEWS: frozenset(
        {CaseStatus.READY_FOR_DECISION, CaseStatus.ESCALATED, CaseStatus.FAILED}
    ),
    CaseStatus.READY_FOR_DECISION: frozenset(
        {CaseStatus.DECIDED, CaseStatus.ESCALATED, CaseStatus.FAILED}
    ),
    CaseStatus.DECIDED: frozenset(
        {CaseStatus.RESPONSE_DRAFTED, CaseStatus.ESCALATED, CaseStatus.FAILED}
    ),
    CaseStatus.RESPONSE_DRAFTED: frozenset({CaseStatus.CLOSED, CaseStatus.ESCALATED}),
    # Terminal states — no transitions allowed
    CaseStatus.CLOSED: frozenset(),
    CaseStatus.ESCALATED: frozenset(),
    CaseStatus.FAILED: frozenset(),
}

_TERMINAL_STATUSES: frozenset[CaseStatus] = frozenset(
    {CaseStatus.CLOSED, CaseStatus.ESCALATED, CaseStatus.FAILED}
)


def can_transition(from_status: CaseStatus, to_status: CaseStatus) -> bool:
    return to_status in _ALLOWED_TRANSITIONS.get(from_status, frozenset())


def assert_transition(from_status: CaseStatus, to_status: CaseStatus) -> None:
    if not can_transition(from_status, to_status):
        raise ValueError(f"Illegal case transition: {from_status.value} → {to_status.value}")


def is_terminal(status: CaseStatus) -> bool:
    return status in _TERMINAL_STATUSES


class Triage(BaseModel):
    """Output of classify(ticket). Pure, deterministic."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    needs_refund_review: bool
    ambiguous: bool
    matched_signals: list[str] = Field(default_factory=list)
    rationale: str
    issue_type: str = "unknown"
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)


class BillingFinding(BaseModel):
    """Normalized billing analysis result.

    Phase 18 (T142) expands eligible: bool to a 4-valued eligibility field.
    A back-compat property `eligible` is kept for Phase 5/15 references.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    eligibility: Literal["eligible", "partial", "ineligible", "indeterminate"] = "eligible"
    requires_human_review: bool = False
    confidence: float | None = None
    summary: str = ""
    performer_agent_id: str = ""
    task_id: UUID | None = None

    @property
    def eligible(self) -> bool:
        return self.eligibility == "eligible"

    @property
    def failed(self) -> bool:
        return False


class BillingSlot(BaseModel):
    """Case slot tracking the billing analysis delegation."""

    model_config = ConfigDict(extra="forbid")

    task_id: UUID | None = None
    received: bool = False
    failed: bool = False
    finding: BillingFinding | None = None
    failure_reason: str | None = None


class RiskFinding(BaseModel):
    """Normalized risk analysis result.

    level ∈ {low, elevated, high} — 'elevated' is the request's 'medium'.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    level: Literal["low", "elevated", "high"] = "low"
    requires_human_review: bool = False
    score: float | None = None
    summary: str = ""
    performer_agent_id: str = ""
    task_id: UUID | None = None

    @property
    def failed(self) -> bool:
        return False


class RiskSlot(BaseModel):
    """Case slot tracking the risk analysis delegation."""

    model_config = ConfigDict(extra="forbid")

    task_id: UUID | None = None
    received: bool = False
    failed: bool = False
    finding: RiskFinding | None = None
    failure_reason: str | None = None


class AnalysisSlot(BaseModel):
    """Generic analysis slot (used in Phase 2; replaced by typed slots in Phase 14)."""

    model_config = ConfigDict(extra="forbid")

    task_id: UUID | None = None
    received: bool = False
    failed: bool = False
    finding: BillingFinding | RiskFinding | None = None
    failure_reason: str | None = None


class PolicyContext(BaseModel):
    """Policy knobs for the decision engine (Phase 18 T144)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_auto_refund_amount: float = 1000.0
    partial_credit_fraction: float = 0.5


class TimeoutStatus(BaseModel):
    """Derived liveness status for the decision engine (Phase 18 T144).

    Computed from pending_tasks and deadline_at; the deadline is recorded
    but not actively enforced (liveness gap, research R6).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    any_missing: bool
    missing_reviews: list[Literal["billing", "risk"]] = Field(default_factory=list)
    deadline_exceeded: bool = False


class RiskAnalysisRequestInput(BaseModel):
    """Input payload for the risk A2A TaskRequest (Phase 12 T068).

    Contains only ticket context — no billing/fraud fields (FR-005, AC1).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: UUID
    ticket_id: str
    customer_id: str
    requested_refund_amount: float
    customer_message_summary: str


class BillingAnalysisRequestInput(BaseModel):
    """Input payload for the billing A2A TaskRequest (Phase 13 T080).

    Contains only ticket context — no billing/fraud-derived fields (FR-005, AC1).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: UUID
    ticket_id: str
    customer_id: str
    requested_refund_amount: float
    purchase_reference: str
    customer_message_summary: str
    policy_context: str


class ResolutionCase(BaseModel):
    """The aggregate case state (Phase 14 T088 authoritative design).

    Mutable (not frozen) since the store updates it.
    Fields billing_result/risk_result supersede AnalysisSlot.finding.
    pending_tasks replaces per-slot received tracking.
    """

    model_config = ConfigDict(extra="forbid")

    # Identity
    case_id: UUID
    ticket_id: str
    customer_id: str
    correlation_id: UUID

    # Ticket context
    ticket_amount: float = 0.0
    ticket_currency: str = ""
    ticket_reason: str = ""

    # Classification
    triage: Triage | None = None

    # Delegation tracking (Phase 14: pending_tasks replaces per-slot received)
    billing_task_id: UUID | None = None
    risk_task_id: UUID | None = None
    pending_tasks: set[UUID] = Field(default_factory=set)

    # Results (Phase 14: replaces AnalysisSlot.finding)
    billing_result: BillingFinding | None = None
    risk_result: RiskFinding | None = None
    billing_slot_failed: bool = False
    risk_slot_failed: bool = False
    billing_failure_reason: str | None = None
    risk_failure_reason: str | None = None

    # Result event ids for evidence (Phase 23 T223)
    billing_result_event_id: UUID | None = None
    risk_result_event_id: UUID | None = None

    # State machine
    status: CaseStatus = CaseStatus.RECEIVED
    status_detail: str | None = None

    # Decision output
    decided_event_id: UUID | None = None
    drafted_event_id: UUID | None = None

    # Timestamps
    created_at: datetime
    updated_at: datetime
    deadline_at: datetime | None = None  # recorded but not enforced (research R6)

    # Optimistic concurrency
    version: int = 0

    def is_ready_to_decide(self) -> bool:
        """True when both peer analyses have been received (or a slot failed).

        A failed slot makes the case immediately decidable even if the other
        slot is still pending (decision-policy.md §C row 2).
        """
        if self.billing_slot_failed or self.risk_slot_failed:
            return True
        return not self.pending_tasks

    def needs_refund_review(self) -> bool:
        return self.triage is not None and self.triage.needs_refund_review


def build_risk_request_input(
    case: ResolutionCase,
) -> RiskAnalysisRequestInput:
    """Pure builder — maps case to risk TaskRequest input (FR-005, AC1)."""
    return RiskAnalysisRequestInput(
        case_id=case.correlation_id,
        ticket_id=case.ticket_id,
        customer_id=case.customer_id,
        requested_refund_amount=case.ticket_amount,
        customer_message_summary=case.ticket_reason,
    )


def build_billing_request_input(
    case: ResolutionCase,
) -> BillingAnalysisRequestInput:
    """Pure builder — maps case to billing TaskRequest input (FR-005, AC1)."""
    return BillingAnalysisRequestInput(
        case_id=case.correlation_id,
        ticket_id=case.ticket_id,
        customer_id=case.customer_id,
        requested_refund_amount=case.ticket_amount,
        purchase_reference=case.ticket_id,
        customer_message_summary=case.ticket_reason,
        policy_context="standard",
    )


def build_timeout_status(case: ResolutionCase, *, now: datetime) -> TimeoutStatus:
    """Derived liveness status — pure, no I/O (Phase 18 T144)."""
    missing: list[Literal["billing", "risk"]] = []
    if case.billing_task_id and case.billing_task_id in case.pending_tasks:
        missing.append("billing")
    if case.risk_task_id and case.risk_task_id in case.pending_tasks:
        missing.append("risk")
    exceeded = case.deadline_at is not None and now > case.deadline_at
    return TimeoutStatus(
        any_missing=len(missing) > 0,
        missing_reviews=missing,
        deadline_exceeded=exceeded,
    )
