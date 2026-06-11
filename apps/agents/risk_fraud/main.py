"""Risk and Fraud Agent — Kafka A2A entrypoint (T017, T019, T020, T029).

Capability: assess_fraud_risk
  - Validates the structured task input (FR-002/FR-011).
  - Loads owned risk/fraud signals (FR-003).
  - Scores fraud risk via a deterministic rules engine (FR-012).
  - Publishes a RiskReviewCompletedPayload to TOPIC_RISK_RESULT (FR-008/US2).
  - Returns the same verdict as the A2A TaskResult (dual-path delivery, research R2).
  - Idempotency: the runtime's IdempotencyTracker short-circuits redelivered task_ids before
    this handler runs — publish happens at most once per logical request (FR-013, T028).
    The domain-result publish (T020) is inside this handler closure, which the runtime invokes
    only after the dedup check, so a duplicate task_id is skipped before any publish (T083).
    Case-level idempotency for same-case_id/different-task_id retries rests on deterministic
    scoring (T027) + the 003 consumer's per-case guards (research R8). The agent adds no
    per-case_id store (T084). The at-least-once gap between publish and mark_processed is
    PoC-acceptable (research R7).
"""

from __future__ import annotations

import structlog

from apps.agents.risk_fraud.identity import build_agent_card, build_identity
from apps.agents.risk_fraud.service import assess, build_a2a_output, to_result_payload

logger = structlog.get_logger(__name__)


def main() -> None:
    from agent_foundation.a2a import A2AMessage
    from agent_foundation.payloads.task import TaskRequest
    from agent_foundation.runtime import AgentRuntime
    from agent_foundation.transport.publisher import Publisher
    from apps.agents.common import BROKER_URL
    from apps.agents.risk_fraud.config import RISK_LLM_SUMMARY_ENABLED
    from packages.contracts.topics import TOPIC_RISK_RESULT

    _llm_enabled = RISK_LLM_SUMMARY_ENABLED

    identity = build_identity()
    card = build_agent_card()
    runtime = AgentRuntime(identity, card, broker_url=BROKER_URL)

    log = logger.bind(agent_id=identity.agent_id)

    @runtime.handler("assess_fraud_risk")
    async def handle_risk(req: TaskRequest) -> A2AMessage:
        log.info("request_received", task_id=str(req.task_id), capability=req.capability)

        # Validate, load signals, score (raises ValueError on invalid input → runtime emits failed)
        assessment, request = assess(req.input.parts)

        log.info(
            "assessment_complete",
            task_id=str(req.task_id),
            risk_level=str(assessment.risk_level),
            confidence=assessment.confidence,
            requires_human_review=assessment.requires_human_review,
            policy_references=assessment.policy_references,
            evidence_count=len(assessment.evidence),
        )

        # --- LLM enrichment (008): optional reasoning-summary polish ---
        narrative = None
        if _llm_enabled:
            try:
                from agent_foundation.llm import build_runtime as build_llm_runtime
                from apps.agents.risk_fraud.llm_summary import enrich_assessment

                llm_rt = build_llm_runtime()
                narrative = await enrich_assessment(
                    llm_rt,
                    assessment,
                    request,
                    causation_id=req.task_id,
                )
                log.info(
                    "llm_enrichment_complete",
                    task_id=str(req.task_id),
                    has_narrative=True,
                )
            except Exception as exc:
                log.warning(
                    "llm_enrichment_failed",
                    task_id=str(req.task_id),
                    error=str(exc),
                )
                narrative = None

        # Build the result payload and publish to TOPIC_RISK_RESULT (dual-path delivery, T020).
        # The Publisher is opened in the async entrypoint below and captured by this closure.
        # This publish is INSIDE the handler (deduped path) — a duplicate task_id is skipped
        # before the handler runs, so no second publish occurs (T083/FR-013).
        payload = to_result_payload(assessment, request, narrative=narrative)
        await _domain_pub.publish(
            payload,
            event_type=TOPIC_RISK_RESULT,
            correlation_id=request.case_id,  # case_id → consumer's risk_result_handler key
            causation_id=req.task_id,  # causal link (FR-014/FR-015)
        )

        log.info(
            "result_published",
            task_id=str(req.task_id),
            topic=TOPIC_RISK_RESULT,
            correlation_id=str(request.case_id),
        )

        if assessment.requires_human_review:
            log.warning(
                "human_review_required",
                task_id=str(req.task_id),
                risk_level=str(assessment.risk_level),
                reasoning_summary=assessment.reasoning_summary,
            )

        return build_a2a_output(assessment, narrative=narrative)

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
