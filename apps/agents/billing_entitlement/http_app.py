"""HTTP A2A startup entrypoint for the AgentCore CLI (T038).

Exposes:
  GET  /.well-known/agent.json  — Agent Card (shared with Kafka entrypoint via identity.py)
  POST /a2a/tasks               — A2A task: analyze_refund_eligibility → recommendation
  GET  /ping                    — AgentCore local health check

This entrypoint does NOT publish to Kafka — the domain result event stays the Kafka
entrypoint's job (US2). It reuses the same service.analyze pipeline (T011).
"""

from __future__ import annotations

import os
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from apps.agents.billing_entitlement.identity import build_agent_card
from apps.agents.billing_entitlement.service import analyze, build_a2a_output

app = FastAPI(title="Billing Entitlement Agent (AgentCore HTTP)", version="1.0.0")

_card = build_agent_card()


@app.get("/ping")
async def ping() -> dict[str, str]:
    return {"status": "ok", "agent_id": _card.agent_id}


@app.get("/.well-known/agent.json")
async def agent_json() -> dict[str, Any]:
    return _card.model_dump(mode="json")


@app.post("/a2a/tasks")
async def handle_task(request: Request) -> JSONResponse:
    """Accept an A2A TaskRequest, run service.analyze, return a TaskResult JSON."""
    from agent_foundation.a2a import A2APart

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={
                "task_id": str(uuid.uuid4()),
                "status": "failed",
                "performer_agent_id": _card.agent_id,
                "error": {"category": "validation", "message": "Request body is not valid JSON"},
            },
        )

    task_id_str = body.get("task_id", str(uuid.uuid4()))

    # Extract input parts from the A2A TaskRequest body
    try:
        input_parts_raw = body.get("input", {}).get("parts", [])
        parts = [A2APart.model_validate(p) for p in input_parts_raw]
        request_obj, rec, _facts = analyze(parts)
        output = build_a2a_output(rec)
        return JSONResponse(
            content={
                "task_id": task_id_str,
                "status": "completed",
                "performer_agent_id": _card.agent_id,
                "output": output.model_dump(mode="json"),
            }
        )
    except Exception as exc:
        return JSONResponse(
            status_code=200,  # A2A protocol: errors are still 200 with failed status
            content={
                "task_id": task_id_str,
                "status": "failed",
                "performer_agent_id": _card.agent_id,
                "error": {"category": "handler_error", "message": str(exc)},
            },
        )


def run() -> None:
    import uvicorn

    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run("apps.agents.billing_entitlement.http_app:app", host="0.0.0.0", port=port)


if __name__ == "__main__":
    run()
