"""Domain models for the Billing and Entitlement Agent."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from packages.contracts.events.payloads import EvidenceItem


class Recommendation(StrEnum):
    APPROVE_FULL_REFUND = "approve_full_refund"
    APPROVE_PARTIAL_REFUND = "approve_partial_refund"
    DENY_REFUND = "deny_refund"
    REQUEST_MORE_INFORMATION = "request_more_information"
    MANUAL_REVIEW = "manual_review"


class RefundEligibilityRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    case_id: UUID
    ticket_id: str
    customer_id: str
    requested_refund_amount: Annotated[float, Field(ge=0)]
    purchase_reference: str
    customer_message_summary: str | None = None
    policy_context: str | None = None


class Subscription(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subscription_id: str
    status: Literal["active", "cancelled", "lapsed"]
    term: Literal["monthly", "annual"]
    started_at: datetime
    renewed_at: datetime | None = None


class Invoice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invoice_id: str
    purchase_reference: str
    amount: float
    currency: str
    issued_at: datetime
    paid: bool


class Payment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payment_id: str
    invoice_id: str
    captured: bool
    amount: float
    reversed_amount: float  # >= 0; a recorded refund/reversal already applied


class Entitlement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entitlement_id: str
    subscription_id: str
    status: Literal["active", "revoked"]
    delivered: bool
    # Entitlement-checker signals (T005/T054)
    access_granted: bool = False
    access_used: bool = False
    feature_enabled: bool = False
    account_active: bool = False


class ProductUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    usage_units: float
    allotment_units: float

    @property
    def usage_ratio(self) -> float:
        if self.allotment_units == 0:
            return 0.0
        return self.usage_units / self.allotment_units


class BillingFacts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subscription: Subscription | None = None
    invoice: Invoice | None = None
    payment: Payment | None = None
    entitlement: Entitlement | None = None
    usage: ProductUsage | None = None


class EligibilityRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recommendation: Recommendation
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    evidence: list[EvidenceItem]
    policy_references: list[str]
    reasoning_summary: str
    requires_human_review: bool
    eligible_refund_amount: Decimal
    # Derived billing-status strings (populated by the rules engine)
    subscription_status: str
    invoice_status: str
    payment_status: str
    entitlement_status: str
    usage_level: str
    refund_window_status: str


__all__ = [
    "EvidenceItem",
    "Recommendation",
    "RefundEligibilityRequest",
    "Subscription",
    "Invoice",
    "Payment",
    "Entitlement",
    "ProductUsage",
    "BillingFacts",
    "EligibilityRecommendation",
]
