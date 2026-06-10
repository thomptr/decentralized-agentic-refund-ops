"""Shared test fixtures for the Risk and Fraud Agent test suite (T002, T042, T113)."""

from __future__ import annotations

import uuid

import pytest

from apps.agents.risk_fraud.mock_data import default_store

# ---------------------------------------------------------------------------
# Request builders (T002)
# ---------------------------------------------------------------------------


def make_risk_request_data(
    *,
    case_id: str | None = None,
    ticket_id: str = "TKT-001",
    customer_id: str = "CUS-CLEAN",
    requested_refund_amount: str = "49.99",
    account_age_days: int | None = None,
) -> dict:
    data: dict = {
        "case_id": case_id or str(uuid.uuid4()),
        "ticket_id": ticket_id,
        "customer_id": customer_id,
        "requested_refund_amount": requested_refund_amount,
    }
    if account_age_days is not None:
        data["account_age_days"] = account_age_days
    return data


def make_a2a_parts(data: dict) -> list:
    """Wrap a dict as an A2APart list suitable for service.assess / validate_input."""
    from agent_foundation.a2a import A2APart

    return [A2APart(type="data", data=data)]


@pytest.fixture
def valid_request_data() -> dict:
    return make_risk_request_data()


@pytest.fixture
def clean_request_data() -> dict:
    return make_risk_request_data(customer_id="CUS-CLEAN")


@pytest.fixture
def blocklist_request_data() -> dict:
    return make_risk_request_data(customer_id="CUS-BLOCKLIST")


@pytest.fixture
def unknown_request_data() -> dict:
    return make_risk_request_data(customer_id="CUS-UNKNOWN-DOES-NOT-EXIST")


# ---------------------------------------------------------------------------
# Store fixtures (T113)
# ---------------------------------------------------------------------------


@pytest.fixture
def risk_store():
    """Return the default InMemoryRiskSignalStore backed by the seeded dataset."""
    return default_store()


@pytest.fixture
def seed_customer_ids() -> list[str]:
    """List of every seeded customer_id in the mock dataset."""
    return [
        "CUS-CLEAN",
        "CUS-CHARGEBACKS",
        "CUS-ONE-CHARGEBACK",
        "CUS-VELOCITY",
        "CUS-INSTRUMENT",
        "CUS-CARD-TESTING",
        "CUS-NEW-ACCOUNT",
        "CUS-ANOMALY",
        "CUS-BLOCKLIST",
        "CUS-CONTRADICTION",
        "CUS-BORDERLINE",
        "CUS-NEW-HIGH-REFUND",
        "CUS-IP-DEVICE",
        "CUS-VIP-ENTERPRISE",
        "CUS-DEVICE",
        "CUS-GEO",
        "CUS-UNUSUAL-AMOUNT",
        "CUS-MISSING-HISTORY",
    ]


# ---------------------------------------------------------------------------
# A2A contract harness fixtures (T042)
# ---------------------------------------------------------------------------


def make_task_request(capability_id: str = "assess_fraud_risk", data: dict | None = None) -> object:
    """Build a valid A2A TaskRequest envelope addressed to the risk-fraud-agent endpoint."""
    from agent_foundation.a2a import A2AMessage, A2APart
    from agent_foundation.payloads.task import TaskRequest
    from packages.contracts.topics import endpoint_topic

    if data is None:
        data = make_risk_request_data()

    task_id = uuid.uuid4()
    return TaskRequest(
        task_id=task_id,
        capability=capability_id,
        target_agent_id="risk-fraud-agent",
        target_topic=endpoint_topic("risk-fraud-agent"),
        input=A2AMessage(
            role="user",
            parts=[A2APart(type="data", data=data)],
        ),
    )


@pytest.mark.skip(reason="marker definition only")
def requires_broker() -> None:
    """Marker: test requires a live Kafka broker (via testcontainers)."""


pytest.ini_options = {}
