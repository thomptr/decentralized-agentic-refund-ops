"""Deterministic refund-eligibility rules engine (T010/T021/T054/T055).

Pure function: evaluate(facts, request, policy) -> EligibilityRecommendation.
No side effects, no clock beyond the window comparison, no randomness (FR-012).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from agent_foundation.observability.decorators import traced
from apps.agents.billing_entitlement.models import (
    BillingFacts,
    EligibilityRecommendation,
    Recommendation,
    RefundEligibilityRequest,
)
from apps.agents.billing_entitlement.policy import (
    REFUND_WINDOW_DAYS,
    USAGE_HEAVY_THRESHOLD,
    RefundPolicy,
)
from packages.contracts.events.payloads import EvidenceItem


@traced("policy.evaluate")
def evaluate(
    facts: BillingFacts,
    request: RefundEligibilityRequest,
    policy: RefundPolicy,
) -> EligibilityRecommendation:
    """Evaluate refund eligibility.  Pure, deterministic.

    Evaluation order (from refund-policy.md):
      1. Data-completeness gate
      2. Contradiction gate (payment contradictions + entitlement mismatch via T055)
      3. Hard denials — RP-001 (window) / RP-002 (paid/captured/not-reversed)
      4. Usage gate — RP-004 (heavy usage)
      5. Approve — all gates passed, not delivered (RP-003)
      6. No applicable rule → manual_review
    """
    from apps.agents.billing_entitlement.entitlement_checker import (
        build_entitlement_evidence,
        check_entitlement,
    )

    now = datetime.now(UTC)
    evidence: list[EvidenceItem] = []
    policy_references: list[str] = []

    # ---------- Step 1: Data-completeness gate ----------
    missing: list[str] = []
    if facts.invoice is None:
        missing.append("invoice")
    if facts.payment is None:
        missing.append("payment")

    if missing:
        evidence.append(
            EvidenceItem(
                source="refund_policy",
                description="Data-completeness gate: missing required billing facts",
                value={"missing": missing},
            )
        )
        return EligibilityRecommendation(
            recommendation=Recommendation.REQUEST_MORE_INFORMATION,
            confidence=0.2,
            evidence=evidence,
            policy_references=[],
            reasoning_summary=f"Missing required billing facts: {', '.join(missing)}.",
            requires_human_review=True,
            eligible_refund_amount=Decimal("0.00"),
            subscription_status=facts.subscription.status if facts.subscription else "unknown",
            invoice_status="unknown",
            payment_status="unknown",
            entitlement_status=facts.entitlement.status if facts.entitlement else "unknown",
            usage_level="unknown",
            refund_window_status="unknown",
        )

    invoice = facts.invoice
    payment = facts.payment
    subscription = facts.subscription
    entitlement = facts.entitlement
    usage = facts.usage

    # Compute derived values
    days_since_invoice = (now - invoice.issued_at).days
    within_window = days_since_invoice <= REFUND_WINDOW_DAYS
    borderline_window = days_since_invoice == REFUND_WINDOW_DAYS

    usage_ratio = (
        usage.usage_units / usage.allotment_units if usage and usage.allotment_units > 0 else 0.0
    )
    is_heavy_usage = usage_ratio > USAGE_HEAVY_THRESHOLD
    borderline_usage = usage is not None and abs(usage_ratio - USAGE_HEAVY_THRESHOLD) < 1e-9

    # Entitlement check (T054) — run regardless; feeds both RP-003 and T055 contradiction gate
    ent_check = None
    if entitlement is not None:
        ent_check = check_entitlement(facts)
        evidence.append(build_entitlement_evidence(ent_check))

    # ---------- Step 2: Contradiction gate ----------
    contradictions: list[str] = []

    # Payment contradiction: partial reversal already applied on a paid invoice
    if payment.reversed_amount > 0 and invoice.paid and payment.reversed_amount < payment.amount:
        contradictions.append(
            f"payment.reversed_amount={payment.reversed_amount} > 0 "
            "on a paid invoice (partial reversal already applied)"
        )

    # Entitlement mismatch → contradiction gate (T055)
    if ent_check is not None and ent_check.mismatch:
        contradictions.append(ent_check.summary)

    if contradictions:
        for conflict in contradictions:
            evidence.append(
                EvidenceItem(
                    source="refund_policy",
                    description="Contradiction gate",
                    value={"conflict": conflict},
                )
            )
        policy_references.append("contradiction-gate")
        return EligibilityRecommendation(
            recommendation=Recommendation.MANUAL_REVIEW,
            confidence=0.3,
            evidence=evidence,
            policy_references=policy_references,
            reasoning_summary=(
                "Contradictory billing signals detected: " + "; ".join(contradictions) + "."
            ),
            requires_human_review=True,
            eligible_refund_amount=Decimal("0.00"),
            subscription_status=subscription.status if subscription else "unknown",
            invoice_status="paid" if invoice.paid else "unpaid",
            payment_status="captured" if payment.captured else "uncaptured",
            entitlement_status=entitlement.status if entitlement else "unknown",
            usage_level=_usage_level(usage_ratio),
            refund_window_status="within" if within_window else "expired",
        )

    # Populate base evidence from owned facts (for all subsequent paths)
    evidence.append(
        EvidenceItem(
            source="invoice",
            description=f"Invoice issued {days_since_invoice} days ago",
            value={
                "invoice_id": invoice.invoice_id,
                "issued_at": invoice.issued_at.isoformat(),
                "paid": invoice.paid,
                "days_since_issued": days_since_invoice,
                "window_days": REFUND_WINDOW_DAYS,
            },
        )
    )
    evidence.append(
        EvidenceItem(
            source="payment",
            description="Payment capture and reversal status",
            value={
                "payment_id": payment.payment_id,
                "captured": payment.captured,
                "amount": payment.amount,
                "reversed_amount": payment.reversed_amount,
            },
        )
    )
    if subscription:
        evidence.append(
            EvidenceItem(
                source="subscription",
                description="Subscription status",
                value={
                    "subscription_id": subscription.subscription_id,
                    "status": subscription.status,
                    "term": subscription.term,
                },
            )
        )
    if usage:
        evidence.append(
            EvidenceItem(
                source="product_usage",
                description=f"Usage ratio: {usage_ratio:.3f} (threshold={USAGE_HEAVY_THRESHOLD})",
                value={
                    "usage_units": usage.usage_units,
                    "allotment_units": usage.allotment_units,
                    "usage_ratio": round(usage_ratio, 6),
                    "heavy_threshold": USAGE_HEAVY_THRESHOLD,
                },
            )
        )

    # ---------- Step 3: Hard denials ----------
    # RP-001: outside refund window
    if not within_window:
        evidence.append(
            EvidenceItem(
                source="refund_policy",
                description="RP-001: outside refund window",
                value={"days_since_invoice": days_since_invoice, "window_days": REFUND_WINDOW_DAYS},
            )
        )
        policy_references.append("RP-001")
        return EligibilityRecommendation(
            recommendation=Recommendation.DENY_REFUND,
            confidence=0.9,
            evidence=evidence,
            policy_references=policy_references,
            reasoning_summary=(
                f"Refund window expired: {days_since_invoice} days since invoice "
                f"(limit: {REFUND_WINDOW_DAYS} days — RP-001)."
            ),
            requires_human_review=False,
            eligible_refund_amount=Decimal("0.00"),
            subscription_status=subscription.status if subscription else "unknown",
            invoice_status="paid" if invoice.paid else "unpaid",
            payment_status="captured" if payment.captured else "uncaptured",
            entitlement_status=entitlement.status if entitlement else "unknown",
            usage_level=_usage_level(usage_ratio),
            refund_window_status="expired",
        )

    # RP-002: unpaid invoice
    if not invoice.paid:
        evidence.append(
            EvidenceItem(
                source="refund_policy",
                description="RP-002: invoice not paid",
                value={"invoice_id": invoice.invoice_id, "paid": invoice.paid},
            )
        )
        policy_references.append("RP-002")
        return EligibilityRecommendation(
            recommendation=Recommendation.DENY_REFUND,
            confidence=0.9,
            evidence=evidence,
            policy_references=policy_references,
            reasoning_summary="Invoice is unpaid; no refundable payment exists (RP-002).",
            requires_human_review=False,
            eligible_refund_amount=Decimal("0.00"),
            subscription_status=subscription.status if subscription else "unknown",
            invoice_status="unpaid",
            payment_status="uncaptured",
            entitlement_status=entitlement.status if entitlement else "unknown",
            usage_level=_usage_level(usage_ratio),
            refund_window_status="within",
        )

    # RP-002: payment not captured
    if not payment.captured:
        evidence.append(
            EvidenceItem(
                source="refund_policy",
                description="RP-002: payment not captured",
                value={"payment_id": payment.payment_id, "captured": payment.captured},
            )
        )
        policy_references.append("RP-002")
        return EligibilityRecommendation(
            recommendation=Recommendation.DENY_REFUND,
            confidence=0.9,
            evidence=evidence,
            policy_references=policy_references,
            reasoning_summary="Payment not captured; no refundable charge exists (RP-002).",
            requires_human_review=False,
            eligible_refund_amount=Decimal("0.00"),
            subscription_status=subscription.status if subscription else "unknown",
            invoice_status="paid",
            payment_status="uncaptured",
            entitlement_status=entitlement.status if entitlement else "unknown",
            usage_level=_usage_level(usage_ratio),
            refund_window_status="within",
        )

    # RP-002: payment already fully reversed
    if payment.reversed_amount >= payment.amount and payment.amount > 0:
        evidence.append(
            EvidenceItem(
                source="refund_policy",
                description="RP-002: payment already fully reversed",
                value={"reversed_amount": payment.reversed_amount, "amount": payment.amount},
            )
        )
        policy_references.append("RP-002")
        return EligibilityRecommendation(
            recommendation=Recommendation.DENY_REFUND,
            confidence=0.9,
            evidence=evidence,
            policy_references=policy_references,
            reasoning_summary="Payment already fully reversed; refund already applied (RP-002).",
            requires_human_review=False,
            eligible_refund_amount=Decimal("0.00"),
            subscription_status=subscription.status if subscription else "unknown",
            invoice_status="paid",
            payment_status="reversed",
            entitlement_status=entitlement.status if entitlement else "unknown",
            usage_level=_usage_level(usage_ratio),
            refund_window_status="within",
        )

    # ---------- Step 4: Usage gate — RP-004 ----------
    if is_heavy_usage:
        refs = ["RP-004"]
        evidence.append(
            EvidenceItem(
                source="refund_policy",
                description="RP-004: heavy usage — materially weakens refund claim",
                value={"usage_ratio": round(usage_ratio, 6), "threshold": USAGE_HEAVY_THRESHOLD},
            )
        )
        if subscription and subscription.status == "active":
            refs.append("RP-005")
            evidence.append(
                EvidenceItem(
                    source="refund_policy",
                    description="RP-005: active subscription with heavy usage",
                    value={"status": subscription.status},
                )
            )
        policy_references.extend(refs)
        return EligibilityRecommendation(
            recommendation=Recommendation.DENY_REFUND,
            confidence=0.6 if borderline_usage else 0.9,
            evidence=evidence,
            policy_references=policy_references,
            reasoning_summary=(
                f"Heavy usage ({usage_ratio:.3f} > {USAGE_HEAVY_THRESHOLD}) "
                "materially weakens the refund claim (RP-004)."
            ),
            requires_human_review=False,
            eligible_refund_amount=Decimal("0.00"),
            subscription_status=subscription.status if subscription else "unknown",
            invoice_status="paid",
            payment_status="captured",
            entitlement_status=entitlement.status if entitlement else "unknown",
            usage_level="heavy",
            refund_window_status="within",
        )

    # Entitlement evidence for the approve/no-rule paths (RP-003)
    delivered = entitlement.delivered if entitlement is not None else False
    if entitlement is not None:
        policy_references.append("RP-003")
        evidence.append(
            EvidenceItem(
                source="refund_policy",
                description="RP-003: entitlement delivered=" + str(delivered),
                value={"delivered": delivered, "approve_supporting": not delivered},
            )
        )

    # Borderline confidence (window or usage exactly at boundary)
    borderline = borderline_window or borderline_usage
    confidence = 0.6 if borderline else 0.9

    # ---------- Step 5: Approve ----------
    # Conditions: within window, paid, captured, not fully reversed, not delivered, light usage
    if not delivered:
        refundable = Decimal(str(round(payment.amount - payment.reversed_amount, 2)))
        refs = ["RP-001", "RP-002"]
        if entitlement is not None:
            refs.append("RP-003")
        if usage is not None:
            refs.append("RP-004")
        if subscription is not None:
            refs.append("RP-005")
        policy_references.extend([r for r in refs if r not in policy_references])

        parts = [
            f"Within refund window ({days_since_invoice}d ≤ {REFUND_WINDOW_DAYS}d — RP-001)",
            "Invoice paid and payment captured (RP-002)",
        ]
        if entitlement is None:
            parts.append("No entitlement record (approve-supporting — RP-003)")
        else:
            parts.append("Product not delivered (approve-supporting — RP-003)")
        if usage:
            parts.append(f"Light usage ({usage_ratio:.3f} — RP-004 does not fire)")
        if borderline_window:
            parts.append(
                f"Borderline: exactly {REFUND_WINDOW_DAYS} days since invoice "
                "(inclusive boundary — confidence lowered to 0.6)"
            )

        return EligibilityRecommendation(
            recommendation=Recommendation.APPROVE_FULL_REFUND,
            confidence=confidence,
            evidence=evidence,
            policy_references=list(dict.fromkeys(policy_references)),
            reasoning_summary=". ".join(parts) + ".",
            requires_human_review=False,
            eligible_refund_amount=refundable,
            subscription_status=subscription.status if subscription else "unknown",
            invoice_status="paid",
            payment_status="captured",
            entitlement_status=entitlement.status if entitlement else "unknown",
            usage_level=_usage_level(usage_ratio),
            refund_window_status="within-borderline" if borderline_window else "within",
        )

    # ---------- Step 6: No applicable rule ----------
    evidence.append(
        EvidenceItem(
            source="refund_policy",
            description="No applicable policy rule resolved this case to a confident verdict",
            value={
                "entitlement_delivered": delivered,
                "usage_ratio": round(usage_ratio, 6),
                "within_window": within_window,
                "invoice_paid": invoice.paid,
            },
        )
    )
    return EligibilityRecommendation(
        recommendation=Recommendation.MANUAL_REVIEW,
        confidence=0.2,
        evidence=evidence,
        policy_references=list(dict.fromkeys(policy_references)),
        reasoning_summary="No applicable policy rule resolved the case to a confident verdict.",
        requires_human_review=True,
        eligible_refund_amount=Decimal("0.00"),
        subscription_status=subscription.status if subscription else "unknown",
        invoice_status="paid",
        payment_status="captured",
        entitlement_status=entitlement.status if entitlement else "unknown",
        usage_level=_usage_level(usage_ratio),
        refund_window_status="within",
    )


def _usage_level(usage_ratio: float) -> str:
    if usage_ratio > USAGE_HEAVY_THRESHOLD:
        return "heavy"
    if usage_ratio >= 0.5:
        return "moderate"
    return "light"
