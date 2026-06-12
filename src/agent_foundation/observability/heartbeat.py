"""Periodic system.agent.heartbeat emitter (FR-018, liveness only)."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

TOPIC_HEARTBEAT = "system.agent.heartbeat"


class HeartbeatEmitter:
    """Emits system.agent.heartbeat periodically from the runtime serve() loop."""

    def __init__(
        self,
        *,
        agent_id: str,
        publisher: Any,
        interval_s: float = 10.0,
        tenant_id: str = "poc",
    ) -> None:
        self._agent_id = agent_id
        self._publisher = publisher
        self._interval_s = interval_s
        self._tenant_id = tenant_id

    @property
    def is_enabled(self) -> bool:
        return self._interval_s > 0

    def _build_envelope(self) -> Any:
        """Wrap the liveness payload in an EventEnvelope, as every other event is."""
        from agent_foundation.envelope import EventEnvelope

        now = datetime.now(UTC)
        return EventEnvelope(
            event_id=uuid4(),
            correlation_id=uuid4(),
            causation_id=None,
            agent_id=self._agent_id,
            tenant_id=self._tenant_id,
            timestamp=now,
            event_type="system.agent.heartbeat.v1",
            schema_version="1.0.0",
            payload={
                "agent_id": self._agent_id,
                "emitted_at": now.isoformat(),
                "interval_s": self._interval_s,
            },
        )

    async def emit_once(self) -> None:
        """Emit a single heartbeat; fail-open on any error."""
        if not self.is_enabled:
            return
        try:
            if hasattr(self._publisher, "publish_raw"):
                # trace=False: heartbeats fire every interval_s per agent; tracing
                # them would flood the backend with parent-less kafka.publish
                # traces. Liveness is observable from the Kafka topic itself.
                await self._publisher.publish_raw(
                    self._build_envelope(), TOPIC_HEARTBEAT, trace=False
                )
        except Exception:
            pass

    async def run(self, stop_event: asyncio.Event | None = None) -> None:
        """Loop emitting heartbeats until stop_event is set (or forever)."""
        if not self.is_enabled:
            return
        while True:
            await self.emit_once()
            if stop_event is not None:
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=self._interval_s)
                    break
                except TimeoutError:
                    pass
            else:
                await asyncio.sleep(self._interval_s)
