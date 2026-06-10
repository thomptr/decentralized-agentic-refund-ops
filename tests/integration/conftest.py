"""Shared fixtures for integration tests (006 T006).

Provides:
- kafka_bootstrap_servers (session-scoped): single testcontainers Kafka broker.
- multi_agent_harness (function-scoped): starts the real billing, risk, and resolution
  agents in-process over the shared broker, with sub-second deadline/tick overrides and
  a seeding seam for per-test billing/risk data.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# Session-scoped Kafka container
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def kafka_bootstrap_servers() -> str:
    from testcontainers.kafka import KafkaContainer  # type: ignore[import-untyped]

    with KafkaContainer(image="confluentinc/cp-kafka:7.6.0") as kafka:
        yield kafka.get_bootstrap_server()


# ---------------------------------------------------------------------------
# Shared agent identity fixture (kept for backward compat with older tests)
# ---------------------------------------------------------------------------


@pytest.fixture
def agent_identity():  # type: ignore[no-untyped-def]
    from agent_foundation.envelope import AgentIdentity

    return AgentIdentity(
        agent_id="test.idempotent", display_name="Idempotency Test", tenant_id="poc"
    )


# ---------------------------------------------------------------------------
# In-process agent runners (T006)
# ---------------------------------------------------------------------------


def _request_customer_id(req: Any) -> str | None:
    """Extract the customer_id from a TaskRequest's data part (best-effort)."""
    for part in req.input.parts:
        data = getattr(part, "data", None)
        if isinstance(data, dict) and "customer_id" in data:
            return str(data["customer_id"])
    return None


async def _run_billing_agent(
    broker_url: str,
    stop_event: asyncio.Event,
    *,
    silent_customers: set[str] | None = None,
) -> None:
    """Run the real billing agent in-process against the given broker.

    Customers in *silent_customers* model a peer that never responds (timeout
    path): the handler blocks until shutdown so neither the domain result nor an
    A2A TaskResult is ever published, leaving the case's billing slot pending so
    the resolution reaper escalates with ``analysis_timeout``.
    """
    from agent_foundation.a2a import A2AMessage
    from agent_foundation.payloads.task import TaskRequest
    from agent_foundation.runtime import AgentRuntime
    from agent_foundation.transport.publisher import Publisher
    from apps.agents.billing_entitlement.identity import build_agent_card, build_identity
    from apps.agents.billing_entitlement.service import analyze, build_a2a_output, build_result_payload
    from packages.contracts.topics import TOPIC_BILLING_RESULT

    silent = silent_customers if silent_customers is not None else set()
    identity = build_identity()
    card = build_agent_card()
    runtime = AgentRuntime(identity, card, broker_url=broker_url)

    async with Publisher(identity, broker_url) as domain_pub:

        @runtime.handler("analyze_refund_eligibility")
        async def handle_eligibility(req: TaskRequest) -> A2AMessage:
            if _request_customer_id(req) in silent:
                await stop_event.wait()
                return A2AMessage(role="agent", parts=[])
            request, rec, facts = analyze(req.input.parts)
            payload = build_result_payload(request, rec, facts)
            await domain_pub.publish(
                payload,
                event_type=TOPIC_BILLING_RESULT,
                correlation_id=request.case_id,
                causation_id=req.task_id,
            )
            return build_a2a_output(rec)

        await runtime.serve(stop_event)


async def _run_risk_agent(
    broker_url: str,
    stop_event: asyncio.Event,
    *,
    silent_customers: set[str] | None = None,
) -> None:
    """Run the real risk agent in-process against the given broker.

    See _run_billing_agent for the *silent_customers* timeout-modelling contract.
    """
    from agent_foundation.a2a import A2AMessage
    from agent_foundation.payloads.task import TaskRequest
    from agent_foundation.runtime import AgentRuntime
    from agent_foundation.transport.publisher import Publisher
    from apps.agents.risk_fraud.identity import build_agent_card, build_identity
    from apps.agents.risk_fraud.service import assess, build_a2a_output, to_result_payload
    from packages.contracts.topics import TOPIC_RISK_RESULT

    silent = silent_customers if silent_customers is not None else set()
    identity = build_identity()
    card = build_agent_card()
    runtime = AgentRuntime(identity, card, broker_url=broker_url)

    async with Publisher(identity, broker_url) as domain_pub:

        @runtime.handler("assess_fraud_risk")
        async def handle_risk(req: TaskRequest) -> A2AMessage:
            if _request_customer_id(req) in silent:
                await stop_event.wait()
                return A2AMessage(role="agent", parts=[])
            assessment, request = assess(req.input.parts)
            payload = to_result_payload(assessment, request)
            await domain_pub.publish(
                payload,
                event_type=TOPIC_RISK_RESULT,
                correlation_id=request.case_id,
                causation_id=req.task_id,
            )
            return build_a2a_output(assessment)

        await runtime.serve(stop_event)


async def _run_resolution_agent(
    broker_url: str,
    stop_event: asyncio.Event,
    *,
    case_deadline_seconds: int = 5,
    reaper_tick_seconds: float = 0.5,
) -> None:
    """Run the real resolution agent in-process with overridden deadline/tick."""
    import apps.agents.customer_resolution.config as _cfg

    # Patch deadline/tick for fast integration tests
    _cfg.CASE_DEADLINE_SECONDS = case_deadline_seconds
    _cfg.REAPER_TICK_SECONDS = reaper_tick_seconds

    from apps.agents.customer_resolution.agent import ResolutionService

    service = ResolutionService(broker_url)
    await service.serve(stop_event)


# ---------------------------------------------------------------------------
# Multi-agent harness fixture (T006)
# ---------------------------------------------------------------------------


class MultiAgentHarness:
    """Provides agent start/stop, data seeding, and the broker URL for tests."""

    def __init__(
        self,
        broker_url: str,
        stop_event: asyncio.Event,
        *,
        silent_billing: set[str] | None = None,
        silent_risk: set[str] | None = None,
    ) -> None:
        self.broker_url = broker_url
        self._stop_event = stop_event
        # Extra billing and risk data seeded per-test
        self._extra_billing: dict[str, Any] = {}
        self._extra_risk: dict[str, Any] = {}
        # Customers whose billing / risk peer never responds (timeout path).
        # Shared (by reference) with the in-process agent runners.
        self._silent_billing = silent_billing if silent_billing is not None else set()
        self._silent_risk = silent_risk if silent_risk is not None else set()

    def seed_billing_facts(self, customer_id: str, facts: Any) -> None:
        """Register billing facts under customer_id for this test.

        The integration test ticket's customer_id must match; the billing agent
        will then return a deterministic verdict based on these facts.
        """
        import apps.agents.billing_entitlement.mock_data as billing_mock

        billing_mock._CUSTOMER_INDEX[customer_id] = f"TEST-{customer_id}"
        billing_mock._DATASET[f"TEST-{customer_id}"] = facts

    def seed_risk_signals(self, customer_id: str, signals: Any) -> None:
        """Register risk signals under customer_id for this test."""
        import apps.agents.risk_fraud.mock_data as risk_mock

        risk_mock._DATASET[customer_id] = signals

    def mark_billing_silent(self, customer_id: str) -> None:
        """Model a billing peer that never responds for *customer_id* (timeout path)."""
        self._silent_billing.add(customer_id)

    def mark_risk_silent(self, customer_id: str) -> None:
        """Model a risk peer that never responds for *customer_id* (timeout path)."""
        self._silent_risk.add(customer_id)

    def stop(self) -> None:
        self._stop_event.set()


@pytest.fixture
async def multi_agent_harness(kafka_bootstrap_servers: str) -> MultiAgentHarness:
    """Start all three real agents in-process with sub-second deadline overrides (T006)."""
    from agent_foundation.transport.topics import create_topics

    broker = kafka_bootstrap_servers
    await create_topics(broker)

    stop_event = asyncio.Event()

    # Use unique consumer group suffix to avoid cross-test state leakage
    suffix = uuid4().hex[:8]

    # Patch consumer group IDs in the resolution agent to be unique per test
    import apps.agents.customer_resolution.config as _cfg
    original_agent_id = _cfg.AGENT_ID
    # Note: we can't change AGENT_ID as it affects the A2A endpoint topic.
    # Instead, we rely on the existing group IDs being unique per Kafka consumer group.

    # Shared (by reference) silent-customer sets — the harness mutates them via
    # mark_*_silent and the in-process agent runners read them at request time.
    silent_billing: set[str] = set()
    silent_risk: set[str] = set()

    billing_task = asyncio.create_task(
        _run_billing_agent(broker, stop_event, silent_customers=silent_billing)
    )
    risk_task = asyncio.create_task(
        _run_risk_agent(broker, stop_event, silent_customers=silent_risk)
    )
    resolution_task = asyncio.create_task(
        _run_resolution_agent(broker, stop_event, case_deadline_seconds=5, reaper_tick_seconds=0.5)
    )

    # Allow agents to start up and subscribe
    await asyncio.sleep(4.0)

    harness = MultiAgentHarness(
        broker, stop_event, silent_billing=silent_billing, silent_risk=silent_risk
    )
    yield harness

    # Teardown: stop all agents
    stop_event.set()
    await asyncio.wait(
        {billing_task, risk_task, resolution_task},
        timeout=10.0,
    )
