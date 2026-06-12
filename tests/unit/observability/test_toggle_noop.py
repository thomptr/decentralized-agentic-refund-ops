"""T016: When toggle is OFF, all observability calls are no-ops and bodies still run."""

from __future__ import annotations

import pytest

from agent_foundation.observability import (
    configure_observability,
    generation,
    get_client,
    get_config,
    span,
    traced,
)


def test_config_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_OBSERVABILITY_ENABLED", "false")
    configure_observability(agent_id="test-agent")
    assert get_config().enabled is False
    assert get_client() is None


def test_span_noop_body_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_OBSERVABILITY_ENABLED", "false")
    configure_observability(agent_id="test-agent")
    ran = []
    with span("test.span"):
        ran.append(True)
    assert ran == [True]


def test_generation_noop_body_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_OBSERVABILITY_ENABLED", "false")
    configure_observability(agent_id="test-agent")
    ran = []
    with generation("test.gen", model="stub"):
        ran.append(True)
    assert ran == [True]


def test_span_reraises_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_OBSERVABILITY_ENABLED", "false")
    configure_observability(agent_id="test-agent")
    with pytest.raises(ValueError, match="boom"), span("test.span"):
        raise ValueError("boom")


def test_traced_decorator_noop_returns_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_OBSERVABILITY_ENABLED", "false")
    configure_observability(agent_id="test-agent")

    @traced("engine.op")
    def pure_fn(x: int) -> int:
        return x * 2

    assert pure_fn(5) == 10


def test_traced_decorator_reraises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_OBSERVABILITY_ENABLED", "false")
    configure_observability(agent_id="test-agent")

    @traced("engine.op")
    def failing_fn() -> None:
        raise RuntimeError("fail")

    with pytest.raises(RuntimeError, match="fail"):
        failing_fn()


def test_no_keys_means_no_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_OBSERVABILITY_ENABLED", "true")
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    configure_observability(agent_id="test-agent")
    assert get_client() is None
