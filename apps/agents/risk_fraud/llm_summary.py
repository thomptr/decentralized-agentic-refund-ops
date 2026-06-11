"""LLM-assisted reasoning summary enrichment for the Risk Fraud Agent (008).

The LLM is assistive only: it polishes the deterministic reasoning_summary produced
by scoring.assess_signals into a clearer narrative for human reviewers. It never
overrides the binding risk_level, recommended_action, confidence, evidence, or
requires_human_review fields — those remain the exclusive output of the deterministic
scoring engine (FR-012).

Default is OFF (RISK_LLM_SUMMARY_ENABLED=false). When enabled the runtime is built
once per handler invocation and uses the stub provider by default (no AWS needed).
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
from apps.agents.risk_fraud.models import RiskAssessment, RiskAssessmentRequest

# ---------------------------------------------------------------------------
# Output schema — frozen, fields are text-only (no binding verdicts)
# ---------------------------------------------------------------------------


class RiskNarrative(BaseModel):
    """LLM-generated polished narrative for a risk assessment.

    Contains ONLY textual enrichment fields. No score, level, action, or
    confidence — those stay deterministic (scoring.assess_signals).
    """

    model_config = ConfigDict(frozen=True)

    polished_summary: str
    evidence_explanation: str


# ---------------------------------------------------------------------------
# Grounding inputs builder
# ---------------------------------------------------------------------------


def _build_grounding_inputs(
    assessment: RiskAssessment,
    request: RiskAssessmentRequest,
) -> dict[str, Any]:
    """Serialize the deterministic assessment fields the LLM needs for context."""
    return {
        "risk_level": str(assessment.risk_level),
        "recommended_action": str(assessment.recommended_action),
        "confidence": assessment.confidence,
        "reasoning_summary": assessment.reasoning_summary,
        "requires_human_review": assessment.requires_human_review,
        "evidence": [e.model_dump(mode="json") for e in assessment.evidence],
        "policy_references": assessment.policy_references,
        "ticket_id": request.ticket_id,
        "customer_id": request.customer_id,
        "case_id": str(request.case_id),
    }


# ---------------------------------------------------------------------------
# Stable instruction block
# ---------------------------------------------------------------------------

_INSTRUCTIONS = """\
You are a risk-analysis assistant for a refund-fraud detection system.

Given a deterministic risk assessment (risk_level, recommended_action, confidence,
evidence items, and policy references), produce a clear, concise narrative that:

1. **polished_summary**: Rewrite the reasoning_summary into a polished 2-4 sentence
   paragraph suitable for a human reviewer. Reference the fired policy rules by ID
   (e.g. FP-002, FP-003) and explain WHY they contribute to the overall risk level.
   Do NOT invent facts — ground every claim in the provided evidence.

2. **evidence_explanation**: Summarize the evidence items into a cohesive explanation
   that a non-technical reviewer can understand. Group related signals (e.g. velocity
   + anomaly = behavioral concern). Keep it factual and grounded.

CONSTRAINTS:
- Do NOT suggest a different risk_level, recommended_action, or confidence.
- Do NOT fabricate evidence or policy rules not present in the input.
- Keep each field under 500 characters.
- Return valid JSON matching the output schema.
"""


def _instructions() -> str:
    """Return the stable instruction block for risk narrative generation."""
    return _INSTRUCTIONS


# ---------------------------------------------------------------------------
# Fallback — returns a RiskNarrative echoing the deterministic summary
# ---------------------------------------------------------------------------


def _make_fallback(assessment: RiskAssessment):
    """Return a zero-arg callable that produces a RiskNarrative from the deterministic fields."""

    def _fallback() -> RiskNarrative:
        return RiskNarrative(
            polished_summary=assessment.reasoning_summary,
            evidence_explanation="; ".join(e.description for e in assessment.evidence[:5])
            or "No evidence details available.",
        )

    return _fallback


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def enrich_assessment(
    runtime: LLMRuntime,
    assessment: RiskAssessment,
    request: RiskAssessmentRequest,
    *,
    causation_id: UUID | None = None,
) -> RiskNarrative:
    """Build an AssistiveRequest and call assist_or_fallback.

    Returns a RiskNarrative (always — falls back to echoing the deterministic summary
    if the LLM is unavailable or produces invalid output).
    """
    grounding = _build_grounding_inputs(assessment, request)
    cid = causation_id or request.case_id

    result: AssistiveResult = await assist_or_fallback(
        runtime,
        agent_id="risk-fraud-agent",
        task_kind=TaskKind.summarize_reasoning,
        correlation_id=request.case_id,
        causation_id=cid,
        instructions=_instructions(),
        grounding_inputs=grounding,
        output_schema=RiskNarrative,
        fallback=_make_fallback(assessment),
    )

    # result.value is always a RiskNarrative (model output or fallback)
    return result.value  # type: ignore[return-value]
