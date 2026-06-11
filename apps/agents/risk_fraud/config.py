"""Local configuration module — single source of truth for the Risk Fraud Agent (T093).

All topic names are resolver-derived (never hardcoded literals).
Both ports are env-configurable and distinct so agentcore dev (8083) and
http_app (8103) can run concurrently.
Local dev requires no AWS deployment (AUTH_MODE=none, agentcore deploy is a future target).
"""

from __future__ import annotations

import os

from apps.agents.common import BROKER_URL as _BROKER_URL  # noqa: F401
from packages.contracts.topics import (  # noqa: F401
    AGENT_ENVIRONMENT,
    TOPIC_RISK_RESULT,
    endpoint_topic,
    topic_for,
)

# ------------------------------------------------------------------
# Agent identity constants
# ------------------------------------------------------------------
AGENT_ID: str = "risk-fraud-agent"
DISPLAY_NAME: str = "Risk Fraud Agent"
TENANT_ID: str = "poc"

# ------------------------------------------------------------------
# Auth
# ------------------------------------------------------------------
AUTH_MODE: str = os.environ.get("AUTH_MODE", "none")

# ------------------------------------------------------------------
# LLM summary enrichment (008 — assistive only, default OFF)
# ------------------------------------------------------------------
RISK_LLM_SUMMARY_ENABLED: bool = os.environ.get(
    "RISK_LLM_SUMMARY_ENABLED", "false"
).lower().strip() in ("true", "1", "yes")

# ------------------------------------------------------------------
# Port configuration (env-configurable, distinct ports)
# ------------------------------------------------------------------
# A2A HTTP surface (http_app.py / uvicorn) — avoids billing agent's :8080
A2A_ENDPOINT_PORT: int = int(os.environ.get("A2A_ENDPOINT_PORT", os.environ.get("PORT", "8103")))

# AgentCore CLI dev server port — set in agentcore/.env.local as PORT=8083
AGENTCORE_PORT: int = int(os.environ.get("AGENTCORE_PORT", "8083"))

# ------------------------------------------------------------------
# Broker / transport
# ------------------------------------------------------------------
# Re-exported so callers import from config, not directly from apps.agents.common
BROKER_URL: str = _BROKER_URL

# ------------------------------------------------------------------
# Topics — always resolver-derived, never hardcoded (acceptance #1)
# ------------------------------------------------------------------
# Risk result event topic (already declared in packages.contracts.topics as TOPIC_RISK_RESULT)
RISK_RESULT_TOPIC: str = TOPIC_RISK_RESULT

# Agent endpoint topic (inbound A2A task requests)
AGENT_ENDPOINT_TOPIC: str = endpoint_topic(AGENT_ID)

__all__ = [
    "AGENT_ID",
    "DISPLAY_NAME",
    "TENANT_ID",
    "AUTH_MODE",
    "A2A_ENDPOINT_PORT",
    "AGENTCORE_PORT",
    "BROKER_URL",
    "AGENT_ENVIRONMENT",
    "RISK_RESULT_TOPIC",
    "AGENT_ENDPOINT_TOPIC",
    "RISK_LLM_SUMMARY_ENABLED",
    "topic_for",
]
