"""T030: Heartbeat emission.

system.agent.heartbeat periodic, carries agent_id; interval=0 disables.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from agent_foundation.observability.heartbeat import HeartbeatEmitter


def test_heartbeat_emitter_interval_zero_disables() -> None:
    publisher = MagicMock()
    emitter = HeartbeatEmitter(agent_id="cr", publisher=publisher, interval_s=0)
    assert not emitter.is_enabled


def test_heartbeat_emitter_positive_interval_enabled() -> None:
    publisher = MagicMock()
    emitter = HeartbeatEmitter(agent_id="cr", publisher=publisher, interval_s=10)
    assert emitter.is_enabled


async def test_heartbeat_emits_with_agent_id() -> None:
    published: list[dict] = []

    async def fake_publish_raw(envelope, topic: str, *, trace: bool = True) -> None:
        published.append({"topic": topic, "envelope": envelope, "trace": trace})

    publisher = MagicMock()
    publisher.publish_raw = fake_publish_raw

    emitter = HeartbeatEmitter(agent_id="billing-entitlement", publisher=publisher, interval_s=10)
    await emitter.emit_once()

    assert len(published) == 1
    assert published[0]["topic"] == "system.agent.heartbeat"
    # Heartbeats must not be traced — they would flood the trace backend.
    assert published[0]["trace"] is False
    envelope = published[0]["envelope"]
    assert envelope.agent_id == "billing-entitlement"
    assert envelope.payload["agent_id"] == "billing-entitlement"
    assert "emitted_at" in envelope.payload


async def test_heartbeat_fail_open_on_publish_error() -> None:
    async def fail_publish(envelope, topic: str, *, trace: bool = True) -> None:
        raise RuntimeError("publish failed")

    publisher = MagicMock()
    publisher.publish_raw = fail_publish

    emitter = HeartbeatEmitter(agent_id="cr", publisher=publisher, interval_s=10)
    # Should not raise
    await emitter.emit_once()
