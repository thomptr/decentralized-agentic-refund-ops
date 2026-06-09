"""Customer Resolution demo agent — mock handler only, no domain business logic.

Capability: resolve_customer_case
  - Delegates analyze_refund_eligibility to billing-entitlement-agent via A2AClient (US3).
  - Returns a fixed mock resolution summary combining the billing verdict.
"""
from __future__ import annotations


def main() -> None:
    from agent_foundation.a2a import A2AMessage, A2APart
    from agent_foundation.envelope import AgentIdentity
    from agent_foundation.payloads.task import TaskRequest
    from agent_foundation.runtime import A2AClient, AgentCard, AgentRuntime, Capability
    from apps.agents.common import BROKER_URL, run_agent
    from packages.contracts.topics import endpoint_topic

    agent_id = "customer-resolution-agent"
    identity = AgentIdentity(
        agent_id=agent_id,
        display_name="Customer Resolution Agent",
        tenant_id="poc",
    )
    card = AgentCard(
        agent_id=agent_id,
        name="Customer Resolution Agent",
        description="Resolves customer cases by coordinating with billing and risk agents (mock).",
        version="1.0.0",
        endpoint_topic=endpoint_topic(agent_id),
        capabilities=[
            Capability(
                id="resolve_customer_case",
                name="Resolve Customer Case",
                description="Resolves a customer case by checking refund eligibility (mock).",
                tags=["resolution", "demo"],
            )
        ],
        security="none",
    )
    runtime = AgentRuntime(identity, card, broker_url=BROKER_URL)
    client = A2AClient(identity, broker_url=BROKER_URL)

    @runtime.handler("resolve_customer_case")
    async def handle_resolve(req: TaskRequest) -> A2AMessage:
        # Delegate to billing-entitlement-agent via A2AClient (no direct call, FR-011)
        billing_input = A2AMessage(
            role="user",
            parts=[A2APart(
                type="data",
                data={"case_id": str(req.task_id), "source": "customer-resolution"},
            )],
        )
        try:
            billing_result = await client.submit(
                "billing-entitlement-agent",
                "analyze_refund_eligibility",
                billing_input,
                correlation_id=req.input.task_id or None,
                causation_id=None,
                timeout_s=15.0,
            )
            billing_data = (
                billing_result.output.parts[0].data
                if billing_result.output and billing_result.output.parts
                else {"eligible": "unknown"}
            )
        except TimeoutError:
            billing_data = {"eligible": "unknown", "reason": "billing-timeout"}

        return A2AMessage(
            role="agent",
            parts=[
                A2APart(
                    type="data",
                    data={
                        "resolution": "mock-resolved",
                        "case_id": str(req.task_id),
                        "billing_verdict": billing_data,
                    },
                )
            ],
        )

    run_agent(runtime)


if __name__ == "__main__":
    main()
