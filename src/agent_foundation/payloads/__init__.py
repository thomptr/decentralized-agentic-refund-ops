from __future__ import annotations

from pydantic import BaseModel

from agent_foundation.a2a import A2AMessage
from agent_foundation.llm.audit_events import (
    LlmInvocationCompletedPayload,
    LlmInvocationFailedPayload,
)
from agent_foundation.payloads.sample import AuditPayload, SamplePayload
from agent_foundation.payloads.support_ticket import SupportTicketCreatedPayload
from agent_foundation.payloads.task import TaskRequest, TaskResult
from agent_foundation.runtime.agent_card import AgentCard
from packages.contracts.events.payloads import (
    BillingRefundAnalysisCompletedPayload,
    CustomerIssueClassifiedPayload,
    CustomerResponseDecisionPayload,
    CustomerResponseDraftedPayload,
    RefundReviewRequestedPayload,
    RiskReviewCompletedPayload,
)
from packages.contracts.topics import (
    TOPIC_BILLING_RESULT,
    TOPIC_ISSUE_CLASSIFIED,
    TOPIC_LLM_INVOCATION_COMPLETED,
    TOPIC_LLM_INVOCATION_FAILED,
    TOPIC_REFUND_REVIEW_REQUESTED,
    TOPIC_RESOLUTION_DECIDED,
    TOPIC_RESPONSE_DRAFTED,
    TOPIC_RISK_RESULT,
    topic_for,
)

_TICKET_CREATED_ET = topic_for("support", "ticket", "created")

PAYLOAD_REGISTRY: dict[str, type[BaseModel]] = {
    "agent.message.v1": A2AMessage,
    "agent.audit.v1": AuditPayload,
    "agent.sample.v1": SamplePayload,
    "agent.task_request.v1": TaskRequest,
    "agent.task_result.v1": TaskResult,
    "agent.agent_card.v1": AgentCard,
    # Dev/demo domain event; included so Publisher can validate and send it.
    _TICKET_CREATED_ET: SupportTicketCreatedPayload,
    # Feature 003: Customer Resolution Agent events
    TOPIC_RESOLUTION_DECIDED: CustomerResponseDecisionPayload,
    TOPIC_ISSUE_CLASSIFIED: CustomerIssueClassifiedPayload,
    TOPIC_REFUND_REVIEW_REQUESTED: RefundReviewRequestedPayload,
    TOPIC_BILLING_RESULT: BillingRefundAnalysisCompletedPayload,
    TOPIC_RISK_RESULT: RiskReviewCompletedPayload,
    TOPIC_RESPONSE_DRAFTED: CustomerResponseDraftedPayload,
    # Feature 008: LLM audit event payloads (opt-in, observability-only)
    TOPIC_LLM_INVOCATION_COMPLETED: LlmInvocationCompletedPayload,
    TOPIC_LLM_INVOCATION_FAILED: LlmInvocationFailedPayload,
}


class UnknownEventType(KeyError):
    def __init__(self, event_type: str) -> None:
        super().__init__(f"No payload model registered for event_type={event_type!r}")
        self.event_type = event_type


class PayloadValidationError(ValueError):
    def __init__(self, event_type: str, detail: str) -> None:
        super().__init__(f"Payload validation failed for event_type={event_type!r}: {detail}")
        self.event_type = event_type
        self.detail = detail


def lookup(event_type: str) -> type[BaseModel]:
    """Return the Pydantic model registered for the given event_type."""
    try:
        return PAYLOAD_REGISTRY[event_type]
    except KeyError as err:
        raise UnknownEventType(event_type) from err
