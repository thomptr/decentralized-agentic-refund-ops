"""HTTP A2A startup entrypoint for the AgentCore CLI (T038, Phase 13).

Exposes:
  GET  /.well-known/agent.json  — Agent Card (shared with Kafka entrypoint via identity.py)
  POST /a2a/tasks               — A2A task: assess_fraud_risk → risk assessment
  GET  /ping                    — AgentCore local health check

Port: 8103 (avoids billing agent's :8080 so both run concurrently; configurable via
PORT/A2A_ENDPOINT_PORT env var).

This entrypoint does NOT publish to Kafka — the domain result event stays the Kafka
entrypoint's job (US2/T020). It reuses the same service.assess pipeline (T016).
"""

from __future__ import annotations

import os
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from apps.agents.risk_fraud.identity import build_agent_card
from apps.agents.risk_fraud.service import assess, build_a2a_output

app = FastAPI(title="Risk Fraud Agent (AgentCore HTTP)", version="1.0.0")

_card = build_agent_card()


@app.get("/ping")
async def ping() -> dict[str, str]:
    return {"status": "ok", "agent_id": _card.agent_id}


@app.get("/.well-known/agent.json")
async def agent_json() -> dict[str, Any]:
    return _card.model_dump(mode="json")


@app.post("/a2a/tasks")
async def handle_task(request: Request) -> JSONResponse:
    """Accept an A2A TaskRequest, run service.assess, return a TaskResult JSON."""
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

    try:
        input_parts_raw = body.get("input", {}).get("parts", [])
        parts = [A2APart.model_validate(p) for p in input_parts_raw]
        assessment, _request = assess(parts)
        output = build_a2a_output(assessment)
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

    port = int(os.environ.get("A2A_ENDPOINT_PORT", os.environ.get("PORT", "8103")))
    uvicorn.run("apps.agents.risk_fraud.http_app:app", host="0.0.0.0", port=port)


if __name__ == "__main__":
    run()
