"""T041: High risk escalation — eligible billing + blocklist risk → escalate to human."""

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
    name="high_risk_escalation",
    support_ticket=make_support_ticket("CUS-004-HIGHRISK", reason="refund request", amount=49.99),
    mock_billing_profile=_billing_dataset["PR-APPROVE"],
    mock_risk_profile=_risk_dataset["CUS-BLOCKLIST"],
    expected_final_state=ExpectedFinalState(
        case_status=CaseStatus.ESCALATED,
        outcome=ResolutionOutcome.ESCALATE_HUMAN,
        escalation_reason="elevated_risk",
        expects_decision=True,
    ),
)
