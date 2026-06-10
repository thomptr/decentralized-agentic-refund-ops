"""Tests for RiskAssessmentRequest input validation (T008, T024)."""

from __future__ import annotations

import uuid

import pytest

from apps.agents.risk_fraud.models import RiskAssessmentRequest

# ---------------------------------------------------------------------------
# T008: Valid input parses correctly
# ---------------------------------------------------------------------------


def test_valid_input_parses():
    data = {
        "case_id": str(uuid.uuid4()),
        "ticket_id": "TKT-001",
        "customer_id": "CUS-CLEAN",
    }
    req = RiskAssessmentRequest.model_validate(data)
    assert req.ticket_id == "TKT-001"
    assert req.customer_id == "CUS-CLEAN"


def test_valid_input_with_optional_fields():
    data = {
        "case_id": str(uuid.uuid4()),
        "ticket_id": "TKT-002",
        "customer_id": "CUS-001",
        "requested_refund_amount": "99.50",
        "account_age_days": 30,
        "customer_message_summary": "I want a refund",
        "metadata": {"source": "test"},
    }
    req = RiskAssessmentRequest.model_validate(data)
    assert str(req.requested_refund_amount) == "99.50"
    assert req.account_age_days == 30


def test_unknown_fields_are_ignored():
    data = {
        "case_id": str(uuid.uuid4()),
        "ticket_id": "TKT-003",
        "customer_id": "CUS-001",
        "unknown_field_xyz": "should be ignored",
    }
    req = RiskAssessmentRequest.model_validate(data)
    assert not hasattr(req, "unknown_field_xyz")


def test_raw_text_fields_not_required():
    """customer_message_summary is optional — no raw sensitive customer text required."""
    data = {
        "case_id": str(uuid.uuid4()),
        "ticket_id": "TKT-004",
        "customer_id": "CUS-001",
    }
    req = RiskAssessmentRequest.model_validate(data)
    assert req.customer_message_summary is None


# ---------------------------------------------------------------------------
# T008: Missing required fields raise ValueError
# ---------------------------------------------------------------------------


def test_missing_case_id_raises():
    data = {"ticket_id": "TKT-001", "customer_id": "CUS-001"}
    with pytest.raises((ValueError, TypeError, Exception)):  # noqa: B017
        RiskAssessmentRequest.model_validate(data)


def test_missing_ticket_id_raises():
    data = {"case_id": str(uuid.uuid4()), "customer_id": "CUS-001"}
    with pytest.raises((ValueError, TypeError, Exception)):  # noqa: B017
        RiskAssessmentRequest.model_validate(data)


def test_missing_customer_id_raises():
    data = {"case_id": str(uuid.uuid4()), "ticket_id": "TKT-001"}
    with pytest.raises((ValueError, TypeError, Exception)):  # noqa: B017
        RiskAssessmentRequest.model_validate(data)


def test_blank_ticket_id_raises():
    data = {"case_id": str(uuid.uuid4()), "ticket_id": "", "customer_id": "CUS-001"}
    with pytest.raises((ValueError, TypeError, Exception)):  # noqa: B017
        RiskAssessmentRequest.model_validate(data)


def test_blank_customer_id_raises():
    data = {"case_id": str(uuid.uuid4()), "ticket_id": "TKT-001", "customer_id": ""}
    with pytest.raises((ValueError, TypeError, Exception)):  # noqa: B017
        RiskAssessmentRequest.model_validate(data)


def test_negative_refund_amount_raises():
    data = {
        "case_id": str(uuid.uuid4()),
        "ticket_id": "TKT-001",
        "customer_id": "CUS-001",
        "requested_refund_amount": "-10.00",
    }
    with pytest.raises((ValueError, TypeError, Exception)):  # noqa: B017
        RiskAssessmentRequest.model_validate(data)


def test_negative_account_age_days_raises():
    data = {
        "case_id": str(uuid.uuid4()),
        "ticket_id": "TKT-001",
        "customer_id": "CUS-001",
        "account_age_days": -1,
    }
    with pytest.raises((ValueError, TypeError, Exception)):  # noqa: B017
        RiskAssessmentRequest.model_validate(data)


# ---------------------------------------------------------------------------
# T024: Malformed input surfaces structured failure (via service)
# ---------------------------------------------------------------------------


def test_malformed_input_service_raises_value_error():
    """Malformed/missing input causes service.validate_input to raise ValueError (FR-011)."""
    from apps.agents.risk_fraud.service import validate_input

    # Empty parts list
    with pytest.raises(ValueError, match="No valid data part"):
        validate_input([])


def test_malformed_input_missing_required_fields():
    """Missing case_id in data part causes validation error propagated as ValueError."""
    from agent_foundation.a2a import A2APart
    from apps.agents.risk_fraud.service import validate_input

    bad_parts = [A2APart(type="data", data={"ticket_id": "TKT-001", "customer_id": "CUS-001"})]
    with pytest.raises((ValueError, TypeError, Exception)):  # noqa: B017  # Pydantic ValidationError
        validate_input(bad_parts)
