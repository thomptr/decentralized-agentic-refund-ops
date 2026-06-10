"""Seeded owned risk/fraud signal dataset (T011, T112).

This module owns the deterministic, in-process signal dataset for the Risk and Fraud Agent PoC.
All data is a pure literal: no datetime.now(), no random(), no uuid() calls (FR-012 determinism).
Day counts are plain integers.

The dataset is keyed by customer_id (case-sensitive). An unknown customer_id returns None,
which the service maps to the missing-data path (requires_human_review=True, conf 0.2, FR-010).

Store seam: callers use default_store() -> RiskSignalStore to obtain the injectable store
(InMemoryRiskSignalStore backed by _DATASET). A PostgresRiskSignalStore or DynamoDbRiskSignalStore
can replace the in-memory store by implementing the same RiskSignalStore Protocol (store.py T111).

Expected verdict notes are derived from contracts/fraud-policy.md + contracts/mock-risk-data.md.
The scoring engine (scoring.py T015) is the authoritative verdict source; these comments
document the *intent* from the contract. Where the written FP-00x contribution values and
HIGH/ELEVATED thresholds produce a borderline result, the borderline rule (score exactly on a
threshold -> upper band, conf 0.6) governs.

Score reference (additive, capped at 1.0):
  FP-001: blocklist -> hard floor HIGH (conf 0.95)
  FP-002: chargebacks >= 2 -> +0.8; >= 1 -> +0.5
  FP-003: refund_requests_in_window >= 5 -> +0.7; >= 3 -> +0.4
  FP-004: card_testing_pattern=True -> +0.6; billing_details_match=False -> +0.4
  FP-005: status="restricted" -> +0.6; status="watch" OR tenure_days<30 -> +0.3
  FP-006: anomaly_score >= 0.7 -> +0.4
  FP-007: device_mismatch=True -> +0.4  [Phase 16 behavioral analyzer]
  FP-008: ip_location_mismatch=True OR ip_country_mismatch=True -> +0.4  [Phase 16]
  FP-009: requested_refund_amount >= typical_refund_amount * 3.0 -> +0.3  [Phase 16]
  ELEVATED_THRESHOLD=0.5, HIGH_THRESHOLD=0.8
"""

from __future__ import annotations

from apps.agents.risk_fraud.models import (
    AccountStanding,
    BehavioralSignal,
    KnownFraudIndicator,
    PaymentInstrumentSignal,
    RefundDisputeHistory,
    RiskSignals,
)
from apps.agents.risk_fraud.store import InMemoryRiskSignalStore, RiskSignalStore


def _clean_signals(customer_id: str, **overrides: object) -> RiskSignals:
    """Baseline-plus-single-field-override helper.

    The clean baseline represents a long-tenured good-standing customer with no risk signals:
      - AccountStanding: status="good", tenure_days=365, support_abuse_flags=0,
                          known_good_customer=True, segment="standard"
      - RefundDisputeHistory: prior_refunds=1, prior_refund_total_amount=25.0,
                               chargebacks=0, velocity_window_days=30
      - PaymentInstrumentSignal: billing_details_match=True, card_testing_pattern=False,
                                  recent_failed_payments=0
      - BehavioralSignal: refund_requests_in_window=0, anomaly_score=0.0,
                           device_mismatch=False, ip_location_mismatch=False,
                           ip_country_mismatch=False, device_change_count=0,
                           typical_refund_amount=25.0
      - KnownFraudIndicator: on_blocklist=False

    Override any sub-model field by passing the sub-model key as a kwarg, e.g.:
        _clean_signals("CUS-X", chargebacks=2)   # overrides RefundDisputeHistory.chargebacks
    """
    standing_fields: dict[str, object] = {
        "status": "good",
        "tenure_days": 365,
        "support_abuse_flags": 0,
        "known_good_customer": True,
        "segment": "standard",
    }
    history_fields: dict[str, object] = {
        "prior_refunds": 1,
        "prior_refund_total_amount": 25.0,
        "chargebacks": 0,
        "velocity_window_days": 30,
    }
    instrument_fields: dict[str, object] = {
        "billing_details_match": True,
        "card_testing_pattern": False,
        "recent_failed_payments": 0,
    }
    behavioral_fields: dict[str, object] = {
        "refund_requests_in_window": 0,
        "anomaly_score": 0.0,
        "device_mismatch": False,
        "ip_location_mismatch": False,
        "ip_country_mismatch": False,
        "device_change_count": 0,
        "typical_refund_amount": 25.0,
    }
    fraud_fields: dict[str, object] = {
        "on_blocklist": False,
    }

    # Apply overrides to the appropriate sub-model bucket
    for key, value in overrides.items():
        if key in standing_fields:
            standing_fields[key] = value
        elif key in history_fields:
            history_fields[key] = value
        elif key in instrument_fields:
            instrument_fields[key] = value
        elif key in behavioral_fields:
            behavioral_fields[key] = value
        elif key in fraud_fields:
            fraud_fields[key] = value
        else:
            raise ValueError(
                f"_clean_signals: unknown override key {key!r}. "
                f"Must be a field on one of the five owned-signal models."
            )

    return RiskSignals(
        customer_id=customer_id,
        account_standing=AccountStanding(customer_id=customer_id, **standing_fields),  # type: ignore[arg-type]
        refund_history=RefundDisputeHistory(customer_id=customer_id, **history_fields),  # type: ignore[arg-type]
        payment_instrument=PaymentInstrumentSignal(customer_id=customer_id, **instrument_fields),  # type: ignore[arg-type]
        behavioral=BehavioralSignal(customer_id=customer_id, **behavioral_fields),  # type: ignore[arg-type]
        known_fraud=KnownFraudIndicator(customer_id=customer_id, **fraud_fields),  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# Deterministic seed dataset (no datetime.now, no random, no uuid) — T112
# ---------------------------------------------------------------------------

_DATASET: dict[str, RiskSignals] = {
    # ------------------------------------------------------------------
    # CUS-CLEAN: long-tenured good-standing customer, all signals clean.
    # FP-002..FP-006 all silent. Expected: low (conf 0.9).
    # ------------------------------------------------------------------
    "CUS-CLEAN": _clean_signals("CUS-CLEAN"),
    # ------------------------------------------------------------------
    # CUS-CHARGEBACKS: 2 prior chargebacks.
    # FP-002 fires at CHARGEBACK_HIGH tier (+0.8). Score = 0.8 -> borderline HIGH
    # (score exactly on HIGH_THRESHOLD -> upper band, conf 0.6). Expected: high (FP-002).
    # ------------------------------------------------------------------
    "CUS-CHARGEBACKS": _clean_signals("CUS-CHARGEBACKS", chargebacks=2),
    # ------------------------------------------------------------------
    # CUS-ONE-CHARGEBACK: 1 prior chargeback.
    # FP-002 fires at CHARGEBACK_ELEVATED tier (+0.5). Score = 0.5 -> borderline ELEVATED
    # (score exactly on ELEVATED_THRESHOLD -> upper band, conf 0.6). Expected: elevated (FP-002).
    # ------------------------------------------------------------------
    "CUS-ONE-CHARGEBACK": _clean_signals("CUS-ONE-CHARGEBACK", chargebacks=1),
    # ------------------------------------------------------------------
    # CUS-VELOCITY: 5 refund requests in the 30-day window.
    # FP-003 fires at VELOCITY_HIGH tier (+0.7). Score = 0.7 -> elevated (conf 0.9).
    # Note: contracts/mock-risk-data.md documents this as "high (FP-003)". The scoring engine
    # (scoring.py T015) is authoritative; it may combine velocity with a secondary signal or
    # adjust the contribution to reach HIGH_THRESHOLD. The seed is exactly as contracted.
    # ------------------------------------------------------------------
    "CUS-VELOCITY": _clean_signals("CUS-VELOCITY", refund_requests_in_window=5),
    # ------------------------------------------------------------------
    # CUS-INSTRUMENT: billing details mismatch.
    # FP-004 mismatch fires (+0.4). Score = 0.4 < ELEVATED_THRESHOLD=0.5 -> low by raw score.
    # contracts/mock-risk-data.md documents expected verdict as "elevated (FP-004)".
    # The scoring engine (T015) is authoritative; FP-004 may also apply card_testing logic.
    # Seed is as contracted: billing_details_match=False, otherwise clean.
    # ------------------------------------------------------------------
    "CUS-INSTRUMENT": _clean_signals("CUS-INSTRUMENT", billing_details_match=False),
    # ------------------------------------------------------------------
    # CUS-CARD-TESTING: card testing pattern detected.
    # FP-004 card-testing fires (+0.6). Score = 0.6 >= ELEVATED_THRESHOLD=0.5, < HIGH=0.8.
    # Expected: elevated (FP-004, conf 0.9).
    # ------------------------------------------------------------------
    "CUS-CARD-TESTING": _clean_signals("CUS-CARD-TESTING", card_testing_pattern=True),
    # ------------------------------------------------------------------
    # CUS-NEW-ACCOUNT: new account (tenure=5 days) with watch status.
    # FP-005 fires: status="watch" (+0.3) AND tenure_days < NEW_ACCOUNT_DAYS (+0.3).
    # Score = 0.3 (only highest-matching standing rule applies per policy) or additive = 0.6
    # (scoring engine decides; status="watch" is the primary FP-005 signal here).
    # tenure_days=5 AND status="watch" -> FP-005 elevated. Expected: elevated (FP-005).
    # ------------------------------------------------------------------
    "CUS-NEW-ACCOUNT": _clean_signals(
        "CUS-NEW-ACCOUNT",
        tenure_days=5,
        status="watch",
        known_good_customer=False,
    ),
    # ------------------------------------------------------------------
    # CUS-ANOMALY: high behavioral anomaly score.
    # FP-006 fires: anomaly_score=0.85 >= ANOMALY_ELEVATED=0.7 (+0.4). Score = 0.4.
    # Score 0.4 < ELEVATED_THRESHOLD=0.5 -> low by raw thresholds.
    # contracts/mock-risk-data.md documents expected verdict as "elevated (FP-006)".
    # The scoring engine (T015) is authoritative.
    # ------------------------------------------------------------------
    "CUS-ANOMALY": _clean_signals("CUS-ANOMALY", anomaly_score=0.85),
    # ------------------------------------------------------------------
    # CUS-BLOCKLIST: on the known-fraud blocklist.
    # FP-001 hard floor fires unconditionally. Score bypassed.
    # Expected: high (FP-001 floor, conf 0.95). Stop evaluation.
    # ------------------------------------------------------------------
    "CUS-BLOCKLIST": _clean_signals("CUS-BLOCKLIST", on_blocklist=True),
    # ------------------------------------------------------------------
    # CUS-CONTRADICTION: contradictory signal set (contradiction gate, T015/fraud-policy.md §3).
    # Strongly-LOW signals: long tenure (365 days), good standing, 0 chargebacks, known_good.
    # Strongly-HIGH signals: velocity=5 (VELOCITY_HIGH tier) on a mismatched instrument.
    # Contradiction gate: long tenure + good standing + zero chargebacks coexist with
    # velocity >= VELOCITY_HIGH on billing_details_match=False.
    # Expected: elevated + requires_human_review=True (conf 0.3).
    # ------------------------------------------------------------------
    "CUS-CONTRADICTION": _clean_signals(
        "CUS-CONTRADICTION",
        refund_requests_in_window=5,
        billing_details_match=False,
    ),
    # ------------------------------------------------------------------
    # CUS-BORDERLINE: signals summing to score exactly 0.5 (borderline elevated).
    # chargebacks=1 -> FP-002 +0.5. Score = 0.5 exactly on ELEVATED_THRESHOLD -> upper band.
    # Expected: elevated (conf 0.6, borderline rule).
    # (Equivalent to CUS-ONE-CHARGEBACK but seeded as a named boundary test case.)
    # ------------------------------------------------------------------
    "CUS-BORDERLINE": _clean_signals("CUS-BORDERLINE", chargebacks=1),
    # ------------------------------------------------------------------
    # Phase 17 scenario: CUS-NEW-HIGH-REFUND (new account, high refund amount).
    # FP-005: tenure_days=5 < NEW_ACCOUNT_DAYS=30 (+0.3, new-account). Score >= 0.3.
    # prior_refund_total_amount=850.0 is context for the engine; FP-009 fires when the
    # *requested* amount (from the A2A request) >= typical_refund_amount * UNUSUAL_AMOUNT_RATIO.
    # typical_refund_amount=50.0 means FP-009 fires if requested_refund_amount >= 150.0 (+0.3).
    # Expected: elevated (FP-005 + potential FP-009 depending on requested amount).
    # ------------------------------------------------------------------
    "CUS-NEW-HIGH-REFUND": _clean_signals(
        "CUS-NEW-HIGH-REFUND",
        tenure_days=5,
        status="good",
        known_good_customer=False,
        prior_refunds=3,
        prior_refund_total_amount=850.0,
        typical_refund_amount=50.0,
    ),
    # ------------------------------------------------------------------
    # Phase 17 scenario: CUS-IP-DEVICE (IP/country mismatch + device change count).
    # FP-008: ip_country_mismatch=True (+0.4). device_change_count=3 is context.
    # Score = 0.4 < ELEVATED_THRESHOLD=0.5 by raw thresholds.
    # Seeded per contracts/mock-risk-data.md request for "IP/device mismatch" scenario.
    # FP-007 fires additionally if device_mismatch=True. Total could reach elevated.
    # ------------------------------------------------------------------
    "CUS-IP-DEVICE": _clean_signals(
        "CUS-IP-DEVICE",
        ip_country_mismatch=True,
        device_change_count=3,
    ),
    # ------------------------------------------------------------------
    # Phase 17 scenario: CUS-VIP-ENTERPRISE (enterprise segment -> manual review).
    # Segment "enterprise" triggers the VIP/enterprise human-review path in scoring.py (T025).
    # All other signals are clean; the scoring engine routes enterprise accounts to
    # requires_human_review=True with recommended_action=manual_review (FP-005 standing tier).
    # Expected: (computed level) + requires_human_review=True.
    # ------------------------------------------------------------------
    "CUS-VIP-ENTERPRISE": _clean_signals("CUS-VIP-ENTERPRISE", segment="enterprise"),
    # ------------------------------------------------------------------
    # Phase 16 scenario: CUS-DEVICE (device mismatch signal).
    # FP-007: device_mismatch=True (+0.4). Expected: elevated (FP-007) once Phase 16 lands.
    # ------------------------------------------------------------------
    "CUS-DEVICE": _clean_signals("CUS-DEVICE", device_mismatch=True),
    # ------------------------------------------------------------------
    # Phase 16 scenario: CUS-GEO (IP/location mismatch).
    # FP-008: ip_location_mismatch=True (+0.4). Expected: elevated (FP-008) once Phase 16 lands.
    # ------------------------------------------------------------------
    "CUS-GEO": _clean_signals("CUS-GEO", ip_location_mismatch=True),
    # ------------------------------------------------------------------
    # Phase 16 scenario: CUS-UNUSUAL-AMOUNT (low typical amount, high request expected).
    # FP-009: fires when requested_refund_amount >= typical_refund_amount * UNUSUAL_AMOUNT_RATIO.
    # typical_refund_amount=20.0 means FP-009 fires if requested_refund_amount >= 60.0 (+0.3).
    # Score contribution depends on the A2A request's requested_refund_amount; seed is context.
    # Expected: elevated (FP-009) for sufficiently large requests, once Phase 16 lands.
    # ------------------------------------------------------------------
    "CUS-UNUSUAL-AMOUNT": _clean_signals("CUS-UNUSUAL-AMOUNT", typical_refund_amount=20.0),
    # ------------------------------------------------------------------
    # Phase 16 scenario: CUS-MISSING-HISTORY (refund_history absent, partial signals).
    # refund_history=None while other signal domains are present -> lowered confidence path (T108).
    # Expected: normal level derived from remaining signals + lowered confidence (conf ~0.6).
    # ------------------------------------------------------------------
    "CUS-MISSING-HISTORY": RiskSignals(
        customer_id="CUS-MISSING-HISTORY",
        account_standing=AccountStanding(
            customer_id="CUS-MISSING-HISTORY",
            status="good",
            tenure_days=180,
            support_abuse_flags=0,
            known_good_customer=False,
            segment="standard",
        ),
        refund_history=None,  # deliberately absent -> missing-history confidence rule (T108)
        payment_instrument=PaymentInstrumentSignal(
            customer_id="CUS-MISSING-HISTORY",
            billing_details_match=True,
            card_testing_pattern=False,
            recent_failed_payments=0,
        ),
        behavioral=BehavioralSignal(
            customer_id="CUS-MISSING-HISTORY",
            refund_requests_in_window=0,
            anomaly_score=0.0,
            device_mismatch=False,
            ip_location_mismatch=False,
            ip_country_mismatch=False,
            device_change_count=0,
            typical_refund_amount=30.0,
        ),
        known_fraud=KnownFraudIndicator(
            customer_id="CUS-MISSING-HISTORY",
            on_blocklist=False,
        ),
    ),
}


# ---------------------------------------------------------------------------
# Store injection seam (T111 / T112)
# ---------------------------------------------------------------------------


def default_store() -> RiskSignalStore:
    """Return the default InMemoryRiskSignalStore backed by the seeded _DATASET.

    Inject a PostgresRiskSignalStore or DynamoDbRiskSignalStore here to swap the backing store
    without changing any caller: all callers depend on the RiskSignalStore Protocol (store.py).
    """
    return InMemoryRiskSignalStore(_DATASET)


def load_signals(customer_id: str) -> RiskSignals | None:
    """Convenience wrapper: look up owned risk signals for customer_id.

    Returns the seeded RiskSignals for known customers, or None for an unknown customer_id
    (triggering the missing-data / requires_human_review path in the scoring engine, FR-010).

    This function is the lookup contract defined in contracts/mock-risk-data.md.
    """
    return default_store().load_signals(customer_id)


__all__ = [
    "RiskSignals",
    "default_store",
    "load_signals",
]
