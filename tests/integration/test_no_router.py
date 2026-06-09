"""Integration tests: US5 — no supervisor, no central router.

Tests T033: confirms the demo wiring contains no dispatcher/router/orchestrator
and cross-agent traffic addresses endpoint topics directly (FR-011, SC-008).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

AGENTS_DIR = Path(__file__).parent.parent.parent / "apps" / "agents"
FORBIDDEN_NAMES = frozenset(
    {
        "dispatcher",
        "router",
        "orchestrator",
        "supervisor",
        "broker_router",
        "middleware_router",
    }
)


def _load_source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _get_agent_files() -> list[Path]:
    return list(AGENTS_DIR.glob("**/main.py")) + [AGENTS_DIR / "common.py"]


def test_no_router_import_in_agent_files() -> None:
    """No module under apps/agents/ imports a dispatcher/router/orchestrator."""
    for path in _get_agent_files():
        if not path.exists():
            continue
        source = _load_source(path)
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not any(
                        forbidden in alias.name.lower() for forbidden in FORBIDDEN_NAMES
                    ), f"{path.name}: imports forbidden name {alias.name!r}"
            elif isinstance(node, ast.ImportFrom):
                module = (node.module or "").lower()
                assert not any(forbidden in module for forbidden in FORBIDDEN_NAMES), (
                    f"{path.name}: from-imports forbidden module {node.module!r}"
                )


def test_no_router_defined_in_agent_files() -> None:
    """No module defines a class or function whose name matches a router/dispatcher."""
    for path in _get_agent_files():
        if not path.exists():
            continue
        source = _load_source(path)
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                name_lower = node.name.lower()
                assert not any(forbidden in name_lower for forbidden in FORBIDDEN_NAMES), (
                    f"{path.name}: defines forbidden symbol {node.name!r}"
                )


def test_customer_resolution_delegates_directly_to_billing() -> None:
    """customer_resolution/main.py submits to billing-entitlement-agent endpoint directly."""
    cr_main = AGENTS_DIR / "customer_resolution" / "main.py"
    if not cr_main.exists():
        pytest.skip("customer_resolution/main.py not found")

    source = _load_source(cr_main)
    assert "billing-entitlement-agent" in source, (
        "customer_resolution/main.py must address billing-entitlement-agent directly"
    )
    assert "A2AClient" in source or "submit" in source, (
        "customer_resolution/main.py must use A2AClient.submit for delegation"
    )


def test_no_shared_intermediary_topic() -> None:
    """Cross-agent calls use endpoint_topic(), not a shared intermediary topic."""
    cr_main = AGENTS_DIR / "customer_resolution" / "main.py"
    if not cr_main.exists():
        pytest.skip("customer_resolution/main.py not found")

    source = _load_source(cr_main)
    # Must NOT address the shared result topic directly as a task routing topic
    assert "TOPIC_TASK_RESULT" not in source or "publish" not in source, (
        "customer_resolution must not route tasks through TOPIC_TASK_RESULT"
    )
    # The A2AClient uses endpoint_topic internally — no intermediary
    forbidden_patterns = ["shared.router", "task.dispatcher", "central.topic"]
    for pattern in forbidden_patterns:
        assert pattern not in source.lower(), f"Found forbidden pattern {pattern!r}"
