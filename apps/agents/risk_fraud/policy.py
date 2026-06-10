"""Named, citable fraud policy (poc-fraud-policy v1.0.0)."""

from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Threshold constants
# ---------------------------------------------------------------------------

ELEVATED_THRESHOLD: float = 0.5
HIGH_THRESHOLD: float = 0.8
CHARGEBACK_ELEVATED: int = 1
CHARGEBACK_HIGH: int = 2
VELOCITY_ELEVATED: int = 3
VELOCITY_HIGH: int = 5
ANOMALY_ELEVATED: float = 0.7
NEW_ACCOUNT_DAYS: int = 30
UNUSUAL_AMOUNT_RATIO: float = 3.0


# ---------------------------------------------------------------------------
# Policy data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PolicyRule:
    id: str
    name: str
    description: str


@dataclass(frozen=True)
class FraudPolicy:
    policy_name: str
    policy_version: str
    rules: list[PolicyRule] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Named rules FP-001 through FP-009
# ---------------------------------------------------------------------------

FP_001 = PolicyRule(
    id="FP-001",
    name="known-fraud-indicator",
    description=(
        "Hard floor: when KnownFraudIndicator.on_blocklist is True the risk level is "
        "unconditionally HIGH regardless of other signals. This overrides all other rules."
    ),
)

FP_002 = PolicyRule(
    id="FP-002",
    name="chargeback-history",
    description=(
        f"Chargeback history increases the fraud score: "
        f"chargebacks >= {CHARGEBACK_HIGH} adds +0.8 (high tier); "
        f"chargebacks >= {CHARGEBACK_ELEVATED} adds +0.5 (elevated tier). "
        f"Only the highest-matching tier applies."
    ),
)

FP_003 = PolicyRule(
    id="FP-003",
    name="refund-velocity",
    description=(
        f"Excessive refund requests within the velocity window increase the fraud score: "
        f"refund_requests_in_window >= {VELOCITY_HIGH} adds +0.7 (high tier); "
        f">= {VELOCITY_ELEVATED} adds +0.4 (elevated tier). "
        f"Only the highest-matching tier applies."
    ),
)

FP_004 = PolicyRule(
    id="FP-004",
    name="instrument-mismatch",
    description=(
        "Payment instrument anomalies increase the fraud score: "
        "card_testing_pattern == True adds +0.6; "
        "billing_details_match == False adds +0.4. "
        "Both can apply independently if both conditions are present."
    ),
)

FP_005 = PolicyRule(
    id="FP-005",
    name="account-standing",
    description=(
        f"Account standing affects the fraud score: "
        f"status == 'restricted' adds +0.6; "
        f"status == 'watch' adds +0.3; "
        f"tenure_days < {NEW_ACCOUNT_DAYS} (new account) adds +0.3 when status is 'good'; "
        f"long-tenured accounts (tenure_days >= {NEW_ACCOUNT_DAYS}) with status 'good' "
        f"contribute a baseline of 0.0 (no penalty)."
    ),
)

FP_006 = PolicyRule(
    id="FP-006",
    name="behavioral-anomaly",
    description=(
        f"Elevated anomaly score increases the fraud score: "
        f"anomaly_score >= {ANOMALY_ELEVATED} adds +0.4."
    ),
)

FP_007 = PolicyRule(
    id="FP-007",
    name="device-mismatch",
    description=(
        "Device fingerprint mismatch increases the fraud score: "
        "behavioral.device_mismatch == True adds +0.4."
    ),
)

FP_008 = PolicyRule(
    id="FP-008",
    name="ip-location-mismatch",
    description=(
        "IP/location mismatch increases the fraud score: "
        "behavioral.ip_location_mismatch == True or behavioral.ip_country_mismatch == True "
        "adds +0.4. Both flags are evaluated with OR logic; only one +0.4 is applied even if "
        "both are True."
    ),
)

FP_009 = PolicyRule(
    id="FP-009",
    name="unusual-refund-amount",
    description=(
        f"Unusually large refund request relative to the customer's typical amount increases "
        f"the fraud score: "
        f"requested_refund_amount >= typical_refund_amount * {UNUSUAL_AMOUNT_RATIO} adds +0.3. "
        f"Rule does not fire when typical_refund_amount is None or zero."
    ),
)

# ---------------------------------------------------------------------------
# Policy singleton
# ---------------------------------------------------------------------------

_RULES: list[PolicyRule] = [
    FP_001,
    FP_002,
    FP_003,
    FP_004,
    FP_005,
    FP_006,
    FP_007,
    FP_008,
    FP_009,
]

FRAUD_POLICY = FraudPolicy(
    policy_name="poc-fraud-policy",
    policy_version="1.0.0",
    rules=_RULES,
)


__all__ = [
    "ELEVATED_THRESHOLD",
    "HIGH_THRESHOLD",
    "CHARGEBACK_ELEVATED",
    "CHARGEBACK_HIGH",
    "VELOCITY_ELEVATED",
    "VELOCITY_HIGH",
    "ANOMALY_ELEVATED",
    "NEW_ACCOUNT_DAYS",
    "UNUSUAL_AMOUNT_RATIO",
    "PolicyRule",
    "FraudPolicy",
    "FP_001",
    "FP_002",
    "FP_003",
    "FP_004",
    "FP_005",
    "FP_006",
    "FP_007",
    "FP_008",
    "FP_009",
    "FRAUD_POLICY",
]
