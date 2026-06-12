"""T029: PII redaction before export — prompts/completions scrubbed; span attrs never carry PII."""
from __future__ import annotations

import pytest

from agent_foundation.observability.attributes import build_span_attrs
from agent_foundation.observability.redaction import redact_for_export
from agent_foundation.observability.config import ObservabilityConfig


def _cfg(redact: bool = True, log_raw_prompts: bool = False, log_raw_outputs: bool = False) -> ObservabilityConfig:
    return ObservabilityConfig(
        enabled=False,
        redact_pii=redact,
        log_raw_prompts=log_raw_prompts,
        log_raw_outputs=log_raw_outputs,
    )


def test_prompt_redacted_by_default() -> None:
    cfg = _cfg(redact=True, log_raw_prompts=False)
    raw = "Customer email is alice@example.com, card 4111-1111-1111-1111"
    result = redact_for_export(raw, field="prompt", config=cfg)
    assert result is not None
    assert "alice@example.com" not in (result or "")
    assert "4111" not in (result or "")


def test_prompt_raw_when_log_raw_prompts() -> None:
    cfg = _cfg(redact=True, log_raw_prompts=True)
    raw = "Customer email is alice@example.com"
    result = redact_for_export(raw, field="prompt", config=cfg)
    assert result == raw


def test_output_redacted_by_default() -> None:
    cfg = _cfg(redact=True, log_raw_outputs=False)
    raw = "SSN: 123-45-6789"
    result = redact_for_export(raw, field="completion", config=cfg)
    assert result is not None
    assert "123-45-6789" not in (result or "")


def test_output_raw_when_log_raw_outputs() -> None:
    cfg = _cfg(redact=True, log_raw_outputs=True)
    raw = "SSN: 123-45-6789"
    result = redact_for_export(raw, field="completion", config=cfg)
    assert result == raw


def test_field_dropped_when_redact_off_and_no_raw_toggle() -> None:
    cfg = _cfg(redact=False, log_raw_prompts=False)
    result = redact_for_export("anything", field="prompt", config=cfg)
    assert result is None


def test_span_attrs_never_carry_free_text() -> None:
    attrs = build_span_attrs(
        correlation_id="c1",
        agent_id="cr",
        # these should NOT appear in attrs
    )
    for v in attrs.values():
        assert "@" not in v
        assert len(v) < 200
