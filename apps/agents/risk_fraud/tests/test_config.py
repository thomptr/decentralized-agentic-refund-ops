"""Tests for the local configuration module (T097)."""

from __future__ import annotations

import os


def test_risk_result_topic_resolver_derived():
    """config.RISK_RESULT_TOPIC == topic_for('risk','review','completed') — resolver-derived."""
    from apps.agents.risk_fraud.config import RISK_RESULT_TOPIC
    from packages.contracts.topics import topic_for

    assert topic_for("risk", "review", "completed") == RISK_RESULT_TOPIC


def test_agent_endpoint_topic_resolver_derived():
    """AGENT_ENDPOINT_TOPIC is resolver-derived and AGENT_ENVIRONMENT-prefixed."""
    from apps.agents.risk_fraud.config import AGENT_ENDPOINT_TOPIC, AGENT_ID
    from packages.contracts.topics import AGENT_ENVIRONMENT, endpoint_topic

    assert endpoint_topic(AGENT_ID) == AGENT_ENDPOINT_TOPIC
    assert AGENT_ENVIRONMENT in AGENT_ENDPOINT_TOPIC


def test_a2a_endpoint_port_default():
    """A2A_ENDPOINT_PORT defaults to 8103."""
    # Ensure env var is not set
    env_backup = os.environ.pop("A2A_ENDPOINT_PORT", None)
    port_backup = os.environ.pop("PORT", None)
    try:
        import importlib

        import apps.agents.risk_fraud.config as cfg

        importlib.reload(cfg)
        assert cfg.A2A_ENDPOINT_PORT == 8103
    finally:
        if env_backup is not None:
            os.environ["A2A_ENDPOINT_PORT"] = env_backup
        if port_backup is not None:
            os.environ["PORT"] = port_backup


def test_agentcore_port_default():
    """AGENTCORE_PORT defaults to 8083."""
    env_backup = os.environ.pop("AGENTCORE_PORT", None)
    try:
        import importlib

        import apps.agents.risk_fraud.config as cfg

        importlib.reload(cfg)
        assert cfg.AGENTCORE_PORT == 8083
    finally:
        if env_backup is not None:
            os.environ["AGENTCORE_PORT"] = env_backup


def test_a2a_endpoint_port_env_override(monkeypatch):
    """A2A_ENDPOINT_PORT honors the env var override."""
    monkeypatch.setenv("A2A_ENDPOINT_PORT", "9999")
    import importlib

    import apps.agents.risk_fraud.config as cfg

    importlib.reload(cfg)
    assert cfg.A2A_ENDPOINT_PORT == 9999


def test_agentcore_port_env_override(monkeypatch):
    """AGENTCORE_PORT honors the env var override."""
    monkeypatch.setenv("AGENTCORE_PORT", "7777")
    import importlib

    import apps.agents.risk_fraud.config as cfg

    importlib.reload(cfg)
    assert cfg.AGENTCORE_PORT == 7777


def test_auth_mode_default_none():
    """AUTH_MODE defaults to 'none'."""
    env_backup = os.environ.pop("AUTH_MODE", None)
    try:
        import importlib

        import apps.agents.risk_fraud.config as cfg

        importlib.reload(cfg)
        assert cfg.AUTH_MODE == "none"
    finally:
        if env_backup is not None:
            os.environ["AUTH_MODE"] = env_backup


def test_agent_card_security_none():
    """build_agent_card().security == 'none'."""
    from apps.agents.risk_fraud.identity import build_agent_card

    card = build_agent_card()
    assert card.security == "none"
