"""Test config loader -- load_model_config layered resolution."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from agent_foundation.llm import (
    ModelConfigError,
)
from agent_foundation.llm.config import (
    clear_runtime_overrides,
    load_model_config,
    reset_yaml_cache,
)


async def test_bare_call_returns_stub_defaults():
    """load_model_config with no env/yaml returns stub defaults."""
    clean_env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("AGENT_LLM_")
        and not k.startswith("BEDROCK_")
        and not k.startswith("AWS_")
    }
    with patch.dict(os.environ, clean_env, clear=True):
        reset_yaml_cache()
        clear_runtime_overrides()
        config = load_model_config("test-agent")
        assert config.provider == "stub"
        assert config.region == "us-east-1"


async def test_env_overrides_work():
    """Env vars override defaults in load_model_config."""
    clean_env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("AGENT_LLM_")
        and not k.startswith("BEDROCK_")
        and not k.startswith("AWS_")
    }
    clean_env["AGENT_LLM_MODE"] = "bedrock"
    clean_env["AGENT_LLM_MODEL"] = "anthropic.claude-3-haiku-20240307-v1:0"
    clean_env["AGENT_LLM_REGION"] = "eu-west-1"
    with patch.dict(os.environ, clean_env, clear=True):
        reset_yaml_cache()
        clear_runtime_overrides()
        config = load_model_config("test-agent")
        assert config.provider == "bedrock"
        assert config.model_id == "anthropic.claude-3-haiku-20240307-v1:0"
        assert config.region == "eu-west-1"


async def test_bedrock_without_model_id_raises():
    """ModelConfigError on bedrock mode without model_id."""
    clean_env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("AGENT_LLM_")
        and not k.startswith("BEDROCK_")
        and not k.startswith("AWS_")
    }
    clean_env["AGENT_LLM_MODE"] = "bedrock"
    clean_env["AGENT_LLM_MODEL"] = ""
    with patch.dict(os.environ, clean_env, clear=True):
        reset_yaml_cache()
        clear_runtime_overrides()
        # load_model_config has a default model_id so it won't be empty
        # unless we strip it; the check is mode=bedrock + no model_id
        # Since the default layer provides a model_id, we test by patching

        with patch("agent_foundation.llm.config._merge_layers") as mock_merge:
            mock_merge.return_value = {"provider": "bedrock"}
            with pytest.raises(ModelConfigError):
                load_model_config("test-agent")
