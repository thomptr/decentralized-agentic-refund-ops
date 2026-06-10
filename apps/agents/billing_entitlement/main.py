"""Billing and Entitlement Agent — Kafka A2A entrypoint (T012/T015/T025/T026/T029).

Capability: analyze_refund_eligibility
  - Validates the structured task input (FR-002/FR-011).
  - Loads owned billing facts (FR-003).
  - Evaluates refund eligibility via a deterministic rules engine (FR-012).
  - Publishes a BillingRefundAnalysisCompletedPayload to TOPIC_BILLING_RESULT (FR-008/US2).
  - Returns the same verdict as the A2A TaskResult (dual-path delivery, research R2).
  - Idempotency: the runtime's IdempotencyTracker short-circuits redelivered task_ids before
    this handler runs — publish happens at most once per logical request (FR-013, T025).
"""

from __future__ import annotations

import structlog

from apps.agents.billing_entitlement.identity import build_agent_card, build_identity
from apps.agents.billing_entitlement.service import analyze, build_a2a_output, build_result_payload

logger = structlog.get_logger(__name__)


def main() -> None:
    from agent_foundation.a2a import A2AMessage
    from agent_foundation.payloads.task import TaskRequest
    from agent_foundation.runtime import AgentRuntime
    from agent_foundation.transport.publisher import Publisher
    from apps.agents.common import BROKER_URL
    from packages.contracts.topics import TOPIC_BILLING_RESULT

    identity = build_identity()
    card = build_agent_card()
    runtime = AgentRuntime(identity, card, broker_url=BROKER_URL)

    # T026: structlog instrumentation — request-received, decision, published result, errors
    log = logger.bind(agent_id=identity.agent_id)

    @runtime.handler("analyze_refund_eligibility")
    async def handle_eligibility(req: TaskRequest) -> A2AMessage:
        log.info("request_received", task_id=str(req.task_id), capability=req.capability)

        # Validate, load facts, evaluate (raises ValueError on invalid input → runtime emits failed)
        request, rec, facts = analyze(req.input.parts)

        log.info(
            "analysis_complete",
            task_id=str(req.task_id),
            recommendation=str(rec.recommendation),
            confidence=rec.confidence,
            requires_human_review=rec.requires_human_review,
            policy_references=rec.policy_references,
            evidence_count=len(rec.evidence),
        )

        # Build the result payload and publish to TOPIC_BILLING_RESULT (dual-path delivery, T015)
        # The Publisher is opened in the async entrypoint below and captured by this closure.
        payload = build_result_payload(request, rec, facts)
        await _domain_pub.publish(
            TOPIC_BILLING_RESULT,
            payload.model_dump(mode="json"),
            correlation_id=request.case_id,
            causation_id=req.task_id,
        )

        log.info(
            "result_published",
            task_id=str(req.task_id),
            topic=TOPIC_BILLING_RESULT,
            correlation_id=str(request.case_id),
        )

        if rec.requires_human_review:
            log.warning(
                "human_review_required",
                task_id=str(req.task_id),
                recommendation=str(rec.recommendation),
                reasoning_summary=rec.reasoning_summary,
            )

        return build_a2a_output(rec)

    # Open a handler-owned Publisher for the domain result event path (research R2/R8)
    import asyncio
    import contextlib
    import signal

    from agent_foundation.logging import configure_logging

    configure_logging()
    stop_event = asyncio.Event()

    def _handle_signal(*_: object) -> None:
        stop_event.set()

    loop = asyncio.new_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError, RuntimeError):
            loop.add_signal_handler(sig, _handle_signal)

    async def _run() -> None:
        global _domain_pub
        async with Publisher(identity, BROKER_URL) as pub:
            _domain_pub = pub
            await runtime.serve(stop_event)

    try:
        loop.run_until_complete(_run())
    finally:
        loop.close()


_domain_pub: object = None  # set inside _run() before the handler is ever called


if __name__ == "__main__":
    main()
