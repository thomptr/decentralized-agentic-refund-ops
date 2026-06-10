"""Event handlers for ticket intake and task-result consumption (US1-US3).

Three consumer loops share a single CaseStateStore:
  1. intake_handler  — consumes support.ticket.created
  2. result_handler  — consumes TOPIC_TASK_RESULT (generic A2A results)
  3. billing_result_handler — consumes TOPIC_BILLING_RESULT (Phase 15)
  4. risk_result_handler    — consumes TOPIC_RISK_RESULT (Phase 16)

All handlers are idempotent via IdempotencyTracker + case-status guards (FR-011/FR-012).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import structlog

from agent_foundation.audit.store import write_audit, write_task_audit
from agent_foundation.envelope import EventEnvelope
from agent_foundation.transport.publisher import Publisher
from apps.agents.customer_resolution.decision_engine import (
    decide,
    requires_human_approval,
)
from apps.agents.customer_resolution.models import (
    BillingFinding,
    CaseStatus,
    PolicyContext,
    ResolutionCase,
    RiskFinding,
    Triage,
    build_timeout_status,
    is_terminal,
)
from apps.agents.customer_resolution.response_drafter import draft_customer_response
from apps.agents.customer_resolution.state_store import (
    AttachOutcome,
    InMemoryCaseStateStore,
)
from apps.agents.customer_resolution.ticket_classifier import (
    build_issue_classified_payload,
    classify,
)
from packages.contracts.events.payloads import (
    BillingRefundAnalysisCompletedPayload,
    CustomerResponseDecisionPayload,
    CustomerResponseDraftedPayload,
    ResolutionOutcome,
    RiskReviewCompletedPayload,
    SupportTicketCreatedPayload,
)
from packages.contracts.topics import (
    TOPIC_ISSUE_CLASSIFIED,
    TOPIC_RESOLUTION_DECIDED,
    TOPIC_RESPONSE_DRAFTED,
)

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Result normalization adapter (T030 / analysis-result-contract.md)
# ---------------------------------------------------------------------------


def normalize_billing_result(
    task_id: UUID,
    performer_agent_id: str,
    data: dict,
) -> BillingFinding | None:
    """Normalize billing TaskResult data to BillingFinding.

    Accepts canonical BillingRefundAnalysisCompletedPayload fields or the demo stub shape.
    Returns None on unparseable data (slot marked failed by caller).
    """
    try:
        if "recommendation" in data:
            rec = data["recommendation"].lower()
            # 5-value vocabulary from billing-entitlement-agent (T016 — SC-009)
            if rec in ("approve_full_refund", "approve", "eligible", "refund"):
                eligibility = "eligible"
            elif rec == "approve_partial_refund":
                eligibility = "partial"
            elif rec in ("deny_refund", "deny", "ineligible", "reject"):
                eligibility = "ineligible"
            elif rec in ("request_more_information", "manual_review"):
                eligibility = "indeterminate"
            elif rec == "partial_refund":
                eligibility = "partial"
            else:
                eligibility = "indeterminate"
            return BillingFinding(
                eligibility=eligibility,
                requires_human_review=bool(data.get("requires_human_review", False)),
                confidence=data.get("confidence"),
                summary=data.get("reasoning_summary", ""),
                performer_agent_id=performer_agent_id,
                task_id=task_id,
            )
        elif "eligible" in data:
            elig = data["eligible"]
            if isinstance(elig, bool):
                eligibility = "eligible" if elig else "ineligible"
            elif isinstance(elig, str):
                _valid = ("eligible", "partial", "ineligible", "indeterminate")
                eligibility = (
                    elig
                    if elig in _valid
                    else ("eligible" if elig.lower() == "true" else "ineligible")
                )
            else:
                return None
            return BillingFinding(
                eligibility=eligibility,
                performer_agent_id=performer_agent_id,
                task_id=task_id,
            )
        return None
    except Exception:
        return None


def normalize_risk_result(
    task_id: UUID,
    performer_agent_id: str,
    data: dict,
    *,
    elevated_threshold: float = 0.5,
    high_threshold: float = 0.8,
) -> RiskFinding | None:
    """Normalize risk TaskResult data to RiskFinding.

    Accepts canonical RiskReviewCompletedPayload fields or the demo stub shape.
    Returns None on unparseable data.
    """
    try:
        if "recommendation" in data:
            rec = data["recommendation"].lower()
            if rec in ("low", "approve", "acceptable"):
                level = "low"
            elif rec == "elevated":
                level = "elevated"
            elif rec in ("high", "deny", "block"):
                level = "high"
            else:
                score = float(data.get("score", data.get("confidence", 0.0)))
                level = _risk_level_from_score(score, elevated_threshold, high_threshold)
            return RiskFinding(
                level=level,
                requires_human_review=bool(data.get("requires_human_review", False)),
                score=_uncertainty_from_confidence(data.get("confidence")),
                summary=data.get("reasoning_summary", ""),
                performer_agent_id=performer_agent_id,
                task_id=task_id,
            )
        elif "risk" in data:
            level = str(data["risk"]).lower()
            if level not in ("low", "elevated", "high"):
                level = "low"
            return RiskFinding(
                level=level,
                score=data.get("score"),
                performer_agent_id=performer_agent_id,
                task_id=task_id,
            )
        return None
    except Exception:
        return None


def _risk_level_from_score(score: float, elevated: float, high: float) -> str:
    if score >= high:
        return "high"
    if score >= elevated:
        return "elevated"
    return "low"


def _uncertainty_from_confidence(confidence: float | None) -> float | None:
    """Map an agent's assessment *confidence* (certainty) to RiskFinding.score.

    The decision engine's compute_confidence treats RiskFinding.score as
    uncertainty: routing certainty == 1.0 - score. The risk agent reports
    `confidence` as its certainty (e.g. 0.9 == very sure), so the matching score
    is 1.0 - confidence. Storing the confidence directly would invert the signal
    and make a confident low-risk finding look maximally uncertain → spurious
    low_confidence escalations.
    """
    if confidence is None:
        return None
    return max(0.0, min(1.0, 1.0 - float(confidence)))


# ---------------------------------------------------------------------------
# Decision emit helpers
# ---------------------------------------------------------------------------


async def _emit_decision_and_draft(
    case: ResolutionCase,
    decision: CustomerResponseDecisionPayload,
    *,
    publisher: Publisher,
    causation_id: UUID,
) -> EventEnvelope:
    """Emit the final decision event and the customer-response.drafted event.

    Returns the decision envelope (used by Phase 20 for causation chaining).
    """
    decided_envelope = await publisher.publish(
        decision,
        event_type=TOPIC_RESOLUTION_DECIDED,
        correlation_id=case.correlation_id,
        causation_id=causation_id,
    )
    case.decided_event_id = decided_envelope.event_id
    logger.info(
        "decision_emitted",
        case_id=str(case.case_id),
        outcome=decision.outcome.value,
        event_id=str(decided_envelope.event_id),
    )

    # Phase 17: emit customer-response.drafted event
    approval_required = requires_human_approval(decision.outcome)
    draft = CustomerResponseDraftedPayload(
        case_id=case.correlation_id,
        ticket_id=decision.ticket_id,
        customer_id=decision.customer_id,
        decision_event_id=decided_envelope.event_id,
        outcome=decision.outcome,
        draft_response=decision.customer_response,
        requires_human_approval=approval_required,
        drafted_at=datetime.now(UTC),
    )
    drafted_envelope = await publisher.publish(
        draft,
        event_type=TOPIC_RESPONSE_DRAFTED,
        correlation_id=case.correlation_id,
        causation_id=decided_envelope.event_id,
    )
    case.drafted_event_id = drafted_envelope.event_id
    logger.info(
        "response_drafted",
        case_id=str(case.case_id),
        requires_human_approval=approval_required,
    )

    return decided_envelope


# ---------------------------------------------------------------------------
# Intake handler (US1, T018/T025)
# ---------------------------------------------------------------------------


async def intake_handler(
    envelope: EventEnvelope,
    *,
    publisher: Publisher,
    store: InMemoryCaseStateStore,
    broker_url: str,
) -> None:
    """Consume support.ticket.created events (US1, T018).

    1. Get-or-create case (idempotent).
    2. Classify the ticket.
    3. Emit classification event (Phase 10).
    4a. Non-refund → direct_response decision, close case.
    4b. Refund → delegate to billing/risk peers, set AWAITING_ANALYSES.
    """
    from apps.agents.customer_resolution.a2a_handlers import delegate

    try:
        ticket = SupportTicketCreatedPayload.model_validate(envelope.payload)
    except Exception:
        logger.error("intake_payload_invalid", event_id=str(envelope.event_id))
        return

    case_id = envelope.correlation_id

    # Idempotent case creation
    case = await store.get_or_create(
        case_id,
        ticket_id=ticket.ticket_id,
        customer_id=ticket.customer_id,
        correlation_id=envelope.correlation_id,
        ticket_amount=ticket.amount,
        ticket_currency=ticket.currency,
        ticket_reason=ticket.reason,
        created_at=datetime.now(UTC),
    )

    # Already processed — skip
    if case.status not in (CaseStatus.RECEIVED, CaseStatus.CLASSIFIED):
        logger.info(
            "intake_duplicate_skipped",
            case_id=str(case_id),
            status=case.status.value,
        )
        await write_audit(publisher, envelope, "duplicate_skipped", "already_processed")
        return

    # Classify
    triage = classify(ticket)
    case.triage = triage
    case.status = CaseStatus.CLASSIFIED
    await store.save(case)

    await write_audit(publisher, envelope, "accepted", None)
    logger.info(
        "ticket_classified",
        case_id=str(case_id),
        needs_refund_review=triage.needs_refund_review,
        ambiguous=triage.ambiguous,
    )

    # Phase 10: emit classification event
    classified_payload = build_issue_classified_payload(ticket, envelope.correlation_id, triage)
    await publisher.publish(
        classified_payload,
        event_type=TOPIC_ISSUE_CLASSIFIED,
        correlation_id=envelope.correlation_id,
        causation_id=envelope.event_id,
    )

    if not triage.needs_refund_review:
        # Non-refund → direct response (US1, SC-001)
        decision = CustomerResponseDecisionPayload(
            case_id=case.correlation_id,
            ticket_id=ticket.ticket_id,
            customer_id=ticket.customer_id,
            outcome=ResolutionOutcome.DIRECT_RESPONSE,
            customer_response=draft_customer_response(ResolutionOutcome.DIRECT_RESPONSE, triage),
            rationale=triage.rationale,
        )
        await _emit_decision_and_draft(
            case, decision, publisher=publisher, causation_id=envelope.event_id
        )
        case.status = CaseStatus.CLOSED
        await store.save(case)
        logger.info("case_closed_direct", case_id=str(case_id))
        return

    # Refund → delegate to peers (US2)
    case.status = CaseStatus.WAITING_FOR_PEER_REVIEWS
    # Root the case deadline (FR-017, T005) — enforced by the reaper (T021)
    from apps.agents.customer_resolution.config import CASE_DEADLINE_SECONDS

    now_ts = datetime.now(UTC)
    case.deadline_at = datetime.fromtimestamp(now_ts.timestamp() + CASE_DEADLINE_SECONDS, tz=UTC)
    await store.save(case)

    try:
        await delegate(
            case,
            publisher=publisher,
            broker_url=broker_url,
            ticket_envelope=envelope,
            state_store=store,
        )
        await store.save(case)
    except Exception as exc:
        logger.error(
            "delegation_failed",
            case_id=str(case_id),
            error=str(exc),
        )
        # Escalate on delegation failure
        decision = CustomerResponseDecisionPayload(
            case_id=case.correlation_id,
            ticket_id=ticket.ticket_id,
            customer_id=ticket.customer_id,
            outcome=ResolutionOutcome.ESCALATE_HUMAN,
            customer_response=draft_customer_response(ResolutionOutcome.ESCALATE_HUMAN),
            escalation_reason="peer_failure",
            rationale=f"Delegation failed: {exc}",
        )
        await _emit_decision_and_draft(
            case, decision, publisher=publisher, causation_id=envelope.event_id
        )
        case.status = CaseStatus.ESCALATED
        await store.save(case)


# ---------------------------------------------------------------------------
# Result handler — generic TaskResult on TOPIC_TASK_RESULT (US3, T034)
# ---------------------------------------------------------------------------


async def result_handler(
    envelope: EventEnvelope,
    *,
    publisher: Publisher,
    store: InMemoryCaseStateStore,
) -> None:
    """Consume A2A TaskResult events (US3, T034).

    Correlates by task_id → case, normalizes the finding, and when the case
    is ready, applies the decision policy and emits exactly one decision.
    """
    from agent_foundation.payloads.task import TaskResult

    try:
        result = TaskResult.model_validate(envelope.payload)
    except Exception:
        logger.error("result_payload_invalid", event_id=str(envelope.event_id))
        return

    task_id = result.task_id
    case = await store.get_by_task_id(task_id)
    if case is None:
        logger.warning("result_no_matching_case", task_id=str(task_id))
        return

    if is_terminal(case.status) or case.status == CaseStatus.DECIDED:
        logger.info(
            "late_result_recorded_not_applied",
            task_id=str(task_id),
            case_id=str(case.case_id),
            status=case.status.value,
        )
        await write_task_audit(publisher, envelope, "duplicate_skipped", task_id, "late_result")
        return

    # Determine which slot this result belongs to
    is_billing = case.billing_task_id == task_id
    is_risk = case.risk_task_id == task_id
    performer = result.performer_agent_id

    # Billing and risk results are delivered on BOTH this generic A2A task-result
    # topic AND their richer domain topics (dual-path delivery, T020). The
    # dedicated billing_result_handler / risk_result_handler own those slots —
    # they carry full payload fields (e.g. usage_level) that the thin A2A result
    # lacks, and they are the single authoritative attach point. Defer a COMPLETED
    # billing/risk result to them so the decision is driven once, from the domain
    # event (keeping the decided event's causation deterministic and avoiding a
    # degraded duplicate finding). Failures still flow through here because a
    # failed task is only ever delivered as an A2A task result.
    if result.status == "completed" and (is_billing or is_risk):
        await write_task_audit(publisher, envelope, "duplicate_skipped", task_id, "dual_path")
        return

    if result.status == "completed" and result.output and result.output.parts:
        data_part = next((p for p in result.output.parts if p.type == "data"), None)
        data = data_part.data if data_part else {}

        if is_billing:
            finding = normalize_billing_result(task_id, performer, data or {})
            if finding is None:
                await store.mark_slot_failed(
                    case.case_id, task_id, is_billing=True, reason="unparseable_result"
                )
            else:
                # Record result event id for evidence (Phase 23 T223)
                case.billing_result_event_id = envelope.event_id
                outcome = await store.apply_result(case.case_id, task_id, finding)
                if outcome == AttachOutcome.ATTACHED:
                    await write_task_audit(publisher, envelope, "completed", task_id)
        else:
            finding = normalize_risk_result(task_id, performer, data or {})
            if finding is None:
                await store.mark_slot_failed(
                    case.case_id, task_id, is_billing=False, reason="unparseable_result"
                )
            else:
                case.risk_result_event_id = envelope.event_id
                outcome = await store.apply_result(case.case_id, task_id, finding)
                if outcome == AttachOutcome.ATTACHED:
                    await write_task_audit(publisher, envelope, "completed", task_id)
    else:
        # failed or rejected
        fail_reason = result.error.message if result.error else result.status
        await store.mark_slot_failed(
            case.case_id, task_id, is_billing=is_billing, reason=fail_reason
        )
        await write_task_audit(publisher, envelope, "rejected", task_id, fail_reason)

    # Re-fetch case after mutation
    case = await store.get(case.case_id) or case

    if not case.is_ready_to_decide():
        return

    await _apply_decision(case, envelope=envelope, publisher=publisher, store=store)


async def _apply_decision(
    case: ResolutionCase,
    *,
    envelope: EventEnvelope | None = None,
    causation_id: UUID | None = None,
    publisher: Publisher,
    store: InMemoryCaseStateStore,
) -> None:
    """Apply the decision policy and emit exactly one decision per case (FR-007).

    Accepts either an ``envelope`` (normal event-driven path) or an explicit
    ``causation_id`` (reaper path, T021).  One of the two must be supplied.
    """
    # Atomically claim the exclusive right to decide. Concurrent handler loops
    # (billing/risk domain events + generic A2A task results + reaper) can all
    # observe the case ready at once; only the claimant emits a decision (FR-007).
    if not await store.claim_decision(case.case_id):
        return
    case = await store.get(case.case_id) or case

    effective_causation_id: UUID = (
        envelope.event_id if envelope is not None else (causation_id or uuid4())
    )

    ts = build_timeout_status(case, now=datetime.now(UTC))
    policy = PolicyContext()

    decision = decide(
        case.triage
        or Triage(
            needs_refund_review=True,
            ambiguous=True,
            rationale="No triage available",
        ),
        case.billing_result,
        case.risk_result,
        policy_context=policy,
        timeout_status=ts,
        decided_at=datetime.now(UTC),
        case_id=case.correlation_id,
        ticket_id=case.ticket_id,
        customer_id=case.customer_id,
    )

    await _emit_decision_and_draft(
        case, decision, publisher=publisher, causation_id=effective_causation_id
    )

    case.status = CaseStatus.DECIDED
    await store.save(case)

    logger.info(
        "case_decided",
        case_id=str(case.case_id),
        outcome=decision.outcome.value,
    )


# ---------------------------------------------------------------------------
# Billing domain result handler (Phase 15, T111)
# ---------------------------------------------------------------------------


async def billing_result_handler(
    envelope: EventEnvelope,
    *,
    publisher: Publisher,
    store: InMemoryCaseStateStore,
) -> None:
    """Consume BillingRefundAnalysisCompletedPayload events (Phase 15)."""
    try:
        payload = BillingRefundAnalysisCompletedPayload.model_validate(envelope.payload)
    except Exception:
        logger.error("billing_result_payload_invalid", event_id=str(envelope.event_id))
        return

    case = await store.get_by_correlation_id(envelope.correlation_id)
    if case is None:
        store.park_billing_result(envelope.correlation_id, payload)
        return

    # Guard: ticket_id mismatch
    if case.ticket_id != payload.ticket_id:
        logger.warning(
            "billing_result_ticket_id_mismatch",
            case_ticket_id=case.ticket_id,
            result_ticket_id=payload.ticket_id,
        )

    if case.billing_task_id is None:
        return

    rec = payload.recommendation.lower()
    # 5-value vocabulary from billing-entitlement-agent (T016 — SC-009)
    if rec in ("approve_full_refund", "approve", "eligible", "refund"):
        eligibility = "eligible"
    elif rec == "approve_partial_refund":
        eligibility = "partial"
    elif rec in ("deny_refund", "deny", "ineligible", "reject"):
        eligibility = "ineligible"
    elif rec in ("request_more_information", "manual_review"):
        eligibility = "indeterminate"
    elif rec == "partial_refund":
        eligibility = "partial"
    else:
        eligibility = "indeterminate"

    # Heavy-usage denials (RP-004) are not a flat "no": the customer consumed
    # most of the value, so the resolution policy treats them as partial-credit
    # candidates (decision-policy Row 6 → offer_partial_credit) rather than an
    # outright ineligible verdict. usage_level is only present on the rich domain
    # payload, which is why this mapping lives here (the thin A2A result defers
    # to this handler — see result_handler).
    if eligibility == "ineligible" and payload.usage_level == "heavy":
        eligibility = "partial"

    finding = BillingFinding(
        eligibility=eligibility,
        requires_human_review=payload.requires_human_review,
        confidence=payload.confidence,
        summary=payload.reasoning_summary,
        task_id=case.billing_task_id,
    )

    case.billing_result_event_id = envelope.event_id
    outcome = await store.apply_result(case.case_id, case.billing_task_id, finding)
    if outcome == AttachOutcome.ATTACHED:
        await write_task_audit(publisher, envelope, "completed", case.billing_task_id)

    case = await store.get(case.case_id) or case
    if (
        case.is_ready_to_decide()
        and case.status not in (CaseStatus.DECIDED,)
        and not is_terminal(case.status)
    ):
        await _apply_decision(case, envelope=envelope, publisher=publisher, store=store)


# ---------------------------------------------------------------------------
# Risk domain result handler (Phase 16, T125)
# ---------------------------------------------------------------------------


async def risk_result_handler(
    envelope: EventEnvelope,
    *,
    publisher: Publisher,
    store: InMemoryCaseStateStore,
) -> None:
    """Consume RiskReviewCompletedPayload events (Phase 16)."""
    try:
        payload = RiskReviewCompletedPayload.model_validate(envelope.payload)
    except Exception:
        logger.error("risk_result_payload_invalid", event_id=str(envelope.event_id))
        return

    case = await store.get_by_correlation_id(envelope.correlation_id)
    if case is None:
        store.park_risk_result(envelope.correlation_id, payload)
        return

    if case.ticket_id != payload.ticket_id:
        logger.warning(
            "risk_result_ticket_id_mismatch",
            case_ticket_id=case.ticket_id,
            result_ticket_id=payload.ticket_id,
        )

    if case.risk_task_id is None:
        return

    rec = payload.recommendation.lower()
    if rec in ("low", "approve", "acceptable"):
        level = "low"
    elif rec == "elevated":
        level = "elevated"
    elif rec in ("high", "deny", "block"):
        level = "high"
    else:
        score = payload.confidence or 0.0
        level = _risk_level_from_score(score, 0.5, 0.8)

    finding = RiskFinding(
        level=level,
        requires_human_review=payload.requires_human_review,
        score=_uncertainty_from_confidence(payload.confidence),
        summary=payload.reasoning_summary,
        task_id=case.risk_task_id,
    )

    # High risk can force immediate escalation (AC4, Phase 16) — but only when
    # billing has NOT already returned an ineligible verdict. When billing is
    # ineligible, an elevated/high risk signal *corroborates* a denial rather
    # than a conflict, so the case must deny (decision-policy Row 5), not
    # escalate. Those cases fall through to the unified decision engine below.
    _high_risk = finding.level in ("elevated", "high") or finding.requires_human_review
    _billing_ineligible = (
        case.billing_result is not None and case.billing_result.eligibility == "ineligible"
    )
    _decidable = case.status not in (CaseStatus.DECIDED,) and not is_terminal(case.status)
    if _high_risk and not _billing_ineligible and _decidable:
        # Claim the single decision atomically so this immediate-escalation path
        # cannot race a billing-triggered decision (FR-007).
        if not await store.claim_decision(case.case_id):
            return
        case = await store.get(case.case_id) or case
        decision = CustomerResponseDecisionPayload(
            case_id=case.correlation_id,
            ticket_id=case.ticket_id,
            customer_id=case.customer_id,
            outcome=ResolutionOutcome.ESCALATE_HUMAN,
            customer_response=draft_customer_response(ResolutionOutcome.ESCALATE_HUMAN),
            escalation_reason="elevated_risk",
            risk_summary=f"level={finding.level}",
            rationale=f"Risk level {finding.level} forces escalation",
        )
        case.risk_result_event_id = envelope.event_id
        case.risk_result = finding
        await _emit_decision_and_draft(
            case, decision, publisher=publisher, causation_id=envelope.event_id
        )
        case.status = CaseStatus.ESCALATED
        await store.save(case)
        logger.info(
            "high_risk_escalation",
            case_id=str(case.case_id),
            risk_level=finding.level,
        )
        return

    case.risk_result_event_id = envelope.event_id
    outcome = await store.apply_result(case.case_id, case.risk_task_id, finding)
    if outcome == AttachOutcome.ATTACHED:
        await write_task_audit(publisher, envelope, "completed", case.risk_task_id)

    case = await store.get(case.case_id) or case
    if (
        case.is_ready_to_decide()
        and case.status not in (CaseStatus.DECIDED,)
        and not is_terminal(case.status)
    ):
        await _apply_decision(case, envelope=envelope, publisher=publisher, store=store)
