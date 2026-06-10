"""T040: Billing denied — ineligible (window expired) + elevated risk → deny refund.

Decision-rule Row 5: ineligible + elevated/high → deny_refund.
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
    name="billing_denied",
    support_ticket=make_support_ticket("CUS-003-DENIED", reason="refund request", amount=49.99),
    mock_billing_profile=_billing_dataset["PR-WINDOW-EXPIRED"],
    mock_risk_profile=_risk_dataset["CUS-VELOCITY"],
    expected_final_state=ExpectedFinalState(
        case_status=CaseStatus.CLOSED,
        outcome=ResolutionOutcome.DENY_REFUND,
        escalation_reason=None,
        expects_decision=True,
    ),
)
