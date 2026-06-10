"""Shared identity and agent card builder (T036).

Extracted from main.py so both the Kafka entrypoint and the HTTP app serve the same card.
"""

from __future__ import annotations

from agent_foundation.envelope import AgentIdentity
from agent_foundation.runtime import AgentCard, Capability
from packages.contracts.topics import endpoint_topic

_AGENT_ID = "billing-entitlement-agent"


def build_identity() -> AgentIdentity:
    return AgentIdentity(
        agent_id=_AGENT_ID,
        display_name="Billing Entitlement Agent",
        tenant_id="poc",
    )


def build_agent_card() -> AgentCard:
    return AgentCard(
        agent_id=_AGENT_ID,
        name="Billing Entitlement Agent",
        description="Analyzes refund eligibility based on owned billing and entitlement data.",
        version="1.0.0",
        endpoint_topic=endpoint_topic(_AGENT_ID),
        capabilities=[
            Capability(
                id="analyze_refund_eligibility",
                name="Analyze Refund Eligibility",
                description=(
                    "Validates the structured refund request, loads owned billing facts, "
                    "and returns a deterministic recommendation (approve_full_refund / "
                    "approve_partial_refund / deny_refund / request_more_information / "
                    "manual_review) with confidence score, evidence, and policy references."
                ),
                tags=["billing", "entitlement", "refund"],
            )
        ],
        security="none",
    )


__all__ = ["build_identity", "build_agent_card"]
