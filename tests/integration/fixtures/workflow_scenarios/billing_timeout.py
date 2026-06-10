"""T042: Billing timeout — billing agent never responds → escalate with analysis_timeout."""

from apps.agents.risk_fraud.mock_data import _DATASET as _risk_dataset
from packages.contracts.events.payloads import ResolutionOutcome
from tests.integration.fixtures.workflow_scenarios.builders import make_support_ticket
from tests.integration.fixtures.workflow_scenarios.schema import (
    SILENT,
    CaseStatus,
    ExpectedFinalState,
    WorkflowScenario,
)

SCENARIO = WorkflowScenario(
    name="billing_timeout",
    support_ticket=make_support_ticket("CUS-005-BTIMEOUT", reason="refund request", amount=49.99),
    mock_billing_profile=SILENT,
    mock_risk_profile=_risk_dataset["CUS-CLEAN"],
    expected_final_state=ExpectedFinalState(
        case_status=CaseStatus.ESCALATED,
        outcome=ResolutionOutcome.ESCALATE_HUMAN,
        escalation_reason="analysis_timeout",
        expects_decision=True,
    ),
)
