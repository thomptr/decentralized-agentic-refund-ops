"""AgentCore app wrapper — local invocation entrypoint (T119, T120).

A BedrockAgentCoreApp @app.entrypoint that:
1. Accepts a dict or JSON-string AgentCore payload.
2. Parses it into RiskAssessmentRequest (T009).
3. Calls service.assess_direct unchanged (T016).
4. Returns a structured JSON response.

This is a demo/testing interface, NOT a supervisor:
- Originates no TaskRequest, dispatches no work.
- Makes no peer call, constructs no Publisher, publishes nothing to Kafka.
- Does not bypass A2A/Kafka contract tests (T032/T039).
The Kafka entrypoint (main.py) is the collaboration path for peer-agent interaction.
"""

from __future__ import annotations

import json
import sys

try:
    from bedrock_agentcore.runtime import BedrockAgentCoreApp
except ImportError:
    # Allow import without bedrock-agentcore installed (e.g., in unit tests)
    BedrockAgentCoreApp = None  # type: ignore[assignment,misc]

from apps.agents.risk_fraud.mock_data import load_signals
from apps.agents.risk_fraud.models import RiskAssessmentRequest
from apps.agents.risk_fraud.scoring import assess_signals

app = BedrockAgentCoreApp() if BedrockAgentCoreApp is not None else None


def _invoke(payload: dict | str) -> dict:
    """Core logic extracted so it can be called in tests without the @app.entrypoint decorator."""
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (ValueError, TypeError) as exc:
            return {"status": "failed", "error": f"Invalid JSON payload: {exc}"}

    try:
        request = RiskAssessmentRequest.model_validate(payload)
    except Exception as exc:
        return {
            "status": "failed",
            "error": str(exc),
            "reason": "Input validation failed (FR-011). No verdict fabricated.",
        }

    signals = load_signals(request.customer_id)
    if signals is None:
        return {
            "status": "completed",
            "recommendation": "unknown",
            "confidence": 0.2,
            "evidence": [
                {
                    "source": "fraud_policy",
                    "description": "Data-completeness gate: no risk record found",
                    "value": {"customer_id": request.customer_id},
                }
            ],
            "reasoning_summary": f"No risk signals found for customer_id={request.customer_id!r}.",
            "requires_human_review": True,
            "policy_references": [],
        }

    assessment = assess_signals(signals, request)
    return {
        "status": "completed",
        "recommendation": str(assessment.risk_level),
        "confidence": assessment.confidence,
        "evidence": [e.model_dump() for e in assessment.evidence],
        "reasoning_summary": assessment.reasoning_summary,
        "requires_human_review": assessment.requires_human_review,
        "policy_references": assessment.policy_references,
    }


if app is not None:

    @app.entrypoint
    def invoke(payload: dict | str) -> dict:
        """AgentCore local invocation entrypoint (T120).

        Accepts a dict or JSON-string payload, parses into RiskAssessmentRequest,
        runs service.assess_signals, and returns structured JSON.
        No Kafka publish, no peer calls (demo/testing only — SC-008/FR-016).
        """
        return _invoke(payload)


if __name__ == "__main__":
    if app is not None:
        app.run()
    else:
        print(
            "bedrock-agentcore is not installed. Cannot run agentcore_app directly.",
            file=sys.stderr,
        )
        sys.exit(1)
