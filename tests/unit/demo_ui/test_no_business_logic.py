"""Guard test (T022): the demo UI contains no business decision logic.

Encodes the "No business decision logic in the UI" acceptance criterion
(Principle V / SC-006) by source-scanning every ``apps/demo_ui`` module and
asserting it imports none of the agents' decision/scoring/drafting engines. The
UI reads recorded outcomes and displays them — it never re-derives a decision.
"""

from __future__ import annotations

from pathlib import Path

import apps.demo_ui as demo_ui_pkg

# Modules that embody business decisions/scoring — the UI must never import these.
FORBIDDEN_IMPORTS = (
    "apps.agents.customer_resolution.decision",
    "apps.agents.customer_resolution.decision_engine",
    "apps.agents.customer_resolution.response_drafter",
    "apps.agents.billing_entitlement.service",
    "apps.agents.billing_entitlement.scoring",
    "apps.agents.risk_fraud.service",
    "apps.agents.risk_fraud.scoring",
)

# Read-side helpers the aggregators are allowed to depend on (sanity allow-list).
ALLOWED_FOUNDATION = (
    "agent_foundation.runtime.discovery",
    "agent_foundation.audit.store",
    "apps.agents.customer_resolution.trace",
    "agent_foundation.transport.publisher",
)


def _demo_ui_sources() -> list[Path]:
    root = Path(demo_ui_pkg.__file__).parent
    return sorted(root.rglob("*.py"))


def test_demo_ui_has_python_sources() -> None:
    assert _demo_ui_sources(), "expected apps/demo_ui to contain Python modules"


def test_no_decision_or_scoring_imports() -> None:
    offenders: list[str] = []
    for path in _demo_ui_sources():
        text = path.read_text(encoding="utf-8")
        for forbidden in FORBIDDEN_IMPORTS:
            if forbidden in text:
                offenders.append(f"{path.name} imports {forbidden}")
    assert not offenders, "UI must contain no business decision logic: " + "; ".join(offenders)


def test_trace_is_the_only_customer_resolution_dependency() -> None:
    # The only customer_resolution module the UI may touch is the read-side trace tool.
    for path in _demo_ui_sources():
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            if "apps.agents.customer_resolution" in line and "import" in line:
                assert "trace" in line, f"{path.name}: unexpected dependency → {line.strip()}"
