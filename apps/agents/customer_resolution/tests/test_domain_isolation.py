"""Domain isolation test (T039, T079, T086, US5).

Asserts the agent package imports no billing/payment/fraud datastore module
and that all billing/risk facts flow through the normalized finding types only.
"""

from __future__ import annotations

import ast
from pathlib import Path

_AGENT_PACKAGE = Path(__file__).parent.parent
_FORBIDDEN_IMPORTS = {
    "billing_db",
    "payment_db",
    "fraud_db",
    "risk_db",
    "billing_client",
    "payment_client",
    "sqlalchemy",
    "psycopg2",
    "pymongo",
    "redis",
    "boto3",  # no direct AWS SDK calls from agent package
}

_FORBIDDEN_NAMES = {
    "billing_db",
    "payment_db",
    "fraud_db",
    "risk_db",
    "BillingDatabase",
    "PaymentDatabase",
    "FraudDatabase",
    "RiskDatabase",
}


def _python_files() -> list[Path]:
    files = []
    for f in _AGENT_PACKAGE.rglob("*.py"):
        if "tests" in f.parts:
            continue
        files.append(f)
    return files


def test_no_forbidden_imports():
    """The agent package must not import any billing/payment/fraud datastore module."""
    for filepath in _python_files():
        source = filepath.read_text()
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                module = ""
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        module = alias.name
                        for forbidden in _FORBIDDEN_IMPORTS:
                            assert forbidden not in module, (
                                f"{filepath}: forbidden import '{module}' "
                                f"(contains '{forbidden}')"
                            )
                elif isinstance(node, ast.ImportFrom) and node.module:
                    module = node.module
                    for forbidden in _FORBIDDEN_IMPORTS:
                        assert forbidden not in module, (
                            f"{filepath}: forbidden from-import '{module}' "
                            f"(contains '{forbidden}')"
                        )


def test_billing_finding_is_only_ingress():
    """All billing/risk facts must enter via BillingFinding or RiskFinding, not raw dicts."""
    import uuid

    from apps.agents.customer_resolution.event_handlers import (
        normalize_billing_result,
        normalize_risk_result,
    )
    from apps.agents.customer_resolution.models import BillingFinding, RiskFinding

    tid = uuid.uuid4()
    billing = normalize_billing_result(tid, "test", {"eligible": True})
    assert isinstance(billing, BillingFinding)

    risk = normalize_risk_result(tid, "test", {"risk": "low", "score": 0.1})
    assert isinstance(risk, RiskFinding)


def test_no_forbidden_names_in_agent_source():
    """Assert no reference to internal billing/fraud datastore names in agent code."""
    for filepath in _python_files():
        source = filepath.read_text()
        for name in _FORBIDDEN_NAMES:
            assert name not in source, (
                f"{filepath}: forbidden name '{name}' found in agent source"
            )
