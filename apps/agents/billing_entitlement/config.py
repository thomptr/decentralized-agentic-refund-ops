"""Local configuration module for the Billing Entitlement Agent (008).

Centralises env-configurable flags so that main.py and service.py
import from a single source of truth.
"""

from __future__ import annotations

import os

# ------------------------------------------------------------------
# LLM summary enrichment (008 — assistive only, default OFF)
# ------------------------------------------------------------------
BILLING_LLM_SUMMARY_ENABLED: bool = os.environ.get(
    "BILLING_LLM_SUMMARY_ENABLED", "false"
).lower().strip() in ("true", "1", "yes")

__all__ = [
    "BILLING_LLM_SUMMARY_ENABLED",
]
