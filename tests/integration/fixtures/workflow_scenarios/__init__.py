"""Workflow scenario fixture registry (T047).

ALL_SCENARIOS maps scenario name → WorkflowScenario for all 10 defined scenarios.
Use get_scenario(name) for safe keyed access.
"""

from tests.integration.fixtures.workflow_scenarios.billing_denied import (
    SCENARIO as _billing_denied,
)
from tests.integration.fixtures.workflow_scenarios.billing_ineligible_low_conflict import (
    SCENARIO as _billing_ineligible_low_conflict,
)
from tests.integration.fixtures.workflow_scenarios.billing_timeout import (
    SCENARIO as _billing_timeout,
)
from tests.integration.fixtures.workflow_scenarios.duplicate_peer_result_event import (
    SCENARIO as _duplicate_peer_result_event,
)
from tests.integration.fixtures.workflow_scenarios.duplicate_ticket_event import (
    SCENARIO as _duplicate_ticket_event,
)
from tests.integration.fixtures.workflow_scenarios.happy_path_full_refund import (
    SCENARIO as _happy_path_full_refund,
)
from tests.integration.fixtures.workflow_scenarios.high_risk_escalation import (
    SCENARIO as _high_risk_escalation,
)
from tests.integration.fixtures.workflow_scenarios.partial_refund import (
    SCENARIO as _partial_refund,
)
from tests.integration.fixtures.workflow_scenarios.risk_timeout import (
    SCENARIO as _risk_timeout,
)
from tests.integration.fixtures.workflow_scenarios.schema import WorkflowScenario
from tests.integration.fixtures.workflow_scenarios.unknown_case_result import (
    SCENARIO as _unknown_case_result,
)

ALL_SCENARIOS: dict[str, WorkflowScenario] = {
    s.name: s
    for s in [
        _happy_path_full_refund,
        _partial_refund,
        _billing_denied,
        _high_risk_escalation,
        _billing_timeout,
        _risk_timeout,
        _duplicate_ticket_event,
        _duplicate_peer_result_event,
        _unknown_case_result,
        _billing_ineligible_low_conflict,
    ]
}

_EXPECTED_NAMES = {
    "happy_path_full_refund",
    "partial_refund",
    "billing_denied",
    "high_risk_escalation",
    "billing_timeout",
    "risk_timeout",
    "duplicate_ticket_event",
    "duplicate_peer_result_event",
    "unknown_case_result",
    "billing_ineligible_low_conflict",
}

assert set(ALL_SCENARIOS.keys()) == _EXPECTED_NAMES, (
    f"ALL_SCENARIOS keys mismatch. "
    f"Missing: {_EXPECTED_NAMES - set(ALL_SCENARIOS.keys())}. "
    f"Extra: {set(ALL_SCENARIOS.keys()) - _EXPECTED_NAMES}."
)


def get_scenario(name: str) -> WorkflowScenario:
    """Return the named scenario, raising KeyError with a helpful message if absent."""
    try:
        return ALL_SCENARIOS[name]
    except KeyError:
        raise KeyError(f"Unknown scenario {name!r}. Available: {sorted(ALL_SCENARIOS)}") from None


__all__ = [
    "ALL_SCENARIOS",
    "get_scenario",
    "WorkflowScenario",
]
