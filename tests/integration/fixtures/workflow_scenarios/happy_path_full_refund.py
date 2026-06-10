"""T038: Happy path — eligible billing + low risk → full refund approved."""

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
    name="happy_path_full_refund",
    support_ticket=make_support_ticket("CUS-001-HAPPY", reason="charged twice", amount=49.99),
    mock_billing_profile=_billing_dataset["PR-APPROVE"],
    mock_risk_profile=_risk_dataset["CUS-CLEAN"],
    expected_final_state=ExpectedFinalState(
        case_status=CaseStatus.CLOSED,
        outcome=ResolutionOutcome.APPROVE_REFUND,
        escalation_reason=None,
        expects_decision=True,
    ),
)
