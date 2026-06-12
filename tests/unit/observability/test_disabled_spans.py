"""Span names listed in AGENT_OBSERVABILITY_DISABLED_SPANS are never exported."""
from __future__ import annotations

import pytest

import agent_foundation.observability.client as client_mod
from agent_foundation.observability.config import ObservabilityConfig
from agent_foundation.observability.tracing import span


class _FakeSpan:
    def update(self, **_: object) -> None: ...
    def end(self) -> None: ...


class _RecordingClient:
    def __init__(self) -> None:
        self.started: list[str] = []

    def start_span(self, *, name: str, **_: object) -> _FakeSpan:
        self.started.append(name)
        return _FakeSpan()


def _install(monkeypatch: pytest.MonkeyPatch, disabled: set[str]) -> _RecordingClient:
    cfg = ObservabilityConfig(enabled=True, disabled_spans=frozenset(disabled))
    fake = _RecordingClient()
    monkeypatch.setattr(client_mod, "_config", cfg)
    monkeypatch.setattr(client_mod, "_client", fake)
    return fake


def test_disabled_spans_parsed_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_OBSERVABILITY_DISABLED_SPANS", "kafka.publish, a2a.task.send ,")
    cfg = ObservabilityConfig.from_env(agent_id="test-agent")
    assert cfg.disabled_spans == frozenset({"kafka.publish", "a2a.task.send"})


def test_disabled_span_not_exported_body_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _install(monkeypatch, {"kafka.publish"})
    ran = []
    with span("kafka.publish", attrs={"topic": "x"}):
        ran.append(True)
    assert ran == [True]  # body still runs (fail-open)
    assert fake.started == []  # nothing sent to the backend


def test_enabled_span_still_exported(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _install(monkeypatch, {"kafka.publish"})
    with span("event.consume"):
        pass
    assert fake.started == ["event.consume"]
