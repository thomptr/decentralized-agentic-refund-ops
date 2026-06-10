"""Orchestration service — validate → load facts → evaluate → build outputs (T011/T014/T023).

Pure functions; no Kafka, no side effects.
"""

from __future__ import annotations

from decimal import Decimal

from agent_foundation.a2a import A2AMessage, A2APart
from apps.agents.billing_entitlement.mock_data import load_facts
from apps.agents.billing_entitlement.models import (
    BillingFacts,
    EligibilityRecommendation,
    Recommendation,
    RefundEligibilityRequest,
)
from apps.agents.billing_entitlement.policy import REFUND_POLICY
from apps.agents.billing_entitlement.rules_engine import evaluate
from packages.contracts.events.payloads import BillingRefundAnalysisCompletedPayload, EvidenceItem


def validate_input(parts: list) -> RefundEligibilityRequest:
    """Extract and validate the data part from A2A input parts.

    Raises ValueError if no data part is present or the data fails validation.
    No fabricated verdict — callers should let this propagate so the runtime emits a failed result.
    """
    for part in parts:
        if getattr(part, "type", None) == "data" and part.data:
            return RefundEligibilityRequest.model_validate(part.data)
    raise ValueError("No valid data part found in input parts (FR-011)")


def _missing_data_recommendation(purchase_reference: str) -> EligibilityRecommendation:
    return EligibilityRecommendation(
        recommendation=Recommendation.REQUEST_MORE_INFORMATION,
        confidence=0.2,
        evidence=[
            EvidenceItem(
                source="refund_policy",
                description="Data-completeness gate: no billing record found",
                value={"reason": f"no billing record for purchase_reference={purchase_reference!r}"},
            )
        ],
        policy_references=[],
        reasoning_summary=(
            f"No billing record found for purchase_reference={purchase_reference!r}. "
            "Manual review required (FR-010)."
        ),
        requires_human_review=True,
        eligible_refund_amount=Decimal("0.00"),
        subscription_status="unknown",
        invoice_status="unknown",
        payment_status="unknown",
        entitlement_status="unknown",
        usage_level="unknown",
        refund_window_status="unknown",
    )


def analyze(
    parts: list,
) -> tuple[RefundEligibilityRequest, EligibilityRecommendation, BillingFacts | None]:
    """Full pipeline: validate input → load facts → evaluate → return (request, rec, facts).

    Raises ValueError on invalid input so the runtime emits TaskResult(status="failed").
    """
    request = validate_input(parts)
    facts = load_facts(request.purchase_reference, request.customer_id)
    if facts is None:
        rec = _missing_data_recommendation(request.purchase_reference)
        return request, rec, None
    rec = evaluate(facts, request, REFUND_POLICY)
    return request, rec, facts


def build_result_payload(
    request: RefundEligibilityRequest,
    rec: EligibilityRecommendation,
    facts: BillingFacts | None,
) -> BillingRefundAnalysisCompletedPayload:
    """Map EligibilityRecommendation + BillingFacts + request → expanded result event payload (T014)."""
    return BillingRefundAnalysisCompletedPayload(
        case_id=request.case_id,
        ticket_id=request.ticket_id,
        customer_id=request.customer_id,
        billing_account_id=(
            facts.subscription.subscription_id
            if facts is not None and facts.subscription is not None
            else None
        ),
        subscription_status=rec.subscription_status,
        invoice_status=rec.invoice_status,
        payment_status=rec.payment_status,
        entitlement_status=rec.entitlement_status,
        usage_level=rec.usage_level,
        refund_window_status=rec.refund_window_status,
        recommendation=str(rec.recommendation),
        confidence=rec.confidence,
        evidence=list(rec.evidence),
        reasoning_summary=rec.reasoning_summary,
        requires_human_review=rec.requires_human_review,
        eligible_refund_amount=rec.eligible_refund_amount,
    )


def build_a2a_output(rec: EligibilityRecommendation) -> A2AMessage:
    """Build the A2A output message from a recommendation (003's normalize_billing_result consumes this)."""
    return A2AMessage(
        role="agent",
        parts=[
            A2APart(
                type="data",
                data={
                    "recommendation": str(rec.recommendation),
                    "confidence": rec.confidence,
                    "evidence": [e.model_dump() for e in rec.evidence],
                    "reasoning_summary": rec.reasoning_summary,
                    "requires_human_review": rec.requires_human_review,
                },
            )
        ],
    )
