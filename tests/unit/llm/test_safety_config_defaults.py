"""Test safe defaults for RuntimeConfig."""

from __future__ import annotations

import os
from unittest.mock import patch

from agent_foundation.llm import RuntimeConfig
from agent_foundation.llm.config import reset_yaml_cache


async def test_log_raw_prompts_default_false():
    """RuntimeConfig from empty env -> log_raw_prompts=False."""
    clean_env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("AGENT_LLM_")
        and not k.startswith("LOG_RAW_")
        and k not in ("BEDROCK_MODEL_ID", "AWS_REGION", "REDACT_PII")
    }
    with patch.dict(os.environ, clean_env, clear=True):
        reset_yaml_cache()
        cfg = RuntimeConfig.from_env()
        assert cfg.log_raw_prompts is False


async def test_log_raw_outputs_default_false():
    """RuntimeConfig from empty env -> log_raw_outputs=False."""
    clean_env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("AGENT_LLM_")
        and not k.startswith("LOG_RAW_")
        and k not in ("BEDROCK_MODEL_ID", "AWS_REGION", "REDACT_PII")
    }
    with patch.dict(os.environ, clean_env, clear=True):
        reset_yaml_cache()
        cfg = RuntimeConfig.from_env()
        assert cfg.log_raw_outputs is False


async def test_redact_pii_default_true():
    """RuntimeConfig from empty env -> redact_pii=True."""
    clean_env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("AGENT_LLM_")
        and not k.startswith("LOG_RAW_")
        and k not in ("BEDROCK_MODEL_ID", "AWS_REGION", "REDACT_PII")
    }
    with patch.dict(os.environ, clean_env, clear=True):
        reset_yaml_cache()
        cfg = RuntimeConfig.from_env()
        assert cfg.redact_pii is True
