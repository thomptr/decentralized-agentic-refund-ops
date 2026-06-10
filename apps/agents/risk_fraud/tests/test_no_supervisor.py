"""Tests confirming the agent originates no task requests and dispatches no work (T031, T109)."""

from __future__ import annotations

import ast
from pathlib import Path

# ---------------------------------------------------------------------------
# T031: Agent constructs no peer/runtime client
# ---------------------------------------------------------------------------


def test_main_module_no_client_import():
    """main.py must not import or construct an A2A client (SC-008/FR-016)."""
    main_path = Path(__file__).parent.parent / "main.py"
    source = main_path.read_text()
    tree = ast.parse(source)

    # Walk all Name/Attribute accesses — check that no 'client' class is imported
    client_names = {"A2AClient", "AgentClient", "RuntimeClient", "TaskClient"}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                assert alias.name not in client_names, (
                    f"main.py imports client class {alias.name!r} — should originate no tasks"
                )


def test_main_module_no_send_calls():
    """main.py must not call .send() or .request() to another agent endpoint."""
    main_path = Path(__file__).parent.parent / "main.py"
    source = main_path.read_text()
    # Simple string check for suspicious patterns
    suspicious = ["client.send(", "client.request(", ".send_task(", "A2AClient("]
    for pattern in suspicious:
        assert pattern not in source, f"main.py contains suspicious peer-call pattern {pattern!r}"


def test_service_no_peer_client_import():
    """service.py must not import any A2A client."""
    service_path = Path(__file__).parent.parent / "service.py"
    source = service_path.read_text()
    client_names = {"A2AClient", "AgentClient", "RuntimeClient"}
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                assert alias.name not in client_names


def test_scoring_no_peer_client_import():
    """scoring.py must not import any A2A client or make network calls."""
    scoring_path = Path(__file__).parent.parent / "scoring.py"
    source = scoring_path.read_text()
    forbidden_imports = {"httpx", "requests", "aiohttp", "boto3"}
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            module = getattr(node, "module", None) or ""
            for alias in node.names:
                full_name = alias.name
                assert full_name not in forbidden_imports, (
                    f"scoring.py imports {full_name!r} — should be a pure function"
                )
                assert not module.startswith("httpx"), (
                    f"scoring.py imports from {module!r} — should be a pure function"
                )


# ---------------------------------------------------------------------------
# T109: Behavioral analyzer / assessment output has no approve/deny/refund field
# ---------------------------------------------------------------------------


def test_risk_assessment_no_refund_decision_field():
    """RiskAssessment has no approve/deny/refund field (FR-016/SC-008)."""

    from apps.agents.risk_fraud.models import RiskAssessment

    model_fields = RiskAssessment.model_fields
    forbidden = ["approve", "deny", "refund_decision", "approve_refund", "deny_refund"]
    for field in forbidden:
        assert field not in model_fields, (
            f"RiskAssessment has forbidden field {field!r} — agent must not make refund decisions"
        )


def test_recommended_action_no_refund_values():
    """RecommendedAction enum values are operational only — no approve/deny refund."""
    from apps.agents.risk_fraud.models import RecommendedAction

    for action in RecommendedAction:
        assert "refund" not in action.value.lower(), (
            f"RecommendedAction.{action.name} contains 'refund' — not operational language"
        )
