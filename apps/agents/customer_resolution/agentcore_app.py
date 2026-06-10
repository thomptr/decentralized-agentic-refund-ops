"""AgentCore app wrapper — local invocation entrypoint for the Customer Resolution Agent.

A BedrockAgentCoreApp @app.entrypoint that:
1. Accepts a dict or JSON-string AgentCore payload (a support ticket + optional peer findings).
2. Classifies the ticket (``ticket_classifier.classify``) and runs the deterministic decision
   engine (``decision_engine.decide``) over any caller-supplied billing/risk findings.
3. Returns the resulting CustomerResponseDecisionPayload as a structured JSON response.

This is a demo/testing interface, NOT the live orchestrator:
- Originates no TaskRequest, delegates to no peer agent.
- Constructs no Publisher, opens no Consumer, publishes nothing to Kafka.
- Implements no billing/risk business logic (FR-005). Peer findings, if any, must be supplied
  in the payload (``billing_result`` / ``risk_result``); absent them the decision engine
  deterministically escalates to a human (missing_analysis) rather than fabricating a verdict.

The Kafka entrypoint (main.py) is the real orchestration path — it delegates to the billing and
risk peers over the A2A-over-Kafka runtime and emits the resolution-decided/response-drafted events.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from uuid import UUID, uuid4

try:
    from bedrock_agentcore.runtime import BedrockAgentCoreApp
except ImportError:
    # Allow import without bedrock-agentcore installed (e.g., in unit tests / the repo env).
    BedrockAgentCoreApp = None  # type: ignore[assignment,misc]

from apps.agents.customer_resolution.config import (
    BILLING_PEER_AGENT_ID,
    RISK_PEER_AGENT_ID,
)
from apps.agents.customer_resolution.decision_engine import decide
from apps.agents.customer_resolution.event_handlers import (
    normalize_billing_result,
    normalize_risk_result,
)
from apps.agents.customer_resolution.ticket_classifier import classify
from packages.contracts.events.payloads import SupportTicketCreatedPayload

app = BedrockAgentCoreApp() if BedrockAgentCoreApp is not None else None


def _invoke(payload: dict | str) -> dict:
    """Core logic extracted so it can be called in tests without the @app.entrypoint decorator.

    Reuses the same pure ``classify`` + ``decide`` pipeline as the Kafka path; the only thing
    the demo path lacks is the peer delegation that fills the billing/risk slots.
    """
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (ValueError, TypeError) as exc:
            return {"status": "failed", "error": f"Invalid JSON payload: {exc}"}

    if not isinstance(payload, dict):
        return {"status": "failed", "error": "Payload must be a JSON object."}

    try:
        ticket = SupportTicketCreatedPayload(
            ticket_id=payload["ticket_id"],
            customer_id=payload["customer_id"],
            amount=float(payload.get("amount", 0.0)),
            currency=payload.get("currency", "USD"),
            reason=payload.get("reason", ""),
            created_at=datetime.now(UTC),
        )
    except Exception as exc:
        return {
            "status": "failed",
            "error": str(exc),
            "reason": "Input validation failed (FR-011). No decision fabricated.",
        }

    triage = classify(ticket)

    # case_id: accept a caller-supplied UUID, else mint one for this single-shot demo run.
    raw_case_id = payload.get("case_id")
    try:
        case_id = UUID(str(raw_case_id)) if raw_case_id else uuid4()
    except (ValueError, TypeError):
        case_id = uuid4()

    # Peer findings are NOT computed here (FR-005). They are accepted from the payload so the
    # full decision matrix can be exercised locally; absent them, decide() escalates to a human.
    billing = None
    if isinstance(payload.get("billing_result"), dict):
        billing = normalize_billing_result(
            uuid4(),
            payload.get("billing_performer_agent_id", BILLING_PEER_AGENT_ID),
            payload["billing_result"],
        )
    risk = None
    if isinstance(payload.get("risk_result"), dict):
        risk = normalize_risk_result(
            uuid4(),
            payload.get("risk_performer_agent_id", RISK_PEER_AGENT_ID),
            payload["risk_result"],
        )

    decision = decide(
        triage,
        billing,
        risk,
        case_id=case_id,
        ticket_id=ticket.ticket_id,
        customer_id=ticket.customer_id,
    )

    return {"status": "completed", **decision.model_dump(mode="json")}


if app is not None:

    @app.entrypoint
    def invoke(payload: dict | str) -> dict:
        """AgentCore local invocation entrypoint.

        Accepts a dict or JSON-string payload (support ticket + optional peer findings),
        runs the classify + decide pipeline, and returns the structured decision JSON.
        No Kafka publish, no peer delegation (demo/testing only — FR-005).
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
