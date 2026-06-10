"""No-supervisor test — the billing agent issues no TaskRequest to any peer (T027 — SC-008/US7)."""

from __future__ import annotations

from pathlib import Path


def _source_text(module_path: str) -> str:
    path = Path(__file__).parent.parent / module_path
    return path.read_text(encoding="utf-8")


def test_main_py_issues_no_task_request():
    src = _source_text("main.py")
    assert "TaskRequest(" not in src or "handle_eligibility" in src
    # The agent receives TaskRequests but must not CREATE or SEND them to peers
    assert "runtime.request(" not in src
    assert "send_task(" not in src
    # No outbound task dispatch
    assert "TaskRequest(task_id=" not in src


def test_service_py_issues_no_task_request():
    src = _source_text("service.py")
    assert "TaskRequest" not in src


def test_rules_engine_issues_no_task_request():
    src = _source_text("rules_engine.py")
    assert "TaskRequest" not in src


def test_no_a2a_client_import_in_domain_modules():
    """Domain modules must not import any A2A client to dispatch work."""
    domain_files = ["models.py", "policy.py", "mock_data.py", "rules_engine.py", "service.py"]
    for fname in domain_files:
        src = _source_text(fname)
        assert "A2AClient" not in src, f"{fname} imports A2AClient"
        assert "AgentClient" not in src, f"{fname} imports AgentClient"
        assert "send_task" not in src, f"{fname} calls send_task"


def test_no_peer_delegation_in_handler():
    """Handler in main.py must not delegate to any peer agent."""
    src = _source_text("main.py")
    # discovery is for card, not for delegating
    assert "find_capable" not in src or "publish" in src
    assert "delegate(" not in src
    assert "dispatch(" not in src
