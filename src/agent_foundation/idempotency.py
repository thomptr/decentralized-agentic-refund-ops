"""In-process LRU + Kafka-backed idempotency tracker."""

from __future__ import annotations

import json
from collections import OrderedDict
from uuid import UUID

from agent_foundation.logging import get_logger

_log = get_logger(__name__)


class _LRUCache:
    def __init__(self, maxsize: int = 10_000) -> None:
        self._cache: OrderedDict[UUID, bool] = OrderedDict()
        self._maxsize = maxsize

    def __contains__(self, key: UUID) -> bool:
        if key in self._cache:
            self._cache.move_to_end(key)
            return True
        return False

    def add(self, key: UUID) -> None:
        self._cache[key] = True
        self._cache.move_to_end(key)
        if len(self._cache) > self._maxsize:
            self._cache.popitem(last=False)


class IdempotencyTracker:
    """Tracks processed event IDs in-memory (LRU) and persists to a compacted Kafka topic."""

    def __init__(
        self,
        consumer_name: str,
        bootstrap_servers: str = "localhost:9092",
    ) -> None:
        self._consumer_name = consumer_name
        self._bootstrap_servers = bootstrap_servers
        self._lru = _LRUCache()
        self._initialized = False

    async def initialize(self) -> None:
        """Rebuild LRU from compacted Kafka topic on startup."""
        from agent_foundation.transport.topics import (
            create_topics,
            processed_id_new_topic,
            processed_id_topic,
        )

        topic = processed_id_topic(self._consumer_name)
        try:
            await create_topics(
                self._bootstrap_servers,
                extra_topics=[processed_id_new_topic(self._consumer_name)],
            )
            await self._rebuild_from_topic(topic)
        except Exception as exc:
            _log.warning("idempotency.init_failed", error=str(exc), topic=topic)
        self._initialized = True

    async def _rebuild_from_topic(self, topic: str) -> None:
        from aiokafka import AIOKafkaConsumer  # type: ignore[import-untyped]

        consumer = AIOKafkaConsumer(
            topic,
            bootstrap_servers=self._bootstrap_servers,
            group_id=None,  # independent consumer
            auto_offset_reset="earliest",
            enable_auto_commit=False,
            consumer_timeout_ms=2000,
        )
        await consumer.start()
        try:
            async for msg in consumer:
                try:
                    data = json.loads(msg.value)
                    event_id = UUID(data["event_id"])
                    self._lru.add(event_id)
                except Exception:
                    pass
        except Exception:
            pass
        finally:
            await consumer.stop()

    async def is_duplicate(self, event_id: UUID) -> bool:
        if not self._initialized:
            await self.initialize()
        return event_id in self._lru

    async def mark_processed(self, event_id: UUID) -> None:
        self._lru.add(event_id)
        await self._persist(event_id)

    async def _persist(self, event_id: UUID) -> None:
        from aiokafka import AIOKafkaProducer  # type: ignore[import-untyped,unused-ignore]

        from agent_foundation.transport.topics import processed_id_topic

        topic = processed_id_topic(self._consumer_name)
        producer = AIOKafkaProducer(bootstrap_servers=self._bootstrap_servers)
        try:
            await producer.start()
            await producer.send_and_wait(
                topic,
                value=json.dumps({"event_id": str(event_id)}).encode(),
                key=str(event_id).encode(),
            )
        except Exception as exc:
            _log.warning("idempotency.persist_failed", error=str(exc), event_id=str(event_id))
        finally:
            await producer.stop()
