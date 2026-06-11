"""Test YAML profile loading and env overrides."""

from __future__ import annotations

import os
import tempfile
from unittest.mock import patch

from agent_foundation.llm import RuntimeConfig, TaskKind
from agent_foundation.llm.config import reset_yaml_cache, resolve_profile


def _write_yaml_profiles(tmpdir, content):
    """Write a model-profiles.yaml to tmpdir and return its path."""
    path = os.path.join(tmpdir, "model-profiles.yaml")
    with open(path, "w") as f:
        f.write(content)
    return path


async def test_registered_agent_yaml_overrides_default():
    """A YAML profile for a specific agent overrides the default."""
    yaml_content = """
default:
    max_tokens: 512
    temperature: 0.1
agents:
    my-custom-agent:
        max_tokens: 2048
        temperature: 0.5
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yaml_path = _write_yaml_profiles(tmpdir, yaml_content)
        env = {k: v for k, v in os.environ.items() if not k.startswith("AGENT_LLM_")}
        env["AGENT_LLM_PROFILES_PATH"] = yaml_path
        with patch.dict(os.environ, env, clear=True):
            reset_yaml_cache()
            cfg = RuntimeConfig(mode="stub")
            profile = resolve_profile("my-custom-agent", TaskKind.classify, config=cfg)
            assert profile.max_tokens == 2048
            assert profile.temperature == 0.5


async def test_unregistered_agent_falls_back_to_yaml_default():
    """An agent not in YAML falls back to the YAML default section."""
    yaml_content = """
default:
    max_tokens: 777
    temperature: 0.2
agents:
    some-other-agent:
        max_tokens: 999
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yaml_path = _write_yaml_profiles(tmpdir, yaml_content)
        env = {k: v for k, v in os.environ.items() if not k.startswith("AGENT_LLM_")}
        env["AGENT_LLM_PROFILES_PATH"] = yaml_path
        with patch.dict(os.environ, env, clear=True):
            reset_yaml_cache()
            cfg = RuntimeConfig(mode="stub")
            profile = resolve_profile("unknown-agent", TaskKind.classify, config=cfg)
            assert profile.max_tokens == 777


async def test_env_vars_override_yaml_values():
    """AGENT_LLM_* env vars override YAML profile values."""
    yaml_content = """
default:
    max_tokens: 512
agents:
    test-agent:
        max_tokens: 1024
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yaml_path = _write_yaml_profiles(tmpdir, yaml_content)
        env = {k: v for k, v in os.environ.items() if not k.startswith("AGENT_LLM_")}
        env["AGENT_LLM_PROFILES_PATH"] = yaml_path
        env["AGENT_LLM_MODEL"] = "anthropic.claude-3-haiku-20240307-v1:0"
        env["AGENT_LLM_TIMEOUT_SECONDS"] = "42.0"
        with patch.dict(os.environ, env, clear=True):
            reset_yaml_cache()
            cfg = RuntimeConfig.from_env()
            profile = resolve_profile("test-agent", TaskKind.classify, config=cfg)
            assert profile.model_id == "anthropic.claude-3-haiku-20240307-v1:0"
            assert profile.timeout_seconds == 42.0
