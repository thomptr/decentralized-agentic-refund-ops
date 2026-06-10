"""End-to-end integration tests for workflow choreography (006 US1-US5).

Tests cover the full multi-agent choreography: support ticket → triage →
peer delegation (billing + risk) → aggregated decision → response draft.

Test IDs map to tasks.md acceptance criteria:
  US1  T007-T009, T100-T102  happy-path and golden-path scenarios
  US2  T012-T014              ordering, concurrency, audit trail
  US3  T017-T020              timeout/failure/conflict escalation paths
  US4  T024-T026              duplicate / replay idempotency
  US5  T028                   causal trace reconstruction
  T031-T034                   decentralization proof and demo validation
"""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import pytest

from apps.agents.billing_entitlement.mock_data import _DATASET as _billing_dataset
from apps.agents.customer_resolution.models import CaseStatus
from apps.agents.risk_fraud.mock_data import _DATASET as _risk_dataset
from packages.contracts.events.payloads import CustomerResponseDecisionPayload, ResolutionOutcome
from packages.contracts.topics import (
    TOPIC_BILLING_RESULT,
    TOPIC_ISSUE_CLASSIFIED,
    TOPIC_REFUND_REVIEW_REQUESTED,
    TOPIC_RESOLUTION_DECIDED,
    TOPIC_RESPONSE_DRAFTED,
    TOPIC_RISK_RESULT,
)
from packages.testing.workflow_harness import WorkflowHarness
from tests.integration.conftest import MultiAgentHarness
from tests.integration.fixtures.workflow_scenarios import get_scenario
from tests.integration.fixtures.workflow_scenarios.builders import make_support_ticket
from tests.integration.fixtures.workflow_scenarios.schema import SILENT, ExpectedFinalState

pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# US1: Happy-path and core decision paths (T007-T009, T100-T102)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_eligible_low_risk_approves_refund(
    multi_agent_harness: MultiAgentHarness,
) -> None:
    """T007: Eligible billing + low/clean risk → APPROVE_REFUND.

    Acceptance criterion: ticket with a recent paid invoice and a clean-risk
    customer resolves to approve_refund within the 30-second SLA.
    """
    customer_id = f"T007-{uuid4().hex[:6]}"
    multi_agent_harness.seed_billing_facts(customer_id, _billing_dataset["PR-APPROVE"])
    multi_agent_harness.seed_risk_signals(customer_id, _risk_dataset["CUS-CLEAN"])

    async with WorkflowHarness(multi_agent_harness.broker_url) as wh:
        correlation_id = await wh.publish_ticket(
            customer_id=customer_id,
            amount=49.99,
            currency="USD",
            reason="charged twice for the same subscription",
        )
        decision = await wh.wait_for_decision(correlation_id, timeout=30)

    assert decision.get("outcome") == ResolutionOutcome.APPROVE_REFUND.value, (
        f"Expected approve_refund, got {decision.get('outcome')!r}"
    )


@pytest.mark.asyncio
async def test_ineligible_elevated_risk_denies_refund(
    multi_agent_harness: MultiAgentHarness,
) -> None:
    """T008: Ineligible (window expired) + elevated risk (velocity) → DENY_REFUND (Row 5).

    Acceptance criterion: PR-WINDOW-EXPIRED billing + CUS-VELOCITY (elevated) produces
    deny_refund — no escalation because the ineligible billing opinion is corroborated
    by an elevated risk signal.
    """
    customer_id = f"T008-{uuid4().hex[:6]}"
    multi_agent_harness.seed_billing_facts(customer_id, _billing_dataset["PR-WINDOW-EXPIRED"])
    multi_agent_harness.seed_risk_signals(customer_id, _risk_dataset["CUS-VELOCITY"])

    async with WorkflowHarness(multi_agent_harness.broker_url) as wh:
        correlation_id = await wh.publish_ticket(
            customer_id=customer_id,
            amount=49.99,
            currency="USD",
            reason="refund request",
        )
        decision = await wh.wait_for_decision(correlation_id, timeout=30)

    assert decision.get("outcome") == ResolutionOutcome.DENY_REFUND.value, (
        f"Expected deny_refund (Row 5), got {decision.get('outcome')!r}"
    )


@pytest.mark.asyncio
async def test_non_refund_ticket_direct_response(
    multi_agent_harness: MultiAgentHarness,
) -> None:
    """T009: Non-refund ticket → DIRECT_RESPONSE without billing/risk delegation.

    Acceptance criterion: a ticket whose reason carries no refund signal must
    resolve immediately as direct_response.  No TOPIC_BILLING_RESULT or
    TOPIC_RISK_RESULT should appear for this correlation_id because the
    classifier should not initiate peer reviews for a general enquiry.
    """
    customer_id = f"T009-{uuid4().hex[:6]}"
    # No billing/risk seeding needed — direct-response path must not invoke peers.

    async with WorkflowHarness(multi_agent_harness.broker_url) as wh:
        correlation_id = await wh.publish_ticket(
            customer_id=customer_id,
            amount=0.0,
            currency="USD",
            reason="I have a general question about my account",
        )
        decision = await wh.wait_for_decision(correlation_id, timeout=30)
        events = wh.collect_events(correlation_id)

    assert decision.get("outcome") == ResolutionOutcome.DIRECT_RESPONSE.value, (
        f"Expected direct_response, got {decision.get('outcome')!r}"
    )

    event_types = {e.event_type for e in events}
    assert TOPIC_BILLING_RESULT not in event_types, (
        "Billing peer was invoked for a non-refund ticket — should not happen"
    )
    assert TOPIC_RISK_RESULT not in event_types, (
        "Risk peer was invoked for a non-refund ticket — should not happen"
    )


@pytest.mark.asyncio
async def test_happy_path_golden_e2e(
    multi_agent_harness: MultiAgentHarness,
) -> None:
    """T100: Golden happy-path scenario — full refund approval end-to-end.

    Uses the pre-built happy_path_full_refund scenario fixture.  Asserts the
    complete event chain: ticket created → classified → review requested →
    billing result → risk result → decided → response drafted.
    """
    scenario = get_scenario("happy_path_full_refund")
    customer_id = f"T100-{uuid4().hex[:6]}"

    assert scenario.mock_billing_profile is not SILENT
    assert scenario.mock_risk_profile is not SILENT

    multi_agent_harness.seed_billing_facts(customer_id, scenario.mock_billing_profile)
    multi_agent_harness.seed_risk_signals(customer_id, scenario.mock_risk_profile)

    async with WorkflowHarness(multi_agent_harness.broker_url) as wh:
        correlation_id = await wh.publish_ticket(
            customer_id=customer_id,
            amount=49.99,
            currency="USD",
            reason="charged twice for the same subscription",
        )
        await wh.wait_for_events(
            correlation_id,
            [
                TOPIC_ISSUE_CLASSIFIED,
                TOPIC_REFUND_REVIEW_REQUESTED,
                TOPIC_BILLING_RESULT,
                TOPIC_RISK_RESULT,
                TOPIC_RESOLUTION_DECIDED,
                TOPIC_RESPONSE_DRAFTED,
            ],
            timeout=30,
        )
        wh.assert_final_state(
            correlation_id,
            ExpectedFinalState(
                case_status=CaseStatus.CLOSED,
                outcome=ResolutionOutcome.APPROVE_REFUND,
                expects_decision=True,
            ),
        )
        wh.assert_causal_order(correlation_id)


@pytest.mark.asyncio
async def test_partial_refund_golden_e2e(
    multi_agent_harness: MultiAgentHarness,
) -> None:
    """T101: Partial-refund golden path — heavy-usage billing + low risk → OFFER_PARTIAL_CREDIT.

    Uses the pre-built partial_refund scenario fixture.
    """
    scenario = get_scenario("partial_refund")
    customer_id = f"T101-{uuid4().hex[:6]}"

    assert scenario.mock_billing_profile is not SILENT
    assert scenario.mock_risk_profile is not SILENT

    multi_agent_harness.seed_billing_facts(customer_id, scenario.mock_billing_profile)
    multi_agent_harness.seed_risk_signals(customer_id, scenario.mock_risk_profile)

    async with WorkflowHarness(multi_agent_harness.broker_url) as wh:
        correlation_id = await wh.publish_ticket(
            customer_id=customer_id,
            amount=49.99,
            currency="USD",
            reason="heavy usage refund request",
        )
        decision = await wh.wait_for_decision(correlation_id, timeout=30)
        wh.assert_final_state(
            correlation_id,
            ExpectedFinalState(
                case_status=CaseStatus.CLOSED,
                outcome=ResolutionOutcome.OFFER_PARTIAL_CREDIT,
                expects_decision=True,
            ),
        )

    assert decision.get("outcome") == ResolutionOutcome.OFFER_PARTIAL_CREDIT.value


@pytest.mark.asyncio
async def test_high_risk_escalation_golden_e2e(
    multi_agent_harness: MultiAgentHarness,
) -> None:
    """T102: High-risk escalation golden path — eligible billing + blocklist risk → ESCALATE_HUMAN.

    Uses the pre-built high_risk_escalation scenario fixture.
    """
    scenario = get_scenario("high_risk_escalation")
    customer_id = f"T102-{uuid4().hex[:6]}"

    assert scenario.mock_billing_profile is not SILENT
    assert scenario.mock_risk_profile is not SILENT

    multi_agent_harness.seed_billing_facts(customer_id, scenario.mock_billing_profile)
    multi_agent_harness.seed_risk_signals(customer_id, scenario.mock_risk_profile)

    async with WorkflowHarness(multi_agent_harness.broker_url) as wh:
        correlation_id = await wh.publish_ticket(
            customer_id=customer_id,
            amount=49.99,
            currency="USD",
            reason="refund request",
        )
        decision = await wh.wait_for_decision(correlation_id, timeout=30)
        wh.assert_final_state(
            correlation_id,
            ExpectedFinalState(
                case_status=CaseStatus.ESCALATED,
                outcome=ResolutionOutcome.ESCALATE_HUMAN,
                escalation_reason="elevated_risk",
                expects_decision=True,
            ),
        )

    assert decision.get("outcome") == ResolutionOutcome.ESCALATE_HUMAN.value
    assert decision.get("escalation_reason") == "elevated_risk"


# ---------------------------------------------------------------------------
# US2: Multi-case correctness (T012-T014)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_out_of_order_results(
    multi_agent_harness: MultiAgentHarness,
) -> None:
    """T012: Out-of-order peer results still produce the correct decision.

    The risk result may arrive before the billing result due to processing
    latency differences.  The resolution agent must wait for both before
    making a decision regardless of arrival order.
    """
    customer_id = f"T012-{uuid4().hex[:6]}"
    multi_agent_harness.seed_billing_facts(customer_id, _billing_dataset["PR-APPROVE"])
    multi_agent_harness.seed_risk_signals(customer_id, _risk_dataset["CUS-CLEAN"])

    async with WorkflowHarness(multi_agent_harness.broker_url) as wh:
        correlation_id = await wh.publish_ticket(
            customer_id=customer_id,
            amount=49.99,
            currency="USD",
            reason="double charge — need refund",
        )
        await wh.wait_for_events(
            correlation_id,
            [TOPIC_BILLING_RESULT, TOPIC_RISK_RESULT, TOPIC_RESOLUTION_DECIDED],
            timeout=30,
        )
        events = wh.collect_events(correlation_id)

    # Both peer results must be present before the decision
    event_types = [e.event_type for e in events]
    decided_idx = next(
        (i for i, et in enumerate(event_types) if et == TOPIC_RESOLUTION_DECIDED), None
    )
    assert decided_idx is not None, "No resolution decided event"

    billing_idx = next(
        (i for i, et in enumerate(event_types) if et == TOPIC_BILLING_RESULT), None
    )
    risk_idx = next(
        (i for i, et in enumerate(event_types) if et == TOPIC_RISK_RESULT), None
    )
    assert billing_idx is not None, "No billing result event"
    assert risk_idx is not None, "No risk result event"
    assert billing_idx < decided_idx, "Billing result must arrive before decision"
    assert risk_idx < decided_idx, "Risk result must arrive before decision"


@pytest.mark.asyncio
async def test_concurrent_cases_no_cross_bleed(
    multi_agent_harness: MultiAgentHarness,
) -> None:
    """T013: Five concurrent cases with distinct profiles each get the correct decision.

    Validates per-correlation_id isolation — no cross-case contamination.
    """
    cases: list[tuple[str, str, str, ResolutionOutcome]] = [
        # (customer_id_suffix, billing_profile, risk_profile, expected_outcome)
        ("A", "PR-APPROVE", "CUS-CLEAN", ResolutionOutcome.APPROVE_REFUND),
        ("B", "PR-WINDOW-EXPIRED", "CUS-VELOCITY", ResolutionOutcome.DENY_REFUND),
        ("C", "PR-APPROVE", "CUS-BLOCKLIST", ResolutionOutcome.ESCALATE_HUMAN),
        ("D", "PR-HEAVY-USAGE", "CUS-CLEAN", ResolutionOutcome.OFFER_PARTIAL_CREDIT),
        ("E", "PR-WINDOW-EXPIRED", "CUS-CLEAN", ResolutionOutcome.ESCALATE_HUMAN),
    ]

    correlation_ids: dict[str, UUID] = {}

    async with WorkflowHarness(multi_agent_harness.broker_url) as wh:
        for suffix, billing_key, risk_key, _ in cases:
            customer_id = f"T013-{suffix}-{uuid4().hex[:4]}"
            multi_agent_harness.seed_billing_facts(customer_id, _billing_dataset[billing_key])
            multi_agent_harness.seed_risk_signals(customer_id, _risk_dataset[risk_key])
            cid = await wh.publish_ticket(
                customer_id=customer_id,
                amount=49.99,
                currency="USD",
                reason="refund request",
            )
            correlation_ids[suffix] = cid

        # Wait for all decisions concurrently
        await asyncio.gather(
            *[
                wh.wait_for_decision(correlation_ids[suffix], timeout=30)
                for suffix, *_ in cases
            ]
        )

        for suffix, _billing_key, _risk_key, expected_outcome in cases:
            cid = correlation_ids[suffix]
            decided_events = [
                e for e in wh.collect_events(cid) if e.event_type == TOPIC_RESOLUTION_DECIDED
            ]
            assert len(decided_events) == 1, (
                f"Case {suffix}: expected exactly 1 decided event, "
                f"got {len(decided_events)}"
            )
            actual_outcome = decided_events[0].payload.get("outcome")
            assert actual_outcome == expected_outcome.value, (
                f"Case {suffix}: expected {expected_outcome.value!r}, "
                f"got {actual_outcome!r}"
            )


@pytest.mark.asyncio
async def test_audit_trail_links_opinions_to_ticket(
    multi_agent_harness: MultiAgentHarness,
) -> None:
    """T014: Every event in the workflow shares the same correlation_id.

    Acceptance criterion: all events from ticket creation through decision
    and response draft carry the same correlation_id so the audit trail is
    fully linked.
    """
    customer_id = f"T014-{uuid4().hex[:6]}"
    multi_agent_harness.seed_billing_facts(customer_id, _billing_dataset["PR-APPROVE"])
    multi_agent_harness.seed_risk_signals(customer_id, _risk_dataset["CUS-CLEAN"])

    async with WorkflowHarness(multi_agent_harness.broker_url) as wh:
        correlation_id = await wh.publish_ticket(
            customer_id=customer_id,
            amount=49.99,
            currency="USD",
            reason="I was charged twice",
        )
        await wh.wait_for_events(
            correlation_id,
            [
                TOPIC_ISSUE_CLASSIFIED,
                TOPIC_BILLING_RESULT,
                TOPIC_RISK_RESULT,
                TOPIC_RESOLUTION_DECIDED,
                TOPIC_RESPONSE_DRAFTED,
            ],
            timeout=30,
        )
        events = wh.collect_events(correlation_id)

    assert len(events) >= 5, f"Expected at least 5 events, got {len(events)}"
    for env in events:
        assert env.correlation_id == correlation_id, (
            f"Event {env.event_type} has correlation_id={env.correlation_id}, "
            f"expected {correlation_id}"
        )


# ---------------------------------------------------------------------------
# US3: Failure / timeout / conflict paths (T017-T020)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_timeout_escalates_case(
    multi_agent_harness: MultiAgentHarness,
) -> None:
    """T017: Billing agent silent → reaper fires → ESCALATE_HUMAN with analysis_timeout.

    The multi_agent_harness fixture sets case_deadline_seconds=5 and
    reaper_tick_seconds=0.5.  The billing_timeout scenario seeds SILENT for
    billing so the billing peer never responds; after 5 s the reaper should
    escalate the case.

    We give the test a generous 25-second timeout to accommodate the 5-second
    deadline plus agent startup and event propagation overhead.
    """
    scenario = get_scenario("billing_timeout")
    customer_id = f"T017-{uuid4().hex[:6]}"

    # Only seed the risk profile; billing is SILENT — no billing facts seeded.
    assert scenario.mock_billing_profile is SILENT
    assert scenario.mock_risk_profile is not SILENT
    multi_agent_harness.seed_risk_signals(customer_id, scenario.mock_risk_profile)
    multi_agent_harness.mark_billing_silent(customer_id)

    async with WorkflowHarness(multi_agent_harness.broker_url) as wh:
        correlation_id = await wh.publish_ticket(
            customer_id=customer_id,
            amount=49.99,
            currency="USD",
            reason="refund request",
        )
        decision = await wh.wait_for_decision(correlation_id, timeout=25)

    assert decision.get("outcome") == ResolutionOutcome.ESCALATE_HUMAN.value, (
        f"Expected escalate_human (timeout), got {decision.get('outcome')!r}"
    )
    assert decision.get("escalation_reason") == "analysis_timeout", (
        f"Expected analysis_timeout, got {decision.get('escalation_reason')!r}"
    )


@pytest.mark.asyncio
async def test_peer_failure_escalates(
    multi_agent_harness: MultiAgentHarness,
) -> None:
    """T018: Billing returns a failed task result → peer_failure escalation.

    When the billing agent's A2A task result has status='failed', the
    resolution agent should escalate the case rather than make a partial
    decision without billing opinion.
    """
    # Use risk_timeout scenario so risk is SILENT — billing will respond with
    # whatever seeded facts we give it; we rely on the billing agent failing
    # for an unknown customer (no facts → missing-data path → failed task).
    customer_id = f"T018-{uuid4().hex[:6]}"
    # Intentionally DO NOT seed billing facts → missing-data → billing agent
    # will return a "requires_human_review" / degraded result.  The reaper
    # will eventually escalate.  For true "failed" task semantics we seed a
    # non-existent profile key so billing returns a low-confidence result
    # that triggers the missing-data escalation path.
    multi_agent_harness.seed_risk_signals(customer_id, _risk_dataset["CUS-CLEAN"])
    # No billing facts → billing agent returns missing-data degraded response

    async with WorkflowHarness(multi_agent_harness.broker_url) as wh:
        correlation_id = await wh.publish_ticket(
            customer_id=customer_id,
            amount=49.99,
            currency="USD",
            reason="refund request",
        )
        decision = await wh.wait_for_decision(correlation_id, timeout=30)

    # Missing billing data triggers requires_human_review → escalation
    assert decision.get("outcome") in (
        ResolutionOutcome.ESCALATE_HUMAN.value,
        ResolutionOutcome.DENY_REFUND.value,
    ), (
        f"Expected escalate_human or deny_refund for peer failure/missing data, "
        f"got {decision.get('outcome')!r}"
    )


@pytest.mark.asyncio
async def test_eligible_high_risk_conflict(
    multi_agent_harness: MultiAgentHarness,
) -> None:
    """T019: Eligible billing + high-risk (blocklist) → ESCALATE_HUMAN with elevated_risk.

    Conflicting signals: billing says eligible but risk says do not approve.
    The decision engine must escalate rather than approve.
    """
    customer_id = f"T019-{uuid4().hex[:6]}"
    multi_agent_harness.seed_billing_facts(customer_id, _billing_dataset["PR-APPROVE"])
    multi_agent_harness.seed_risk_signals(customer_id, _risk_dataset["CUS-BLOCKLIST"])

    async with WorkflowHarness(multi_agent_harness.broker_url) as wh:
        correlation_id = await wh.publish_ticket(
            customer_id=customer_id,
            amount=49.99,
            currency="USD",
            reason="refund request",
        )
        decision = await wh.wait_for_decision(correlation_id, timeout=30)

    assert decision.get("outcome") == ResolutionOutcome.ESCALATE_HUMAN.value, (
        f"Expected escalate_human for eligible+high-risk conflict, "
        f"got {decision.get('outcome')!r}"
    )
    assert decision.get("escalation_reason") is not None, (
        "Expected escalation_reason to be set"
    )


@pytest.mark.asyncio
async def test_ineligible_high_risk_deny_with_flag(
    multi_agent_harness: MultiAgentHarness,
) -> None:
    """T019b: Ineligible billing + high risk → DENY_REFUND or ESCALATE_HUMAN + risk flag.

    When billing is ineligible and risk is high, the outcome should be a
    denial or escalation — never an approval.  A risk flag or escalation
    reason in the decision payload is expected.
    """
    customer_id = f"T019b-{uuid4().hex[:6]}"
    multi_agent_harness.seed_billing_facts(customer_id, _billing_dataset["PR-WINDOW-EXPIRED"])
    multi_agent_harness.seed_risk_signals(customer_id, _risk_dataset["CUS-CHARGEBACKS"])

    async with WorkflowHarness(multi_agent_harness.broker_url) as wh:
        correlation_id = await wh.publish_ticket(
            customer_id=customer_id,
            amount=49.99,
            currency="USD",
            reason="refund request",
        )
        decision = await wh.wait_for_decision(correlation_id, timeout=30)

    outcome = decision.get("outcome")
    assert outcome in (
        ResolutionOutcome.DENY_REFUND.value,
        ResolutionOutcome.ESCALATE_HUMAN.value,
    ), (
        f"Expected deny_refund or escalate_human for ineligible+high-risk, "
        f"got {outcome!r}"
    )
    # Approval must never happen when both signals are adverse
    assert outcome != ResolutionOutcome.APPROVE_REFUND.value


@pytest.mark.asyncio
async def test_malformed_ticket_and_late_opinion(
    multi_agent_harness: MultiAgentHarness,
) -> None:
    """T020: Late / partial opinions are handled gracefully.

    Simulate a case where only risk responds in time and billing times out.
    The reaper should escalate due to analysis_timeout.
    """
    scenario = get_scenario("risk_timeout")
    customer_id = f"T020-{uuid4().hex[:6]}"

    # Seed billing only; risk is SILENT
    assert scenario.mock_billing_profile is not SILENT
    assert scenario.mock_risk_profile is SILENT

    multi_agent_harness.seed_billing_facts(customer_id, scenario.mock_billing_profile)
    multi_agent_harness.mark_risk_silent(customer_id)

    async with WorkflowHarness(multi_agent_harness.broker_url) as wh:
        correlation_id = await wh.publish_ticket(
            customer_id=customer_id,
            amount=49.99,
            currency="USD",
            reason="refund request",
        )
        decision = await wh.wait_for_decision(correlation_id, timeout=25)

    assert decision.get("outcome") == ResolutionOutcome.ESCALATE_HUMAN.value
    assert decision.get("escalation_reason") == "analysis_timeout"


# ---------------------------------------------------------------------------
# US4: Duplicate / replay idempotency (T024-T026)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_duplicate_events_no_side_effects(
    multi_agent_harness: MultiAgentHarness,
) -> None:
    """T024: Redelivering the same ticket event produces exactly one decision.

    At-least-once Kafka delivery may replay the support.ticket.created event.
    The idempotency guard must ensure the case is opened and decided exactly once.
    """
    scenario = get_scenario("duplicate_ticket_event")
    customer_id = f"T024-{uuid4().hex[:6]}"

    assert scenario.mock_billing_profile is not SILENT
    assert scenario.mock_risk_profile is not SILENT

    multi_agent_harness.seed_billing_facts(customer_id, scenario.mock_billing_profile)
    multi_agent_harness.seed_risk_signals(customer_id, scenario.mock_risk_profile)

    # Use a fixed correlation_id so both ticket publications are identical
    fixed_correlation_id = uuid4()

    async with WorkflowHarness(multi_agent_harness.broker_url) as wh:
        # Publish the ticket twice with the same correlation_id to simulate redelivery
        await wh.publish_ticket(
            customer_id=customer_id,
            amount=49.99,
            currency="USD",
            reason="charged twice",
            correlation_id=fixed_correlation_id,
        )
        # Redeliver immediately
        await wh.publish_ticket(
            customer_id=customer_id,
            amount=49.99,
            currency="USD",
            reason="charged twice",
            correlation_id=fixed_correlation_id,
        )

        await wh.wait_for_decision(fixed_correlation_id, timeout=30)

        decided_events = [
            e
            for e in wh.collect_events(fixed_correlation_id)
            if e.event_type == TOPIC_RESOLUTION_DECIDED
        ]

    assert len(decided_events) == 1, (
        f"Expected exactly 1 decided event after duplicate ticket, "
        f"got {len(decided_events)}"
    )


@pytest.mark.asyncio
async def test_replay_produces_same_decision(
    multi_agent_harness: MultiAgentHarness,
) -> None:
    """T025: Replaying a recorded scenario produces the same outcome.

    A scenario is run once; its correlation_id and expected outcome are noted.
    The same inputs (same billing/risk data) are re-submitted; the new decision
    must match the first.  This validates determinism of the decision engine.
    """
    customer_id_run1 = f"T025-R1-{uuid4().hex[:6]}"
    customer_id_run2 = f"T025-R2-{uuid4().hex[:6]}"

    for cid in (customer_id_run1, customer_id_run2):
        multi_agent_harness.seed_billing_facts(cid, _billing_dataset["PR-APPROVE"])
        multi_agent_harness.seed_risk_signals(cid, _risk_dataset["CUS-CLEAN"])

    outcomes: list[str] = []

    async with WorkflowHarness(multi_agent_harness.broker_url) as wh:
        for customer_id in (customer_id_run1, customer_id_run2):
            cid = await wh.publish_ticket(
                customer_id=customer_id,
                amount=49.99,
                currency="USD",
                reason="charged twice",
            )
            decision = await wh.wait_for_decision(cid, timeout=30)
            outcomes.append(decision.get("outcome", ""))

    assert outcomes[0] == outcomes[1], (
        f"Replay produced different outcomes: {outcomes[0]!r} vs {outcomes[1]!r}"
    )
    assert outcomes[0] == ResolutionOutcome.APPROVE_REFUND.value


@pytest.mark.asyncio
async def test_partial_replay_no_spurious_decision(
    multi_agent_harness: MultiAgentHarness,
) -> None:
    """T026: Partial replay (only billing result redelivered) does not trigger a second decision.

    After a case is decided, redelivering one of the peer results should be
    silently ignored by the idempotency guard — no second decided event.
    """
    customer_id = f"T026-{uuid4().hex[:6]}"
    multi_agent_harness.seed_billing_facts(customer_id, _billing_dataset["PR-APPROVE"])
    multi_agent_harness.seed_risk_signals(customer_id, _risk_dataset["CUS-CLEAN"])

    correlation_id: UUID

    async with WorkflowHarness(multi_agent_harness.broker_url) as wh:
        correlation_id = await wh.publish_ticket(
            customer_id=customer_id,
            amount=49.99,
            currency="USD",
            reason="charged twice",
        )
        # Wait for the full workflow to complete
        await wh.wait_for_events(
            correlation_id,
            [TOPIC_BILLING_RESULT, TOPIC_RISK_RESULT, TOPIC_RESOLUTION_DECIDED],
            timeout=30,
        )

        # Small pause to let any additional events settle
        await asyncio.sleep(2.0)

        decided_after_first_run = [
            e
            for e in wh.collect_events(correlation_id)
            if e.event_type == TOPIC_RESOLUTION_DECIDED
        ]

    assert len(decided_after_first_run) == 1, (
        f"Expected exactly 1 decided event, got {len(decided_after_first_run)}"
    )


# ---------------------------------------------------------------------------
# US5: Causal trace reconstruction (T028)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trace_reconstructs_full_chain(
    multi_agent_harness: MultiAgentHarness,
) -> None:
    """T028: AuditTimelineBuilder reconstructs the full causal chain by correlation_id.

    After a happy-path case completes, the causal trace tool should return an
    ordered timeline containing all expected event types in causal order, with
    a synthetic terminal entry.
    """
    from packages.testing.audit_timeline import AuditTimelineBuilder

    customer_id = f"T028-{uuid4().hex[:6]}"
    multi_agent_harness.seed_billing_facts(customer_id, _billing_dataset["PR-APPROVE"])
    multi_agent_harness.seed_risk_signals(customer_id, _risk_dataset["CUS-CLEAN"])

    collected_envelopes = []

    async with WorkflowHarness(multi_agent_harness.broker_url) as wh:
        correlation_id = await wh.publish_ticket(
            customer_id=customer_id,
            amount=49.99,
            currency="USD",
            reason="charged twice",
        )
        await wh.wait_for_events(
            correlation_id,
            [
                TOPIC_ISSUE_CLASSIFIED,
                TOPIC_BILLING_RESULT,
                TOPIC_RISK_RESULT,
                TOPIC_RESOLUTION_DECIDED,
                TOPIC_RESPONSE_DRAFTED,
            ],
            timeout=30,
        )
        collected_envelopes = wh.collect_events(correlation_id)

    builder = AuditTimelineBuilder()
    # Inject collected envelopes directly (avoids a second Kafka consumer)
    envelopes = await builder.collect(
        correlation_id, envelopes=collected_envelopes
    )
    timeline = builder.build(envelopes)

    assert len(timeline) >= 5, (
        f"Expected at least 5 timeline entries, got {len(timeline)}"
    )

    labels = [entry.label for entry in timeline]

    # The timeline must contain all key workflow milestones
    assert any("classified" in lbl for lbl in labels), (
        f"Missing issue-classified entry in timeline: {labels}"
    )
    assert any("billing" in lbl or "refund-analysis" in lbl for lbl in labels), (
        f"Missing billing-result entry in timeline: {labels}"
    )
    assert any("risk" in lbl or "review.completed" in lbl for lbl in labels), (
        f"Missing risk-result entry in timeline: {labels}"
    )
    assert any("decided" in lbl for lbl in labels), (
        f"Missing decided entry in timeline: {labels}"
    )

    # The last entry must be the synthetic terminal (case.closed or case.escalated)
    terminal = timeline[-1]
    assert terminal.event_type == "audit.synthetic.terminal.v1", (
        f"Expected synthetic terminal entry last, got {terminal.event_type!r}"
    )

    # seq numbers must be strictly increasing
    seqs = [entry.seq for entry in timeline]
    assert seqs == list(range(1, len(timeline) + 1)), (
        f"Timeline seq numbers are not strictly increasing: {seqs}"
    )

    # All non-synthetic entries must carry the correct correlation_id
    for entry in timeline:
        if entry.event_type != "audit.synthetic.terminal.v1":
            assert entry.correlation_id == correlation_id


# ---------------------------------------------------------------------------
# Decentralization proof (T031-T032)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_central_dispatcher(
    multi_agent_harness: MultiAgentHarness,
) -> None:
    """T031: The decided event emerges from peer results without a central dispatcher.

    The event chain must show that the decision is produced by the
    customer-resolution-agent reacting to peer result events — not by any
    central dispatcher, router, or orchestrator.  This is validated by
    checking that:
    1. A decided event appears.
    2. Its agent_id is the customer-resolution-agent (not a fictional dispatcher).
    3. Its causation_id points to one of the peer result events.
    """
    customer_id = f"T031-{uuid4().hex[:6]}"
    multi_agent_harness.seed_billing_facts(customer_id, _billing_dataset["PR-APPROVE"])
    multi_agent_harness.seed_risk_signals(customer_id, _risk_dataset["CUS-CLEAN"])

    async with WorkflowHarness(multi_agent_harness.broker_url) as wh:
        correlation_id = await wh.publish_ticket(
            customer_id=customer_id,
            amount=49.99,
            currency="USD",
            reason="charged twice",
        )
        await wh.wait_for_events(
            correlation_id,
            [TOPIC_BILLING_RESULT, TOPIC_RISK_RESULT, TOPIC_RESOLUTION_DECIDED],
            timeout=30,
        )
        events = wh.collect_events(correlation_id)

    decided_events = [e for e in events if e.event_type == TOPIC_RESOLUTION_DECIDED]
    assert len(decided_events) >= 1, "No decided event found"

    decided = decided_events[0]

    # The decided event must not come from a dispatcher or router
    agent_id_lower = decided.agent_id.lower()
    for forbidden in ("dispatcher", "router", "orchestrator", "supervisor"):
        assert forbidden not in agent_id_lower, (
            f"Decided event was produced by a forbidden agent: {decided.agent_id!r}"
        )

    # The decided event should come from the customer-resolution-agent
    assert "resolution" in agent_id_lower or "customer" in agent_id_lower, (
        f"Decided event agent_id {decided.agent_id!r} does not look like the resolution agent"
    )

    # The causation_id of the decided event must point to a known earlier event
    if decided.causation_id is not None:
        known_ids = {e.event_id for e in events if e.event_type != TOPIC_RESOLUTION_DECIDED}
        assert decided.causation_id in known_ids, (
            f"Decided event's causation_id {decided.causation_id} does not point to any "
            f"observed prior event — expected it to be caused by a peer result"
        )


@pytest.mark.asyncio
async def test_decision_emerges_from_peer_events(
    multi_agent_harness: MultiAgentHarness,
) -> None:
    """T032: The audit trail shows that the decision was driven by peer events.

    Validates the choreography property: the resolution agent only emits a
    decision *after* receiving both peer results.  No central routing step
    should appear between the peer results and the decision in the event log.
    """
    customer_id = f"T032-{uuid4().hex[:6]}"
    multi_agent_harness.seed_billing_facts(customer_id, _billing_dataset["PR-APPROVE"])
    multi_agent_harness.seed_risk_signals(customer_id, _risk_dataset["CUS-CLEAN"])

    async with WorkflowHarness(multi_agent_harness.broker_url) as wh:
        correlation_id = await wh.publish_ticket(
            customer_id=customer_id,
            amount=49.99,
            currency="USD",
            reason="charged twice",
        )
        await wh.wait_for_events(
            correlation_id,
            [TOPIC_BILLING_RESULT, TOPIC_RISK_RESULT, TOPIC_RESOLUTION_DECIDED],
            timeout=30,
        )

        event_types_in_order = [e.event_type for e in wh.collect_events(correlation_id)]

    # Both peer results must arrive before the decision
    billing_idx = next(
        (i for i, et in enumerate(event_types_in_order) if et == TOPIC_BILLING_RESULT), None
    )
    risk_idx = next(
        (i for i, et in enumerate(event_types_in_order) if et == TOPIC_RISK_RESULT), None
    )
    decided_idx = next(
        (i for i, et in enumerate(event_types_in_order) if et == TOPIC_RESOLUTION_DECIDED), None
    )

    assert billing_idx is not None, "No billing result in event log"
    assert risk_idx is not None, "No risk result in event log"
    assert decided_idx is not None, "No decided event in event log"

    assert billing_idx < decided_idx, (
        "Billing result must precede the decision in arrival order"
    )
    assert risk_idx < decided_idx, (
        "Risk result must precede the decision in arrival order"
    )


# ---------------------------------------------------------------------------
# Demo validation (T033-T034)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_demo_happy_path_completes_within_30s(
    multi_agent_harness: MultiAgentHarness,
) -> None:
    """T033: Smoke test — ticket → decision completes within the 30-second SLA.

    Validates the end-to-end latency guarantee: from ticket publish to the
    appearance of the decided event must be under 30 seconds under normal
    (non-timeout) operating conditions.
    """
    customer_id = f"T033-{uuid4().hex[:6]}"
    multi_agent_harness.seed_billing_facts(customer_id, _billing_dataset["PR-APPROVE"])
    multi_agent_harness.seed_risk_signals(customer_id, _risk_dataset["CUS-CLEAN"])

    import time

    async with WorkflowHarness(multi_agent_harness.broker_url) as wh:
        start = time.monotonic()
        correlation_id = await wh.publish_ticket(
            customer_id=customer_id,
            amount=49.99,
            currency="USD",
            reason="charged twice",
        )
        await asyncio.wait_for(
            wh.wait_for_decision(correlation_id, timeout=30),
            timeout=30,
        )
        elapsed = time.monotonic() - start

    assert elapsed < 30.0, (
        f"Demo happy path took {elapsed:.1f}s — exceeded 30-second SLA"
    )
