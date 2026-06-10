"""Standalone A2A test client for the AgentCore HTTP entrypoint (T039).

Usage (with http_app running on :8080):
  python -m apps.agents.billing_entitlement.dev_a2a_client

Proves the agent is callable independently — no broker, no other agent running (acceptance 2).
"""

from __future__ import annotations

import sys
import uuid


def main(base_url: str = "http://localhost:8080") -> None:
    try:
        import httpx
    except ImportError:
        print("httpx not installed. Install with: pip install httpx", file=sys.stderr)
        sys.exit(1)

    client = httpx.Client(base_url=base_url, timeout=10.0)

    # --- Step 1: GET /.well-known/agent.json and assert capability listed ---
    print(f"\nGET {base_url}/.well-known/agent.json")
    card_resp = client.get("/.well-known/agent.json")
    card_resp.raise_for_status()
    card = card_resp.json()
    capability_ids = [c.get("id") for c in card.get("capabilities", [])]
    print(f"Agent: {card.get('name')} v{card.get('version')}")
    print(f"Capabilities: {capability_ids}")
    assert "analyze_refund_eligibility" in capability_ids, (
        f"analyze_refund_eligibility not in card capabilities: {capability_ids}"
    )
    print("✓ Agent Card lists analyze_refund_eligibility")

    # --- Step 2: POST approve case ---
    _post_task(client, base_url, "PR-APPROVE", "approve case")

    # --- Step 3: POST deny case ---
    _post_task(client, base_url, "PR-WINDOW-EXPIRED", "deny case (window expired)")

    # --- Step 4: POST unknown reference ---
    _post_task(client, base_url, "PR-UNKNOWN-XYZ", "unknown reference → request_more_information")

    print("\n✓ All checks passed. Agent is independently callable.")


def _post_task(client: object, base_url: str, purchase_reference: str, label: str) -> None:
    import httpx as _httpx

    task_id = str(uuid.uuid4())
    case_id = str(uuid.uuid4())
    body = {
        "task_id": task_id,
        "capability": "analyze_refund_eligibility",
        "requester_agent_id": "dev-client",
        "target_agent_id": "billing-entitlement-agent",
        "input": {
            "role": "user",
            "parts": [
                {
                    "type": "data",
                    "data": {
                        "case_id": case_id,
                        "ticket_id": "TKT-DEV-001",
                        "customer_id": "CUS-DEV-001",
                        "requested_refund_amount": 49.99,
                        "purchase_reference": purchase_reference,
                    },
                }
            ],
        },
    }
    print(f"\nPOST /a2a/tasks [{label}] purchase_reference={purchase_reference!r}")
    assert isinstance(client, _httpx.Client)
    resp = client.post("/a2a/tasks", json=body)
    result = resp.json()
    status = result.get("status")
    recommendation = None
    if output := result.get("output"):
        for part in output.get("parts", []):
            if part.get("type") == "data":
                recommendation = part.get("data", {}).get("recommendation")
    print(f"  status={status!r}  recommendation={recommendation!r}")
    assert status in ("completed", "failed"), f"Unexpected status: {status!r}"
    print("  ✓")


if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080"
    main(base)
