"""Shared identity and agent card builder (T010).

Extracted from main.py so both the Kafka entrypoint and the HTTP app serve the same card.
assess_refund_risk is the descriptive intent; assess_fraud_risk is the shipped capability id.
"""

from __future__ import annotations

from agent_foundation.envelope import AgentIdentity
from agent_foundation.runtime import AgentCard, Capability
from packages.contracts.topics import endpoint_topic

AGENT_ID = "risk-fraud-agent"


def build_identity() -> AgentIdentity:
    return AgentIdentity(
        agent_id=AGENT_ID,
        display_name="Risk Fraud Agent",
        tenant_id="poc",
    )


def build_agent_card() -> AgentCard:
    return AgentCard(
        agent_id=AGENT_ID,
        name="Risk Fraud Agent",
        description="Assesses fraud risk for refund requests based on owned risk/fraud signals.",
        version="1.0.0",
        endpoint_topic=endpoint_topic(AGENT_ID),
        capabilities=[
            Capability(
                id="assess_fraud_risk",
                name="Assess Fraud Risk",
                description=(
                    "Validates the structured refund risk request, loads owned risk/fraud signals, "
                    "and returns a deterministic risk assessment (low / elevated / high) with "
                    "confidence score, evidence, policy references, and a human-review flag. "
                    "Descriptive intent: assess_refund_risk."
                ),
                tags=["risk", "fraud", "refund"],
            )
        ],
        security="none",
    )


# Module-level singleton used by config.py (T093) and http_app.py
CARD = build_agent_card()
IDENTITY = build_identity()

__all__ = ["AGENT_ID", "CARD", "IDENTITY", "build_identity", "build_agent_card"]
