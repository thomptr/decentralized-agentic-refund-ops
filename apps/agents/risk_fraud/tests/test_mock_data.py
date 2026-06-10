"""Tests for mock signal data store (T012, T114, T115, T116, T117)."""

from __future__ import annotations

import pytest

from apps.agents.risk_fraud.mock_data import load_signals
from apps.agents.risk_fraud.models import RiskSignals

# ---------------------------------------------------------------------------
# T012: load_signals returns seeded signals for known customers, None for unknown
# ---------------------------------------------------------------------------


def test_load_signals_known_customer_returns_signals():
    signals = load_signals("CUS-CLEAN")
    assert signals is not None
    assert isinstance(signals, RiskSignals)
    assert signals.customer_id == "CUS-CLEAN"


def test_load_signals_unknown_customer_returns_none():
    result = load_signals("CUS-DOES-NOT-EXIST-XYZ")
    assert result is None


def test_load_signals_case_sensitive():
    result = load_signals("cus-clean")  # wrong case
    assert result is None


# ---------------------------------------------------------------------------
# T114: Table-driven coverage of seeded scenarios
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "customer_id",
    [
        "CUS-CLEAN",
        "CUS-CHARGEBACKS",
        "CUS-ONE-CHARGEBACK",
        "CUS-VELOCITY",
        "CUS-INSTRUMENT",
        "CUS-CARD-TESTING",
        "CUS-NEW-ACCOUNT",
        "CUS-ANOMALY",
        "CUS-BLOCKLIST",
        "CUS-CONTRADICTION",
        "CUS-BORDERLINE",
    ],
)
def test_seeded_customer_has_signals(customer_id: str):
    signals = load_signals(customer_id)
    assert signals is not None
    assert signals.customer_id == customer_id


def test_cus_clean_known_good_low_history(risk_store):
    signals = risk_store.load_signals("CUS-CLEAN")
    assert signals is not None
    as_ = signals.account_standing
    rh = signals.refund_history
    assert as_ is not None
    assert as_.known_good_customer is True
    assert as_.status == "good"
    assert as_.tenure_days >= 30
    assert rh is not None
    assert rh.chargebacks == 0


def test_cus_chargebacks_has_two_chargebacks(risk_store):
    signals = risk_store.load_signals("CUS-CHARGEBACKS")
    assert signals is not None
    assert signals.refund_history is not None
    assert signals.refund_history.chargebacks == 2


def test_cus_one_chargeback_has_one_chargeback(risk_store):
    signals = risk_store.load_signals("CUS-ONE-CHARGEBACK")
    assert signals is not None
    assert signals.refund_history is not None
    assert signals.refund_history.chargebacks == 1


def test_cus_velocity_high_refund_requests(risk_store):
    signals = risk_store.load_signals("CUS-VELOCITY")
    assert signals is not None
    assert signals.behavioral is not None
    assert signals.behavioral.refund_requests_in_window == 5


def test_cus_instrument_billing_mismatch(risk_store):
    signals = risk_store.load_signals("CUS-INSTRUMENT")
    assert signals is not None
    assert signals.payment_instrument is not None
    assert signals.payment_instrument.billing_details_match is False


def test_cus_blocklist_on_blocklist(risk_store):
    signals = risk_store.load_signals("CUS-BLOCKLIST")
    assert signals is not None
    assert signals.known_fraud is not None
    assert signals.known_fraud.on_blocklist is True


def test_cus_new_account_low_tenure(risk_store):
    signals = risk_store.load_signals("CUS-NEW-ACCOUNT")
    assert signals is not None
    assert signals.account_standing is not None
    assert signals.account_standing.tenure_days < 30


# ---------------------------------------------------------------------------
# T115: Isolation — only risk/fraud-domain fields
# ---------------------------------------------------------------------------


def test_risk_signals_no_billing_fields():
    """RiskSignals exposes only risk/fraud-domain fields (SC-003/FR-009)."""
    signals = load_signals("CUS-CLEAN")
    assert signals is not None
    # Verify no billing-eligibility or customer-resolution fields
    forbidden_fields = [
        "subscription",
        "invoice",
        "payment",
        "entitlement",
        "usage",
        "billing_account_id",
        "subscription_status",
        "refund_window_status",
        "eligible_refund_amount",
    ]
    for field in forbidden_fields:
        assert not hasattr(signals, field), f"RiskSignals should not have field {field!r}"


def test_account_standing_no_billing_fields():
    signals = load_signals("CUS-CLEAN")
    assert signals is not None and signals.account_standing is not None
    forbidden = ["subscription_id", "invoice_id", "payment_id", "entitlement_id"]
    for field in forbidden:
        assert not hasattr(signals.account_standing, field)


# ---------------------------------------------------------------------------
# T116: Missing profile and VIP/enterprise paths
# ---------------------------------------------------------------------------


def test_load_signals_cus_unknown_returns_none():
    assert load_signals("CUS-UNKNOWN") is None


def test_cus_vip_enterprise_segment(risk_store):
    signals = risk_store.load_signals("CUS-VIP-ENTERPRISE")
    assert signals is not None
    assert signals.account_standing is not None
    assert signals.account_standing.segment == "enterprise"


def test_cus_missing_history_refund_history_none(risk_store):
    signals = risk_store.load_signals("CUS-MISSING-HISTORY")
    assert signals is not None
    assert signals.refund_history is None


# ---------------------------------------------------------------------------
# T117: Determinism + immutability
# ---------------------------------------------------------------------------


def test_load_signals_deterministic():
    result1 = load_signals("CUS-CLEAN")
    result2 = load_signals("CUS-CLEAN")
    assert result1 == result2


def test_risk_signals_frozen():
    signals = load_signals("CUS-CLEAN")
    assert signals is not None
    with pytest.raises((ValueError, TypeError, Exception)):  # noqa: B017  # pydantic frozen model raises ValidationError on direct assignment
        signals.customer_id = "MUTATED"  # type: ignore[misc]


def test_account_standing_frozen():
    signals = load_signals("CUS-CLEAN")
    assert signals is not None and signals.account_standing is not None
    with pytest.raises((ValueError, TypeError, Exception)):  # noqa: B017
        signals.account_standing.status = "restricted"  # type: ignore[misc]


def test_mock_data_no_datetime_or_random(tmp_path):
    """Static source assertion: mock_data.py must not import datetime.now or random."""
    import ast
    from pathlib import Path

    source_path = Path(__file__).parent.parent / "mock_data.py"
    source = source_path.read_text()
    tree = ast.parse(source)

    # Check for datetime.now() calls
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "now":
                pytest.fail("mock_data.py uses datetime.now() — breaks determinism (FR-012)")

    # Check for random module import
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [alias.name for alias in node.names]
            assert "random" not in names, "mock_data.py must not import random"
