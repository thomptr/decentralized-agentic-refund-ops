"""Assistive-result idempotency store — in-process LRU + compacted Kafka topic."""

from __future__ import annotations

import json
from collections import OrderedDict
from typing import Any

from agent_foundation.llm.result import AssistiveResult
from agent_foundation.logging import get_logger

_log = get_logger(__name__)


class _LRUResultCache:
    def __init__(self, maxsize: int = 10_000) -> None:
        self._cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._maxsize = maxsize

    def get(self, key: str) -> dict[str, Any] | None:
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def put(self, key: str, data: dict[str, Any]) -> None:
        self._cache[key] = data
        self._cache.move_to_end(key)
        if len(self._cache) > self._maxsize:
            self._cache.popitem(last=False)


class AssistiveResultStore:
    def __init__(self, bootstrap_servers: str = "localhost:9092") -> None:
        self._bootstrap_servers = bootstrap_servers
        self._lru = _LRUResultCache()

    async def get(self, idempotency_key: str) -> AssistiveResult | None:
        data = self._lru.get(idempotency_key)
        if data is not None:
            return AssistiveResult.model_validate(data)
        return None

    async def put(self, idempotency_key: str, result: AssistiveResult) -> None:
        data = result.model_dump(mode="json")
        self._lru.put(idempotency_key, data)
        await self._persist(idempotency_key, data)

    async def _persist(self, key: str, data: dict[str, Any]) -> None:
        try:
            from aiokafka import AIOKafkaProducer  # type: ignore[import-untyped]

            producer = AIOKafkaProducer(bootstrap_servers=self._bootstrap_servers)
            try:
                await producer.start()
                await producer.send_and_wait(
                    "local.llm.assistive-result.compacted.v1",
                    value=json.dumps(data, default=str).encode(),
                    key=key.encode(),
                )
            finally:
                await producer.stop()
        except Exception as exc:
            _log.warning("assistive_store.persist_failed", error=str(exc), key=key)
