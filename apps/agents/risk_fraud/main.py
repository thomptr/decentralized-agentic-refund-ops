"""Risk Fraud demo agent — mock handler only, no domain business logic.

Capability: assess_fraud_risk
  - Returns a fixed mock risk score.
"""

from __future__ import annotations


def main() -> None:
    from agent_foundation.a2a import A2AMessage, A2APart
    from agent_foundation.envelope import AgentIdentity
    from agent_foundation.payloads.task import TaskRequest
    from agent_foundation.runtime import AgentCard, AgentRuntime, Capability
    from apps.agents.common import BROKER_URL, run_agent
    from packages.contracts.topics import endpoint_topic

    agent_id = "risk-fraud-agent"
    identity = AgentIdentity(
        agent_id=agent_id,
        display_name="Risk Fraud Agent",
        tenant_id="poc",
    )
    card = AgentCard(
        agent_id=agent_id,
        name="Risk Fraud Agent",
        description="Assesses fraud risk for transactions (mock).",
        version="1.0.0",
        endpoint_topic=endpoint_topic(agent_id),
        capabilities=[
            Capability(
                id="assess_fraud_risk",
                name="Assess Fraud Risk",
                description="Returns a mock fraud risk score.",
                tags=["risk", "demo"],
            )
        ],
        security="none",
    )
    runtime = AgentRuntime(identity, card, broker_url=BROKER_URL)

    @runtime.handler("assess_fraud_risk")
    async def handle_risk(req: TaskRequest) -> A2AMessage:
        return A2AMessage(
            role="agent",
            parts=[
                A2APart(
                    type="data",
                    data={"risk": "low", "score": 0.1, "task_id": str(req.task_id)},
                )
            ],
        )

    run_agent(runtime)


if __name__ == "__main__":
    main()
