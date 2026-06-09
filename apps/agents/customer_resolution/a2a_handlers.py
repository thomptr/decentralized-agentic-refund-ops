"""A2A handlers: peer discovery, delegation, AgentCard/AgentRuntime setup (US2, T022-T025).

Phase 12 (T068-T079): hardened risk request with idempotency key and AC validation.
Phase 13 (T080-T086): hardened billing request with idempotency key.
Phase 11 (T062-T067): RefundReviewRequestedPayload emission after delegation.

The "accepted" point for the refund-review announcement is after both TaskRequest
Publisher.publish() calls succeed. No blocking submit() is used (async delegation model).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog

from agent_foundation.envelope import EventEnvelope
from agent_foundation.runtime import AgentCard, Capability
from agent_foundation.transport.publisher import Publisher
from apps.agents.customer_resolution.config import (
    AGENT_ID,
    AGENT_VERSION,
    BILLING_CAPABILITY_ID,
    BILLING_PEER_AGENT_ID,
    DELEGATION_TIMEOUT_SECONDS,
    RISK_CAPABILITY_ID,
    RISK_PEER_AGENT_ID,
)
from apps.agents.customer_resolution.models import (
    ResolutionCase,
    build_billing_request_input,
    build_risk_request_input,
)
from packages.contracts.events.payloads import RefundReviewRequestedPayload
from packages.contracts.topics import (
    TOPIC_REFUND_REVIEW_REQUESTED,
    endpoint_topic,
)

logger = structlog.get_logger(__name__)


class RiskPeerUnavailable(Exception):
    """Raised when no capable risk agent card is discoverable (AC3, Phase 12)."""


class BillingPeerUnavailable(Exception):
    """Raised when no capable billing agent card is discoverable."""


def build_agent_card() -> AgentCard:
    """Build the AgentCard for the customer-resolution-agent (FR-001)."""
    return AgentCard(
        agent_id=AGENT_ID,
        name="Customer Resolution Agent",
        description=(
            "Resolves customer support tickets by triaging refund requests, "
            "delegating billing and risk analyses, and emitting final decisions."
        ),
        version=AGENT_VERSION,
        endpoint_topic=endpoint_topic(AGENT_ID),
        capabilities=[
            Capability(
                id="resolve_customer_case",
                name="Resolve Customer Case",
                description="Resolves a customer case by coordinating billing and risk analyses.",
                tags=["resolution", "refund"],
            )
        ],
        security="none",
    )


async def validate_risk_capability(broker_url: str) -> AgentCard:
    """Discover the risk peer and validate its assess_fraud_risk capability (AC3, Phase 12 T070).

    Raises RiskPeerUnavailable if no published card declares assess_fraud_risk.
    Fail-closed: the risk request is sent ONLY after this validation succeeds.
    """
    from agent_foundation.runtime import find_capable

    cards = await find_capable(RISK_CAPABILITY_ID, broker_url)
    for card in cards:
        if card.agent_id == RISK_PEER_AGENT_ID:
            return card
    raise RiskPeerUnavailable(
        f"No published card for {RISK_PEER_AGENT_ID} declares capability {RISK_CAPABILITY_ID}"
    )


async def validate_billing_capability(broker_url: str) -> AgentCard:
    """Discover the billing peer and validate its analyze_refund_eligibility capability."""
    from agent_foundation.runtime import find_capable

    cards = await find_capable(BILLING_CAPABILITY_ID, broker_url)
    for card in cards:
        if card.agent_id == BILLING_PEER_AGENT_ID:
            return card
    raise BillingPeerUnavailable(
        f"No published card for {BILLING_PEER_AGENT_ID} declares {BILLING_CAPABILITY_ID}"
    )


async def request_risk_analysis(
    case: ResolutionCase,
    *,
    publisher: Publisher,
    broker_url: str,
    ticket_envelope: EventEnvelope,
) -> None:
    """Send the risk A2A TaskRequest (Phase 12 T071, idempotency AC2).

    Idempotency key = stable task_id: reuse case.risk_task_id if already set,
    else mint a new one and record it. Published to endpoint_topic("risk-fraud-agent").

    On RiskPeerUnavailable: case status → PENDING_RISK (undiscoverable).
    On publish failure: case status → ESCALATED.
    """
    from agent_foundation.a2a import A2AMessage, A2APart
    from agent_foundation.payloads.task import TaskRequest

    # Validate capability through Agent Card (AC3)
    try:
        await validate_risk_capability(broker_url)
    except RiskPeerUnavailable:
        logger.warning(
            "risk_peer_unavailable",
            case_id=str(case.case_id),
        )
        raise

    # Stable idempotency key (AC2)
    if case.risk_task_id is None:
        case.risk_task_id = uuid.uuid5(case.correlation_id, RISK_CAPABILITY_ID)

    risk_input = build_risk_request_input(case)
    task_request = TaskRequest(
        task_id=case.risk_task_id,
        capability=RISK_CAPABILITY_ID,
        requester_agent_id=AGENT_ID,
        target_agent_id=RISK_PEER_AGENT_ID,
        input=A2AMessage(
            role="user",
            parts=[
                A2APart(
                    type="data",
                    data=risk_input.model_dump(mode="json"),
                )
            ],
        ),
    )

    await publisher.publish(
        task_request,
        event_type="agent.task_request.v1",
        correlation_id=case.correlation_id,
        causation_id=ticket_envelope.event_id,
        topic=endpoint_topic(RISK_PEER_AGENT_ID),
    )
    logger.info(
        "risk_task_requested",
        case_id=str(case.case_id),
        task_id=str(case.risk_task_id),
    )


async def request_billing_analysis(
    case: ResolutionCase,
    *,
    publisher: Publisher,
    broker_url: str,
    ticket_envelope: EventEnvelope,
) -> None:
    """Send the billing A2A TaskRequest (Phase 13 T081, idempotency AC2).

    Idempotency key = stable task_id: reuse case.billing_task_id if already set,
    else mint via uuid5(correlation_id, capability) and record it.
    Does NOT await the result inline (async, AC4).
    """
    from agent_foundation.a2a import A2AMessage, A2APart
    from agent_foundation.payloads.task import TaskRequest

    # Validate capability
    try:
        await validate_billing_capability(broker_url)
    except BillingPeerUnavailable:
        logger.warning("billing_peer_unavailable", case_id=str(case.case_id))
        raise

    # Stable idempotency key (AC2)
    if case.billing_task_id is None:
        case.billing_task_id = uuid.uuid5(case.correlation_id, BILLING_CAPABILITY_ID)

    billing_input = build_billing_request_input(case)
    task_request = TaskRequest(
        task_id=case.billing_task_id,
        capability=BILLING_CAPABILITY_ID,
        requester_agent_id=AGENT_ID,
        target_agent_id=BILLING_PEER_AGENT_ID,
        input=A2AMessage(
            role="user",
            parts=[
                A2APart(
                    type="data",
                    data=billing_input.model_dump(mode="json"),
                )
            ],
        ),
    )

    await publisher.publish(
        task_request,
        event_type="agent.task_request.v1",
        correlation_id=case.correlation_id,
        causation_id=ticket_envelope.event_id,
        topic=endpoint_topic(BILLING_PEER_AGENT_ID),
    )
    logger.info(
        "billing_task_requested",
        case_id=str(case.case_id),
        task_id=str(case.billing_task_id),
    )


async def delegate(
    case: ResolutionCase,
    *,
    publisher: Publisher,
    broker_url: str,
    ticket_envelope: EventEnvelope,
    state_store: object,
) -> None:
    """Issue billing and risk TaskRequests, then emit the RefundReviewRequestedPayload.

    After both TaskRequests publish successfully, emits TOPIC_REFUND_REVIEW_REQUESTED
    (Phase 11). Does not emit the announcement if either request fails (fail-closed).
    Records task_ids on the case and registers them in the state store.
    """
    # Emit requests — billing first, then risk
    try:
        await request_billing_analysis(
            case, publisher=publisher, broker_url=broker_url, ticket_envelope=ticket_envelope
        )
        await request_risk_analysis(
            case, publisher=publisher, broker_url=broker_url, ticket_envelope=ticket_envelope
        )
    except (BillingPeerUnavailable, RiskPeerUnavailable, Exception):
        logger.warning(
            "delegation_failed",
            case_id=str(case.case_id),
        )
        raise

    # Register task_ids in the state store secondary index
    if hasattr(state_store, "add_pending_task"):
        if case.billing_task_id:
            await state_store.add_pending_task(case.case_id, case.billing_task_id)
        if case.risk_task_id:
            await state_store.add_pending_task(case.case_id, case.risk_task_id)

    # Emit refund-review.requested announcement (Phase 11, T064)
    # "Accepted" == both publishes succeeded (async delegation model, research R2)
    if case.billing_task_id and case.risk_task_id:
        requested_at = datetime.now(UTC)
        announcement = RefundReviewRequestedPayload(
            case_id=case.correlation_id,
            ticket_id=case.ticket_id,
            customer_id=case.customer_id,
            requested_reviews=["billing", "risk"],
            billing_task_id=case.billing_task_id,
            risk_task_id=case.risk_task_id,
            timeout_seconds=DELEGATION_TIMEOUT_SECONDS,
            requested_at=requested_at,
        )
        await publisher.publish(
            announcement,
            event_type=TOPIC_REFUND_REVIEW_REQUESTED,
            correlation_id=case.correlation_id,
            causation_id=ticket_envelope.event_id,
        )
        logger.info(
            "refund_review_requested",
            case_id=str(case.case_id),
            billing_task_id=str(case.billing_task_id),
            risk_task_id=str(case.risk_task_id),
        )


def build_refund_review_requested(
    case: ResolutionCase,
    *,
    timeout_seconds: int | None = DELEGATION_TIMEOUT_SECONDS,
    requested_at: datetime | None = None,
) -> RefundReviewRequestedPayload:
    """Pure builder for the refund-review-requested payload (Phase 11 T062)."""
    if requested_at is None:
        requested_at = datetime.now(UTC)
    assert case.billing_task_id is not None
    assert case.risk_task_id is not None
    return RefundReviewRequestedPayload(
        case_id=case.correlation_id,
        ticket_id=case.ticket_id,
        customer_id=case.customer_id,
        requested_reviews=["billing", "risk"],
        billing_task_id=case.billing_task_id,
        risk_task_id=case.risk_task_id,
        timeout_seconds=timeout_seconds,
        requested_at=requested_at,
    )
