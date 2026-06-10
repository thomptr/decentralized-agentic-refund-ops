"""Shared test fixtures for the Billing and Entitlement Agent test suite (T002)."""

from __future__ import annotations

import uuid

import pytest


def make_eligibility_request_data(
    *,
    case_id: str | None = None,
    ticket_id: str = "TKT-001",
    customer_id: str = "CUS-001",
    requested_refund_amount: float = 49.99,
    purchase_reference: str = "PR-APPROVE",
) -> dict:
    return {
        "case_id": case_id or str(uuid.uuid4()),
        "ticket_id": ticket_id,
        "customer_id": customer_id,
        "requested_refund_amount": requested_refund_amount,
        "purchase_reference": purchase_reference,
    }


@pytest.fixture
def valid_request_data() -> dict:
    return make_eligibility_request_data()


@pytest.fixture
def approve_request_data() -> dict:
    return make_eligibility_request_data(purchase_reference="PR-APPROVE")


@pytest.fixture
def deny_window_request_data() -> dict:
    return make_eligibility_request_data(purchase_reference="PR-WINDOW-EXPIRED")


@pytest.fixture
def unknown_request_data() -> dict:
    return make_eligibility_request_data(purchase_reference="PR-UNKNOWN-XYZ-DOESNOTEXIST")


@pytest.mark.skip(reason="marker definition only")
def requires_broker() -> None:
    """Marker: test requires a live Kafka broker (via testcontainers)."""


pytest.ini_options = {}
