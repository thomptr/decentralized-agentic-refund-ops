"""Domain event payload models for future business agents.

These contracts are NOT registered in the foundation PAYLOAD_REGISTRY.
Future agents import from here and register their own event types.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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


class RefundReviewRequestedPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_id: str
    customer_id: str
    amount: float
    currency: str
    review_type: Literal["billing", "risk", "combined"]
    requested_by_agent_id: str


class BillingRefundAnalysisCompletedPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_id: str
    recommendation: str
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    evidence: list[EvidenceItem]
    reasoning_summary: str
    requires_human_review: bool


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
    "RefundReviewRequestedPayload",
    "BillingRefundAnalysisCompletedPayload",
    "RiskReviewCompletedPayload",
    "AgentTaskAcceptedPayload",
    "AgentTaskCompletedPayload",
    "AgentTaskFailedPayload",
]
