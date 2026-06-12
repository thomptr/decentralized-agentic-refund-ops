"""Unit-test conftest for observability: forces toggle OFF so no LangFuse/OTel network is needed."""

import pytest


@pytest.fixture(autouse=True)
def _observability_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_OBSERVABILITY_ENABLED", "false")
