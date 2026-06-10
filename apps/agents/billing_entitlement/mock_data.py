"""Seeded owned-fact dataset for the Billing and Entitlement Agent (FR-003).

Keyed by purchase_reference (primary) or customer_id (fallback).
A miss returns None → missing-data path in the rules engine.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from apps.agents.billing_entitlement.models import (
    BillingFacts,
    Entitlement,
    Invoice,
    Payment,
    ProductUsage,
    Subscription,
)
from apps.agents.billing_entitlement.policy import REFUND_WINDOW_DAYS

_NOW = datetime.now(UTC)


def _invoice(
    ref: str,
    *,
    days_ago: float,
    paid: bool = True,
    amount: float = 49.99,
    currency: str = "USD",
) -> Invoice:
    return Invoice(
        invoice_id=f"INV-{ref}",
        purchase_reference=ref,
        amount=amount,
        currency=currency,
        issued_at=_NOW - timedelta(days=days_ago),
        paid=paid,
    )


def _payment(
    ref: str, *, captured: bool = True, amount: float = 49.99, reversed_amount: float = 0.0
) -> Payment:
    return Payment(
        payment_id=f"PAY-{ref}",
        invoice_id=f"INV-{ref}",
        captured=captured,
        amount=amount,
        reversed_amount=reversed_amount,
    )


def _subscription(
    ref: str,
    *,
    status: str = "active",
    term: str = "monthly",
    days_started_ago: float = 90.0,
) -> Subscription:
    return Subscription(
        subscription_id=f"SUB-{ref}",
        status=status,  # type: ignore[arg-type]
        term=term,  # type: ignore[arg-type]
        started_at=_NOW - timedelta(days=days_started_ago),
    )


def _entitlement(
    ref: str,
    *,
    status: str = "active",
    delivered: bool = False,
    access_granted: bool = True,
    access_used: bool = False,
    feature_enabled: bool = True,
    account_active: bool = True,
) -> Entitlement:
    return Entitlement(
        entitlement_id=f"ENT-{ref}",
        subscription_id=f"SUB-{ref}",
        status=status,  # type: ignore[arg-type]
        delivered=delivered,
        access_granted=access_granted,
        access_used=access_used,
        feature_enabled=feature_enabled,
        account_active=account_active,
    )


def _usage(usage_units: float, allotment_units: float = 5.0) -> ProductUsage:
    return ProductUsage(usage_units=usage_units, allotment_units=allotment_units)


_DATASET: dict[str, BillingFacts] = {
    # approve: within window, paid, not delivered, light usage, active subscription
    "PR-APPROVE": BillingFacts(
        subscription=_subscription("PR-APPROVE"),
        invoice=_invoice("PR-APPROVE", days_ago=5),
        payment=_payment("PR-APPROVE"),
        entitlement=_entitlement("PR-APPROVE"),
        usage=_usage(0.5),
    ),
    # deny via RP-001: outside 30-day window
    "PR-WINDOW-EXPIRED": BillingFacts(
        subscription=_subscription("PR-WINDOW-EXPIRED"),
        invoice=_invoice("PR-WINDOW-EXPIRED", days_ago=45),
        payment=_payment("PR-WINDOW-EXPIRED"),
        entitlement=_entitlement("PR-WINDOW-EXPIRED"),
        usage=_usage(0.5),
    ),
    # deny via RP-002: invoice not paid
    "PR-UNPAID": BillingFacts(
        subscription=_subscription("PR-UNPAID"),
        invoice=_invoice("PR-UNPAID", days_ago=5, paid=False),
        payment=_payment("PR-UNPAID", captured=False),
        entitlement=_entitlement(
            "PR-UNPAID",
            access_granted=False,
            access_used=False,
            feature_enabled=False,
            account_active=True,
        ),
        usage=_usage(0.5),
    ),
    # deny via RP-002: payment already fully reversed
    "PR-ALREADY-REFUNDED": BillingFacts(
        subscription=_subscription("PR-ALREADY-REFUNDED", status="cancelled"),
        invoice=_invoice("PR-ALREADY-REFUNDED", days_ago=5),
        payment=_payment("PR-ALREADY-REFUNDED", reversed_amount=49.99),
        entitlement=_entitlement(
            "PR-ALREADY-REFUNDED",
            access_granted=False,
            access_used=False,
            feature_enabled=False,
            account_active=False,
        ),
        usage=_usage(0.5),
    ),
    # deny via RP-004: heavy usage (ratio=0.95)
    "PR-HEAVY-USAGE": BillingFacts(
        subscription=_subscription("PR-HEAVY-USAGE"),
        invoice=_invoice("PR-HEAVY-USAGE", days_ago=5),
        payment=_payment("PR-HEAVY-USAGE"),
        entitlement=_entitlement(
            "PR-HEAVY-USAGE",
            delivered=True,
            access_granted=True,
            access_used=True,
            feature_enabled=True,
            account_active=True,
        ),
        usage=_usage(4.75),
    ),
    # manual_review via contradiction gate:
    #   - payment.reversed_amount > 0 on a paid invoice (partial reversal already applied)
    #   - entitlement.status="active" on a cancelled subscription → account_active mismatch
    "PR-CONTRADICTION": BillingFacts(
        subscription=_subscription("PR-CONTRADICTION", status="cancelled"),
        invoice=_invoice("PR-CONTRADICTION", days_ago=5),
        payment=_payment("PR-CONTRADICTION", reversed_amount=10.00),
        entitlement=_entitlement(
            "PR-CONTRADICTION",
            status="active",
            delivered=True,
            access_granted=True,
            access_used=True,
            feature_enabled=True,
            account_active=True,  # contradiction: active on cancelled sub
        ),
        usage=_usage(0.5),
    ),
    # approve (borderline): exactly 30 days, usage_ratio=0.80 (exactly at threshold → below heavy)
    # confidence=0.6 due to borderline window
    "PR-BORDERLINE": BillingFacts(
        subscription=_subscription("PR-BORDERLINE"),
        invoice=_invoice("PR-BORDERLINE", days_ago=REFUND_WINDOW_DAYS),
        payment=_payment("PR-BORDERLINE"),
        entitlement=_entitlement("PR-BORDERLINE"),
        usage=_usage(4.0),  # 4.0/5.0 = 0.80 exactly
    ),
}

# Customer-id fallback index (for cases where purchase_reference is unknown)
_CUSTOMER_INDEX: dict[str, str] = {
    "CUS-APPROVE": "PR-APPROVE",
    "CUS-BORDERLINE": "PR-BORDERLINE",
}


def load_facts(purchase_reference: str, customer_id: str) -> BillingFacts | None:
    """Look up owned billing facts.

    Returns None if no record is found → caller takes the missing-data path.
    """
    if purchase_reference in _DATASET:
        return _DATASET[purchase_reference]
    ref = _CUSTOMER_INDEX.get(customer_id)
    if ref is not None:
        return _DATASET.get(ref)
    return None
