"""T043: Risk timeout — risk agent never responds → escalate with analysis_timeout."""

from apps.agents.billing_entitlement.mock_data import _DATASET as _billing_dataset
from packages.contracts.events.payloads import ResolutionOutcome
from tests.integration.fixtures.workflow_scenarios.builders import make_support_ticket
from tests.integration.fixtures.workflow_scenarios.schema import (
    SILENT,
    CaseStatus,
    ExpectedFinalState,
    WorkflowScenario,
)

SCENARIO = WorkflowScenario(
    name="risk_timeout",
    support_ticket=make_support_ticket("CUS-006-RTIMEOUT", reason="refund request", amount=49.99),
    mock_billing_profile=_billing_dataset["PR-APPROVE"],
    mock_risk_profile=SILENT,
    expected_final_state=ExpectedFinalState(
        case_status=CaseStatus.ESCALATED,
        outcome=ResolutionOutcome.ESCALATE_HUMAN,
        escalation_reason="analysis_timeout",
        expects_decision=True,
    ),
)
