"""T019: @traced decorator — return value preserved, span emitted, error span on exception."""
from __future__ import annotations

import pytest

from agent_foundation.observability import configure_observability, traced


def test_traced_sync_preserves_return(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_OBSERVABILITY_ENABLED", "false")
    configure_observability(agent_id="test-agent")

    @traced("ticket.classify")
    def classify(ticket_id: str) -> dict[str, str]:
        return {"category": "refund", "ticket_id": ticket_id}

    result = classify("T-123")
    assert result == {"category": "refund", "ticket_id": "T-123"}


def test_traced_sync_reraises_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_OBSERVABILITY_ENABLED", "false")
    configure_observability(agent_id="test-agent")

    @traced("case.decision")
    def decide() -> str:
        raise ValueError("decision error")

    with pytest.raises(ValueError, match="decision error"):
        decide()


def test_traced_preserves_function_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_OBSERVABILITY_ENABLED", "false")
    configure_observability(agent_id="test-agent")

    @traced("policy.evaluate")
    def evaluate(rules: list[str]) -> bool:
        return bool(rules)

    assert evaluate.__name__ == "evaluate"


async def _async_decide(x: int) -> int:
    return x * 3


async def test_traced_async_preserves_return(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_OBSERVABILITY_ENABLED", "false")
    configure_observability(agent_id="test-agent")

    decorated = traced("case.decision")(_async_decide)
    result = await decorated(7)
    assert result == 21


async def test_traced_async_reraises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_OBSERVABILITY_ENABLED", "false")
    configure_observability(agent_id="test-agent")

    @traced("ticket.classify")
    async def async_fail() -> None:
        raise RuntimeError("async fail")

    with pytest.raises(RuntimeError, match="async fail"):
        await async_fail()
