"""LLM-assisted reasoning summary enrichment for the Billing Entitlement Agent (008).

The LLM is assistive only: it polishes the deterministic reasoning_summary produced
by rules_engine.evaluate into a clearer narrative for human reviewers. It never
overrides the binding recommendation, confidence, eligible_refund_amount, evidence,
or requires_human_review fields — those remain the exclusive output of the
deterministic rules engine (FR-012).

Default is OFF (BILLING_LLM_SUMMARY_ENABLED=false). When enabled the runtime is
built once per handler invocation and uses the stub provider by default (no AWS
needed).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from agent_foundation.llm import (
    AssistiveResult,
    LLMRuntime,
    TaskKind,
    assist_or_fallback,
)
from apps.agents.billing_entitlement.models import (
    EligibilityRecommendation,
    RefundEligibilityRequest,
)

# ---------------------------------------------------------------------------
# Output schema — frozen, fields are text-only (no binding verdicts)
# ---------------------------------------------------------------------------


class BillingNarrative(BaseModel):
    """LLM-generated polished narrative for a billing eligibility recommendation.

    Contains ONLY textual enrichment fields. No recommendation, confidence, or
    eligible_refund_amount — those stay deterministic (rules_engine.evaluate).
    """

    model_config = ConfigDict(frozen=True)

    polished_summary: str
    evidence_explanation: str


# ---------------------------------------------------------------------------
# Grounding inputs builder
# ---------------------------------------------------------------------------


def _build_grounding_inputs(
    rec: EligibilityRecommendation,
    request: RefundEligibilityRequest,
) -> dict[str, Any]:
    """Serialize the deterministic recommendation fields the LLM needs for context."""
    return {
        "recommendation": str(rec.recommendation),
        "confidence": rec.confidence,
        "reasoning_summary": rec.reasoning_summary,
        "requires_human_review": rec.requires_human_review,
        "eligible_refund_amount": str(rec.eligible_refund_amount),
        "evidence": [e.model_dump(mode="json") for e in rec.evidence],
        "policy_references": rec.policy_references,
        "subscription_status": rec.subscription_status,
        "invoice_status": rec.invoice_status,
        "payment_status": rec.payment_status,
        "entitlement_status": rec.entitlement_status,
        "usage_level": rec.usage_level,
        "refund_window_status": rec.refund_window_status,
        "ticket_id": request.ticket_id,
        "customer_id": request.customer_id,
        "case_id": str(request.case_id),
    }


# ---------------------------------------------------------------------------
# Stable instruction block
# ---------------------------------------------------------------------------

_INSTRUCTIONS = """\
You are a billing-analysis assistant for a refund eligibility system.

Given a deterministic refund eligibility recommendation (recommendation, confidence,
eligible_refund_amount, evidence items, and policy references), produce a clear,
concise narrative that:

1. **polished_summary**: Rewrite the reasoning_summary into a polished 2-4 sentence
   paragraph suitable for a human reviewer. Reference the fired policy rules by ID
   (e.g. RP-001, RP-002) and explain WHY they contribute to the overall recommendation.
   Include the subscription, invoice, payment, and entitlement statuses in context.
   Do NOT invent facts — ground every claim in the provided evidence.

2. **evidence_explanation**: Summarize the evidence items into a cohesive explanation
   that a non-technical reviewer can understand. Group related billing signals
   (e.g. subscription status + payment status = account health). Keep it factual
   and grounded.

CONSTRAINTS:
- Do NOT suggest a different recommendation, confidence, or eligible_refund_amount.
- Do NOT fabricate evidence or policy rules not present in the input.
- Keep each field under 500 characters.
- Return valid JSON matching the output schema.
"""


def _instructions() -> str:
    """Return the stable instruction block for billing narrative generation."""
    return _INSTRUCTIONS


# ---------------------------------------------------------------------------
# Fallback — returns a BillingNarrative echoing the deterministic summary
# ---------------------------------------------------------------------------


def _make_fallback(rec: EligibilityRecommendation):
    """Return a zero-arg callable that produces a BillingNarrative from the deterministic fields."""

    def _fallback() -> BillingNarrative:
        return BillingNarrative(
            polished_summary=rec.reasoning_summary,
            evidence_explanation="; ".join(e.description for e in rec.evidence[:5])
            or "No evidence details available.",
        )

    return _fallback


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def enrich_recommendation(
    runtime: LLMRuntime,
    rec: EligibilityRecommendation,
    request: RefundEligibilityRequest,
    *,
    causation_id: UUID | None = None,
) -> BillingNarrative:
    """Build an AssistiveRequest and call assist_or_fallback.

    Returns a BillingNarrative (always — falls back to echoing the deterministic
    summary if the LLM is unavailable or produces invalid output).
    """
    grounding = _build_grounding_inputs(rec, request)
    cid = causation_id or request.case_id

    result: AssistiveResult = await assist_or_fallback(
        runtime,
        agent_id="billing-entitlement-agent",
        task_kind=TaskKind.summarize_reasoning,
        correlation_id=request.case_id,
        causation_id=cid,
        instructions=_instructions(),
        grounding_inputs=grounding,
        output_schema=BillingNarrative,
        fallback=_make_fallback(rec),
    )

    # result.value is always a BillingNarrative (model output or fallback)
    return result.value  # type: ignore[return-value]
