"""ResolutionService — orchestrates the three concurrent loops (T011, T095).

Three loops share a single CaseStateStore:
  1. AgentRuntime.serve()   — listens on endpoint_topic for A2A TaskRequests
  2. intake Consumer        — support.ticket.created events
  3. result Consumer        — TOPIC_TASK_RESULT (generic A2A results)

No billing/risk business logic lives here (FR-005). The service depends on
CaseStateStore via the interface, defaulting to InMemoryCaseStateStore.
"""

from __future__ import annotations

import asyncio

import structlog

from agent_foundation.envelope import AgentIdentity
from agent_foundation.transport.consumer import Consumer
from agent_foundation.transport.publisher import Publisher
from apps.agents.customer_resolution.a2a_handlers import build_agent_card
from apps.agents.customer_resolution.config import AGENT_DISPLAY_NAME, AGENT_ID, AGENT_TENANT_ID
from apps.agents.customer_resolution.event_handlers import (
    billing_result_handler,
    intake_handler,
    result_handler,
    risk_result_handler,
)
from apps.agents.customer_resolution.reaper import run_reaper
from apps.agents.customer_resolution.state_store import InMemoryCaseStateStore
from packages.contracts.topics import (
    TOPIC_BILLING_RESULT,
    TOPIC_RISK_RESULT,
    TOPIC_TASK_RESULT,
    topic_for,
)

logger = structlog.get_logger(__name__)

_TICKET_CREATED_TOPIC = topic_for("support", "ticket", "created")


class ResolutionService:
    """Orchestrates all concurrent loops for the Customer Resolution Agent.

    Constructor-injected store (defaulting to InMemoryCaseStateStore) so a
    Postgres/DynamoDB backend can be swapped in without changing the handlers
    (acceptance criterion: store interface replaceable, Phase 14 T095).
    """

    def __init__(
        self,
        broker_url: str,
        store: InMemoryCaseStateStore | None = None,
    ) -> None:
        self._broker_url = broker_url
        self._store = store or InMemoryCaseStateStore()

        self._identity = AgentIdentity(
            agent_id=AGENT_ID,
            display_name=AGENT_DISPLAY_NAME,
            tenant_id=AGENT_TENANT_ID,
        )
        self._card = build_agent_card()

    async def serve(self, stop_event: asyncio.Event | None = None) -> None:
        """Run all three loops concurrently (FR-016, research R7)."""
        from agent_foundation.runtime import AgentRuntime

        runtime = AgentRuntime(self._identity, self._card, broker_url=self._broker_url)

        async with Publisher(self._identity, self._broker_url) as publisher:
            intake_consumer = Consumer(
                broker_url=self._broker_url,
                group_id=f"{AGENT_ID}.intake",
                agent_identity=self._identity,
                idempotent=True,
            )
            intake_consumer.subscribe(topics=[_TICKET_CREATED_TOPIC])

            result_consumer = Consumer(
                broker_url=self._broker_url,
                group_id=f"{AGENT_ID}.results",
                agent_identity=self._identity,
                idempotent=True,
            )
            result_consumer.subscribe(topics=[TOPIC_TASK_RESULT])

            billing_consumer = Consumer(
                broker_url=self._broker_url,
                group_id=f"{AGENT_ID}.billing-results",
                agent_identity=self._identity,
                idempotent=True,
            )
            billing_consumer.subscribe(topics=[TOPIC_BILLING_RESULT])

            risk_consumer = Consumer(
                broker_url=self._broker_url,
                group_id=f"{AGENT_ID}.risk-results",
                agent_identity=self._identity,
                idempotent=True,
            )
            risk_consumer.subscribe(topics=[TOPIC_RISK_RESULT])

            broker_url = self._broker_url
            store = self._store

            async def _intake(envelope):
                await intake_handler(
                    envelope,
                    publisher=publisher,
                    store=store,
                    broker_url=broker_url,
                )

            async def _result(envelope):
                await result_handler(envelope, publisher=publisher, store=store)

            async def _billing(envelope):
                await billing_result_handler(envelope, publisher=publisher, store=store)

            async def _risk(envelope):
                await risk_result_handler(envelope, publisher=publisher, store=store)

            logger.info("resolution_service_starting", agent_id=AGENT_ID)

            await asyncio.gather(
                runtime.serve(stop_event),
                intake_consumer.run(_intake, stop_event=stop_event, publisher=publisher),
                result_consumer.run(_result, stop_event=stop_event, publisher=publisher),
                billing_consumer.run(_billing, stop_event=stop_event, publisher=publisher),
                risk_consumer.run(_risk, stop_event=stop_event, publisher=publisher),
                run_reaper(store, publisher, stop_event=stop_event),
            )
