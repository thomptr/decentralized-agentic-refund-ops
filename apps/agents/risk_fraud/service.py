"""Orchestration service — validate → load signals → score → build outputs (T016, T019).

Pure functions; no Kafka, no side effects. Enables reuse by both the Kafka entrypoint (main.py)
and the AgentCore/HTTP entrypoint (http_app.py / app/RiskFraud/main.py).
"""

from __future__ import annotations

# Conditional import — only used when LLM enrichment is enabled
from typing import TYPE_CHECKING

from agent_foundation.a2a import A2AMessage, A2APart
from apps.agents.risk_fraud.mock_data import load_signals
from apps.agents.risk_fraud.models import (
    RiskAssessment,
    RiskAssessmentRequest,
)
from apps.agents.risk_fraud.scoring import assess_signals
from packages.contracts.events.payloads import EvidenceItem, RiskReviewCompletedPayload

if TYPE_CHECKING:
    from apps.agents.risk_fraud.llm_summary import RiskNarrative


def validate_input(parts: list) -> RiskAssessmentRequest:
    """Extract and validate the data part from A2A input parts.

    Raises ValueError if no data part is present or the data fails validation.
    No fabricated verdict — callers should let this propagate so the runtime emits failed result.
    """
    for part in parts:
        if getattr(part, "type", None) == "data" and part.data:
            return RiskAssessmentRequest.model_validate(part.data)
    raise ValueError("No valid data part found in input parts (FR-011)")


def _missing_data_assessment(customer_id: str) -> RiskAssessment:
    """Build a human-review assessment when load_signals returns None (FR-010)."""
    from apps.agents.risk_fraud.models import RecommendedAction, RiskLevel

    return RiskAssessment(
        risk_level=RiskLevel.LOW,
        recommended_action=RecommendedAction.REQUEST_MORE_INFORMATION,
        confidence=0.2,
        evidence=[
            EvidenceItem(
                source="fraud_policy",
                description="Data-completeness gate: no risk signal record found",
                value={
                    "reason": f"no risk signals for customer_id={customer_id!r}",
                    "rule": "data-completeness-gate",
                },
            )
        ],
        policy_references=[],
        reasoning_summary=(
            f"No risk signal record found for customer_id={customer_id!r}. "
            "Unable to assess risk without owned signal data (FR-010). "
            "Manual review required."
        ),
        requires_human_review=True,
    )


def assess(
    parts: list,
) -> tuple[RiskAssessment, RiskAssessmentRequest]:
    """Full pipeline: validate input → load signals → score → return (assessment, request).

    Raises ValueError on invalid input so the runtime emits TaskResult(status="failed").
    """
    request = validate_input(parts)
    signals = load_signals(request.customer_id)
    if signals is None:
        assessment = _missing_data_assessment(request.customer_id)
    else:
        assessment = assess_signals(signals, request)
    return assessment, request


def to_result_payload(
    assessment: RiskAssessment,
    request: RiskAssessmentRequest,
    *,
    narrative: RiskNarrative | None = None,
) -> RiskReviewCompletedPayload:
    """Map RiskAssessment + request to RiskReviewCompletedPayload (T019).

    The ``recommendation`` wire field is risk_level.value (SC-009 / R5).
    FP-00x policy references are surfaced as EvidenceItems with source="fraud_policy" in the
    assessment.evidence; no dedicated policy_references field on the wire payload (SC-002).

    When ``narrative`` is provided (LLM enrichment enabled), the enriched_reasoning_summary
    and evidence_explanation text fields are populated. Binding fields (recommendation,
    confidence, evidence, requires_human_review) are ALWAYS from the deterministic assessment.
    """
    return RiskReviewCompletedPayload(
        ticket_id=request.ticket_id,
        recommendation=str(assessment.risk_level),
        confidence=assessment.confidence,
        evidence=list(assessment.evidence),
        reasoning_summary=assessment.reasoning_summary,
        requires_human_review=assessment.requires_human_review,
        enriched_reasoning_summary=(narrative.polished_summary if narrative is not None else None),
        evidence_explanation=(narrative.evidence_explanation if narrative is not None else None),
    )


def build_a2a_output(
    assessment: RiskAssessment,
    *,
    narrative: RiskNarrative | None = None,
) -> A2AMessage:
    """Build the A2A output message from an assessment (consumed by 003 normalize_risk_result).

    When ``narrative`` is provided (LLM enrichment enabled), enriched text fields are included.
    Binding fields are ALWAYS from the deterministic assessment.
    """
    data: dict = {
        "recommendation": str(assessment.risk_level),
        "score": assessment.confidence,  # stub-compatible numeric score (R5)
        "confidence": assessment.confidence,
        "evidence": [e.model_dump() for e in assessment.evidence],
        "reasoning_summary": assessment.reasoning_summary,
        "requires_human_review": assessment.requires_human_review,
        "policy_references": assessment.policy_references,
    }
    if narrative is not None:
        data["enriched_reasoning_summary"] = narrative.polished_summary
        data["evidence_explanation"] = narrative.evidence_explanation
    return A2AMessage(
        role="agent",
        parts=[A2APart(type="data", data=data)],
    )
