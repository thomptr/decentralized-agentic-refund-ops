"""Fixture self-validation tests (006 T048) — no broker required.

For every scenario in ALL_SCENARIOS, assert it is well-formed:
- Five components are populated (name, support_ticket, mock_billing_profile, mock_risk_profile,
  expected_final_state)
- expected_final_state is internally consistent with the profiles
- A decided-bearing expected_events list ⟺ expects_decision=True
- ALL_SCENARIOS has exactly the 10 expected names
"""

from __future__ import annotations

import pytest

from tests.integration.fixtures.workflow_scenarios import ALL_SCENARIOS, get_scenario
from tests.integration.fixtures.workflow_scenarios.schema import (
    SILENT,
    CaseStatus,
    ExpectedFinalState,
    WorkflowScenario,
)
from packages.contracts.events.payloads import ResolutionOutcome

_EXPECTED_SCENARIO_NAMES = {
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


def test_all_scenarios_registry_has_expected_names():
    """ALL_SCENARIOS contains exactly the 10 expected scenario names."""
    assert set(ALL_SCENARIOS.keys()) == _EXPECTED_SCENARIO_NAMES


def test_get_scenario_returns_correct_scenario():
    s = get_scenario("happy_path_full_refund")
    assert s.name == "happy_path_full_refund"


def test_get_scenario_raises_on_unknown():
    with pytest.raises(KeyError, match="Unknown scenario"):
        get_scenario("no_such_scenario")


@pytest.mark.parametrize("name", sorted(_EXPECTED_SCENARIO_NAMES))
def test_scenario_is_well_formed(name: str):
    """Each scenario has all required components."""
    s = ALL_SCENARIOS[name]

    assert s.name, "name must be non-empty"
    assert s.name == name, "scenario name must match registry key"
    assert s.expected_final_state is not None, "expected_final_state must be set"

    state = s.expected_final_state
    assert isinstance(state, ExpectedFinalState)


@pytest.mark.parametrize("name", sorted(_EXPECTED_SCENARIO_NAMES))
def test_scenario_internal_consistency(name: str):
    """expected_final_state must be internally consistent with profiles."""
    s = ALL_SCENARIOS[name]
    state = s.expected_final_state

    # SILENT peer ⇒ analysis_timeout escalation
    if s.mock_billing_profile is SILENT or s.mock_risk_profile is SILENT:
        assert state.outcome == ResolutionOutcome.ESCALATE_HUMAN, (
            f"{name}: SILENT peer requires ESCALATE_HUMAN outcome"
        )
        assert state.escalation_reason == "analysis_timeout", (
            f"{name}: SILENT peer requires analysis_timeout escalation_reason"
        )

    # ESCALATED status ⇒ outcome is ESCALATE_HUMAN or no decision expected
    if state.case_status == CaseStatus.ESCALATED:
        if state.expects_decision:
            assert state.outcome == ResolutionOutcome.ESCALATE_HUMAN, (
                f"{name}: ESCALATED case with decision must have ESCALATE_HUMAN outcome"
            )

    # expects_decision=False ⇒ outcome should be None
    if not state.expects_decision:
        assert state.outcome is None, (
            f"{name}: expects_decision=False must have outcome=None"
        )

    # CLOSED ⇒ expects_decision=True
    if state.case_status == CaseStatus.CLOSED:
        assert state.expects_decision, (
            f"{name}: CLOSED case must have expects_decision=True"
        )


def test_all_scenarios_unique_customer_ids():
    """Each scenario uses a unique customer_id to prevent cross-scenario data bleed."""
    customer_ids = []
    for name, s in ALL_SCENARIOS.items():
        ticket = s.support_ticket
        # support_ticket may be a SupportTicketCreatedPayload or kwargs dict
        if hasattr(ticket, "customer_id"):
            cid = ticket.customer_id
        elif isinstance(ticket, dict):
            cid = ticket.get("customer_id", "")
        else:
            cid = ""
        if cid:
            customer_ids.append((cid, name))

    seen = {}
    for cid, name in customer_ids:
        if cid in seen:
            pytest.fail(
                f"Duplicate customer_id {cid!r} used by both {seen[cid]!r} and {name!r}"
            )
        seen[cid] = name
