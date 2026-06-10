"""T230: Billing ineligible + low risk conflict → escalate_human/conflicting_analyses.

Decision-rule Row 8: ineligible billing + low risk produces a conflicting signal set.
The decision engine escalates rather than denying because the risk opinion does not
corroborate ineligibility (low risk suggests a legitimate customer).
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
    name="billing_ineligible_low_conflict",
    support_ticket=make_support_ticket(
        "CUS-010-INELIGIBLE-LOW", reason="refund request", amount=49.99
    ),
    mock_billing_profile=_billing_dataset["PR-WINDOW-EXPIRED"],
    mock_risk_profile=_risk_dataset["CUS-CLEAN"],
    expected_final_state=ExpectedFinalState(
        case_status=CaseStatus.ESCALATED,
        outcome=ResolutionOutcome.ESCALATE_HUMAN,
        escalation_reason="conflicting_analyses",
        expects_decision=True,
    ),
)
