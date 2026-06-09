#!/usr/bin/env python3
"""Dev-only script: subscribes to all initial canonical topics and prints each validated EventEnvelope as formatted JSON. Requires Kafka at localhost:9092 (docker compose -f infra/local/docker-compose.yml up -d). Run with: python apps/api/dev_consume_events.py"""
from __future__ import annotations

import asyncio
import json
import os
import signal

from agent_foundation.envelope import AgentIdentity, EventEnvelope
from agent_foundation.logging import configure_logging
from agent_foundation.transport.consumer import Consumer
from agent_foundation.transport.topics import TOPIC_AUDIT, TOPIC_MESSAGE, TOPIC_SAMPLE

SUBSCRIBED_TOPICS: list[str] = [TOPIC_MESSAGE, TOPIC_AUDIT, TOPIC_SAMPLE]


async def handler(envelope: EventEnvelope) -> None:
    print(json.dumps(envelope.model_dump(mode="json"), indent=2, default=str))
    print("---")


async def main() -> None:
    configure_logging()
    print(
        f"[dev_consume_events] Subscribing to: {', '.join(SUBSCRIBED_TOPICS)}\n"
        "Press Ctrl-C to stop.\n"
    )

    identity = AgentIdentity(
        agent_id="dev.consumer",
        display_name="Dev Consumer",
        tenant_id="local",
    )

    broker_url = os.getenv("KAFKA_BROKER_URL", "localhost:9092")
    consumer = Consumer(
        broker_url=broker_url,
        group_id="dev.consumer",
        agent_identity=identity,
        idempotent=False,
    )
    consumer.subscribe(SUBSCRIBED_TOPICS)

    loop = asyncio.get_event_loop()
    stop_event = asyncio.Event()

    def _sigint(*_: object) -> None:
        stop_event.set()

    loop.add_signal_handler(signal.SIGINT, _sigint)

    try:
        await consumer.run(handler, stop_event=stop_event)
    except KeyboardInterrupt:
        pass
    finally:
        await consumer.stop()


if __name__ == "__main__":
    asyncio.run(main())
