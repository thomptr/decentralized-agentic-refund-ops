"""Billing Entitlement demo agent — mock handler only, no domain business logic.

Capability: analyze_refund_eligibility
  - Returns a fixed mock eligibility verdict.
  - Failure sentinel: when input text part equals "FAIL", the handler raises so the
    runtime produces TaskResult(status="failed", error.category="handler_error").
"""
from __future__ import annotations


def main() -> None:
    from agent_foundation.a2a import A2AMessage, A2APart
    from agent_foundation.envelope import AgentIdentity
    from agent_foundation.payloads.task import TaskRequest
    from agent_foundation.runtime import AgentCard, AgentRuntime, Capability
    from apps.agents.common import BROKER_URL, run_agent
    from packages.contracts.topics import endpoint_topic

    agent_id = "billing-entitlement-agent"
    identity = AgentIdentity(
        agent_id=agent_id,
        display_name="Billing Entitlement Agent",
        tenant_id="poc",
    )
    card = AgentCard(
        agent_id=agent_id,
        name="Billing Entitlement Agent",
        description="Analyzes refund eligibility based on billing data (mock).",
        version="1.0.0",
        endpoint_topic=endpoint_topic(agent_id),
        capabilities=[
            Capability(
                id="analyze_refund_eligibility",
                name="Analyze Refund Eligibility",
                description="Returns a mock refund eligibility verdict.",
                tags=["billing", "demo"],
            )
        ],
        security="none",
    )
    runtime = AgentRuntime(identity, card, broker_url=BROKER_URL)

    @runtime.handler("analyze_refund_eligibility")
    async def handle_eligibility(req: TaskRequest) -> A2AMessage:
        # Failure sentinel: raise when input text part equals "FAIL"
        for part in req.input.parts:
            if part.type == "text" and part.text == "FAIL":
                raise RuntimeError("Billing failure sentinel triggered")

        return A2AMessage(
            role="agent",
            parts=[
                A2APart(
                    type="data",
                    data={"eligible": True, "reason": "mock", "task_id": str(req.task_id)},
                )
            ],
        )

    run_agent(runtime)


if __name__ == "__main__":
    main()
