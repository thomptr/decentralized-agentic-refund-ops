"""Centralized capture-policy seam for PII redaction before LangFuse export (FR-017/SC-007)."""
from __future__ import annotations

from typing import Any


def redact_for_export(value: str | None, *, field: str, config: Any) -> str | None:
    """Apply the capture-policy to a free-text value before LangFuse export.

    Policy matrix:
    - field="prompt":     log_raw_prompts=True → raw; redact_pii=True → scrubbed; else → None
    - field="completion": log_raw_outputs=True → raw; redact_pii=True → scrubbed; else → None
    - field="status":     always scrubbed (redact_pii=True) or dropped (redact_pii=False)

    On any Redactor error falls open to the scrubbed-or-dropped safe value.
    """
    if value is None:
        return None

    log_raw = False
    if field == "prompt":
        log_raw = getattr(config, "log_raw_prompts", False)
    elif field == "completion":
        log_raw = getattr(config, "log_raw_outputs", False)

    if log_raw:
        return value

    redact_pii = getattr(config, "redact_pii", True)
    if not redact_pii:
        return None

    try:
        from agent_foundation.llm.redaction import Redactor

        redactor = Redactor(enabled=True)
        result = redactor.scrub(value)
        return str(result) if result is not None else None
    except Exception:
        return None
