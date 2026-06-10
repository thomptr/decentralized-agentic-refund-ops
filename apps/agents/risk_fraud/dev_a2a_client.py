"""Dev helper: GET the agent card + POST sample tasks to the local HTTP A2A surface (T038, T090).

Usage:
    python -m apps.agents.risk_fraud.dev_a2a_client

Defaults to http://localhost:8103 (Risk Agent's A2A endpoint port, distinct from
billing agent's :8080).
"""

from __future__ import annotations

import json
import sys
import uuid

try:
    import httpx
except ImportError:
    print("httpx is required: pip install httpx", file=sys.stderr)
    sys.exit(1)


BASE_URL = "http://localhost:8103"


def _make_task(customer_id: str, ticket_id: str = "TKT-001") -> dict:
    """Build a 003-shaped sample assess_fraud_risk TaskRequest."""
    return {
        "task_id": str(uuid.uuid4()),
        "capability": "assess_fraud_risk",
        "input": {
            "parts": [
                {
                    "type": "data",
                    "data": {
                        "case_id": str(uuid.uuid4()),
                        "ticket_id": ticket_id,
                        "customer_id": customer_id,
                        "requested_refund_amount": "49.99",
                    },
                }
            ]
        },
    }


def main(base_url: str = BASE_URL) -> None:
    client = httpx.Client(base_url=base_url, timeout=10.0)

    # 1. Fetch and validate the Agent Card
    print(f"GET {base_url}/.well-known/agent.json")
    card_resp = client.get("/.well-known/agent.json")
    card_resp.raise_for_status()
    card = card_resp.json()
    cap_ids = [c.get("id") for c in card.get("capabilities", [])]
    assert "assess_fraud_risk" in cap_ids, (
        f"Expected assess_fraud_risk in capabilities, got {cap_ids}"
    )
    print(f"Card: agent_id={card.get('agent_id')}, capabilities={cap_ids}\n")

    # 2. POST sample tasks (clean + risky customers)
    samples = [
        ("CUS-CLEAN", "Clean customer — expected: low"),
        ("CUS-BLOCKLIST", "Blocklist customer — expected: high"),
        ("CUS-CHARGEBACKS", "Repeat chargebacks — expected: high"),
        ("CUS-NEW-ACCOUNT", "New account — expected: elevated"),
    ]

    for customer_id, description in samples:
        task = _make_task(customer_id)
        print(f"POST /a2a/tasks  [{description}]")
        resp = client.post("/a2a/tasks", json=task)
        resp.raise_for_status()
        result = resp.json()
        status = result.get("status")
        output_parts = result.get("output", {}).get("parts", [])
        data = output_parts[0].get("data", {}) if output_parts else {}
        print(
            f"  status={status}  "
            f"recommendation={data.get('recommendation')}  "
            f"confidence={data.get('confidence')}  "
            f"requires_human_review={data.get('requires_human_review')}"
        )
        print(json.dumps(data, indent=2)[:300])
        print()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Risk Fraud Agent dev A2A client")
    parser.add_argument("--base-url", default=BASE_URL, help="Agent HTTP base URL")
    args = parser.parse_args()
    main(args.base_url)
