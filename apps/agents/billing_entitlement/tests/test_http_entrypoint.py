"""HTTP A2A entrypoint tests (T037 — acceptance criteria 1 & 2, FR-011)."""

from __future__ import annotations

import uuid

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed; skip HTTP entrypoint tests")
pytest.importorskip("httpx", reason="httpx not installed; skip HTTP entrypoint tests")

from fastapi.testclient import TestClient

from apps.agents.billing_entitlement.http_app import app

_client = TestClient(app)


def _make_task_body(purchase_reference: str = "PR-APPROVE") -> dict:
    return {
        "task_id": str(uuid.uuid4()),
        "capability": "analyze_refund_eligibility",
        "requester_agent_id": "test-client",
        "target_agent_id": "billing-entitlement-agent",
        "input": {
            "role": "user",
            "parts": [
                {
                    "type": "data",
                    "data": {
                        "case_id": str(uuid.uuid4()),
                        "ticket_id": "TKT-001",
                        "customer_id": "CUS-001",
                        "requested_refund_amount": 49.99,
                        "purchase_reference": purchase_reference,
                    },
                }
            ],
        },
    }


# --- Agent Card (acceptance criterion 1) ---

def test_agent_card_lists_capability():
    resp = _client.get("/.well-known/agent.json")
    assert resp.status_code == 200
    card = resp.json()
    capability_ids = [c["id"] for c in card["capabilities"]]
    assert "analyze_refund_eligibility" in capability_ids


def test_ping_ok():
    resp = _client.get("/ping")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# --- POST /a2a/tasks (acceptance criterion 2) ---

def test_post_task_approve_case_returns_recommendation():
    resp = _client.post("/a2a/tasks", json=_make_task_body("PR-APPROVE"))
    assert resp.status_code == 200
    result = resp.json()
    assert result["status"] == "completed"
    parts = result["output"]["parts"]
    data_parts = [p for p in parts if p["type"] == "data"]
    assert len(data_parts) == 1
    rec = data_parts[0]["data"]["recommendation"]
    assert rec == "approve_full_refund"


def test_post_task_deny_case_returns_deny():
    resp = _client.post("/a2a/tasks", json=_make_task_body("PR-WINDOW-EXPIRED"))
    assert resp.status_code == 200
    result = resp.json()
    assert result["status"] == "completed"
    parts = result["output"]["parts"]
    data_parts = [p for p in parts if p["type"] == "data"]
    rec = data_parts[0]["data"]["recommendation"]
    assert rec == "deny_refund"


def test_post_task_malformed_returns_failed():
    resp = _client.post("/a2a/tasks", json={
        "task_id": str(uuid.uuid4()),
        "input": {"role": "user", "parts": [{"type": "text", "text": "not data"}]},
    })
    result = resp.json()
    assert result["status"] == "failed"
    assert result["error"]["category"] == "handler_error"


def test_post_task_missing_required_field_returns_failed():
    body = _make_task_body()
    # Remove required field from data part
    body["input"]["parts"][0]["data"].pop("case_id")
    resp = _client.post("/a2a/tasks", json=body)
    result = resp.json()
    assert result["status"] == "failed"


def test_post_task_without_broker_works():
    """Agent is independently callable — no broker required (acceptance 2)."""
    resp = _client.post("/a2a/tasks", json=_make_task_body("PR-APPROVE"))
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"
