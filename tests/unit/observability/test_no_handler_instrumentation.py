"""T039: Guard test — no observability/tracing API references in agent handler modules (SC-003)."""
from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

HANDLER_MODULES = [
    "apps/agents/customer_resolution/event_handlers.py",
    "apps/agents/billing_entitlement/event_handlers.py",
    "apps/agents/risk_fraud/event_handlers.py",
]

FORBIDDEN_IMPORTS = {
    "agent_foundation.observability",
    "langfuse",
    "opentelemetry",
}

FORBIDDEN_NAMES = {
    "span",
    "generation",
    "traced",
    "configure_observability",
    "get_client",
    "flush",
    "Langfuse",
    "tracer",
}

REPO_ROOT = Path(__file__).parent.parent.parent.parent


def _get_imports_and_names(path: Path) -> tuple[set[str], set[str]]:
    if not path.exists():
        return set(), set()
    tree = ast.parse(path.read_text())
    imports: set[str] = set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module)
                for alias in node.names:
                    names.add(alias.name)
        elif isinstance(node, ast.Name):
            names.add(node.id)
    return imports, names


@pytest.mark.parametrize("handler_rel", HANDLER_MODULES)
def test_no_observability_imports_in_handler(handler_rel: str) -> None:
    path = REPO_ROOT / handler_rel
    if not path.exists():
        pytest.skip(f"{handler_rel} not found")
    imports, _ = _get_imports_and_names(path)
    violations = {i for i in imports if any(i.startswith(f) for f in FORBIDDEN_IMPORTS)}
    assert not violations, f"{handler_rel} imports observability APIs: {violations}"
