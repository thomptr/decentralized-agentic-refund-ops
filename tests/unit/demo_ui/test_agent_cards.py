"""Unit tests for roster aggregation (T006) — no broker required."""

from __future__ import annotations

from datetime import UTC, datetime

from agent_foundation.runtime.agent_card import AgentCard, Capability
from apps.demo_ui.agent_cards import build_roster_entries

EXPECTED = (
    "customer-resolution-agent",
    "billing-entitlement-agent",
    "risk-fraud-agent",
)


def _card(agent_id: str, *, version: str = "1.0.0", cap_id: str = "do_thing") -> AgentCard:
    return AgentCard(
        agent_id=agent_id,
        name=f"{agent_id} name",
        description=f"{agent_id} description",
        version=version,
        endpoint_topic=f"local.{agent_id}.tasks.requested.v1",
        capabilities=[
            Capability(id=cap_id, name="Do Thing", description="Does a thing", tags=["x"])
        ],
    )


def test_one_entry_per_expected_agent_in_order() -> None:
    cards = [_card(a) for a in EXPECTED]
    entries = build_roster_entries(cards, expected_agent_ids=EXPECTED)
    assert [e.agent_id for e in entries] == list(EXPECTED)


def test_missing_agent_present_as_not_announced() -> None:
    # Only billing announced; the other two must still appear, not be omitted (FR-004).
    entries = build_roster_entries(
        [_card("billing-entitlement-agent")], expected_agent_ids=EXPECTED
    )
    by_id = {e.agent_id: e for e in entries}
    assert by_id["customer-resolution-agent"].announced is False
    assert by_id["customer-resolution-agent"].liveness == "not_announced"
    assert by_id["risk-fraud-agent"].announced is False
    assert by_id["billing-entitlement-agent"].announced is True


def test_latest_card_per_agent_no_superseded_dupes() -> None:
    # Two cards for the same agent: the later one wins (FR-003).
    cards = [
        _card("risk-fraud-agent", version="1.0.0"),
        _card("risk-fraud-agent", version="2.5.0"),
    ]
    entries = build_roster_entries(cards, expected_agent_ids=("risk-fraud-agent",))
    assert len(entries) == 1
    assert entries[0].version == "2.5.0"


def test_capability_mapping() -> None:
    entries = build_roster_entries(
        [_card("billing-entitlement-agent", cap_id="analyze_refund_eligibility")],
        expected_agent_ids=("billing-entitlement-agent",),
    )
    caps = entries[0].capabilities
    assert len(caps) == 1
    assert caps[0].id == "analyze_refund_eligibility"
    assert caps[0].name == "Do Thing"
    assert caps[0].tags == ["x"]


def test_liveness_and_announce_time_mapping() -> None:
    now = datetime.now(UTC)
    entries = build_roster_entries(
        [_card("billing-entitlement-agent")],
        announce_times={"billing-entitlement-agent": now},
        liveness={"billing-entitlement-agent": "live"},
        expected_agent_ids=("billing-entitlement-agent",),
    )
    assert entries[0].liveness == "live"
    assert entries[0].last_announced == now


def test_announced_without_probe_defaults_to_unknown() -> None:
    # An announced agent with no liveness result is "unknown", never "live".
    entries = build_roster_entries(
        [_card("customer-resolution-agent")],
        expected_agent_ids=("customer-resolution-agent",),
    )
    assert entries[0].announced is True
    assert entries[0].liveness == "unknown"
