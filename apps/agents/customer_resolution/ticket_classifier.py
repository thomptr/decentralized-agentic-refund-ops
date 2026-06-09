"""Ticket classifier — deterministic, pure triage function (US1, T015).

classify(ticket) -> Triage is the sole entry point. It applies the refund-intent
vocabulary from decision-policy.md §A and config.REFUND_INTENT_SIGNALS.

Also provides build_issue_classified_payload (Phase 10, T051) which constructs
the CustomerIssueClassifiedPayload for emission after triage.
"""

from __future__ import annotations

from uuid import UUID

from apps.agents.customer_resolution.config import REFUND_INTENT_SIGNALS
from apps.agents.customer_resolution.models import Triage
from packages.contracts.events.payloads import (
    CustomerIssueClassifiedPayload,
    SupportTicketCreatedPayload,
)


def classify(ticket: SupportTicketCreatedPayload) -> Triage:
    """Classify a support ticket as refund-review vs. direct-response.

    Pure and deterministic — no I/O. Matches the refund-intent vocabulary
    against the ticket reason field (case-insensitive substring match).

    Ambiguous/empty tickets default to refund review with ambiguous=True.
    """
    reason_lower = (ticket.reason or "").lower()
    matched: list[str] = []

    for signal in REFUND_INTENT_SIGNALS:
        if signal in reason_lower:
            matched.append(signal)

    if matched:
        return Triage(
            needs_refund_review=True,
            ambiguous=False,
            matched_signals=matched,
            rationale=f"Refund intent detected: {', '.join(matched)}",
            issue_type="refund_request",
            confidence=1.0,
        )

    # Empty or unrecognizable — default to review with ambiguity recorded
    if not reason_lower or _looks_ambiguous(reason_lower):
        return Triage(
            needs_refund_review=True,
            ambiguous=True,
            matched_signals=[],
            rationale="Ambiguous intent — defaulted to refund review",
            issue_type="unknown",
            confidence=0.5,
        )

    # Clear non-refund (recognizable how-to/account question)
    return Triage(
        needs_refund_review=False,
        ambiguous=False,
        matched_signals=[],
        rationale="No refund intent detected",
        issue_type="general_inquiry",
        confidence=0.9,
    )


def _looks_ambiguous(reason_lower: str) -> bool:
    """Return True if the reason text is too short or unrecognizable to classify."""
    return len(reason_lower.strip()) < 5


def build_issue_classified_payload(
    ticket: SupportTicketCreatedPayload,
    correlation_id: UUID,
    triage: Triage,
) -> CustomerIssueClassifiedPayload:
    """Pure builder — constructs classification event payload (Phase 10, T051).

    case_id is the resolution-case identity (= inbound envelope correlation_id).
    requires_billing_review and requires_risk_review are set from needs_refund_review.
    requires_human_review is set from triage.ambiguous.
    """
    return CustomerIssueClassifiedPayload(
        case_id=correlation_id,
        ticket_id=ticket.ticket_id,
        customer_id=ticket.customer_id,
        issue_type=triage.issue_type,
        confidence=triage.confidence,
        requires_billing_review=triage.needs_refund_review,
        requires_risk_review=triage.needs_refund_review,
        requires_human_review=triage.ambiguous,
        reasoning_summary=triage.rationale,
    )
