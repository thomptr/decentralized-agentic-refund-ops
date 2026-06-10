"""T046: Unknown case result — orphan billing result with no matching case.

No support ticket is created. A lone billing result arrives for a case_id that
does not exist in the store. No decision should be emitted; the event is silently
dropped (or logged) and the case status remains at the initial RECEIVED sentinel.
"""

from apps.agents.billing_entitlement.mock_data import _DATASET as _billing_dataset
from tests.integration.fixtures.workflow_scenarios.schema import (
    CaseStatus,
    ExpectedFinalState,
    WorkflowScenario,
)

SCENARIO = WorkflowScenario(
    name="unknown_case_result",
    support_ticket=None,
    mock_billing_profile=_billing_dataset["PR-APPROVE"],
    mock_risk_profile=None,
    expected_final_state=ExpectedFinalState(
        case_status=CaseStatus.RECEIVED,
        outcome=None,
        expects_decision=False,
    ),
)
