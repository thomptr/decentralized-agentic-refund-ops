"""PII redaction for audit records, logs, and UI display."""

from __future__ import annotations

import re
from typing import Any

_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
_PHONE_RE = re.compile(r"\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}\b")
_PAN_RE = re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b")
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_LONG_DIGITS_RE = re.compile(r"\b\d{8,}\b")

_PATTERNS = [
    (_EMAIL_RE, "[REDACTED_EMAIL]"),
    (_PAN_RE, "[REDACTED_CARD]"),
    (_SSN_RE, "[REDACTED_SSN]"),
    (_PHONE_RE, "[REDACTED_PHONE]"),
    (_LONG_DIGITS_RE, "[REDACTED_NUMBER]"),
]


def redact_text(text: str) -> str:
    for pattern, placeholder in _PATTERNS:
        text = pattern.sub(placeholder, text)
    return text


def redact_mapping(data: dict[str, Any]) -> dict[str, Any]:
    return {k: _redact_value(v) for k, v in data.items()}


def _redact_value(v: Any) -> Any:
    if isinstance(v, str):
        return redact_text(v)
    if isinstance(v, dict):
        return redact_mapping(v)
    if isinstance(v, list):
        return [_redact_value(item) for item in v]
    return v


class Redactor:
    def __init__(self, *, enabled: bool = True) -> None:
        self._enabled = enabled

    @classmethod
    def from_config(cls, config: Any) -> Redactor:
        return cls(enabled=getattr(config, "redact_pii", True))

    def scrub(self, value: Any) -> Any:
        if not self._enabled:
            return value
        if isinstance(value, str):
            return redact_text(value)
        if isinstance(value, dict):
            return redact_mapping(value)
        if isinstance(value, list):
            return [self.scrub(item) for item in value]
        return value
