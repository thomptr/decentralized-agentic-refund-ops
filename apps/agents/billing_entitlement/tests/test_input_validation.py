"""Input-validation tests (T008/T022 — FR-002/FR-011)."""

from __future__ import annotations

import uuid

import pytest

from agent_foundation.a2a import A2APart
from apps.agents.billing_entitlement.service import validate_input


def _data_part(data: dict) -> list:
    return [A2APart(type="data", data=data)]


def _text_part(text: str) -> list:
    return [A2APart(type="text", text=text)]


def _valid_data(**overrides) -> dict:
    base = {
        "case_id": str(uuid.uuid4()),
        "ticket_id": "TKT-001",
        "customer_id": "CUS-001",
        "requested_refund_amount": 49.99,
        "purchase_reference": "PR-APPROVE",
    }
    base.update(overrides)
    return base


# --- Valid inputs ---

def test_valid_data_part_accepted():
    req = validate_input(_data_part(_valid_data()))
    assert req.ticket_id == "TKT-001"
    assert req.purchase_reference == "PR-APPROVE"


def test_extra_fields_ignored():
    data = _valid_data(unknown_field="ignored", another_extra=42)
    req = validate_input(_data_part(data))
    assert req.ticket_id == "TKT-001"


def test_optional_fields_absent():
    req = validate_input(_data_part(_valid_data()))
    assert req.customer_message_summary is None
    assert req.policy_context is None


def test_optional_fields_present():
    data = _valid_data(customer_message_summary="summary", policy_context="context")
    req = validate_input(_data_part(data))
    assert req.customer_message_summary == "summary"


def test_zero_refund_amount_accepted():
    req = validate_input(_data_part(_valid_data(requested_refund_amount=0)))
    assert req.requested_refund_amount == 0.0


# --- Invalid inputs ---

def test_no_data_part_raises():
    with pytest.raises((ValueError, Exception)):
        validate_input(_text_part("not a data part"))


def test_empty_parts_raises():
    with pytest.raises((ValueError, Exception)):
        # A2AMessage requires non-empty parts, so pass an empty list
        validate_input([])


def test_missing_required_field_case_id_raises():
    data = _valid_data()
    del data["case_id"]
    with pytest.raises((ValueError, Exception)):
        validate_input(_data_part(data))


def test_missing_required_field_ticket_id_raises():
    data = _valid_data()
    del data["ticket_id"]
    with pytest.raises((ValueError, Exception)):
        validate_input(_data_part(data))


def test_missing_required_field_purchase_reference_raises():
    data = _valid_data()
    del data["purchase_reference"]
    with pytest.raises((ValueError, Exception)):
        validate_input(_data_part(data))


def test_negative_refund_amount_raises():
    with pytest.raises((ValueError, Exception)):
        validate_input(_data_part(_valid_data(requested_refund_amount=-1.0)))


def test_invalid_case_id_raises():
    with pytest.raises((ValueError, Exception)):
        validate_input(_data_part(_valid_data(case_id="not-a-uuid")))
