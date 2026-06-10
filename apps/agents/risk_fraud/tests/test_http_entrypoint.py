"""Tests for the HTTP A2A entrypoint (T032, T088, T089).

Uses FastAPI TestClient — no broker required.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from apps.agents.risk_fraud.http_app import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# T032: Card advertises assess_fraud_risk
# ---------------------------------------------------------------------------


def test_agent_card_endpoint(client: TestClient):
    resp = client.get("/.well-known/agent.json")
    assert resp.status_code == 200
    card = resp.json()
    assert card["agent_id"] == "risk-fraud-agent"
    cap_ids = [c["id"] for c in card.get("capabilities", [])]
    assert "assess_fraud_risk" in cap_ids


def test_ping_endpoint(client: TestClient):
    resp = client.get("/ping")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# T088: Port resolves to 8103 from default
# ---------------------------------------------------------------------------


def test_http_app_default_port():
    import inspect

    from apps.agents.risk_fraud.http_app import run

    # Verify the run() function uses the expected default port
    source = inspect.getsource(run)
    assert "8103" in source


# ---------------------------------------------------------------------------
# T032 / T088: Valid task returns verdict
# ---------------------------------------------------------------------------


def _task_body(customer_id: str = "CUS-CLEAN") -> dict:
    return {
        "task_id": str(uuid.uuid4()),
        "capability": "assess_fraud_risk",
        "input": {
            "parts": [
                {
                    "type": "data",
                    "data": {
                        "case_id": str(uuid.uuid4()),
                        "ticket_id": "TKT-001",
                        "customer_id": customer_id,
                    },
                }
            ]
        },
    }


def test_valid_task_returns_completed(client: TestClient):
    resp = client.post("/a2a/tasks", json=_task_body("CUS-CLEAN"))
    assert resp.status_code == 200
    result = resp.json()
    assert result["status"] == "completed"
    data = result["output"]["parts"][0]["data"]
    assert data["recommendation"] in ("low", "elevated", "high")


def test_bad_input_returns_failed(client: TestClient):
    """Malformed input (missing case_id) → structured failed result (FR-011)."""
    bad_body = {
        "task_id": str(uuid.uuid4()),
        "capability": "assess_fraud_risk",
        "input": {
            "parts": [
                {
                    "type": "data",
                    "data": {"ticket_id": "TKT-001"},  # missing case_id and customer_id
                }
            ]
        },
    }
    resp = client.post("/a2a/tasks", json=bad_body)
    assert resp.status_code == 200
    result = resp.json()
    assert result["status"] == "failed"
    assert "error" in result


def test_invalid_json_body_returns_400(client: TestClient):
    resp = client.post(
        "/a2a/tasks", content="not-json", headers={"Content-Type": "application/json"}
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# T089: Direct-call proof — Customer Resolution Agent request shape
# ---------------------------------------------------------------------------


def test_resolution_direct_call_proof(client: TestClient):
    """Build the request shape 003 sends and verify it routes through correctly."""
    # The Customer Resolution Agent sends these fields via build_risk_request_input
    body = {
        "task_id": str(uuid.uuid4()),
        "capability": "assess_fraud_risk",
        "input": {
            "parts": [
                {
                    "type": "data",
                    "data": {
                        "case_id": str(uuid.uuid4()),
                        "ticket_id": "TKT-TEST-003",
                        "customer_id": "CUS-CLEAN",
                        "requested_refund_amount": "49.99",
                        "customer_message_summary": "I would like a refund",
                    },
                }
            ]
        },
    }
    resp = client.post("/a2a/tasks", json=body)
    assert resp.status_code == 200
    result = resp.json()
    assert result["status"] == "completed"
    data = result["output"]["parts"][0]["data"]
    # Verify normalize_risk_result can parse it (003 consumer)
    assert data["recommendation"] in ("low", "elevated", "high")
    assert isinstance(data["requires_human_review"], bool)
    assert isinstance(data["confidence"], float)
