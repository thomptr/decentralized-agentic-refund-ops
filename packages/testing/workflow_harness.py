"""WorkflowHarness — Kafka+A2A interaction layer for integration tests (T090-T096)."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import UTC, datetime
from types import TracebackType
from typing import Any
from uuid import UUID, uuid4

from agent_foundation.envelope import AgentIdentity, EventEnvelope
from agent_foundation.transport.consumer import Consumer
from agent_foundation.transport.publisher import Publisher
from packages.contracts.events.payloads import SupportTicketCreatedPayload
from packages.contracts.topics import (
    TOPIC_AUDIT,
    TOPIC_BILLING_RESULT,
    TOPIC_ISSUE_CLASSIFIED,
    TOPIC_REFUND_REVIEW_REQUESTED,
    TOPIC_RESOLUTION_DECIDED,
    TOPIC_RESPONSE_DRAFTED,
    TOPIC_RISK_RESULT,
    TOPIC_TASK_RESULT,
    topic_for,
)

_TICKET_CREATED_TOPIC = topic_for("support", "ticket", "created")

_HARNESS_IDENTITY = AgentIdentity(
    agent_id="workflow-harness",
    display_name="Workflow Test Harness",
    tenant_id="poc",
)

_ALL_TOPICS = [
    _TICKET_CREATED_TOPIC,
    TOPIC_ISSUE_CLASSIFIED,
    TOPIC_REFUND_REVIEW_REQUESTED,
    TOPIC_BILLING_RESULT,
    TOPIC_RISK_RESULT,
    TOPIC_TASK_RESULT,
    TOPIC_RESOLUTION_DECIDED,
    TOPIC_RESPONSE_DRAFTED,
    TOPIC_AUDIT,
]


class WorkflowHarness:
    """Reusable Kafka+A2A interaction layer for end-to-end integration tests."""

    def __init__(self, broker_url: str, *, group_id_suffix: str | None = None) -> None:
        self._broker_url = broker_url
        suffix = group_id_suffix or uuid4().hex[:8]
        self._group_id = f"workflow-harness-{suffix}"
        # correlation_id -> list[EventEnvelope] in arrival order
        self._buffer: defaultdict[UUID, list[EventEnvelope]] = defaultdict(list)
        self._stop = asyncio.Event()
        self._consumer_task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------
    # Async context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> WorkflowHarness:
        consumer = Consumer(
            broker_url=self._broker_url,
            group_id=self._group_id,
            agent_identity=_HARNESS_IDENTITY,
            idempotent=False,
        )
        consumer.subscribe(topics=_ALL_TOPICS)
        # Read from the start of each topic. The harness is created right before
        # the ticket is published, so a "latest" offset would race with partition
        # assignment and miss early events (issue.classified, fast direct-response
        # decisions). Replaying from the beginning is safe: each test uses a fresh
        # group and a unique correlation_id, so prior-test events are simply
        # buffered under correlation_ids the test never reads.
        consumer.seek_to_beginning()
        self._consumer_task = asyncio.create_task(
            consumer.run(self._handle_envelope, stop_event=self._stop)
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self._stop.set()
        if self._consumer_task is not None:
            try:
                await asyncio.wait_for(self._consumer_task, timeout=5.0)
            except (asyncio.TimeoutError, TimeoutError, asyncio.CancelledError, Exception):
                self._consumer_task.cancel()

    # ------------------------------------------------------------------
    # Internal handler
    # ------------------------------------------------------------------

    async def _handle_envelope(self, envelope: EventEnvelope) -> None:
        self._buffer[envelope.correlation_id].append(envelope)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def publish_ticket(
        self,
        *,
        customer_id: str,
        amount: float,
        currency: str,
        reason: str,
        ticket_id: str | None = None,
        correlation_id: UUID | None = None,
    ) -> UUID:
        """Publish a support.ticket.created.v1 event and return the correlation_id."""
        cid = correlation_id or uuid4()
        payload = SupportTicketCreatedPayload(
            ticket_id=ticket_id or f"TKT-{customer_id}-{cid.hex[:6]}",
            customer_id=customer_id,
            amount=amount,
            currency=currency,
            reason=reason,
            created_at=datetime.now(UTC),
        )
        async with Publisher(_HARNESS_IDENTITY, self._broker_url) as pub:
            await pub.publish(
                payload,
                event_type=_TICKET_CREATED_TOPIC,
                correlation_id=cid,
                causation_id=None,
            )
        return cid

    async def wait_for_events(
        self,
        correlation_id: UUID,
        expected_types: list[str],
        *,
        timeout: float = 30.0,
    ) -> list[EventEnvelope]:
        """Wait until all expected_types are seen for correlation_id; raise TimeoutError on expiry."""
        deadline = asyncio.get_event_loop().time() + timeout
        while True:
            seen = {e.event_type for e in self._buffer[correlation_id]}
            if all(t in seen for t in expected_types):
                return list(self._buffer[correlation_id])
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                missing = [t for t in expected_types if t not in seen]
                raise TimeoutError(
                    f"Timed out waiting for event types {missing} "
                    f"on correlation_id={correlation_id}"
                )
            await asyncio.sleep(min(0.1, remaining))

    def collect_events(self, correlation_id: UUID) -> list[EventEnvelope]:
        """Return buffered events for correlation_id in arrival order."""
        return list(self._buffer[correlation_id])

    async def wait_for_decision(
        self,
        correlation_id: UUID,
        *,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """Wait for TOPIC_RESOLUTION_DECIDED and return its payload dict."""
        await self.wait_for_events(
            correlation_id, [TOPIC_RESOLUTION_DECIDED], timeout=timeout
        )
        for env in self._buffer[correlation_id]:
            if env.event_type == TOPIC_RESOLUTION_DECIDED:
                return dict(env.payload)
        raise AssertionError("TOPIC_RESOLUTION_DECIDED not found after wait")

    def assert_final_state(
        self,
        correlation_id: UUID,
        expected_final_state: Any,
    ) -> None:
        """Assert terminal state from observed events (not from agent store)."""
        from tests.integration.fixtures.workflow_scenarios.schema import ExpectedFinalState

        assert isinstance(expected_final_state, ExpectedFinalState)

        decided_env = next(
            (e for e in self._buffer[correlation_id] if e.event_type == TOPIC_RESOLUTION_DECIDED),
            None,
        )

        if expected_final_state.expects_decision:
            assert decided_env is not None, (
                f"Expected a {TOPIC_RESOLUTION_DECIDED} event for {correlation_id} "
                "but none was observed"
            )
            payload = decided_env.payload
            if expected_final_state.outcome is not None:
                actual_outcome = payload.get("outcome")
                assert actual_outcome == expected_final_state.outcome.value, (
                    f"Expected outcome={expected_final_state.outcome.value!r}, "
                    f"got {actual_outcome!r}"
                )
            if expected_final_state.escalation_reason is not None:
                actual_reason = payload.get("escalation_reason")
                assert actual_reason == expected_final_state.escalation_reason, (
                    f"Expected escalation_reason={expected_final_state.escalation_reason!r}, "
                    f"got {actual_reason!r}"
                )
        else:
            assert decided_env is None, (
                f"Did not expect a {TOPIC_RESOLUTION_DECIDED} event but one was observed"
            )

    def assert_causal_order(self, correlation_id: UUID) -> None:
        """Check every non-root event's causation_id resolves to an earlier event.

        Events for one case are consumed across several Kafka topics, so raw
        arrival order is not necessarily causal (the consumer may surface a
        downstream topic's partition before the upstream one). Validate the
        causal invariant directly instead: every causation_id must reference an
        observed event whose timestamp is not after the caused event's
        (happened-before), which is order-of-arrival independent.
        """
        events = self._buffer[correlation_id]
        by_id: dict[UUID, EventEnvelope] = {e.event_id: e for e in events}
        for env in events:
            if env.causation_id is None:
                continue
            cause = by_id.get(env.causation_id)
            if cause is None:
                # The causation may reference a task_id, or an envelope on a topic
                # this harness does not subscribe to (endpoint task.requested,
                # task_result, etc.). Only ordering among observed events is
                # checkable, so skip links whose cause we never saw.
                continue
            assert cause.timestamp <= env.timestamp, (
                f"Event {env.event_id} (type={env.event_type}) is timestamped before "
                f"its cause {cause.event_id} (type={cause.event_type})."
            )

    def assert_event_before(
        self,
        correlation_id: UUID,
        earlier_type: str,
        later_type: str,
    ) -> None:
        """Assert that earlier_type appears before later_type in arrival order."""
        events = self._buffer[correlation_id]
        types_in_order = [e.event_type for e in events]
        try:
            earlier_idx = types_in_order.index(earlier_type)
        except ValueError:
            raise AssertionError(
                f"Event type {earlier_type!r} not found in events for {correlation_id}"
            )
        try:
            later_idx = types_in_order.index(later_type)
        except ValueError:
            raise AssertionError(
                f"Event type {later_type!r} not found in events for {correlation_id}"
            )
        assert earlier_idx < later_idx, (
            f"Expected {earlier_type!r} (index {earlier_idx}) before "
            f"{later_type!r} (index {later_idx})"
        )
