"""Unit tests for WorkflowHarness (T097) — no broker required."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from agent_foundation.envelope import EventEnvelope
from packages.contracts.events.payloads import ResolutionOutcome
from packages.contracts.topics import (
    TOPIC_ISSUE_CLASSIFIED,
    TOPIC_RESOLUTION_DECIDED,
    TOPIC_RESPONSE_DRAFTED,
    topic_for,
)
from packages.testing.workflow_harness import WorkflowHarness

_TICKET_CREATED_TOPIC = topic_for("support", "ticket", "created")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_envelope(
    event_type: str,
    correlation_id,
    *,
    causation_id=None,
    payload: dict | None = None,
    timestamp: datetime | None = None,
) -> EventEnvelope:
    """Build a minimal valid EventEnvelope for testing."""
    return EventEnvelope(
        event_id=uuid4(),
        correlation_id=correlation_id,
        causation_id=causation_id,
        agent_id="test.agent",
        tenant_id="poc",
        timestamp=timestamp or datetime.now(UTC),
        event_type=event_type,
        schema_version="1.0.0",
        payload=payload or {},
    )


def _make_harness() -> WorkflowHarness:
    """Create a WorkflowHarness without starting the background consumer."""
    return WorkflowHarness("localhost:9092", group_id_suffix="test")


def _inject(harness: WorkflowHarness, envelope: EventEnvelope) -> None:
    """Synchronously inject an envelope into the harness buffer."""
    asyncio.run(harness._handle_envelope(envelope))


# ---------------------------------------------------------------------------
# collect_events: isolation by correlation_id
# ---------------------------------------------------------------------------


class TestCollectEvents:
    def test_buckets_by_correlation_id(self) -> None:
        harness = _make_harness()
        cid_a = uuid4()
        cid_b = uuid4()

        env_a = _make_envelope(_TICKET_CREATED_TOPIC, cid_a)
        env_b = _make_envelope(_TICKET_CREATED_TOPIC, cid_b)

        _inject(harness, (env_a))
        _inject(harness, (env_b))

        assert harness.collect_events(cid_a) == [env_a]
        assert harness.collect_events(cid_b) == [env_b]

    def test_no_cross_case_bleed(self) -> None:
        harness = _make_harness()
        cid_a = uuid4()
        cid_b = uuid4()
        cid_c = uuid4()

        for i in range(3):
            e = _make_envelope(TOPIC_ISSUE_CLASSIFIED, cid_a, causation_id=uuid4())
            _inject(harness, (e))

        env_b = _make_envelope(TOPIC_ISSUE_CLASSIFIED, cid_b, causation_id=uuid4())
        _inject(harness, (env_b))

        assert len(harness.collect_events(cid_a)) == 3
        assert harness.collect_events(cid_b) == [env_b]
        assert harness.collect_events(cid_c) == []

    def test_empty_for_unknown_correlation_id(self) -> None:
        harness = _make_harness()
        assert harness.collect_events(uuid4()) == []


# ---------------------------------------------------------------------------
# wait_for_events: resolves when all types arrive
# ---------------------------------------------------------------------------


class TestWaitForEvents:
    @pytest.mark.asyncio
    async def test_resolves_when_all_types_present(self) -> None:
        harness = _make_harness()
        cid = uuid4()

        env1 = _make_envelope(_TICKET_CREATED_TOPIC, cid)
        env2 = _make_envelope(TOPIC_ISSUE_CLASSIFIED, cid, causation_id=env1.event_id)
        await harness._handle_envelope(env1)
        await harness._handle_envelope(env2)

        result = await harness.wait_for_events(
            cid,
            [_TICKET_CREATED_TOPIC, TOPIC_ISSUE_CLASSIFIED],
            timeout=1.0,
        )
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_times_out_when_type_never_arrives(self) -> None:
        harness = _make_harness()
        cid = uuid4()

        env1 = _make_envelope(_TICKET_CREATED_TOPIC, cid)
        await harness._handle_envelope(env1)

        with pytest.raises(TimeoutError):
            await harness.wait_for_events(
                cid,
                [_TICKET_CREATED_TOPIC, TOPIC_RESOLUTION_DECIDED],
                timeout=0.2,
            )

    @pytest.mark.asyncio
    async def test_resolves_immediately_if_already_present(self) -> None:
        harness = _make_harness()
        cid = uuid4()

        env = _make_envelope(_TICKET_CREATED_TOPIC, cid)
        await harness._handle_envelope(env)

        result = await harness.wait_for_events(cid, [_TICKET_CREATED_TOPIC], timeout=1.0)
        assert result == [env]

    @pytest.mark.asyncio
    async def test_event_delivered_after_start(self) -> None:
        harness = _make_harness()
        cid = uuid4()

        async def _deliver_late() -> None:
            await asyncio.sleep(0.05)
            env = _make_envelope(TOPIC_RESOLUTION_DECIDED, cid, causation_id=uuid4(),
                                 payload={"outcome": "approve_refund"})
            await harness._handle_envelope(env)

        asyncio.create_task(_deliver_late())
        result = await harness.wait_for_events(cid, [TOPIC_RESOLUTION_DECIDED], timeout=1.0)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# assert_causal_order: detects broken causation chain
# ---------------------------------------------------------------------------


class TestAssertCausalOrder:
    def test_valid_causal_chain_passes(self) -> None:
        harness = _make_harness()
        cid = uuid4()

        root = _make_envelope(_TICKET_CREATED_TOPIC, cid)
        child = _make_envelope(TOPIC_ISSUE_CLASSIFIED, cid, causation_id=root.event_id)
        grandchild = _make_envelope(TOPIC_RESOLUTION_DECIDED, cid, causation_id=child.event_id,
                                    payload={"outcome": "approve_refund"})

        _inject(harness, (root))
        _inject(harness, (child))
        _inject(harness, (grandchild))

        harness.assert_causal_order(cid)

    def test_effect_before_cause_raises(self) -> None:
        harness = _make_harness()
        cid = uuid4()

        from datetime import timedelta

        base = datetime(2026, 1, 1, tzinfo=UTC)
        parent = _make_envelope(_TICKET_CREATED_TOPIC, cid, timestamp=base + timedelta(seconds=1))
        # Child references the observed parent but is timestamped BEFORE it.
        child = _make_envelope(
            TOPIC_ISSUE_CLASSIFIED, cid, causation_id=parent.event_id, timestamp=base
        )

        _inject(harness, (parent))
        _inject(harness, (child))

        with pytest.raises(AssertionError, match="timestamped before"):
            harness.assert_causal_order(cid)

    def test_unobserved_causation_is_skipped(self) -> None:
        # A causation_id that references an envelope on a topic the harness does
        # not subscribe to (e.g. a task request) is not a failure — only ordering
        # among observed events is checked.
        harness = _make_harness()
        cid = uuid4()

        root = _make_envelope(_TICKET_CREATED_TOPIC, cid)
        branched = _make_envelope(TOPIC_ISSUE_CLASSIFIED, cid, causation_id=uuid4())

        _inject(harness, (root))
        _inject(harness, (branched))

        harness.assert_causal_order(cid)  # does not raise

    def test_root_event_with_no_causation_passes(self) -> None:
        harness = _make_harness()
        cid = uuid4()

        root = _make_envelope(_TICKET_CREATED_TOPIC, cid)
        _inject(harness, (root))

        harness.assert_causal_order(cid)


# ---------------------------------------------------------------------------
# assert_final_state: reads the decided event payload
# ---------------------------------------------------------------------------


class TestAssertFinalState:
    def _inject_decided(
        self,
        harness: WorkflowHarness,
        cid,
        outcome: str,
        escalation_reason: str | None = None,
    ) -> None:
        payload: dict = {"outcome": outcome}
        if escalation_reason is not None:
            payload["escalation_reason"] = escalation_reason
        env = _make_envelope(TOPIC_RESOLUTION_DECIDED, cid, causation_id=uuid4(), payload=payload)
        _inject(harness, (env))

    def test_approve_refund_passes(self) -> None:
        from apps.agents.customer_resolution.models import CaseStatus
        from tests.integration.fixtures.workflow_scenarios.schema import ExpectedFinalState

        harness = _make_harness()
        cid = uuid4()
        self._inject_decided(harness, cid, "approve_refund")

        harness.assert_final_state(
            cid,
            ExpectedFinalState(
                case_status=CaseStatus.CLOSED,
                outcome=ResolutionOutcome.APPROVE_REFUND,
                expects_decision=True,
            ),
        )

    def test_wrong_outcome_raises(self) -> None:
        from apps.agents.customer_resolution.models import CaseStatus
        from tests.integration.fixtures.workflow_scenarios.schema import ExpectedFinalState

        harness = _make_harness()
        cid = uuid4()
        self._inject_decided(harness, cid, "deny_refund")

        with pytest.raises(AssertionError, match="outcome"):
            harness.assert_final_state(
                cid,
                ExpectedFinalState(
                    case_status=CaseStatus.CLOSED,
                    outcome=ResolutionOutcome.APPROVE_REFUND,
                    expects_decision=True,
                ),
            )

    def test_escalate_human_with_reason_passes(self) -> None:
        from apps.agents.customer_resolution.models import CaseStatus
        from tests.integration.fixtures.workflow_scenarios.schema import ExpectedFinalState

        harness = _make_harness()
        cid = uuid4()
        self._inject_decided(harness, cid, "escalate_human", "high risk score")

        harness.assert_final_state(
            cid,
            ExpectedFinalState(
                case_status=CaseStatus.ESCALATED,
                outcome=ResolutionOutcome.ESCALATE_HUMAN,
                escalation_reason="high risk score",
                expects_decision=True,
            ),
        )

    def test_no_decided_event_when_not_expected(self) -> None:
        from apps.agents.customer_resolution.models import CaseStatus
        from tests.integration.fixtures.workflow_scenarios.schema import ExpectedFinalState

        harness = _make_harness()
        cid = uuid4()
        # No decided event injected

        harness.assert_final_state(
            cid,
            ExpectedFinalState(
                case_status=CaseStatus.CLOSED,
                expects_decision=False,
            ),
        )

    def test_missing_decided_when_expected_raises(self) -> None:
        from apps.agents.customer_resolution.models import CaseStatus
        from tests.integration.fixtures.workflow_scenarios.schema import ExpectedFinalState

        harness = _make_harness()
        cid = uuid4()

        with pytest.raises(AssertionError, match="Expected a"):
            harness.assert_final_state(
                cid,
                ExpectedFinalState(
                    case_status=CaseStatus.CLOSED,
                    outcome=ResolutionOutcome.APPROVE_REFUND,
                    expects_decision=True,
                ),
            )


# ---------------------------------------------------------------------------
# assert_event_before: offset ordering
# ---------------------------------------------------------------------------


class TestAssertEventBefore:
    def test_correct_order_passes(self) -> None:
        harness = _make_harness()
        cid = uuid4()

        root = _make_envelope(_TICKET_CREATED_TOPIC, cid)
        child = _make_envelope(TOPIC_ISSUE_CLASSIFIED, cid, causation_id=root.event_id)

        _inject(harness, (root))
        _inject(harness, (child))

        harness.assert_event_before(cid, _TICKET_CREATED_TOPIC, TOPIC_ISSUE_CLASSIFIED)

    def test_reversed_order_raises(self) -> None:
        harness = _make_harness()
        cid = uuid4()

        root = _make_envelope(_TICKET_CREATED_TOPIC, cid)
        child = _make_envelope(TOPIC_ISSUE_CLASSIFIED, cid, causation_id=root.event_id)

        _inject(harness, (root))
        _inject(harness, (child))

        with pytest.raises(AssertionError):
            harness.assert_event_before(cid, TOPIC_ISSUE_CLASSIFIED, _TICKET_CREATED_TOPIC)

    def test_missing_earlier_type_raises(self) -> None:
        harness = _make_harness()
        cid = uuid4()

        root = _make_envelope(_TICKET_CREATED_TOPIC, cid)
        _inject(harness, (root))

        with pytest.raises(AssertionError, match="not found"):
            harness.assert_event_before(cid, TOPIC_RESOLUTION_DECIDED, _TICKET_CREATED_TOPIC)
