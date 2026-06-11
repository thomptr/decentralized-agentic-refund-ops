from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture(autouse=True)
def _no_kafka_persist():
    """Prevent AssistiveResultStore from trying to connect to Kafka in tests."""
    with patch(
        "agent_foundation.llm.store.AssistiveResultStore._persist",
        new_callable=AsyncMock,
    ):
        yield
