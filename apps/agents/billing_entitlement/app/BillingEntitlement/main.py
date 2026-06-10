"""AgentCore A2A entrypoint for the Billing Entitlement Agent.

Grafts the existing deterministic refund-eligibility pipeline (``service.analyze``)
onto the AWS AgentCore A2A runtime contract. AgentCore's ``serve_a2a`` speaks the
standard a2a-sdk wire protocol (JSON-RPC ``message/send``), which is DISTINCT from
this repo's internal A2A runtime (feature 002). All business logic
(``rules_engine`` / ``entitlement_checker`` / ``policy`` / ``service``) is reused
unchanged — this file is purely the runtime shell.

Run locally:

    cd apps/agents/billing_entitlement
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
# import path from source. parents[5] == repo root (app/BillingEntitlement/main.py).
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

from agent_foundation.a2a import A2APart  # noqa: E402
from apps.agents.billing_entitlement.service import analyze, build_a2a_output  # noqa: E402


def _input_parts(context: RequestContext) -> list[A2APart]:
    """Map incoming a2a-sdk message parts → the A2APart list ``service.analyze`` expects.

    The refund request arrives as a structured DataPart. As a convenience we also
    accept a JSON-encoded data payload sent as a TextPart (e.g. `agentcore dev '{...}'`).
    """
    parts: list[A2APart] = []
    message = context.message
    for part in message.parts if message else []:
        root = getattr(part, "root", part)  # a2a-sdk wraps parts as Part(root=DataPart|TextPart)
        kind = getattr(root, "kind", None)
        if kind == "data" and getattr(root, "data", None):
            parts.append(A2APart(type="data", data=dict(root.data)))
        elif kind == "text" and getattr(root, "text", None):
            try:
                parts.append(A2APart(type="data", data=json.loads(root.text)))
            except (ValueError, TypeError):
                continue
    return parts


class BillingEntitlementExecutor(AgentExecutor):
    """Runs the deterministic refund-eligibility analysis as a single-shot A2A task."""

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task = context.current_task or new_task(context.message)
        if not context.current_task:
            await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)

        try:
            _request, rec, _facts = analyze(_input_parts(context))
        except ValueError as exc:
            # Invalid / missing input → fail the task (FR-011); no fabricated verdict.
            print(f"[billing-entitlement] input rejected: {exc}", file=sys.stderr)
            await updater.failed()
            return

        # build_a2a_output → a single data part carrying the recommendation payload
        # that the customer-resolution agent's normalize_billing_result already consumes.
        out = build_a2a_output(rec)
        await updater.add_artifact([Part(root=DataPart(data=out.parts[0].data))])
        await updater.complete()

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        # Synchronous, single-shot analysis — nothing to cancel.
        pass


CARD = AgentCard(
    name="billing-entitlement-agent",
    description="Analyzes refund eligibility based on owned billing and entitlement data.",
    url="http://localhost:9000/",
    version="1.0.0",
    # Streaming is advertised so the AgentCore inspector (which calls message/stream)
    # works. The executor pushes task/artifact/complete events to the EventQueue, which
    # the a2a-sdk streams over SSE; the same single-shot path also serves message/send.
    capabilities=AgentCapabilities(streaming=True),
    skills=[
        AgentSkill(
            id="analyze_refund_eligibility",
            name="Analyze Refund Eligibility",
            description=(
                "Validates the structured refund request, loads owned billing facts, and "
                "returns a deterministic recommendation (approve_full_refund / "
                "approve_partial_refund / deny_refund / request_more_information / "
                "manual_review) with confidence, evidence, and policy references."
            ),
            tags=["billing", "entitlement", "refund"],
        )
    ],
    default_input_modes=["data", "text"],
    default_output_modes=["data"],
)


if __name__ == "__main__":
    serve_a2a(BillingEntitlementExecutor(), CARD)
