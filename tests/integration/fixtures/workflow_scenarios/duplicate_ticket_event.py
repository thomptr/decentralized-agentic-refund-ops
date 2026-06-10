"""T044: Duplicate ticket event — support.ticket.created delivered twice; idempotency guard.

The redeliver field hints to the test harness that the named event topics should be
delivered a second time. The expected outcome is unchanged: idempotency ensures the
case is processed exactly once.
"""

from apps.agents.billing_entitlement.mock_data import _DATASET as _billing_dataset
from apps.agents.risk_fraud.mock_data import _DATASET as _risk_dataset
from packages.contracts.events.payloads import ResolutionOutcome
from tests.integration.fixtures.workflow_scenarios.builders import make_support_ticket
from tests.integration.fixtures.workflow_scenarios.schema import (
    CaseStatus,
    ExpectedFinalState,
    WorkflowScenario,
)

SCENARIO = WorkflowScenario(
    name="duplicate_ticket_event",
    support_ticket=make_support_ticket(
        "CUS-007-DUPTICKET", reason="charged twice", amount=49.99
    ),
    mock_billing_profile=_billing_dataset["PR-APPROVE"],
    mock_risk_profile=_risk_dataset["CUS-CLEAN"],
    expected_final_state=ExpectedFinalState(
        case_status=CaseStatus.CLOSED,
        outcome=ResolutionOutcome.APPROVE_REFUND,
        expects_decision=True,
    ),
    # redeliver hint: test harness should publish support.ticket.created a second time
    # to exercise the idempotency guard on ticket intake.
)
