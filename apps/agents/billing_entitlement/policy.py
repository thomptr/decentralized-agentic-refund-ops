"""Named, citable refund policy (poc-refund-policy v1.0.0)."""

from __future__ import annotations

from dataclasses import dataclass, field

REFUND_WINDOW_DAYS: int = 30
USAGE_HEAVY_THRESHOLD: float = 0.8


@dataclass(frozen=True)
class PolicyRule:
    id: str
    name: str
    description: str


@dataclass(frozen=True)
class RefundPolicy:
    policy_name: str
    policy_version: str
    rules: list[PolicyRule] = field(default_factory=list)


_RULES: list[PolicyRule] = [
    PolicyRule(
        id="RP-001",
        name="refund-window",
        description=(
            f"Refund must be requested within {REFUND_WINDOW_DAYS} days of invoice issue date "
            f"(inclusive boundary: exactly {REFUND_WINDOW_DAYS} days counts as within)."
        ),
    ),
    PolicyRule(
        id="RP-002",
        name="paid-invoice",
        description=(
            "Invoice must be paid, payment must be captured, and the payment must not already "
            "be fully reversed (already-refunded cases are denied)."
        ),
    ),
    PolicyRule(
        id="RP-003",
        name="entitlement-delivered",
        description=(
            "Value not delivered/used supports the refund claim (approve-supporting); "
            "value delivered and used weakens the claim."
        ),
    ),
    PolicyRule(
        id="RP-004",
        name="usage-threshold",
        description=(
            f"Heavy usage (usage_ratio > {USAGE_HEAVY_THRESHOLD}) materially weakens the "
            f"refund claim and results in denial. Exactly {USAGE_HEAVY_THRESHOLD} is below heavy."
        ),
    ),
    PolicyRule(
        id="RP-005",
        name="subscription-status",
        description=(
            "Cancelled subscription within the refund window supports the claim; "
            "active subscription with heavy usage further weakens it."
        ),
    ),
]

REFUND_POLICY = RefundPolicy(
    policy_name="poc-refund-policy",
    policy_version="1.0.0",
    rules=_RULES,
)

__all__ = [
    "REFUND_WINDOW_DAYS",
    "USAGE_HEAVY_THRESHOLD",
    "PolicyRule",
    "RefundPolicy",
    "REFUND_POLICY",
]
