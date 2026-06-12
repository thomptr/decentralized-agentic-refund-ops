"""Deterministic decision engine (Phase 18 T147-T151 authoritative design).

This module implements the pure, total decide() function that maps:
  (classification, billing_result, risk_result, policy_context, timeout_status) ->
  CustomerResponseDecisionPayload

Truth table (ordered; first matching row wins — escalation precedence):

  Row 1: any_missing / None billing or risk -> escalate_human (missing_analysis)
  Row 2: failed/rejected slot or requires_human_review ->
         escalate_human (peer_failure/peer_requested_review)
  Row 3: confidence < CONFIDENCE_THRESHOLD -> escalate_human (low_confidence)
  Row 4: billing eligible AND risk low -> approve_refund
  Row 5: billing ineligible AND risk in {elevated, high} -> deny_refund
  Row 6: billing partial AND risk in {low, elevated} -> offer_partial_credit
  Row 7: billing indeterminate -> request_more_information
  Row 8: residual conflict -> escalate_human (conflicting_analyses)

Note: The direct_response outcome (non-refund ticket, row 0) is handled by the caller
before invoking decide() — when triage.needs_refund_review is False.

Phase 17 requires_human_approval logic is also here (T136).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from agent_foundation.observability.decorators import traced
from apps.agents.customer_resolution.config import (
    CONFIDENCE_THRESHOLD,
    HUMAN_APPROVAL_OUTCOMES,
)
from apps.agents.customer_resolution.models import (
    BillingFinding,
    PolicyContext,
    RiskFinding,
    TimeoutStatus,
    Triage,
)
from apps.agents.customer_resolution.response_drafter import draft_customer_response
from packages.contracts.events.payloads import (
    CustomerResponseDecisionPayload,
    ResolutionOutcome,
)


def compute_confidence(
    triage: Triage | None,
    billing: BillingFinding | None,
    risk: RiskFinding | None,
) -> float:
    """Pure, deterministic confidence score bounded to [0.0, 1.0] (Phase 18 T147).

    Takes the minimum of available confidence values. Returns low value when
    inputs are absent. No randomness, no I/O.
    """
    scores: list[float] = []
    if triage is not None:
        scores.append(triage.confidence)
    if billing is not None and billing.confidence is not None:
        scores.append(billing.confidence)
    if risk is not None and risk.score is not None:
        # Convert risk score to a certainty (1.0 = certain, 0.0 = uncertain)
        # High risk score → lower confidence in approve/deny routing
        scores.append(1.0 - risk.score)

    if not scores:
        return 0.0
    return max(0.0, min(1.0, min(scores)))


def build_evidence(
    triage: Triage | None,
    billing: BillingFinding | None,
    risk: RiskFinding | None,
) -> list[dict]:
    """Pure builder — one evidence entry per present finding (Phase 18 T149).

    Never invents a field absent from the inputs.
    """
    evidence = []
    if triage is not None:
        evidence.append(
            {
                "source": "classification",
                "task_id": None,
                "performer_agent_id": None,
                "summary": triage.rationale,
                "confidence": triage.confidence,
            }
        )
    if billing is not None:
        evidence.append(
            {
                "source": "billing",
                "task_id": str(billing.task_id) if billing.task_id else None,
                "performer_agent_id": billing.performer_agent_id or None,
                "summary": billing.summary or f"eligibility={billing.eligibility}",
                "confidence": billing.confidence,
            }
        )
    if risk is not None:
        evidence.append(
            {
                "source": "risk",
                "task_id": str(risk.task_id) if risk.task_id else None,
                "performer_agent_id": risk.performer_agent_id or None,
                "summary": risk.summary or f"level={risk.level}",
                "confidence": None,
            }
        )
    return evidence


@traced("case.decision")
def decide(
    triage: Triage,
    billing: BillingFinding | None,
    risk: RiskFinding | None,
    *,
    policy_context: PolicyContext | None = None,
    timeout_status: TimeoutStatus | None = None,
    decided_at: datetime | None = None,
    case_id: UUID | None = None,
    ticket_id: str = "",
    customer_id: str = "",
) -> CustomerResponseDecisionPayload:
    """Pure, total decision function (Phase 18 T148). First matching row wins.

    For direct_response (non-refund ticket), the caller emits the outcome directly
    without calling decide() — but this function handles it defensively via triage.
    """
    if decided_at is None:
        decided_at = datetime.now(UTC)

    ts = timeout_status

    # Ensure case_id is a UUID
    cid = case_id or UUID(int=0)

    # Row 0: direct_response — non-refund ticket (caller handles this but support it here too)
    if not triage.needs_refund_review:
        return CustomerResponseDecisionPayload(
            case_id=cid,
            ticket_id=ticket_id,
            customer_id=customer_id,
            outcome=ResolutionOutcome.DIRECT_RESPONSE,
            customer_response=draft_customer_response(ResolutionOutcome.DIRECT_RESPONSE),
            rationale=triage.rationale,
        )

    # Row 1: missing/timed-out analysis
    if ts is not None and ts.any_missing:
        reason = "analysis_timeout" if ts.deadline_exceeded else "missing_analysis"
        return CustomerResponseDecisionPayload(
            case_id=cid,
            ticket_id=ticket_id,
            customer_id=customer_id,
            outcome=ResolutionOutcome.ESCALATE_HUMAN,
            customer_response=draft_customer_response(ResolutionOutcome.ESCALATE_HUMAN),
            escalation_reason=reason,
            rationale=f"Missing analysis: {ts.missing_reviews}",
        )

    if billing is None or risk is None:
        return CustomerResponseDecisionPayload(
            case_id=cid,
            ticket_id=ticket_id,
            customer_id=customer_id,
            outcome=ResolutionOutcome.ESCALATE_HUMAN,
            customer_response=draft_customer_response(ResolutionOutcome.ESCALATE_HUMAN),
            escalation_reason="missing_analysis",
            rationale="Required analysis result is missing",
        )

    billing_summary = billing.summary or f"eligibility={billing.eligibility}"
    risk_summary = risk.summary or f"level={risk.level}"

    # Row 2: failed/rejected slots or peer-requested human review
    if billing.failed or risk.failed:
        return CustomerResponseDecisionPayload(
            case_id=cid,
            ticket_id=ticket_id,
            customer_id=customer_id,
            outcome=ResolutionOutcome.ESCALATE_HUMAN,
            customer_response=draft_customer_response(ResolutionOutcome.ESCALATE_HUMAN),
            escalation_reason="peer_failure",
            billing_summary=billing_summary,
            risk_summary=risk_summary,
            rationale="Peer analysis failed",
        )

    if billing.requires_human_review or risk.requires_human_review:
        return CustomerResponseDecisionPayload(
            case_id=cid,
            ticket_id=ticket_id,
            customer_id=customer_id,
            outcome=ResolutionOutcome.ESCALATE_HUMAN,
            customer_response=draft_customer_response(ResolutionOutcome.ESCALATE_HUMAN),
            escalation_reason="peer_requested_review",
            billing_summary=billing_summary,
            risk_summary=risk_summary,
            rationale="Peer requested human review",
        )

    # Row 3: low confidence
    confidence = compute_confidence(triage, billing, risk)
    if confidence < CONFIDENCE_THRESHOLD:
        return CustomerResponseDecisionPayload(
            case_id=cid,
            ticket_id=ticket_id,
            customer_id=customer_id,
            outcome=ResolutionOutcome.ESCALATE_HUMAN,
            customer_response=draft_customer_response(ResolutionOutcome.ESCALATE_HUMAN),
            escalation_reason="low_confidence",
            billing_summary=billing_summary,
            risk_summary=risk_summary,
            rationale=f"Confidence {confidence:.2f} below threshold {CONFIDENCE_THRESHOLD}",
        )

    # Row 4: approve — eligible AND low risk
    if billing.eligibility == "eligible" and risk.level == "low":
        return CustomerResponseDecisionPayload(
            case_id=cid,
            ticket_id=ticket_id,
            customer_id=customer_id,
            outcome=ResolutionOutcome.APPROVE_REFUND,
            customer_response=draft_customer_response(ResolutionOutcome.APPROVE_REFUND),
            billing_summary=billing_summary,
            risk_summary=risk_summary,
            rationale="Eligible for refund; low risk",
        )

    # Row 5: deny — ineligible AND elevated/high risk
    if billing.eligibility == "ineligible" and risk.level in ("elevated", "high"):
        return CustomerResponseDecisionPayload(
            case_id=cid,
            ticket_id=ticket_id,
            customer_id=customer_id,
            outcome=ResolutionOutcome.DENY_REFUND,
            customer_response=draft_customer_response(ResolutionOutcome.DENY_REFUND),
            billing_summary=billing_summary,
            risk_summary=risk_summary,
            rationale="Ineligible for refund; elevated/high risk",
        )

    # Row 6: partial credit — partial AND low/elevated risk
    if billing.eligibility == "partial" and risk.level in ("low", "elevated"):
        return CustomerResponseDecisionPayload(
            case_id=cid,
            ticket_id=ticket_id,
            customer_id=customer_id,
            outcome=ResolutionOutcome.OFFER_PARTIAL_CREDIT,
            customer_response=draft_customer_response(ResolutionOutcome.OFFER_PARTIAL_CREDIT),
            billing_summary=billing_summary,
            risk_summary=risk_summary,
            rationale="Partial eligibility; acceptable risk",
        )

    # Row 7: request more info — indeterminate billing
    if billing.eligibility == "indeterminate":
        return CustomerResponseDecisionPayload(
            case_id=cid,
            ticket_id=ticket_id,
            customer_id=customer_id,
            outcome=ResolutionOutcome.REQUEST_MORE_INFORMATION,
            customer_response=draft_customer_response(ResolutionOutcome.REQUEST_MORE_INFORMATION),
            billing_summary=billing_summary,
            risk_summary=risk_summary,
            rationale="Billing analysis inconclusive",
        )

    # Row 8: residual conflict (eligible+high, ineligible+low, etc.)
    return CustomerResponseDecisionPayload(
        case_id=cid,
        ticket_id=ticket_id,
        customer_id=customer_id,
        outcome=ResolutionOutcome.ESCALATE_HUMAN,
        customer_response=draft_customer_response(ResolutionOutcome.ESCALATE_HUMAN),
        escalation_reason="conflicting_analyses",
        billing_summary=billing_summary,
        risk_summary=risk_summary,
        rationale=f"Conflicting: billing={billing.eligibility}, risk={risk.level}",
    )


def requires_human_approval(outcome: ResolutionOutcome) -> bool:
    """Deterministic human-approval gate (Phase 17 T136)."""
    return outcome in HUMAN_APPROVAL_OUTCOMES
