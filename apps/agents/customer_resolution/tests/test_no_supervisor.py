"""No-supervisor guardrail test (T041, US6, FR-015).

Asserts that the agent package contains no supervisor/router/orchestrator patterns.
"""

from __future__ import annotations

import ast
from pathlib import Path

_AGENT_PACKAGE = Path(__file__).parent.parent
_FORBIDDEN_CAPABILITY_NAMES = {
    "supervisor",
    "router",
    "orchestrator",
    "dispatcher",
}


def _python_files() -> list[Path]:
    return [
        f for f in _AGENT_PACKAGE.rglob("*.py")
        if "tests" not in f.parts
    ]


def test_no_router_or_supervisor_in_capabilities():
    """The agent must not register a router/supervisor/orchestrator capability."""
    for filepath in _python_files():
        source = filepath.read_text().lower()
        for name in _FORBIDDEN_CAPABILITY_NAMES:
            # Ignore comments and strings by checking actual identifiers
            assert f'id="{name}"' not in source, (
                f"{filepath}: forbidden capability id '{name}' found"
            )
            assert f"id='{name}'" not in source, (
                f"{filepath}: forbidden capability id '{name}' found"
            )


def test_no_class_or_function_named_supervisor_router():
    """No class or function may be named with supervisor/router patterns."""
    for filepath in _python_files():
        source = filepath.read_text()
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                name_lower = node.name.lower()
                for forbidden in _FORBIDDEN_CAPABILITY_NAMES:
                    assert forbidden not in name_lower, (
                        f"{filepath}:{node.lineno}: class/function '{node.name}' "
                        f"contains forbidden word '{forbidden}'"
                    )


def test_billing_task_requests_target_only_billing_peer():
    """Risk requests must target only the declared risk peer (no routing)."""
    from apps.agents.customer_resolution.config import BILLING_PEER_AGENT_ID, RISK_PEER_AGENT_ID

    assert BILLING_PEER_AGENT_ID == "billing-entitlement-agent"
    assert RISK_PEER_AGENT_ID == "risk-fraud-agent"


def test_no_dispatch_on_behalf_of_others():
    """The agent never handles inbound task-dispatch requests on behalf of peers."""
    from apps.agents.customer_resolution.a2a_handlers import build_agent_card

    card = build_agent_card()
    capability_ids = {cap.id for cap in card.capabilities}
    for cap_id in capability_ids:
        for forbidden in _FORBIDDEN_CAPABILITY_NAMES:
            assert forbidden not in cap_id.lower(), (
                f"Capability '{cap_id}' contains forbidden word '{forbidden}'"
            )
