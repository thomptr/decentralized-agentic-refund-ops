"""Focused A2A contract tests (Phase 9, T041/T042/T056).

Cases 1, 2, and 10 (card validates, card returns expected metadata, card has auth metadata).
No broker required.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent_foundation.runtime.agent_card import AgentCard, Capability
from packages.contracts.topics import endpoint_topic

# ── helpers ──────────────────────────────────────────────────────────────────


def make_agent_card(
    agent_id: str = "test.agent",
    cap_id: str = "do.something",
    **kwargs: object,
) -> AgentCard:
    return AgentCard(
        agent_id=agent_id,
        name="Test Agent",
        description="An agent for contract tests",
        version="1.0.0",
        endpoint_topic=endpoint_topic(agent_id),
        capabilities=[Capability(id=cap_id, name="Do Something", description="A capability")],
        **kwargs,  # type: ignore[arg-type]
    )


# ── Case 1: Agent Card validates successfully (T041) ─────────────────────────


def test_case1_agent_card_validates_successfully() -> None:
    """Valid AgentCard constructs and JSON-round-trips cleanly."""
    card = make_agent_card()
    restored = AgentCard.model_validate_json(card.model_dump_json())
    assert restored == card


def test_case1_malformed_card_empty_capabilities_raises() -> None:
    with pytest.raises(ValidationError):
        AgentCard(
            agent_id="test.agent",
            name="X",
            description="Y",
            version="1.0.0",
            endpoint_topic=endpoint_topic("test.agent"),
            capabilities=[],
        )


def test_case1_malformed_card_duplicate_cap_ids_raises() -> None:
    cap = Capability(id="do.something", name="X", description="Y")
    with pytest.raises(ValidationError, match="unique ids"):
        AgentCard(
            agent_id="test.agent",
            name="X",
            description="Y",
            version="1.0.0",
            endpoint_topic=endpoint_topic("test.agent"),
            capabilities=[cap, cap],
        )


def test_case1_malformed_card_bad_semver_raises() -> None:
    with pytest.raises(ValidationError, match="semver"):
        AgentCard(
            agent_id="test.agent",
            name="X",
            description="Y",
            version="1.0",
            endpoint_topic=endpoint_topic("test.agent"),
            capabilities=[Capability(id="do.something", name="X", description="Y")],
        )


# ── Case 2: Agent Card endpoint returns expected metadata (T042) ──────────────


def test_case2_card_has_agent_identity() -> None:
    card = make_agent_card(agent_id="my.agent")
    assert card.agent_id == "my.agent"
    assert card.name
    assert card.description
    assert card.version


def test_case2_card_endpoint_topic_matches_factory() -> None:
    agent_id = "my.agent"
    card = make_agent_card(agent_id=agent_id)
    assert card.endpoint_topic == endpoint_topic(agent_id)


def test_case2_card_capabilities_present() -> None:
    card = make_agent_card(cap_id="do.something")
    assert len(card.capabilities) >= 1
    assert card.capabilities[0].id == "do.something"


# ── Case 10 (Phase 10): Card acceptance — identity, skills, capabilities, auth ─


def test_phase10_card_json_includes_all_acceptance_criteria() -> None:
    """Card JSON contains identity, capabilities, and auth metadata."""
    card = make_agent_card()
    data = card.model_dump()

    # Identity
    assert "agent_id" in data
    assert "name" in data
    assert "version" in data

    # Skills/capabilities
    assert "capabilities" in data
    assert len(data["capabilities"]) >= 1
    assert "id" in data["capabilities"][0]
    assert "name" in data["capabilities"][0]
    assert "description" in data["capabilities"][0]

    # Auth metadata (T052 stub)
    assert "security" in data
    assert data["security"] == "none"


def test_phase10_card_auth_stub_default_is_none() -> None:
    card = make_agent_card()
    assert card.security == "none"


def test_phase10_card_invalid_security_value_raises() -> None:
    with pytest.raises((ValidationError, Exception)):
        AgentCard(
            agent_id="test.agent",
            name="X",
            description="Y",
            version="1.0.0",
            endpoint_topic=endpoint_topic("test.agent"),
            capabilities=[Capability(id="do.something", name="X", description="Y")],
            security="oauth2",  # not a valid value
        )
