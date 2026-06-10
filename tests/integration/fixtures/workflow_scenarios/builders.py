"""Shared scenario builders (006 T037).

Provides:
- FIXED_TS: a module-level fixed timestamp (no wall-clock at import).
- make_support_ticket(**kwargs): builds a SupportTicketCreatedPayload.
- instantiate(scenario, correlation_id): mints a per-run (case_id, ticket) pair.
- SILENT: sentinel for a peer profile that never responds.
- expected_event(topic_const, payload_type, caused_by=...): convenience constructor.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from packages.contracts.events.payloads import SupportTicketCreatedPayload
from packages.contracts.topics import (
    TOPIC_AUDIT,
    TOPIC_BILLING_RESULT,
    TOPIC_ISSUE_CLASSIFIED,
    TOPIC_REFUND_REVIEW_REQUESTED,
    TOPIC_RESOLUTION_DECIDED,
    TOPIC_RESPONSE_DRAFTED,
    TOPIC_RISK_RESULT,
)
from tests.integration.fixtures.workflow_scenarios.schema import (
    SILENT,
    ExpectedEvent,
    WorkflowScenario,
)

# Fixed timestamp: no wall-clock at import (replay determinism, FR-016)
FIXED_TS: datetime = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)


def make_support_ticket(
    customer_id: str,
    *,
    amount: float = 49.99,
    currency: str = "USD",
    reason: str = "charged twice",
    ticket_id: str | None = None,
    created_at: datetime | None = None,
) -> SupportTicketCreatedPayload:
    """Build a SupportTicketCreatedPayload with deterministic defaults."""
    return SupportTicketCreatedPayload(
        ticket_id=ticket_id or f"TKT-{customer_id}",
        customer_id=customer_id,
        amount=amount,
        currency=currency,
        reason=reason,
        created_at=created_at or FIXED_TS,
    )


def instantiate(
    scenario: WorkflowScenario,
    correlation_id: UUID | None = None,
) -> tuple[UUID, SupportTicketCreatedPayload]:
    """Mint a per-run (correlation_id, ticket) pair from a scenario.

    The same fixture can be reused across multiple test runs (e.g. the ≥10
    concurrent cases in US2/T013) by calling instantiate() once per run.
    """
    cid = correlation_id or uuid4()
    ticket_kwargs = scenario.support_ticket
    if isinstance(ticket_kwargs, SupportTicketCreatedPayload):
        # Already a built instance — create a copy with fresh IDs if needed
        return cid, ticket_kwargs
    # Treat as kwargs dict
    return cid, make_support_ticket(**ticket_kwargs)


def expected_event(
    topic: str,
    payload_type: type | None = None,
    *,
    caused_by: str | None = None,
    notes: str | None = None,
) -> ExpectedEvent:
    """Convenience constructor for ExpectedEvent, resolving topic via topics.py."""
    return ExpectedEvent(
        topic=topic,
        payload_type=payload_type,
        caused_by=caused_by,
        notes=notes,
    )


__all__ = [
    "FIXED_TS",
    "SILENT",
    "make_support_ticket",
    "instantiate",
    "expected_event",
]
