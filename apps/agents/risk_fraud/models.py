"""Domain models for the Risk and Fraud Agent."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from packages.contracts.events.payloads import EvidenceItem


class RiskLevel(StrEnum):
    LOW = "low"
    ELEVATED = "elevated"
    HIGH = "high"


class RecommendedAction(StrEnum):
    APPROVE_RISK_CLEARANCE = "approve_risk_clearance"
    ALLOW_WITH_CAUTION = "allow_with_caution"
    DENY_OR_ESCALATE = "deny_or_escalate"
    REQUEST_MORE_INFORMATION = "request_more_information"
    MANUAL_REVIEW = "manual_review"


# ---------------------------------------------------------------------------
# Owned-signal models (T005) — one per domain signal area
# ---------------------------------------------------------------------------


class AccountStanding(BaseModel):
    """Account-level standing and tenure signals."""

    model_config = ConfigDict(frozen=True)

    customer_id: str
    status: Literal["good", "watch", "restricted"] = "good"
    tenure_days: int = 0
    support_abuse_flags: int = Field(default=0, ge=0)
    known_good_customer: bool = False
    segment: Literal["standard", "vip", "enterprise"] = "standard"


class RefundDisputeHistory(BaseModel):
    """Historical refund and dispute signals."""

    model_config = ConfigDict(frozen=True)

    customer_id: str
    prior_refunds: int = 0
    prior_refund_total_amount: float = Field(default=0.0, ge=0.0)
    chargebacks: int = 0
    velocity_window_days: int = 30


class PaymentInstrumentSignal(BaseModel):
    """Payment instrument health and fraud-pattern signals."""

    model_config = ConfigDict(frozen=True)

    customer_id: str
    billing_details_match: bool = True
    card_testing_pattern: bool = False
    recent_failed_payments: int = Field(default=0, ge=0)


class BehavioralSignal(BaseModel):
    """Behavioral anomaly and device/IP signals."""

    model_config = ConfigDict(frozen=True)

    customer_id: str
    refund_requests_in_window: int = 0
    anomaly_score: float = Field(default=0.0, ge=0.0, le=1.0)
    device_mismatch: bool = False
    ip_location_mismatch: bool = False
    ip_country_mismatch: bool = False
    device_change_count: int = Field(default=0, ge=0)
    typical_refund_amount: float | None = Field(default=None, ge=0)


class KnownFraudIndicator(BaseModel):
    """Known-fraud blocklist indicator."""

    model_config = ConfigDict(frozen=True)

    customer_id: str
    on_blocklist: bool = False


class RiskSignals(BaseModel):
    """Aggregate container for all owned risk/fraud signals for a customer."""

    model_config = ConfigDict(frozen=True)

    customer_id: str
    account_standing: AccountStanding | None = None
    refund_history: RefundDisputeHistory | None = None
    payment_instrument: PaymentInstrumentSignal | None = None
    behavioral: BehavioralSignal | None = None
    known_fraud: KnownFraudIndicator | None = None


# ---------------------------------------------------------------------------
# Output model (T006)
# ---------------------------------------------------------------------------


class RiskAssessment(BaseModel):
    """Structured risk/fraud assessment result produced by the scoring engine."""

    model_config = ConfigDict(frozen=True)

    risk_level: RiskLevel
    recommended_action: RecommendedAction
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    evidence: list[EvidenceItem]
    policy_references: list[str]
    reasoning_summary: str
    requires_human_review: bool


# ---------------------------------------------------------------------------
# Input model (T009)
# ---------------------------------------------------------------------------


class RiskAssessmentRequest(BaseModel):
    """Structured input for the assess_fraud_risk A2A capability."""

    model_config = ConfigDict(extra="ignore")

    case_id: UUID
    ticket_id: Annotated[str, Field(min_length=1)]
    customer_id: Annotated[str, Field(min_length=1)]
    requested_refund_amount: Annotated[Decimal, Field(ge=0)] | None = None
    customer_message_summary: str | None = None
    account_age_days: Annotated[int, Field(ge=0)] | None = None
    metadata: dict | None = None


# Alias as requested in spec
RefundRiskAssessmentRequest = RiskAssessmentRequest


__all__ = [
    "EvidenceItem",
    "RiskLevel",
    "RecommendedAction",
    "AccountStanding",
    "RefundDisputeHistory",
    "PaymentInstrumentSignal",
    "BehavioralSignal",
    "KnownFraudIndicator",
    "RiskSignals",
    "RiskAssessment",
    "RiskAssessmentRequest",
    "RefundRiskAssessmentRequest",
]
