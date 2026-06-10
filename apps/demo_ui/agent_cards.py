"""Roster aggregation for User Story 1 (T007).

Reads the three peer agents' self-published Agent Cards and probes their HTTP
``/ping`` for liveness, returning exactly one ``RosterEntry`` per expected agent
(a missing agent is present with ``announced=False`` — never omitted, FR-004).
Read + map only — no business decision logic.
"""

from __future__ import annotations

import contextlib
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from agent_foundation.runtime.agent_card import AgentCard
from agent_foundation.runtime.discovery import discover_agents
from apps.demo_ui import config

Liveness = Literal["live", "unknown", "not_announced"]


class CapabilityView(BaseModel):
    """A single declared capability, mapped from ``AgentCard.Capability``."""

    id: str
    name: str
    description: str
    tags: list[str] = []


class RosterEntry(BaseModel):
    """The latest card for one expected agent, plus liveness (data-model.md)."""

    agent_id: str
    name: str | None = None
    description: str | None = None
    version: str | None = None
    endpoint_topic: str | None = None
    capabilities: list[CapabilityView] = []
    announced: bool = False
    last_announced: datetime | None = None
    liveness: Liveness = "not_announced"


def _capabilities(card: AgentCard) -> list[CapabilityView]:
    return [
        CapabilityView(id=c.id, name=c.name, description=c.description, tags=list(c.tags))
        for c in card.capabilities
    ]


def build_roster_entries(
    cards: list[AgentCard],
    *,
    announce_times: dict[str, datetime] | None = None,
    liveness: dict[str, Liveness] | None = None,
    expected_agent_ids: tuple[str, ...] = config.EXPECTED_AGENT_IDS,
) -> list[RosterEntry]:
    """Assemble one ``RosterEntry`` per expected agent from already-read cards.

    Pure mapping (no I/O) so it is unit-testable with fabricated ``AgentCard``
    fixtures. The latest card per agent wins (FR-003); duplicates collapse to the
    last occurrence (matching the compacted-topic / ``discover_agents`` semantics).
    """
    announce_times = announce_times or {}
    liveness = liveness or {}

    # Latest-card-per-agent: last occurrence wins (no superseded duplicates).
    latest: dict[str, AgentCard] = {}
    for card in cards:
        latest[card.agent_id] = card

    entries: list[RosterEntry] = []
    for agent_id in expected_agent_ids:
        card = latest.get(agent_id)
        if card is None:
            entries.append(RosterEntry(agent_id=agent_id, liveness="not_announced"))
            continue
        entries.append(
            RosterEntry(
                agent_id=card.agent_id,
                name=card.name,
                description=card.description,
                version=card.version,
                endpoint_topic=card.endpoint_topic,
                capabilities=_capabilities(card),
                announced=True,
                last_announced=announce_times.get(agent_id),
                liveness=liveness.get(agent_id, "unknown"),
            )
        )
    return entries


async def _read_announce_times(broker_url: str) -> dict[str, datetime]:
    """Thin reader of the compacted agent-card topic capturing each card's latest
    announcement envelope timestamp (research R2). Best-effort: never raises."""
    from aiokafka import AIOKafkaConsumer  # type: ignore[import-untyped]

    from agent_foundation.envelope import EventEnvelope
    from agent_foundation.transport.topics import TOPIC_AGENT_CARD

    consumer = AIOKafkaConsumer(
        TOPIC_AGENT_CARD,
        bootstrap_servers=broker_url,
        group_id=None,
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        value_deserializer=lambda b: b,
    )
    times: dict[str, datetime] = {}
    try:
        await consumer.start()
        while True:
            batches = await consumer.getmany(timeout_ms=1000)
            if not batches:
                break
            for records in batches.values():
                for msg in records:
                    try:
                        env = EventEnvelope.model_validate_json(msg.value)
                        times[env.agent_id] = env.timestamp
                    except Exception:
                        pass
    except Exception:
        pass
    finally:
        with contextlib.suppress(Exception):
            await consumer.stop()
    return times


def _probe_liveness(url: str | None) -> Liveness:
    """Probe one agent's HTTP ``/ping``. 2xx → live, anything else → unknown.

    Never raises (FR-016): a connection error / timeout / non-2xx degrades to
    ``unknown`` so a dead agent never crashes the roster.
    """
    if not url:
        return "unknown"
    try:
        import httpx

        resp = httpx.get(url, timeout=config.PROBE_TIMEOUT_SECONDS)
        return "live" if resp.is_success else "unknown"
    except Exception:
        return "unknown"


def build_roster(broker_url: str = config.BROKER_URL) -> list[RosterEntry]:
    """Discover cards, capture announce times, probe liveness, and assemble the roster.

    Every read is best-effort: a broker outage yields not-announced entries rather
    than an exception (FR-016).
    """
    try:
        cards = config.run_async(discover_agents(broker_url), timeout=config.READ_TIMEOUT_SECONDS)
    except Exception:
        cards = []
    try:
        announce_times = config.run_async(
            _read_announce_times(broker_url), timeout=config.READ_TIMEOUT_SECONDS
        )
    except Exception:
        announce_times = {}

    liveness: dict[str, Liveness] = {}
    announced_ids = {c.agent_id for c in cards}
    for agent_id, url in config.LIVENESS_ENDPOINTS.items():
        if agent_id in announced_ids:
            liveness[agent_id] = _probe_liveness(url)

    return build_roster_entries(cards, announce_times=announce_times, liveness=liveness)
