"""Workflow scenario fixture schema (006 T036).

Frozen dataclasses/Pydantic models that describe a complete workflow scenario:
- ExpectedEvent: a single expected event in the choreography
- ExpectedFinalState: the expected terminal case state
- WorkflowScenario: the full scenario with billing/risk profiles and expectations

A SILENT sentinel value on a profile means that peer never responds (timeout path).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from packages.contracts.events.payloads import ResolutionOutcome

from apps.agents.customer_resolution.models import CaseStatus


class _SilentSentinel:
    """Marker indicating a peer agent never responds (timeout/reaper path)."""

    _instance: _SilentSentinel | None = None

    def __new__(cls) -> _SilentSentinel:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "SILENT"


SILENT: _SilentSentinel = _SilentSentinel()


@dataclass(frozen=True)
class ExpectedEvent:
    """A single expected choreography event (one step in the workflow).

    Attributes:
        topic:        The Kafka topic constant (from packages/contracts/topics.py).
        payload_type: Python type of the event payload (for isinstance checks).
        caused_by:    Human-readable note about what prior step triggered this one.
        notes:        Optional clarifying note.
    """

    topic: str
    payload_type: type | None = None
    caused_by: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class ExpectedFinalState:
    """The expected terminal case state after the scenario plays out.

    Attributes:
        case_status:            Terminal CaseStatus (CLOSED, ESCALATED, …).
        outcome:                Expected ResolutionOutcome, or None for non-decision paths.
        escalation_reason:      Expected escalation_reason string, or None.
        risk_flag_emitted:      Whether a separate risk-flag event should be emitted.
        expects_decision:       Whether a customer.resolution.decided event is expected.
        eligible_refund_amount: Expected eligible_refund_amount for partial-credit scenarios.
    """

    case_status: CaseStatus
    outcome: ResolutionOutcome | None = None
    escalation_reason: str | None = None
    risk_flag_emitted: bool = False
    expects_decision: bool = True
    eligible_refund_amount: Decimal | None = None


@dataclass
class WorkflowScenario:
    """A complete end-to-end workflow scenario fixture.

    Attributes:
        name:                  Unique scenario name (key in ALL_SCENARIOS registry).
        support_ticket:        SupportTicketCreatedPayload dict or factory kwargs.
        mock_billing_profile:  BillingFacts to seed into the billing agent, or SILENT.
        mock_risk_profile:     RiskSignals to seed into the risk agent, or SILENT.
        expected_events:       Ordered list of ExpectedEvent steps.
        expected_final_state:  Terminal state assertion.
    """

    name: str
    support_ticket: Any  # SupportTicketCreatedPayload kwargs or built instance
    mock_billing_profile: Any  # BillingFacts | SILENT
    mock_risk_profile: Any  # RiskSignals | SILENT
    expected_events: list[ExpectedEvent] = field(default_factory=list)
    expected_final_state: ExpectedFinalState | None = None
