"""Ticket classifier Ã¢â‚¬â€ deterministic, pure triage function (US1, T015).

classify(ticket) -> Triage is the sole entry point. It applies the refund-intent
vocabulary from decision-policy.md Ã‚Â§A and config.REFUND_INTENT_SIGNALS.

Also provides build_issue_classified_payload (Phase 10, T051) which constructs
the CustomerIssueClassifiedPayload for emission after triage.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from apps.agents.customer_resolution.config import AGENT_ID, REFUND_INTENT_SIGNALS
from apps.agents.customer_resolution.models import Triage
from packages.contracts.events.payloads import (
    CustomerIssueClassifiedPayload,
    SupportTicketCreatedPayload,
)

# ---------------------------------------------------------------------------
# LLM output schema (Phase 008 -- CRA classify)
# ---------------------------------------------------------------------------


class TicketClassification(BaseModel):
    """LLM-produced classification output (frozen, schema-validated)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    issue_type: str
    needs_refund_review: bool
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    matched_signals: list[str] = Field(default_factory=list)

    def to_triage(self) -> Triage:
        """Map LLM classification to the existing Triage model."""
        return Triage(
            needs_refund_review=self.needs_refund_review,
            ambiguous=self.confidence < 0.7,
            matched_signals=list(self.matched_signals),
            rationale=self.rationale,
            issue_type=self.issue_type,
            confidence=self.confidence,
        )


def classify(ticket: SupportTicketCreatedPayload) -> Triage:
    """Classify a support ticket as refund-review vs. direct-response.

    Pure and deterministic Ã¢â‚¬â€ no I/O. Matches the refund-intent vocabulary
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

    # Empty or unrecognizable Ã¢â‚¬â€ default to review with ambiguity recorded
    if not reason_lower or _looks_ambiguous(reason_lower):
        return Triage(
            needs_refund_review=True,
            ambiguous=True,
            matched_signals=[],
            rationale="Ambiguous intent Ã¢â‚¬â€ defaulted to refund review",
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
    """Pure builder Ã¢â‚¬â€ constructs classification event payload (Phase 10, T051).

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


# ---------------------------------------------------------------------------
# LLM-assisted classification (Phase 008)
# ---------------------------------------------------------------------------


async def classify_with_llm(
    ticket: SupportTicketCreatedPayload,
    runtime: Any,
    *,
    correlation_id: Any = None,
    causation_id: Any = None,
) -> Triage:
    """Classify using the shared LLM runtime with deterministic fallback.

    On any LLM failure the deterministic classify(ticket) is used as fallback.
    The LLM result is mapped via TicketClassification.to_triage().
    """
    from uuid import uuid4

    from agent_foundation.llm import assist_or_fallback

    cid = correlation_id or uuid4()
    cause = causation_id or uuid4()

    result = await assist_or_fallback(
        runtime,
        agent_id=AGENT_ID,
        task_kind="classify",
        correlation_id=cid,
        causation_id=cause,
        instructions=(
            "Classify this customer support ticket. Determine the issue_type, "
            "whether it needs refund review, your confidence level, a rationale, "
            "and any matched signals from the ticket text."
        ),
        grounding_inputs={
            "ticket_id": ticket.ticket_id,
            "customer_id": ticket.customer_id,
            "reason": ticket.reason or "",
            "amount": ticket.amount,
            "currency": ticket.currency,
        },
        output_schema=TicketClassification,
        fallback=lambda: TicketClassification(
            issue_type=classify(ticket).issue_type,
            needs_refund_review=classify(ticket).needs_refund_review,
            confidence=classify(ticket).confidence,
            rationale=classify(ticket).rationale,
            matched_signals=list(classify(ticket).matched_signals),
        ),
    )

    if isinstance(result.value, TicketClassification):
        return result.value.to_triage()

    # Fallback: deterministic classify
    return classify(ticket)