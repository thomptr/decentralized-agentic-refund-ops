"""RuntimeConfig, ModelProfile, BedrockModelConfig, resolve_profile, load_model_config."""

from __future__ import annotations

import os
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from agent_foundation.llm.request import TaskKind

LLMProvider = Literal["stub", "bedrock", "agentcore"]


class BedrockModelConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: str = "bedrock"
    region: str = "us-east-1"
    model_id: str = "anthropic.claude-3-5-sonnet-20241022-v2:0"
    temperature: float = 0.0
    max_tokens: int = 1024
    timeout_seconds: int = 30
    retry_max_attempts: int = 3


class ModelProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    mode: LLMProvider = "stub"
    model_id: str = "anthropic.claude-3-5-sonnet-20241022-v2:0"
    region: str | None = None
    temperature: float = 0.0
    max_tokens: int = 1024
    top_p: float | None = None
    timeout_seconds: float = 8.0
    max_repairs: int = 2


class RuntimeConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    mode: LLMProvider = "stub"
    model_id: str = "anthropic.claude-3-5-sonnet-20241022-v2:0"
    region: str | None = None
    timeout_seconds: float = 8.0
    max_repairs: int = 2
    bootstrap_servers: str = "localhost:9092"
    log_raw_prompts: bool = False
    log_raw_outputs: bool = False
    redact_pii: bool = True

    @classmethod
    def from_env(cls) -> RuntimeConfig:
        return cls(
            mode=os.environ.get("AGENT_LLM_MODE", "stub"),  # type: ignore[arg-type]
            model_id=os.environ.get(
                "AGENT_LLM_MODEL",
                os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20241022-v2:0"),
            ),
            region=os.environ.get("AGENT_LLM_REGION", os.environ.get("AWS_REGION")),
            timeout_seconds=float(os.environ.get("AGENT_LLM_TIMEOUT_SECONDS", "8.0")),
            max_repairs=int(os.environ.get("AGENT_LLM_MAX_REPAIRS", "2")),
            bootstrap_servers=os.environ.get("AGENT_LLM_BOOTSTRAP_SERVERS", "localhost:9092"),
            log_raw_prompts=_parse_bool(os.environ.get("LOG_RAW_LLM_PROMPTS", "false")),
            log_raw_outputs=_parse_bool(os.environ.get("LOG_RAW_LLM_OUTPUTS", "false")),
            redact_pii=_parse_bool(os.environ.get("REDACT_PII", "true")),
        )


def _parse_bool(value: str) -> bool:
    return value.lower().strip() in ("true", "1", "yes")


# ---------------------------------------------------------------------------
# Per-agent profile registry
# ---------------------------------------------------------------------------

_PROFILE_REGISTRY: dict[tuple[str, TaskKind], ModelProfile] = {
    ("customer-resolution-agent", TaskKind.classify): ModelProfile(max_tokens=256),
    ("customer-resolution-agent", TaskKind.draft_response): ModelProfile(max_tokens=512),
    ("billing-entitlement-agent", TaskKind.summarize_reasoning): ModelProfile(max_tokens=200),
    ("risk-fraud-agent", TaskKind.summarize_reasoning): ModelProfile(max_tokens=200),
}

_DEFAULT_PROFILE = ModelProfile()


def resolve_profile(
    agent_id: str,
    task_kind: TaskKind,
    *,
    config: RuntimeConfig | None = None,
) -> ModelProfile:
    """Resolve the model profile for an agent + task, applying env overrides."""
    cfg = config or RuntimeConfig.from_env()

    yaml_profiles = _load_yaml_profiles()
    yaml_key = f"{agent_id}.{task_kind}"
    if yaml_key in yaml_profiles:
        base = yaml_profiles[yaml_key]
    elif agent_id in yaml_profiles:
        base = yaml_profiles[agent_id]
    elif (agent_id, task_kind) in _PROFILE_REGISTRY:
        base = _PROFILE_REGISTRY[(agent_id, task_kind)]
    elif "default" in yaml_profiles:
        base = yaml_profiles["default"]
    else:
        base = _DEFAULT_PROFILE

    overrides: dict[str, Any] = {}
    if cfg.mode != "stub":
        overrides["mode"] = cfg.mode
    if os.environ.get("AGENT_LLM_MODEL"):
        overrides["model_id"] = cfg.model_id
    if cfg.region is not None and os.environ.get("AGENT_LLM_REGION"):
        overrides["region"] = cfg.region
    if os.environ.get("AGENT_LLM_TIMEOUT_SECONDS"):
        overrides["timeout_seconds"] = cfg.timeout_seconds
    if os.environ.get("AGENT_LLM_MAX_REPAIRS"):
        overrides["max_repairs"] = cfg.max_repairs

    if overrides:
        return base.model_copy(update=overrides)
    return base


# ---------------------------------------------------------------------------
# YAML profile loading
# ---------------------------------------------------------------------------

_yaml_cache: dict[str, ModelProfile] | None = None


def _load_yaml_profiles() -> dict[str, ModelProfile]:
    global _yaml_cache
    if _yaml_cache is not None:
        return _yaml_cache

    path = os.environ.get("AGENT_LLM_PROFILES_PATH", "config/model-profiles.yaml")
    if not os.path.isfile(path):
        _yaml_cache = {}
        return _yaml_cache

    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        _yaml_cache = {}
        return _yaml_cache

    with open(path) as f:
        data = yaml.safe_load(f) or {}

    profiles: dict[str, ModelProfile] = {}

    default_data = data.get("default", {})
    if default_data:
        profiles["default"] = _build_profile(default_data)

    agents = data.get("agents", {})
    for aid, agent_data in agents.items():
        merged = {**default_data, **agent_data}
        profiles[aid] = _build_profile(merged)

    _yaml_cache = profiles
    return profiles


def _build_profile(data: dict[str, Any]) -> ModelProfile:
    field_map = {
        "provider": "mode",
        "model_id": "model_id",
        "region": "region",
        "temperature": "temperature",
        "max_tokens": "max_tokens",
        "top_p": "top_p",
        "timeout_seconds": "timeout_seconds",
        "max_repairs": "max_repairs",
    }
    kwargs: dict[str, Any] = {}
    for yaml_key, profile_key in field_map.items():
        if yaml_key in data:
            kwargs[profile_key] = data[yaml_key]
    return ModelProfile(**kwargs)


def reset_yaml_cache() -> None:
    global _yaml_cache
    _yaml_cache = None


# ---------------------------------------------------------------------------
# Layered load_model_config (CFG2)
# ---------------------------------------------------------------------------


class ModelConfigError(ValueError):
    pass


_runtime_overrides: dict[str, dict[str, Any]] = {}


def register_runtime_override(agent_id: str, **fields: Any) -> None:
    _runtime_overrides[agent_id] = fields


def clear_runtime_overrides() -> None:
    _runtime_overrides.clear()


def _merge_layers(*layers: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for layer in layers:
        for k, v in layer.items():
            if v is not None:
                merged[k] = v
    return merged


def _load_env_layer() -> dict[str, Any]:
    result: dict[str, Any] = {}
    env_map = {
        "AGENT_LLM_MODE": "provider",
        "AGENT_LLM_MODEL": "model_id",
        "BEDROCK_MODEL_ID": "model_id",
        "AGENT_LLM_REGION": "region",
        "AWS_REGION": "region",
        "AWS_DEFAULT_REGION": "region",
        "AGENT_LLM_TIMEOUT_SECONDS": "timeout_seconds",
        "BEDROCK_TIMEOUT_SECONDS": "timeout_seconds",
        "BEDROCK_TEMPERATURE": "temperature",
        "BEDROCK_MAX_TOKENS": "max_tokens",
    }
    for env_var, field in env_map.items():
        val = os.environ.get(env_var)
        if val is not None and field not in result:
            if field in ("timeout_seconds", "temperature"):
                try:
                    result[field] = float(val)
                except ValueError as exc:
                    raise ModelConfigError(f"Non-numeric value for {env_var}: {val!r}") from exc
            elif field in ("max_tokens",):
                try:
                    result[field] = int(val)
                except ValueError as exc:
                    raise ModelConfigError(f"Non-numeric value for {env_var}: {val!r}") from exc
            else:
                result[field] = val
    return result


def _load_yaml_layer(agent_id: str) -> dict[str, Any]:
    path = os.environ.get("AGENT_LLM_CONFIG_FILE", "config/agent_llm.yaml")
    if not os.path.isfile(path):
        return {}
    try:
        import yaml
    except ImportError:
        return {}
    try:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
    except Exception as exc:
        raise ModelConfigError(f"Failed to parse YAML config {path}: {exc}") from exc

    defaults = data.get("defaults", {})
    agent_section = data.get("agents", {}).get(agent_id, {})
    return {**defaults, **agent_section}


def load_model_config(agent_id: str) -> BedrockModelConfig:
    defaults = {
        "provider": "stub",
        "region": "us-east-1",
        "model_id": "anthropic.claude-3-5-sonnet-20241022-v2:0",
        "temperature": 0.0,
        "max_tokens": 1024,
        "timeout_seconds": 30,
        "retry_max_attempts": 3,
    }
    yaml_layer = _load_yaml_layer(agent_id)
    env_layer = _load_env_layer()
    override_layer = _runtime_overrides.get(agent_id, {})

    merged = _merge_layers(defaults, yaml_layer, env_layer, override_layer)
    mode = merged.get("provider", "stub")

    if mode in ("bedrock", "agentcore") and not merged.get("model_id"):
        raise ModelConfigError(
            f"agent_id={agent_id!r} mode={mode!r}: model_id is required for {mode} mode"
        )

    try:
        return BedrockModelConfig(
            **{k: v for k, v in merged.items() if k in BedrockModelConfig.model_fields}
        )
    except Exception as exc:
        raise ModelConfigError(
            f"agent_id={agent_id!r} mode={mode!r}: invalid config: {exc}"
        ) from exc
