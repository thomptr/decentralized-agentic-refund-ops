"""Shared test fixtures for the Customer Resolution Agent test suite (T002)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from uuid import UUID

import pytest

from agent_foundation.a2a import A2AMessage, A2APart
from agent_foundation.payloads.task import TaskError, TaskResult
from apps.agents.customer_resolution.models import (
    BillingFinding,
    RiskFinding,
)
from apps.agents.customer_resolution.state_store import InMemoryCaseStateStore
from packages.contracts.events.payloads import SupportTicketCreatedPayload


def make_ticket(
    *,
    ticket_id: str = "TKT-001",
    customer_id: str = "CUS-001",
    amount: float = 49.99,
    currency: str = "USD",
    reason: str = "I was charged twice for my subscription, please refund",
) -> SupportTicketCreatedPayload:
    return SupportTicketCreatedPayload(
        ticket_id=ticket_id,
        customer_id=customer_id,
        amount=amount,
        currency=currency,
        reason=reason,
        created_at=datetime.now(UTC),
    )


def make_non_refund_ticket() -> SupportTicketCreatedPayload:
    return make_ticket(
        ticket_id="TKT-002",
        reason="How do I change my email address?",
    )


def make_billing_task_result(
    task_id: UUID,
    *,
    eligible: bool = True,
    requires_human_review: bool = False,
    status: str = "completed",
) -> TaskResult:
    if status == "completed":
        return TaskResult(
            task_id=task_id,
            status="completed",
            performer_agent_id="billing-entitlement-agent",
            output=A2AMessage(
                role="agent",
                parts=[
                    A2APart(
                        type="data",
                        data={
                            "eligible": eligible,
                            "reason": "mock",
                            "task_id": str(task_id),
                        },
                    )
                ],
            ),
        )
    return TaskResult(
        task_id=task_id,
        status=status,
        performer_agent_id="billing-entitlement-agent",
        error=TaskError(category="handler_error", message="billing failed"),
    )


def make_risk_task_result(
    task_id: UUID,
    *,
    risk_level: str = "low",
    score: float = 0.1,
    requires_human_review: bool = False,
    status: str = "completed",
) -> TaskResult:
    if status == "completed":
        return TaskResult(
            task_id=task_id,
            status="completed",
            performer_agent_id="risk-fraud-agent",
            output=A2AMessage(
                role="agent",
                parts=[
                    A2APart(
                        type="data",
                        data={
                            "risk": risk_level,
                            "score": score,
                            "task_id": str(task_id),
                        },
                    )
                ],
            ),
        )
    return TaskResult(
        task_id=task_id,
        status=status,
        performer_agent_id="risk-fraud-agent",
        error=TaskError(category="handler_error", message="risk failed"),
    )


@pytest.fixture
def store() -> InMemoryCaseStateStore:
    return InMemoryCaseStateStore()


@pytest.fixture
def refund_ticket() -> SupportTicketCreatedPayload:
    return make_ticket()


@pytest.fixture
def non_refund_ticket() -> SupportTicketCreatedPayload:
    return make_non_refund_ticket()


@pytest.fixture
def eligible_billing() -> BillingFinding:
    return BillingFinding(
        eligibility="eligible",
        confidence=0.9,
        task_id=uuid.uuid4(),
        performer_agent_id="billing-entitlement-agent",
    )


@pytest.fixture
def ineligible_billing() -> BillingFinding:
    return BillingFinding(
        eligibility="ineligible",
        confidence=0.9,
        task_id=uuid.uuid4(),
        performer_agent_id="billing-entitlement-agent",
    )


@pytest.fixture
def low_risk() -> RiskFinding:
    return RiskFinding(
        level="low",
        score=0.1,
        task_id=uuid.uuid4(),
        performer_agent_id="risk-fraud-agent",
    )


@pytest.fixture
def high_risk() -> RiskFinding:
    return RiskFinding(
        level="high",
        score=0.9,
        task_id=uuid.uuid4(),
        performer_agent_id="risk-fraud-agent",
    )
