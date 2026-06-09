"""Contract tests for resolution payloads and registry (T013, T049, T060, T103, T117, T132)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from agent_foundation.payloads import lookup
from packages.contracts.events.payloads import (
    CustomerIssueClassifiedPayload,
    CustomerResponseDecisionPayload,
    CustomerResponseDraftedPayload,
    RefundReviewRequestedPayload,
    ResolutionOutcome,
)
from packages.contracts.topics import (
    TOPIC_BILLING_RESULT,
    TOPIC_ISSUE_CLASSIFIED,
    TOPIC_REFUND_REVIEW_REQUESTED,
    TOPIC_RESOLUTION_DECIDED,
    TOPIC_RESPONSE_DRAFTED,
    TOPIC_RISK_RESULT,
)
from src.agent_foundation.transport.topics import TOPIC_NAMES

# --- CustomerResponseDecisionPayload ---

def test_decision_payload_round_trip():
    p = CustomerResponseDecisionPayload(
        case_id=uuid.uuid4(),
        ticket_id="TKT-001",
        customer_id="CUS-001",
        outcome=ResolutionOutcome.APPROVE_REFUND,
        customer_response="Refund approved.",
    )
    data = p.model_dump(mode="json")
    p2 = CustomerResponseDecisionPayload.model_validate(data)
    assert p2 == p


def test_decision_payload_escalation_reason_required():
    with pytest.raises(ValidationError):
        CustomerResponseDecisionPayload(
            case_id=uuid.uuid4(),
            ticket_id="T",
            customer_id="C",
            outcome=ResolutionOutcome.ESCALATE_HUMAN,
            customer_response="forwarded",
            # escalation_reason missing
        )


def test_decision_payload_escalation_reason_ok():
    p = CustomerResponseDecisionPayload(
        case_id=uuid.uuid4(),
        ticket_id="T",
        customer_id="C",
        outcome=ResolutionOutcome.ESCALATE_HUMAN,
        customer_response="forwarded",
        escalation_reason="peer_failure",
    )
    assert p.escalation_reason == "peer_failure"


def test_decision_payload_registered():
    model = lookup(TOPIC_RESOLUTION_DECIDED)
    assert model is CustomerResponseDecisionPayload


def test_topic_resolution_decided_in_topic_names():
    assert TOPIC_RESOLUTION_DECIDED in TOPIC_NAMES


# --- CustomerIssueClassifiedPayload ---

def test_classified_payload_round_trip():
    p = CustomerIssueClassifiedPayload(
        case_id=uuid.uuid4(),
        ticket_id="TKT-001",
        customer_id="CUS-001",
        issue_type="refund_request",
        confidence=0.95,
        requires_billing_review=True,
        requires_risk_review=True,
        requires_human_review=False,
        reasoning_summary="Refund intent detected",
    )
    data = p.model_dump(mode="json")
    p2 = CustomerIssueClassifiedPayload.model_validate(data)
    assert p2 == p


def test_classified_payload_confidence_bounds():
    with pytest.raises(ValidationError):
        CustomerIssueClassifiedPayload(
            case_id=uuid.uuid4(),
            ticket_id="T",
            customer_id="C",
            issue_type="x",
            confidence=1.5,  # invalid
            requires_billing_review=False,
            requires_risk_review=False,
            requires_human_review=False,
            reasoning_summary="",
        )


def test_classified_payload_registered():
    assert lookup(TOPIC_ISSUE_CLASSIFIED) is CustomerIssueClassifiedPayload


def test_topic_issue_classified_in_topic_names():
    assert TOPIC_ISSUE_CLASSIFIED in TOPIC_NAMES


# --- RefundReviewRequestedPayload ---

def test_refund_review_requested_round_trip():
    p = RefundReviewRequestedPayload(
        case_id=uuid.uuid4(),
        ticket_id="TKT-001",
        customer_id="CUS-001",
        requested_reviews=["billing", "risk"],
        billing_task_id=uuid.uuid4(),
        risk_task_id=uuid.uuid4(),
        requested_at=datetime.now(UTC),
    )
    data = p.model_dump(mode="json")
    p2 = RefundReviewRequestedPayload.model_validate(data)
    assert p2 == p


def test_refund_review_requested_empty_reviews():
    with pytest.raises(ValidationError):
        RefundReviewRequestedPayload(
            case_id=uuid.uuid4(),
            ticket_id="T",
            customer_id="C",
            requested_reviews=[],
            billing_task_id=uuid.uuid4(),
            risk_task_id=uuid.uuid4(),
            requested_at=datetime.now(UTC),
        )


def test_refund_review_requested_duplicate_reviews():
    with pytest.raises(ValidationError):
        RefundReviewRequestedPayload(
            case_id=uuid.uuid4(),
            ticket_id="T",
            customer_id="C",
            requested_reviews=["billing", "billing"],
            billing_task_id=uuid.uuid4(),
            risk_task_id=uuid.uuid4(),
            requested_at=datetime.now(UTC),
        )


def test_refund_review_registered():
    assert lookup(TOPIC_REFUND_REVIEW_REQUESTED) is RefundReviewRequestedPayload


def test_topic_refund_review_in_topic_names():
    assert TOPIC_REFUND_REVIEW_REQUESTED in TOPIC_NAMES


# --- CustomerResponseDraftedPayload ---

def test_response_drafted_round_trip():
    p = CustomerResponseDraftedPayload(
        case_id=uuid.uuid4(),
        ticket_id="TKT-001",
        customer_id="CUS-001",
        decision_event_id=uuid.uuid4(),
        outcome=ResolutionOutcome.DENY_REFUND,
        draft_response="We cannot process your refund.",
        requires_human_approval=False,
        drafted_at=datetime.now(UTC),
    )
    data = p.model_dump(mode="json")
    p2 = CustomerResponseDraftedPayload.model_validate(data)
    assert p2 == p


def test_response_drafted_empty_response():
    with pytest.raises(ValidationError):
        CustomerResponseDraftedPayload(
            case_id=uuid.uuid4(),
            ticket_id="T",
            customer_id="C",
            decision_event_id=uuid.uuid4(),
            outcome=ResolutionOutcome.DENY_REFUND,
            draft_response="",  # empty
            requires_human_approval=False,
            drafted_at=datetime.now(UTC),
        )


def test_response_drafted_escalate_requires_human_approval():
    with pytest.raises(ValidationError):
        CustomerResponseDraftedPayload(
            case_id=uuid.uuid4(),
            ticket_id="T",
            customer_id="C",
            decision_event_id=uuid.uuid4(),
            outcome=ResolutionOutcome.ESCALATE_HUMAN,
            draft_response="forwarded",
            requires_human_approval=False,  # must be True for escalate
            drafted_at=datetime.now(UTC),
        )


def test_response_drafted_registered():
    assert lookup(TOPIC_RESPONSE_DRAFTED) is CustomerResponseDraftedPayload


def test_topic_response_drafted_in_topic_names():
    assert TOPIC_RESPONSE_DRAFTED in TOPIC_NAMES


# --- Topic registration completeness ---

def test_billing_result_registered():
    from packages.contracts.events.payloads import BillingRefundAnalysisCompletedPayload
    assert lookup(TOPIC_BILLING_RESULT) is BillingRefundAnalysisCompletedPayload
    assert TOPIC_BILLING_RESULT in TOPIC_NAMES


def test_risk_result_registered():
    from packages.contracts.events.payloads import RiskReviewCompletedPayload
    assert lookup(TOPIC_RISK_RESULT) is RiskReviewCompletedPayload
    assert TOPIC_RISK_RESULT in TOPIC_NAMES
