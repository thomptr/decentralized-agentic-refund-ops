"""T045: Duplicate peer result event — billing result delivered twice; idempotency guard.

The billing analysis result is published twice (e.g. Kafka at-least-once redelivery).
The expected outcome is unchanged: the case should be decided exactly once.
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
    name="duplicate_peer_result_event",
    support_ticket=make_support_ticket(
        "CUS-008-DUPRESULT", reason="charged twice", amount=49.99
    ),
    mock_billing_profile=_billing_dataset["PR-APPROVE"],
    mock_risk_profile=_risk_dataset["CUS-CLEAN"],
    expected_final_state=ExpectedFinalState(
        case_status=CaseStatus.CLOSED,
        outcome=ResolutionOutcome.APPROVE_REFUND,
        expects_decision=True,
    ),
    # Test harness should deliver the billing result event twice to exercise
    # the idempotency guard on peer result intake.
)
