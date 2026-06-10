"""Entitlement checker — deterministic four-signal evaluation (T054).

Pure, no clock/random. Reads only owned Entitlement + Subscription facts (FR-009).
"""

from __future__ import annotations

from dataclasses import dataclass

from packages.contracts.events.payloads import EvidenceItem


@dataclass(frozen=True)
class EntitlementCheck:
    granted: bool
    used: bool
    feature_enabled: bool
    has_access: bool
    mismatch: bool
    summary: str


def check_entitlement(facts: object) -> EntitlementCheck:
    """Evaluate the four entitlement signals against the owned Entitlement/Subscription facts.

    Mismatch conditions (any → mismatch=True, → contradiction gate):
      1. access_granted=False yet access_used=True
      2. account_active=True on a cancelled subscription
      3. entitlement.status="revoked" while feature_enabled=True
    """
    from apps.agents.billing_entitlement.models import BillingFacts

    bf: BillingFacts = facts  # type: ignore[assignment]
    entitlement = bf.entitlement
    subscription = bf.subscription

    if entitlement is None:
        return EntitlementCheck(
            granted=False,
            used=False,
            feature_enabled=False,
            has_access=False,
            mismatch=False,
            summary="No entitlement record found",
        )

    granted = entitlement.access_granted
    used = entitlement.access_used
    feature_enabled = entitlement.feature_enabled
    has_access = entitlement.account_active

    conflicts: list[str] = []
    if not granted and used:
        conflicts.append("access_granted=False but access_used=True")
    if has_access and subscription is not None and subscription.status == "cancelled":
        conflicts.append(f"account_active=True but subscription.status='{subscription.status}'")
    if entitlement.status == "revoked" and feature_enabled:
        conflicts.append("entitlement.status='revoked' but feature_enabled=True")

    mismatch = bool(conflicts)
    if mismatch:
        summary = "Entitlement mismatch: " + "; ".join(conflicts)
    elif used and granted:
        summary = "Access granted and used (value delivered)"
    elif granted and not used:
        summary = "Access granted but not used (value not consumed)"
    elif not granted and not used:
        summary = "Access not granted and not used (not delivered)"
    else:
        summary = "Entitlement state normal"

    return EntitlementCheck(
        granted=granted,
        used=used,
        feature_enabled=feature_enabled,
        has_access=has_access,
        mismatch=mismatch,
        summary=summary,
    )


def build_entitlement_evidence(check: EntitlementCheck) -> EvidenceItem:
    """Build an EvidenceItem from an EntitlementCheck result (source='entitlement')."""
    return EvidenceItem(
        source="entitlement",
        description=check.summary,
        value={
            "granted": check.granted,
            "used": check.used,
            "feature_enabled": check.feature_enabled,
            "has_access": check.has_access,
            "mismatch": check.mismatch,
        },
    )


__all__ = ["EntitlementCheck", "check_entitlement", "build_entitlement_evidence"]
