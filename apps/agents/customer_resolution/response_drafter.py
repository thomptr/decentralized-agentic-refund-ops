"""Customer-facing response templates (US1/US3, T016/T032/T150).

draft_customer_response(outcome, triage, billing, risk) -> str is the primary entry.
All templates are pure — no I/O, no internal fields leaked to customers.

Phase 17 (T135): build_response_drafted_payload
Phase 22 (T204-T214): structured ResponseDraft with AllowedFacts
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator

from apps.agents.customer_resolution.config import (
    FRAUD_SCORING_FIELDS,
    INTERNAL_ONLY_DRAFT_FIELDS,
    MAX_SUMMARY_LENGTH,
)
from apps.agents.customer_resolution.models import BillingFinding, RiskFinding, Triage
from packages.contracts.events.payloads import (
    CustomerResponseDraftedPayload,
    ResolutionOutcome,
)

# ---------------------------------------------------------------------------
# Phase 22: Structured drafter types
# ---------------------------------------------------------------------------


class ResponseType(str):
    REFUND_CONFIRMATION = "refund_confirmation"
    REFUND_DENIAL = "refund_denial"
    ESCALATION_ACKNOWLEDGEMENT = "escalation_acknowledgement"
    DIRECT_ANSWER = "direct_answer"
    PARTIAL_CREDIT_OFFER = "partial_credit_offer"
    INFORMATION_REQUEST = "information_request"


_OUTCOME_TO_RESPONSE_TYPE: dict[ResolutionOutcome, str] = {
    ResolutionOutcome.APPROVE_REFUND: ResponseType.REFUND_CONFIRMATION,
    ResolutionOutcome.DENY_REFUND: ResponseType.REFUND_DENIAL,
    ResolutionOutcome.ESCALATE_HUMAN: ResponseType.ESCALATION_ACKNOWLEDGEMENT,
    ResolutionOutcome.DIRECT_RESPONSE: ResponseType.DIRECT_ANSWER,
    ResolutionOutcome.OFFER_PARTIAL_CREDIT: ResponseType.PARTIAL_CREDIT_OFFER,
    ResolutionOutcome.REQUEST_MORE_INFORMATION: ResponseType.INFORMATION_REQUEST,
}


class ToneConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    brand_name: str = "Support"
    greeting: str = "Dear Customer,"
    signoff: str = "Best regards,\nThe Support Team"
    formality: str = "friendly"
    apologetic: bool = True


class AllowedFacts(BaseModel):
    """Whitelist of customer-safe facts (Phase 22 T206).

    Contains NO risk score/confidence/level/evidence/reasoning — fraud suppression by construction.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    refund_amount: float | None = None
    currency: str | None = None
    order_reference: str | None = None
    billing_outcome_summary: str | None = None
    eligibility: bool | None = None


class ResponseDraft(BaseModel):
    """Structured response draft output (Phase 22 T207)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    subject: str
    body: str
    response_type: str
    requires_human_approval: bool

    @model_validator(mode="after")
    def validate_draft(self) -> ResponseDraft:
        if not self.subject.strip():
            raise ValueError("subject must be non-empty")
        if not self.body.strip():
            raise ValueError("body must be non-empty")
        return self


DEFAULT_TONE = ToneConfig()


# ---------------------------------------------------------------------------
# Core response templates (per outcome)
# ---------------------------------------------------------------------------

_TEMPLATES: dict[ResolutionOutcome, str] = {
    ResolutionOutcome.APPROVE_REFUND: (
        "We have reviewed your request and are pleased to approve your refund. "
        "Please allow 3-5 business days for the amount to appear in your account."
    ),
    ResolutionOutcome.DENY_REFUND: (
        "We have reviewed your request. Based on our review, we are unable to process "
        "a refund at this time. If you have further questions, please contact our support team."
    ),
    ResolutionOutcome.ESCALATE_HUMAN: (
        "Thank you for contacting us. Your case has been forwarded to a specialist "
        "who will review your request and reach out to you shortly."
    ),
    ResolutionOutcome.DIRECT_RESPONSE: (
        "Thank you for reaching out. Our team is happy to assist you. "
        "Please let us know if you need any further information."
    ),
    ResolutionOutcome.OFFER_PARTIAL_CREDIT: (
        "We have reviewed your request. We are able to offer a partial credit "
        "to your account as a resolution. A specialist will reach out with details."
    ),
    ResolutionOutcome.REQUEST_MORE_INFORMATION: (
        "Thank you for contacting us. To better assist you, we need some additional "
        "information. A support specialist will be in touch shortly."
    ),
}


def draft_customer_response(
    outcome: ResolutionOutcome,
    triage: Triage | None = None,
    billing: BillingFinding | None = None,
    risk: RiskFinding | None = None,
) -> str:
    """Return a safe, customer-facing response draft (pure, no I/O).

    Never exposes internal fields (rationale, escalation_reason, billing_summary,
    risk_summary). Templates live here; exact wording is illustrative.
    """
    text = _TEMPLATES.get(outcome, _TEMPLATES[ResolutionOutcome.DIRECT_RESPONSE])
    _assert_no_internal_leak(text)
    return text


def _assert_no_internal_leak(text: str) -> None:
    """Fail closed if internal field names appear in the customer draft."""
    for field in INTERNAL_ONLY_DRAFT_FIELDS:
        if field in text.lower():
            raise ValueError(f"Internal field '{field}' leaked into customer draft")
    for field in FRAUD_SCORING_FIELDS:
        if field in text.lower():
            raise ValueError(f"Fraud-scoring field '{field}' leaked into customer draft")


# ---------------------------------------------------------------------------
# Phase 17: build_response_drafted_payload
# ---------------------------------------------------------------------------


# Import is deferred to avoid circular; CustomerResponseDraftedPayload is in payloads
def build_response_drafted_payload(
    decision_payload: CustomerResponseDecisionPayload,  # type: ignore[name-defined]
    decision_envelope: EventEnvelope,  # type: ignore[name-defined]
    *,
    requires_human_approval: bool,
    drafted_at: datetime,
) -> CustomerResponseDraftedPayload:
    """Pure builder for the customer-response.drafted event (Phase 17 T135)."""
    return CustomerResponseDraftedPayload(
        case_id=decision_envelope.correlation_id,
        ticket_id=decision_payload.ticket_id,
        customer_id=decision_payload.customer_id,
        decision_event_id=decision_envelope.event_id,
        outcome=decision_payload.outcome,
        draft_response=decision_payload.customer_response,
        requires_human_approval=requires_human_approval,
        drafted_at=drafted_at,
    )


# ---------------------------------------------------------------------------
# Phase 22: structured drafter
# ---------------------------------------------------------------------------


def build_allowed_facts(
    ticket_amount: float,
    ticket_currency: str,
    ticket_id: str,
    billing: BillingFinding | None,
) -> AllowedFacts:
    """Build the customer-safe fact whitelist (Phase 22 T211).

    Deliberately does NOT read RiskFinding fields (fraud suppression by construction).
    """
    return AllowedFacts(
        refund_amount=ticket_amount,
        currency=ticket_currency,
        order_reference=ticket_id,
        billing_outcome_summary=(billing.summary if billing and billing.summary else None),
        eligibility=billing.eligible if billing else None,
    )


def draft_structured_response(
    ticket_summary: str,
    outcome: ResolutionOutcome,
    allowed_facts: AllowedFacts,
    tone_config: ToneConfig | None = None,
) -> ResponseDraft:
    """Structured response drafter (Phase 22 T212).

    Renders solely from allowed_facts + tone_config. Returns a frozen ResponseDraft.
    """
    from apps.agents.customer_resolution.config import HUMAN_APPROVAL_OUTCOMES

    tone = tone_config or DEFAULT_TONE
    body = _TEMPLATES.get(outcome, _TEMPLATES[ResolutionOutcome.DIRECT_RESPONSE])

    # Append amount if present in allowed_facts for approve/partial
    if allowed_facts.refund_amount and outcome in (
        ResolutionOutcome.APPROVE_REFUND,
        ResolutionOutcome.OFFER_PARTIAL_CREDIT,
    ):
        currency = allowed_facts.currency or ""
        body = f"{body} Amount: {allowed_facts.refund_amount} {currency}".strip()

    _assert_no_internal_leak(body)

    return ResponseDraft(
        subject=f"{tone.brand_name}: Your support request has been reviewed",
        body=f"{tone.greeting}\n\n{body}\n\n{tone.signoff}",
        response_type=_OUTCOME_TO_RESPONSE_TYPE.get(outcome, ResponseType.DIRECT_ANSWER),
        requires_human_approval=(outcome in HUMAN_APPROVAL_OUTCOMES),
    )


def minimize_summary(text: str) -> str:
    """Produce a length-bounded summary stripped of raw ticket content (Phase 23 T227)."""
    if not text:
        return ""
    return text[:MAX_SUMMARY_LENGTH]


# ---------------------------------------------------------------------------
# LLM-assisted drafting (Phase 008)
# ---------------------------------------------------------------------------


async def draft_with_llm(
    outcome: ResolutionOutcome,
    allowed_facts: AllowedFacts,
    tone_config: ToneConfig | None,
    runtime: object,
    *,
    correlation_id: object = None,
    causation_id: object = None,
    ticket_summary: str = "",
) -> ResponseDraft:
    """Draft a customer response using the LLM runtime with deterministic fallback.

    When the reasoning path is fallback, requires_human_approval is forced True.
    The grounding check (_assert_no_internal_leak) runs on the model body before returning.
    """
    from uuid import uuid4

    from agent_foundation.llm import ReasoningPath, assist_or_fallback
    from apps.agents.customer_resolution.config import AGENT_ID

    cid = correlation_id or uuid4()
    cause = causation_id or uuid4()

    tone = tone_config or DEFAULT_TONE

    def _fallback() -> ResponseDraft:
        return draft_structured_response(ticket_summary, outcome, allowed_facts, tone)

    result = await assist_or_fallback(
        runtime,
        agent_id=AGENT_ID,
        task_kind="draft_response",
        correlation_id=cid,
        causation_id=cause,
        instructions=(
            "Draft a customer-facing response for this support case. "
            "Use ONLY the allowed facts provided. Do NOT reveal internal fields, "
            "risk scores, confidence values, or evidence details. "
            "The response must be professional and empathetic."
        ),
        grounding_inputs={
            "outcome": outcome.value,
            "allowed_facts": allowed_facts.model_dump(mode="json"),
            "tone": tone.model_dump(mode="json"),
            "ticket_summary": ticket_summary,
        },
        output_schema=ResponseDraft,
        fallback=_fallback,
    )

    if isinstance(result.value, ResponseDraft):
        draft = result.value
        # Grounding check: reject body that leaks internal fields
        try:
            _assert_no_internal_leak(draft.body)
        except ValueError:
            # Leaked internal field -- force fallback
            draft = _fallback()
            draft = ResponseDraft(
                subject=draft.subject,
                body=draft.body,
                response_type=draft.response_type,
                requires_human_approval=True,
            )
            return draft

        # When reasoning path == fallback, force human approval
        if result.reasoning_path == ReasoningPath.fallback:
            draft = ResponseDraft(
                subject=draft.subject,
                body=draft.body,
                response_type=draft.response_type,
                requires_human_approval=True,
            )
        return draft

    # Safety net: deterministic fallback
    return _fallback()

# Avoid circular imports at module level — import CustomerResponseDecisionPayload lazily.
# These type hints are used by build_response_drafted_payload above.
try:
    from agent_foundation.envelope import EventEnvelope  # noqa: F401
    from packages.contracts.events.payloads import (
        CustomerResponseDecisionPayload,  # noqa: F401
        CustomerResponseDraftedPayload,  # noqa: F401
    )
except ImportError:
    pass
