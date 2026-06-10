"""AgentCore A2A entrypoint for the Customer Resolution Agent.

Grafts the agent's deterministic classify + decision pipeline (``ticket_classifier.classify`` /
``decision_engine.decide``, via ``agentcore_app._invoke``) onto the AWS AgentCore A2A runtime
contract. AgentCore's ``serve_a2a`` speaks the standard a2a-sdk wire protocol (JSON-RPC
``message/send``), which is DISTINCT from this repo's internal A2A-over-Kafka runtime (feature 002).
All business logic is reused unchanged — this file is purely the runtime shell.

This entrypoint is a demo/testing interface only: it does NOT delegate to the billing/risk peers
and does NOT publish to Kafka. Peer findings can be supplied inline in the request payload
(``billing_result`` / ``risk_result``); absent them the decision engine deterministically escalates
to a human. The Kafka entrypoint (apps/agents/customer_resolution/main.py) is the real orchestrator.

Run locally:

    cd apps/agents/customer_resolution
    agentcore dev
"""

from __future__ import annotations

import sys
from pathlib import Path

# --- Make the monorepo importable from the AgentCore dev venv ----------------
# `agentcore dev` builds an isolated venv from this directory's pyproject.toml and
# runs this file directly. The agent's logic lives in the repo's `apps/`, `packages/`
# and `src/` trees, which are NOT pip-installed into that venv, so we put them on the
# import path from source. parents[5] == repo root (app/CustomerResolution/main.py).
# NOTE: this source-path wiring makes `agentcore dev` work locally; a real
# `agentcore deploy` (CodeZip) would need the monorepo packages vendored into
# codeLocation instead — out of scope for local run.
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

from apps.agents.customer_resolution.agentcore_app import _invoke  # noqa: E402


def _payload(context: RequestContext) -> dict | str:
    """Extract the resolution input from the incoming a2a-sdk message.

    The ticket arrives as a structured DataPart. As a convenience we also accept a
    JSON-encoded payload sent as a TextPart (e.g. `agentcore dev '{...}'`), which
    ``_invoke`` decodes itself.
    """
    message = context.message
    for part in message.parts if message else []:
        root = getattr(part, "root", part)  # a2a-sdk wraps parts as Part(root=DataPart|TextPart)
        kind = getattr(root, "kind", None)
        if kind == "data" and getattr(root, "data", None):
            return dict(root.data)
        if kind == "text" and getattr(root, "text", None):
            return root.text
    return {}


class CustomerResolutionExecutor(AgentExecutor):
    """Runs the deterministic classify + decide pipeline as a single-shot A2A task."""

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task = context.current_task or new_task(context.message)
        if not context.current_task:
            await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)

        result = _invoke(_payload(context))
        if result.get("status") == "failed":
            # Invalid / missing input → fail the task (FR-011); no fabricated decision.
            print(f"[customer-resolution] input rejected: {result.get('error')}", file=sys.stderr)
            await updater.failed()
            return

        await updater.add_artifact([Part(root=DataPart(data=result))])
        await updater.complete()

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        # Synchronous, single-shot decision — nothing to cancel.
        pass


CARD = AgentCard(
    name="customer-resolution-agent",
    description=(
        "Resolves customer support tickets by triaging refund requests and applying a "
        "deterministic decision engine over billing and risk findings."
    ),
    url="http://localhost:9002/",
    version="1.0.0",
    # Streaming is advertised so the AgentCore inspector (which calls message/stream) works.
    # The executor pushes task/artifact/complete events to the EventQueue, which the a2a-sdk
    # streams over SSE; the same single-shot path also serves message/send.
    capabilities=AgentCapabilities(streaming=True),
    skills=[
        AgentSkill(
            id="resolve_customer_case",
            name="Resolve Customer Case",
            description=(
                "Triages a support ticket (refund-intent classification) and runs the "
                "deterministic decision engine to produce a resolution outcome "
                "(approve_refund / deny_refund / offer_partial_credit / "
                "request_more_information / escalate_human / direct_response) with a "
                "customer-safe response draft. Optional billing_result / risk_result peer "
                "findings can be supplied in the payload; absent them the case escalates "
                "to a human."
            ),
            tags=["resolution", "refund", "triage"],
        )
    ],
    default_input_modes=["data", "text"],
    default_output_modes=["data"],
)


if __name__ == "__main__":
    serve_a2a(CustomerResolutionExecutor(), CARD)
