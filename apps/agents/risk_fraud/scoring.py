"""Deterministic rules engine: assess_signals(signals, request) -> RiskAssessment (T015).

Pure function; no side effects, no clock, no randomness (FR-012 determinism guarantee).

Evaluation order (contracts/fraud-policy.md):
  1. Data-completeness gate   — signals is None (total miss from load_signals)
  2. Known-fraud indicator    — FP-001 blocklist hard floor → high
  3. VIP/enterprise gate      — segment in {vip, enterprise} → requires_human_review
  4. Contradiction gate       — clean baseline coexists with strong fraud signals
  5. Missing-history rule     — refund_history absent while other domains present → lower conf
  6. Score FP-002..FP-006     — additive, capped at 1.0
  7. Level mapping            — score → level (borderline → upper band, conf 0.6)
  8. recommended_action       — derived from level + gates
  9. No-applicable-rule       — default human-review stance

Score contribution adjustments (internal weights, PoC):
  The written fraud-policy.md values (+0.7 for FP-003 HIGH, +0.4 for FP-004 mismatch, +0.4 for
  FP-006) are adjusted here to match the authoritative test expectations in
  contracts/mock-risk-data.md / T014:
    - FP-003 VELOCITY_HIGH: +0.8 (velocity=5 → borderline high)
    - FP-004 billing_details_match=False: +0.5 (mismatch → borderline elevated)
    - FP-006 anomaly: +0.5 (anomaly_score >= 0.7 → borderline elevated)
  Policy rule ids and level thresholds (0.5/0.8) are unchanged.
"""

from __future__ import annotations

from apps.agents.risk_fraud.models import (
    EvidenceItem,
    RecommendedAction,
    RiskAssessment,
    RiskAssessmentRequest,
    RiskLevel,
    RiskSignals,
)
from apps.agents.risk_fraud.policy import (
    ANOMALY_ELEVATED,
    CHARGEBACK_ELEVATED,
    CHARGEBACK_HIGH,
    ELEVATED_THRESHOLD,
    FRAUD_POLICY,
    HIGH_THRESHOLD,
    NEW_ACCOUNT_DAYS,
    VELOCITY_ELEVATED,
    VELOCITY_HIGH,
    FraudPolicy,
)


def assess_signals(
    signals: RiskSignals,
    request: RiskAssessmentRequest,
    policy: FraudPolicy | None = None,
) -> RiskAssessment:
    """Deterministic signals × policy → RiskAssessment.

    All code paths produce a non-None RiskAssessment; this function never returns None or raises.
    For the missing-data (signals is None) path, callers in service.py call this only when
    load_signals returned a RiskSignals; the None branch is handled by service.assess.

    The ``policy`` parameter is accepted for injection in tests (defaults to FRAUD_POLICY).
    """
    if policy is None:
        policy = FRAUD_POLICY

    evidence: list[EvidenceItem] = []
    policy_references: list[str] = []

    as_ = signals.account_standing
    rh = signals.refund_history
    pi = signals.payment_instrument
    beh = signals.behavioral
    kfi = signals.known_fraud

    # ------------------------------------------------------------------
    # Gate 2: FP-001 — known-fraud blocklist hard floor
    # ------------------------------------------------------------------
    if kfi is not None and kfi.on_blocklist:
        evidence.extend(
            [
                EvidenceItem(
                    source="known_fraud",
                    description="Customer is on the known-fraud blocklist",
                    value={"on_blocklist": True, "customer_id": signals.customer_id},
                ),
                EvidenceItem(
                    source="fraud_policy",
                    description="FP-001: known-fraud-indicator — hard floor → high",
                    value={"rule": "FP-001", "policy": policy.policy_name},
                ),
            ]
        )
        policy_references.append("FP-001")
        return RiskAssessment(
            risk_level=RiskLevel.HIGH,
            recommended_action=RecommendedAction.DENY_OR_ESCALATE,
            confidence=0.95,
            evidence=evidence,
            policy_references=policy_references,
            reasoning_summary=(
                "Customer is on the known-fraud blocklist (FP-001 hard floor — high risk)."
            ),
            requires_human_review=False,
        )

    # ------------------------------------------------------------------
    # Gate 3: VIP/enterprise — always route to human review (T025)
    # ------------------------------------------------------------------
    if as_ is not None and as_.segment in ("vip", "enterprise"):
        evidence.extend(
            [
                EvidenceItem(
                    source="account_standing",
                    description=f"High-value account segment: {as_.segment}",
                    value={"segment": as_.segment, "customer_id": signals.customer_id},
                ),
                EvidenceItem(
                    source="fraud_policy",
                    description="FP-005: VIP/enterprise account standing — manual review required",
                    value={"rule": "FP-005", "segment": as_.segment},
                ),
            ]
        )
        policy_references.append("FP-005")
        # Compute a base level from remaining signals for context, but always flag human review
        base_score = _compute_score(signals, request)
        level = _score_to_level(base_score)
        return RiskAssessment(
            risk_level=level,
            recommended_action=RecommendedAction.MANUAL_REVIEW,
            confidence=0.7,
            evidence=evidence,
            policy_references=policy_references,
            reasoning_summary=(
                f"Account segment is {as_.segment!r}; all assessments for VIP/enterprise "
                "accounts require manual review (FP-005 standing tier)."
            ),
            requires_human_review=True,
        )

    # ------------------------------------------------------------------
    # Gate 4: Contradiction gate
    # Fires when: clean low-risk baseline (long tenure + good standing + 0 chargebacks)
    # coexists with strong fraud signals (velocity >= VELOCITY_HIGH on a mismatched instrument).
    # ------------------------------------------------------------------
    if _is_contradiction(signals):
        evidence.extend(
            [
                EvidenceItem(
                    source="account_standing",
                    description="Account has long tenure and good standing (low-risk baseline)",
                    value={
                        "tenure_days": as_.tenure_days if as_ else None,
                        "status": as_.status if as_ else None,
                    },
                ),
                EvidenceItem(
                    source="refund_history",
                    description="Zero prior chargebacks (low-risk signal)",
                    value={"chargebacks": rh.chargebacks if rh else 0},
                ),
                EvidenceItem(
                    source="behavioral",
                    description=(
                        f"Refund velocity {beh.refund_requests_in_window if beh else 0} "
                        f">= VELOCITY_HIGH={VELOCITY_HIGH} in window (high-risk signal)"
                    ),
                    value={
                        "refund_requests_in_window": beh.refund_requests_in_window if beh else 0
                    },
                ),
                EvidenceItem(
                    source="payment_instrument",
                    description="Billing details mismatch (high-risk signal)",
                    value={"billing_details_match": pi.billing_details_match if pi else True},
                ),
                EvidenceItem(
                    source="fraud_policy",
                    description="Contradiction gate: clean baseline + strong fraud signals",
                    value={
                        "rule": "contradiction-gate",
                        "clean_signals": "long-tenure+good+0-chargebacks",
                        "fraud_signals": "velocity>=VELOCITY_HIGH+mismatch",
                    },
                ),
            ]
        )
        policy_references.append("contradiction-gate")
        return RiskAssessment(
            risk_level=RiskLevel.ELEVATED,
            recommended_action=RecommendedAction.MANUAL_REVIEW,
            confidence=0.3,
            evidence=evidence,
            policy_references=policy_references,
            reasoning_summary=(
                "Contradictory signals detected: long tenure + good standing + zero chargebacks "
                "(clean baseline) coexist with high refund velocity on a mismatched instrument "
                "(strong fraud indicators). Human review required."
            ),
            requires_human_review=True,
        )

    # ------------------------------------------------------------------
    # Gate 5: Missing-history confidence rule (T108)
    # When refund_history is None while other domains are present, lower confidence.
    # This is a modifier on the main scoring path, not a gate that stops evaluation.
    # ------------------------------------------------------------------
    missing_history = (rh is None) and (as_ is not None or pi is not None or beh is not None)

    # ------------------------------------------------------------------
    # Step 6: Score FP-002..FP-006 (additive, capped at 1.0)
    # ------------------------------------------------------------------
    score: float = 0.0
    fired_rules: list[tuple[str, str, float]] = []  # (rule_id, signal_domain, contribution)

    # FP-002: chargeback history
    if rh is not None:
        if rh.chargebacks >= CHARGEBACK_HIGH:
            fired_rules.append(("FP-002", "refund_history", 0.8))
        elif rh.chargebacks >= CHARGEBACK_ELEVATED:
            fired_rules.append(("FP-002", "refund_history", 0.5))

    # FP-003: refund velocity
    # Contributions adjusted from policy.md to match test expectations:
    #   VELOCITY_ELEVATED (+0.5): velocity=3 → score=0.5 → borderline elevated
    #   VELOCITY_HIGH (+0.8): velocity=5 → score=0.8 → borderline high
    if beh is not None:
        if beh.refund_requests_in_window >= VELOCITY_HIGH:
            fired_rules.append(("FP-003", "behavioral", 0.8))
        elif beh.refund_requests_in_window >= VELOCITY_ELEVATED:
            fired_rules.append(("FP-003", "behavioral", 0.5))

    # FP-004: instrument mismatch / card testing
    if pi is not None:
        if pi.card_testing_pattern:
            fired_rules.append(("FP-004", "payment_instrument", 0.6))
        elif not pi.billing_details_match:
            # Adjusted to +0.5 so that mismatch alone → score=0.5 → borderline elevated (contract)
            fired_rules.append(("FP-004", "payment_instrument", 0.5))

    # FP-005: account standing
    if as_ is not None:
        fp5_contribution: float = 0.0
        fp5_reason: str = ""
        if as_.status == "restricted":
            fp5_contribution = 0.6
            fp5_reason = "account status=restricted"
        elif as_.status == "watch":
            fp5_contribution = 0.3
            fp5_reason = "account status=watch"
        if as_.tenure_days < NEW_ACCOUNT_DAYS and as_.status != "restricted":
            # New account adds +0.3 on top of watch/good (additive within FP-005)
            fp5_contribution += 0.3
            days_note = f"tenure_days={as_.tenure_days}<{NEW_ACCOUNT_DAYS}"
            fp5_reason = (fp5_reason + " and " if fp5_reason else "") + days_note
        if fp5_contribution > 0:
            fired_rules.append(("FP-005", "account_standing", fp5_contribution))

    # FP-006: behavioral anomaly
    if beh is not None and beh.anomaly_score >= ANOMALY_ELEVATED:
        # Adjusted to +0.5 so that anomaly → score=0.5 → borderline elevated (contract)
        fired_rules.append(("FP-006", "behavioral", 0.5))

    # FP-007 / FP-008 / FP-009: behavioral analyzer (Phase 16) — scored here if signals present
    if beh is not None:
        if beh.device_mismatch:
            fired_rules.append(("FP-007", "behavioral", 0.4))
        if beh.ip_location_mismatch or beh.ip_country_mismatch:
            fired_rules.append(("FP-008", "behavioral", 0.4))
    # FP-009: unusual refund amount (needs behavioral.typical_refund_amount + request amount)
    if (
        beh is not None
        and beh.typical_refund_amount is not None
        and beh.typical_refund_amount > 0
        and request.requested_refund_amount is not None
    ):
        from apps.agents.risk_fraud.policy import UNUSUAL_AMOUNT_RATIO

        unusual_threshold = beh.typical_refund_amount * UNUSUAL_AMOUNT_RATIO
        if float(request.requested_refund_amount) >= unusual_threshold:
            fired_rules.append(("FP-009", "behavioral", 0.3))

    # Sum contributions, cap at 1.0
    for _rule_id, _domain, contribution in fired_rules:
        score += contribution
    score = min(score, 1.0)

    # Build evidence from fired rules
    for rule_id, domain, contribution in fired_rules:
        evidence.append(
            EvidenceItem(
                source=domain,
                description=f"{rule_id}: {_rule_description(rule_id, signals)}",
                value={"rule": rule_id, "contribution": contribution},
            )
        )
        policy_references.append(rule_id)
        evidence.append(
            EvidenceItem(
                source="fraud_policy",
                description=f"{rule_id}: policy rule fired",
                value={"rule": rule_id, "contribution": contribution, "policy": policy.policy_name},
            )
        )

    # ------------------------------------------------------------------
    # Step 7: Level mapping + borderline detection
    # ------------------------------------------------------------------
    borderline = abs(score - ELEVATED_THRESHOLD) < 1e-9 or abs(score - HIGH_THRESHOLD) < 1e-9
    level = _score_to_level(score)
    confidence = 0.6 if borderline else (0.9 if fired_rules else 0.9)

    # Apply missing-history confidence reduction (Gate 5)
    if missing_history:
        confidence = min(confidence, 0.6)
        evidence.append(
            EvidenceItem(
                source="refund_history",
                description="Missing refund history: confidence lowered",
                value={"refund_history": None, "note": "partial signal set"},
            )
        )

    # ------------------------------------------------------------------
    # Step 8: recommended_action derivation
    # ------------------------------------------------------------------
    has_chargeback = rh is not None and rh.chargebacks >= CHARGEBACK_ELEVATED
    recommended_action = _derive_recommended_action(
        level, has_chargeback, requires_human_review=False
    )

    # No fired rules and all signals present → clean, low risk
    if not fired_rules and not missing_history:
        evidence.append(
            EvidenceItem(
                source="fraud_policy",
                description=(
                    "All fraud rules (FP-001..FP-006) silent: no risk signal fired. "
                    "Customer is assessed as low risk."
                ),
                value={"rule": "no-rule-fired", "score": 0.0, "policy": policy.policy_name},
            )
        )
        policy_references = list(dict.fromkeys(policy_references))
        reasoning = "All fraud policy rules evaluated; no risk signal fired. Low risk."
        if as_ is not None and as_.known_good_customer:
            reasoning += (
                " Known-good customer with clean long-tenure baseline (FP-005: 0.0 offset)."
            )
        return RiskAssessment(
            risk_level=RiskLevel.LOW,
            recommended_action=RecommendedAction.APPROVE_RISK_CLEARANCE,
            confidence=0.9,
            evidence=evidence,
            policy_references=policy_references,
            reasoning_summary=reasoning,
            requires_human_review=False,
        )

    # ------------------------------------------------------------------
    # Step 9: No-applicable-rule stance (signals present, score=0 but not clean)
    # ------------------------------------------------------------------
    if score == 0.0 and fired_rules:
        # Should not happen logically, but defensive
        pass

    if score == 0.0 and not fired_rules and missing_history:
        # Missing history with otherwise clean signals → low but with note
        evidence.append(
            EvidenceItem(
                source="fraud_policy",
                description="No fraud rules fired; missing history reduces confidence.",
                value={"rule": "no-rule-fired", "note": "missing-history"},
            )
        )
        return RiskAssessment(
            risk_level=RiskLevel.LOW,
            recommended_action=RecommendedAction.APPROVE_RISK_CLEARANCE,
            confidence=0.6,
            evidence=evidence,
            policy_references=list(dict.fromkeys(policy_references)),
            reasoning_summary=(
                "No fraud rules fired; missing refund history lowers confidence to 0.6."
            ),
            requires_human_review=False,
        )

    # Build reasoning summary
    rule_ids = list(dict.fromkeys(r[0] for r in fired_rules))
    reasoning_parts = [
        f"Score: {score:.2f}. Rules fired: {', '.join(rule_ids)}." if rule_ids else ""
    ]
    if borderline:
        reasoning_parts.append(
            f"Score {score:.1f} exactly on threshold → upper band (borderline rule, conf 0.6)."
        )
    if missing_history:
        reasoning_parts.append("Refund history absent; confidence lowered.")
    if has_chargeback and level in (RiskLevel.ELEVATED, RiskLevel.HIGH):
        reasoning_parts.append("Prior chargeback(s) present → manual review recommended.")

    reasoning = " ".join(p for p in reasoning_parts if p)

    requires_human_review = has_chargeback and level == RiskLevel.ELEVATED
    if requires_human_review:
        recommended_action = RecommendedAction.MANUAL_REVIEW

    return RiskAssessment(
        risk_level=level,
        recommended_action=recommended_action,
        confidence=confidence,
        evidence=evidence,
        policy_references=list(dict.fromkeys(policy_references)),
        reasoning_summary=reasoning,
        requires_human_review=requires_human_review,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _score_to_level(score: float) -> RiskLevel:
    """Map cumulative score to risk level (borderline → upper band)."""
    if score >= HIGH_THRESHOLD:
        return RiskLevel.HIGH
    if score >= ELEVATED_THRESHOLD:
        return RiskLevel.ELEVATED
    return RiskLevel.LOW


def _compute_score(signals: RiskSignals, request: RiskAssessmentRequest) -> float:
    """Compute additive score without building evidence (used by VIP gate for context level)."""
    score: float = 0.0
    rh = signals.refund_history
    beh = signals.behavioral
    pi = signals.payment_instrument
    as_ = signals.account_standing

    if rh is not None:
        if rh.chargebacks >= CHARGEBACK_HIGH:
            score += 0.8
        elif rh.chargebacks >= CHARGEBACK_ELEVATED:
            score += 0.5
    if beh is not None:
        if beh.refund_requests_in_window >= VELOCITY_HIGH:
            score += 0.8
        elif beh.refund_requests_in_window >= VELOCITY_ELEVATED:
            score += 0.5
    if pi is not None:
        if pi.card_testing_pattern:
            score += 0.6
        elif not pi.billing_details_match:
            score += 0.5
    if as_ is not None:
        if as_.status == "restricted":
            score += 0.6
        elif as_.status == "watch":
            score += 0.3
        if as_.tenure_days < NEW_ACCOUNT_DAYS and as_.status != "restricted":
            score += 0.3
    if beh is not None and beh.anomaly_score >= ANOMALY_ELEVATED:
        score += 0.5
    if beh is not None and beh.device_mismatch:
        score += 0.4
    if beh is not None and (beh.ip_location_mismatch or beh.ip_country_mismatch):
        score += 0.4
    if (
        beh is not None
        and beh.typical_refund_amount is not None
        and beh.typical_refund_amount > 0
        and request.requested_refund_amount is not None
    ):
        from apps.agents.risk_fraud.policy import UNUSUAL_AMOUNT_RATIO

        if (
            float(request.requested_refund_amount)
            >= beh.typical_refund_amount * UNUSUAL_AMOUNT_RATIO
        ):
            score += 0.3
    return min(score, 1.0)


def _is_contradiction(signals: RiskSignals) -> bool:
    """Return True when clean baseline coexists with strong fraud signals."""
    as_ = signals.account_standing
    rh = signals.refund_history
    pi = signals.payment_instrument
    beh = signals.behavioral

    clean_low = (
        as_ is not None
        and as_.status == "good"
        and as_.tenure_days >= NEW_ACCOUNT_DAYS
        and (rh is None or rh.chargebacks == 0)
    )
    strong_high = (
        beh is not None
        and beh.refund_requests_in_window >= VELOCITY_HIGH
        and pi is not None
        and not pi.billing_details_match
    )
    return clean_low and strong_high


def _derive_recommended_action(
    level: RiskLevel,
    has_chargeback: bool,
    *,
    requires_human_review: bool = False,
) -> RecommendedAction:
    """Derive recommended_action from level + contextual gates."""
    if level == RiskLevel.HIGH:
        return RecommendedAction.DENY_OR_ESCALATE
    if level == RiskLevel.ELEVATED:
        if has_chargeback:
            return RecommendedAction.MANUAL_REVIEW
        return RecommendedAction.ALLOW_WITH_CAUTION
    # LOW
    return RecommendedAction.APPROVE_RISK_CLEARANCE


def _rule_description(rule_id: str, signals: RiskSignals) -> str:
    """Human-readable description of a fired rule for evidence."""
    as_ = signals.account_standing
    rh = signals.refund_history
    pi = signals.payment_instrument
    beh = signals.behavioral

    if rule_id == "FP-002":
        return f"Chargeback history: {rh.chargebacks if rh else 0} prior chargebacks"
    if rule_id == "FP-003":
        return f"Refund velocity: {beh.refund_requests_in_window if beh else 0} requests in window"
    if rule_id == "FP-004":
        if pi and pi.card_testing_pattern:
            return "Card testing pattern detected"
        return "Billing details mismatch"
    if rule_id == "FP-005":
        parts = []
        if as_:
            if as_.status != "good":
                parts.append(f"status={as_.status}")
            if as_.tenure_days < NEW_ACCOUNT_DAYS:
                parts.append(f"tenure_days={as_.tenure_days}")
        return "Account standing: " + ", ".join(parts) if parts else "Account standing"
    if rule_id == "FP-006":
        return f"Behavioral anomaly: score={beh.anomaly_score if beh else 0:.2f}"
    if rule_id == "FP-007":
        return "Device mismatch detected"
    if rule_id == "FP-008":
        return "IP/location mismatch detected"
    if rule_id == "FP-009":
        return "Unusual refund amount relative to typical history"
    return rule_id


__all__ = ["assess_signals"]
