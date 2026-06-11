"""Test RuntimeConfig and model profile resolution."""

from __future__ import annotations

import os
from unittest.mock import patch

from pydantic import BaseModel, ConfigDict

from agent_foundation.llm import (
    BedrockModelConfig,
    RuntimeConfig,
    TaskKind,
)
from agent_foundation.llm.config import reset_yaml_cache, resolve_profile


class SampleResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    summary: str
    confidence: float = 0.5


async def test_from_env_defaults_to_stub():
    """RuntimeConfig.from_env with no env vars defaults to stub mode."""
    clean_env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("AGENT_LLM_") and k not in ("BEDROCK_MODEL_ID", "AWS_REGION")
    }
    with patch.dict(os.environ, clean_env, clear=True):
        reset_yaml_cache()
        cfg = RuntimeConfig.from_env()
        assert cfg.mode == "stub"


async def test_resolve_profile_returns_per_agent():
    """resolve_profile returns specific profiles for registered agents."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("AGENT_LLM_")}
    # Point to a non-existent file so the in-code registry is used
    env["AGENT_LLM_PROFILES_PATH"] = "/nonexistent/model-profiles.yaml"
    with patch.dict(os.environ, env, clear=True):
        reset_yaml_cache()
        cfg = RuntimeConfig(mode="stub")
        profile_cra = resolve_profile("customer-resolution-agent", TaskKind.classify, config=cfg)
        profile_billing = resolve_profile(
            "billing-entitlement-agent", TaskKind.summarize_reasoning, config=cfg
        )
        # CRA classify has max_tokens=256 per the in-code registry
        assert profile_cra.max_tokens == 256
        # Billing summarize has max_tokens=200 per the in-code registry
        assert profile_billing.max_tokens == 200


async def test_resolve_profile_unknown_agent_falls_back():
    """Unregistered agent should get the default profile."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("AGENT_LLM_")}
    env["AGENT_LLM_PROFILES_PATH"] = "/nonexistent/model-profiles.yaml"
    with patch.dict(os.environ, env, clear=True):
        reset_yaml_cache()
        cfg = RuntimeConfig(mode="stub")
        profile = resolve_profile("unknown-agent", TaskKind.classify, config=cfg)
        # Default profile max_tokens is 1024
        assert profile.max_tokens == 1024


async def test_bedrock_model_config_validates():
    """BedrockModelConfig round-trips through construction."""
    config = BedrockModelConfig(
        provider="bedrock",
        region="us-west-2",
        model_id="anthropic.claude-3-haiku-20240307-v1:0",
        temperature=0.5,
        max_tokens=512,
        timeout_seconds=15,
    )
    assert config.region == "us-west-2"
    assert config.temperature == 0.5
    dumped = config.model_dump()
    restored = BedrockModelConfig.model_validate(dumped)
    assert restored == config
