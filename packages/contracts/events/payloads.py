"""Domain event payload models for future business agents.

These contracts are NOT registered in the foundation PAYLOAD_REGISTRY.
Future agents import from here and register their own event types.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EvidenceItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str
    description: str
    value: Any


class SupportTicketCreatedPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_id: str
    customer_id: str
    amount: float
    currency: str
    reason: str
    created_at: datetime


# --- Customer Resolution Agent contracts (Feature 003) ---


class ResolutionOutcome(StrEnum):
    """Possible outcomes for a customer resolution case."""

    APPROVE_REFUND = "approve_refund"
    DENY_REFUND = "deny_refund"
    ESCALATE_HUMAN = "escalate_human"
    DIRECT_RESPONSE = "direct_response"
    # Phase 18 extensions:
    OFFER_PARTIAL_CREDIT = "offer_partial_credit"
    REQUEST_MORE_INFORMATION = "request_more_information"


class CustomerResponseDecisionPayload(BaseModel):
    """Final decision emitted on TOPIC_RESOLUTION_DECIDED (local.customer.resolution.decided.v1).

    Note: Phase 23 introduces CustomerResolutionDecidedPayload as the authoritative
    replacement on a new topic. This payload is retained for backward compatibility
    during the transition.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: UUID
    ticket_id: str
    customer_id: str
    outcome: ResolutionOutcome
    customer_response: str
    escalation_reason: str | None = None
    billing_summary: str | None = None
    risk_summary: str | None = None
    rationale: str = ""

    @model_validator(mode="after")
    def validate_escalation_reason(self) -> CustomerResponseDecisionPayload:
        if self.outcome == ResolutionOutcome.ESCALATE_HUMAN and not self.escalation_reason:
            raise ValueError("escalation_reason is required when outcome is escalate_human")
        return self


class CustomerIssueClassifiedPayload(BaseModel):
    """Emitted immediately after triage on local.resolution.customer-issue.classified.v1."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: UUID
    ticket_id: str
    customer_id: str
    issue_type: str
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    requires_billing_review: bool
    requires_risk_review: bool
    requires_human_review: bool
    reasoning_summary: str


class RefundReviewRequestedPayload(BaseModel):
    """Emitted after A2A task requests are sent on local.resolution.refund-review.requested.v1.

    Repurposed from the old per-review shape (Phase 11). The aggregate shape records
    both billing and risk task ids so the announcement is traceable.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: UUID
    ticket_id: str
    customer_id: str
    requested_reviews: list[Literal["billing", "risk"]]
    billing_task_id: UUID
    risk_task_id: UUID
    timeout_seconds: int | None = None
    requested_by_agent_id: str = "customer-resolution-agent"
    requested_at: datetime

    @model_validator(mode="after")
    def validate_reviews(self) -> RefundReviewRequestedPayload:
        if not self.requested_reviews:
            raise ValueError("requested_reviews must be non-empty")
        if len(self.requested_reviews) != len(set(self.requested_reviews)):
            raise ValueError("requested_reviews must not contain duplicates")
        return self


class CustomerResponseDraftedPayload(BaseModel):
    """Emitted after every final decision on local.resolution.customer-response.drafted.v1.

    Carries only the customer-facing draft (no internal rationale). Phase 17 (T127).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: UUID
    ticket_id: str
    customer_id: str
    decision_event_id: UUID
    outcome: ResolutionOutcome
    draft_response: str
    requires_human_approval: bool
    drafted_by_agent_id: str = "customer-resolution-agent"
    drafted_at: datetime

    @model_validator(mode="after")
    def validate_draft_payload(self) -> CustomerResponseDraftedPayload:
        if not self.draft_response.strip():
            raise ValueError("draft_response must be non-empty")
        if self.outcome == ResolutionOutcome.ESCALATE_HUMAN and not self.requires_human_approval:
            raise ValueError("requires_human_approval must be True when outcome is escalate_human")
        return self


class BillingRefundAnalysisCompletedPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    # Original fields (preserved for 003 consumer compatibility)
    ticket_id: str
    recommendation: str
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    evidence: list[EvidenceItem]
    reasoning_summary: str
    requires_human_review: bool
    # Expanded fields (T003 — new fields carry safe defaults for backward compatibility)
    case_id: UUID
    customer_id: str
    billing_account_id: str | None = None
    subscription_status: str = "unknown"
    invoice_status: str = "unknown"
    payment_status: str = "unknown"
    entitlement_status: str = "unknown"
    usage_level: str = "unknown"
    refund_window_status: str = "unknown"
    eligible_refund_amount: Decimal = Decimal("0.00")


class RiskReviewCompletedPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_id: str
    recommendation: str
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    evidence: list[EvidenceItem]
    reasoning_summary: str
    requires_human_review: bool


class AgentTaskAcceptedPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: UUID
    accepted_by_agent_id: str
    accepted_at: datetime


class AgentTaskCompletedPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: UUID
    recommendation: str
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    evidence: list[EvidenceItem]
    reasoning_summary: str
    requires_human_review: bool


class AgentTaskFailedPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: UUID
    error_message: str
    error_code: str | None = None
    failed_at: datetime


__all__ = [
    "EvidenceItem",
    "SupportTicketCreatedPayload",
    "ResolutionOutcome",
    "CustomerResponseDecisionPayload",
    "CustomerIssueClassifiedPayload",
    "CustomerResponseDraftedPayload",
    "RefundReviewRequestedPayload",
    "BillingRefundAnalysisCompletedPayload",
    "RiskReviewCompletedPayload",
    "AgentTaskAcceptedPayload",
    "AgentTaskCompletedPayload",
    "AgentTaskFailedPayload",
]
