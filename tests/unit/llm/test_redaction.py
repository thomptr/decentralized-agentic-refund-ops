"""Test PII redaction."""

from __future__ import annotations

from agent_foundation.llm import Redactor, RuntimeConfig, redact_mapping, redact_text


async def test_redact_email():
    """redact_text replaces email addresses."""
    text = "Contact john@example.com for support."
    result = redact_text(text)
    assert "john@example.com" not in result
    assert "[REDACTED_EMAIL]" in result


async def test_redact_phone():
    """redact_text replaces phone numbers."""
    text = "Call 555-123-4567 for help."
    result = redact_text(text)
    assert "555-123-4567" not in result
    assert "[REDACTED_PHONE]" in result


async def test_redact_pan():
    """redact_text replaces credit card PANs."""
    text = "Card number 4111-1111-1111-1111 on file."
    result = redact_text(text)
    assert "4111-1111-1111-1111" not in result
    assert "[REDACTED_CARD]" in result


async def test_redact_ssn():
    """redact_text replaces SSNs."""
    text = "SSN is 123-45-6789."
    result = redact_text(text)
    assert "123-45-6789" not in result
    assert "[REDACTED_SSN]" in result


async def test_redact_mapping_nested():
    """redact_mapping handles nested dicts."""
    data = {
        "customer": {
            "email": "user@test.com",
            "phone": "555-987-6543",
        },
        "note": "Simple note",
    }
    result = redact_mapping(data)
    assert "[REDACTED_EMAIL]" in result["customer"]["email"]
    assert "[REDACTED_PHONE]" in result["customer"]["phone"]
    assert result["note"] == "Simple note"


async def test_redactor_disabled_passes_through():
    """Redactor.from_config with redact_pii=False passes through unchanged."""
    config = RuntimeConfig(mode="stub", redact_pii=False)
    redactor = Redactor.from_config(config)
    original = "john@example.com"
    assert redactor.scrub(original) == original
