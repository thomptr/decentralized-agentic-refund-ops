"""Configuration constants for the Customer Resolution Agent.

All thresholds and capability IDs are PoC illustrative values, not production policy.
"""

from __future__ import annotations

import os as _os

from packages.contracts.events.payloads import ResolutionOutcome

# Agent identity
AGENT_ID = "customer-resolution-agent"
AGENT_DISPLAY_NAME = "Customer Resolution Agent"
AGENT_VERSION = "1.0.0"
AGENT_TENANT_ID = "poc"

# Peer capability IDs (must match the peer AgentCard's capability id)
BILLING_CAPABILITY_ID = "analyze_refund_eligibility"
BILLING_PEER_AGENT_ID = "billing-entitlement-agent"

RISK_CAPABILITY_ID = "assess_fraud_risk"
RISK_PEER_AGENT_ID = "risk-fraud-agent"

# Risk-band thresholds (PoC values)
ELEVATED_RISK_THRESHOLD: float = 0.5
HIGH_RISK_THRESHOLD: float = 0.8

# Decision engine thresholds (Phase 18)
CONFIDENCE_THRESHOLD: float = 0.6
PARTIAL_CREDIT_FRACTION: float = 0.5
MAX_AUTO_REFUND_AMOUNT: float = 1000.0

# Risk-band alias: the request's "medium" maps to the existing "elevated" enum value
RISK_MEDIUM = "elevated"

# Delegation timeout (Phase 11/14)
DELEGATION_TIMEOUT_SECONDS: int = 30

# Case-level deadline enforced by the reaper (006 T002)
# Distinct from DELEGATION_TIMEOUT_SECONDS (which is per-A2A-call; this is the hard case deadline).
CASE_DEADLINE_SECONDS: int = int(_os.environ.get("AGENT_CASE_DEADLINE_SECONDS", "15"))
REAPER_TICK_SECONDS: float = float(_os.environ.get("AGENT_REAPER_TICK_SECONDS", "1.0"))

# Human approval policy (Phase 17): outcomes that require a human gate before acting
# escalate_human always needs a human; approve_refund moves money so is human-gated.
HUMAN_APPROVAL_OUTCOMES: frozenset[ResolutionOutcome] = frozenset(
    {ResolutionOutcome.ESCALATE_HUMAN, ResolutionOutcome.APPROVE_REFUND}
)

# Safe-language guard (Phase 17/22): decision fields that MUST NOT appear in a customer draft
INTERNAL_ONLY_DRAFT_FIELDS: tuple[str, ...] = (
    "rationale",
    "escalation_reason",
    "billing_summary",
    "risk_summary",
)

# Refund intent vocabulary — case-insensitive substring match (decision-policy.md §A)
REFUND_INTENT_SIGNALS: frozenset[str] = frozenset(
    {
        "refund",
        "refunded",
        "charged",
        "charge",
        "overcharge",
        "overcharged",
        "double charged",
        "double-charged",
        "charged twice",
        "dispute",
        "disputed",
        "chargeback",
        "money back",
        "reimburse",
        "reimbursement",
        "billing error",
        "wrong amount",
        "cancel and refund",
    }
)

# Response drafter (Phase 22)
CUSTOMER_SAFE_FACT_KEYS: frozenset[str] = frozenset(
    {"refund_amount", "currency", "order_reference", "billing_outcome_summary", "eligibility"}
)
FRAUD_SCORING_FIELDS: tuple[str, ...] = (
    "score",
    "confidence",
    "risk_level",
    "evidence",
    "reasoning_summary",
)

# Max length for minimized summary fields (Phase 23)
MAX_SUMMARY_LENGTH: int = 200
