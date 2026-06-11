"""Guard test -- assert no forbidden imports in agent_foundation.llm."""

from __future__ import annotations

import ast
import os

_LLM_PACKAGE_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "..",
    "..",
    "src",
    "agent_foundation",
    "llm",
)


def _collect_python_files():
    """Collect all .py files under src/agent_foundation/llm/."""
    result = []
    for root, _dirs, files in os.walk(os.path.normpath(_LLM_PACKAGE_DIR)):
        for f in files:
            if f.endswith(".py"):
                result.append(os.path.join(root, f))
    return result


def _extract_imports(filepath):
    """Extract all import module names from a Python file."""
    with open(filepath) as fh:
        try:
            tree = ast.parse(fh.read(), filename=filepath)
        except SyntaxError:
            return []

    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


async def test_no_agents_imports():
    """No module under src/agent_foundation/llm/ imports apps.agents.*."""
    for filepath in _collect_python_files():
        for mod in _extract_imports(filepath):
            assert not mod.startswith("apps.agents"), f"{filepath} imports {mod}"


async def test_no_decision_engine_imports():
    """No module under src/agent_foundation/llm/ imports decision_engine, rules_engine, scoring."""
    forbidden = {"decision_engine", "rules_engine", "scoring"}
    for filepath in _collect_python_files():
        for mod in _extract_imports(filepath):
            parts = mod.split(".")
            for part in parts:
                assert part not in forbidden, f"{filepath} imports forbidden module: {mod}"


async def test_no_routing_symbols():
    """No routing symbols in LLM package."""
    forbidden_names = {"route", "dispatch", "orchestrate", "supervise"}
    for filepath in _collect_python_files():
        with open(filepath) as fh:
            try:
                tree = ast.parse(fh.read(), filename=filepath)
            except SyntaxError:
                continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                assert node.name not in forbidden_names, (
                    f"{filepath} defines forbidden function: {node.name}"
                )
            elif isinstance(node, ast.ClassDef):
                assert node.name.lower() not in forbidden_names, (
                    f"{filepath} defines forbidden class: {node.name}"
                )
