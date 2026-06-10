"""AgentCore A2A entrypoint for the Risk Fraud Agent (T033).

Grafts the existing deterministic risk-assessment pipeline (``service.assess_signals``)
onto the AWS AgentCore A2A runtime contract. AgentCore's ``serve_a2a`` speaks the
standard a2a-sdk wire protocol (JSON-RPC ``message/send``), which is DISTINCT from
this repo's internal A2A runtime (feature 002). All business logic
(``scoring`` / ``mock_data`` / ``policy`` / ``service``) is reused unchanged — this file
is purely the runtime shell.

This entrypoint does NOT publish to Kafka — the domain result event stays the Kafka
entrypoint's job (US2). The AgentCore path is for local testing/demo only (plan §Architecture
Decision: AgentCore CLI Local Development Parity).

Run locally:

    cd apps/agents/risk_fraud
    agentcore dev
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# --- Make the monorepo importable from the AgentCore dev venv ----------------
# `agentcore dev` builds an isolated venv from this directory's pyproject.toml and
# runs this file directly. The agent's logic lives in the repo's `apps/`, `packages/`
# and `src/` trees, which are NOT pip-installed into that venv, so we put them on the
# import path from source. parents[5] == repo root (app/RiskFraud/main.py).
_REPO_ROOT = Path(__file__).resolve().parents[5]
for _p in (_REPO_ROOT, _REPO_ROOT / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from a2a.server.agent_execution import AgentExecutor, RequestContext  # noqa: E402
from a2a.server.events import EventQueue  # noqa: E402
from a2a.server.tasks import TaskUpdater  # noqa: E402
from a2a.types import (  # noqa: E402
    AgentCapabilities,
    AgentCard,
    AgentSkill,
    DataPart,
    Part,
)
from a2a.utils import new_task  # noqa: E402
from bedrock_agentcore.runtime import serve_a2a  # noqa: E402

from agent_foundation.a2a import A2APart  # noqa: E402
from apps.agents.risk_fraud.service import assess, build_a2a_output  # noqa: E402


def _input_parts(context: RequestContext) -> list[A2APart]:
    """Map incoming a2a-sdk message parts → A2APart list service.assess expects."""
    parts: list[A2APart] = []
    message = context.message
    for part in message.parts if message else []:
        root = getattr(part, "root", part)
        kind = getattr(root, "kind", None)
        if kind == "data" and getattr(root, "data", None):
            parts.append(A2APart(type="data", data=dict(root.data)))
        elif kind == "text" and getattr(root, "text", None):
            try:
                parts.append(A2APart(type="data", data=json.loads(root.text)))
            except (ValueError, TypeError):
                continue
    return parts


class RiskFraudExecutor(AgentExecutor):
    """Runs the deterministic risk/fraud assessment as a single-shot A2A task."""

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task = context.current_task or new_task(context.message)
        if not context.current_task:
            await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)

        try:
            assessment, _request = assess(_input_parts(context))
        except ValueError as exc:
            print(f"[risk-fraud] input rejected: {exc}", file=sys.stderr)
            await updater.failed()
            return

        out = build_a2a_output(assessment)
        await updater.add_artifact([Part(root=DataPart(data=out.parts[0].data))])
        await updater.complete()

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        pass


CARD = AgentCard(
    name="risk-fraud-agent",
    description="Assesses fraud risk for refund requests based on owned risk/fraud signals.",
    url="http://localhost:9001/",
    version="1.0.0",
    capabilities=AgentCapabilities(streaming=True),
    skills=[
        AgentSkill(
            id="assess_fraud_risk",
            name="Assess Fraud Risk",
            description=(
                "Validates the structured refund risk request, loads owned risk/fraud signals, "
                "and returns a deterministic risk assessment (low / elevated / high) with "
                "confidence score, evidence, policy references, and a human-review flag. "
                "Descriptive intent: assess_refund_risk."
            ),
            tags=["risk", "fraud", "refund"],
        )
    ],
    default_input_modes=["data", "text"],
    default_output_modes=["data"],
)


if __name__ == "__main__":
    serve_a2a(RiskFraudExecutor(), CARD)
