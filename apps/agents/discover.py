"""Discovery helper — list all published Agent Cards with no central registry."""
from __future__ import annotations

import asyncio

from apps.agents.common import BROKER_URL


async def _run(broker_url: str) -> None:
    from agent_foundation.runtime.discovery import discover_agents

    cards = await discover_agents(broker_url)
    if not cards:
        print("No agent cards found on the discovery topic.")
        return

    for card in sorted(cards, key=lambda c: c.agent_id):
        print(f"\n[{card.agent_id}] {card.name} v{card.version}")
        print(f"  Description: {card.description}")
        print(f"  Endpoint:    {card.endpoint_topic}")
        print(f"  Security:    {card.security}")
        print("  Capabilities:")
        for cap in card.capabilities:
            tags = f" [{', '.join(cap.tags)}]" if cap.tags else ""
            print(f"    - {cap.id}: {cap.description}{tags}")


def main(broker_url: str = BROKER_URL) -> None:
    asyncio.run(_run(broker_url))


if __name__ == "__main__":
    main()
