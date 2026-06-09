"""Shared fixtures for A2A runtime integration tests."""

from __future__ import annotations

import pytest


@pytest.fixture(scope="module")
def kafka_bootstrap_servers() -> str:
    from testcontainers.kafka import KafkaContainer  # type: ignore[import-untyped]

    with KafkaContainer(image="confluentinc/cp-kafka:7.6.0") as kafka:
        yield kafka.get_bootstrap_server()


@pytest.fixture
def agent_identity():  # type: ignore[no-untyped-def]
    from agent_foundation.envelope import AgentIdentity

    return AgentIdentity(
        agent_id="test.idempotent", display_name="Idempotency Test", tenant_id="poc"
    )
