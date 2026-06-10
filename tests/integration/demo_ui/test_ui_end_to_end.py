"""End-to-end integration test for the demo UI read-side (T023).

Drives one real case through the three in-process agents, then asserts the UI's
``build_timeline`` reproduces ``trace_case`` ordering and attribution exactly
(UI == CLI, SC-002) and that replayed audit records collapse to one row per
event (SC-005). Requires a live Kafka broker via testcontainers.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from agent_foundation.audit.store import query_by_correlation
from apps.agents.billing_entitlement.mock_data import _DATASET as _billing_dataset
from apps.agents.customer_resolution.trace import trace_case
from apps.agents.risk_fraud.mock_data import _DATASET as _risk_dataset
from apps.demo_ui.event_stream import build_stream_from_records
from apps.demo_ui.timeline import build_timeline_from_records
from packages.testing.workflow_harness import WorkflowHarness
from tests.integration.conftest import MultiAgentHarness

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_ui_timeline_matches_trace_case_and_dedups(
    multi_agent_harness: MultiAgentHarness,
) -> None:
    broker = multi_agent_harness.broker_url
    customer_id = f"UI023-{uuid4().hex[:6]}"
    multi_agent_harness.seed_billing_facts(customer_id, _billing_dataset["PR-APPROVE"])
    multi_agent_harness.seed_risk_signals(customer_id, _risk_dataset["CUS-CLEAN"])

    async with WorkflowHarness(broker) as wh:
        correlation_id = await wh.publish_ticket(
            customer_id=customer_id,
            amount=49.99,
            currency="USD",
            reason="charged twice for the same subscription",
        )
        await wh.wait_for_decision(correlation_id, timeout=30)

    # The audit records the UI reads for this case.
    records = await query_by_correlation(broker, correlation_id)
    assert records, "expected audit records for the completed case"

    # UI == CLI: the UI timeline order/attribution equals trace_case over the same envelopes.
    # build_timeline_from_records is the pure aggregator; its sync build_timeline wrapper
    # (asyncio.run) is exercised separately — it cannot run inside this async test's loop.
    # The UI dedups records by event_id before tracing (FR-015), so compute the expected
    # ordering from the same deduped envelope set.
    deduped: dict = {}
    for r in records:
        deduped[r.original_envelope.event_id] = r.original_envelope
    expected_steps = trace_case(correlation_id, list(deduped.values()))
    view = build_timeline_from_records(correlation_id, records)

    assert view.found is True
    assert [e.event_type for e in view.entries] == [s.event_type for s in expected_steps]
    assert [e.actor for e in view.entries] == [s.actor for s in expected_steps]

    # Replay/duplicate audit records collapse to one row per event (SC-005).
    unique_event_ids = {r.original_envelope.event_id for r in records}
    replayed = build_timeline_from_records(correlation_id, records + records)
    assert len(replayed.entries) == len(unique_event_ids)

    stream = build_stream_from_records(records + records, filter_correlation_id=correlation_id)
    assert len(stream.events) == len(unique_event_ids)
