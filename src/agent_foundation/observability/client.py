"""Guarded LangFuse/OTel client singleton — no-op fallback when off/unavailable."""

from __future__ import annotations

from typing import Any

from agent_foundation.observability.config import ObservabilityConfig

_client: Any = None
_config: ObservabilityConfig | None = None


def get_client() -> Any:
    """Return the active LangFuse client, or None if observability is off/unavailable."""
    return _client


def get_config() -> ObservabilityConfig:
    """Return the active config, falling back to a disabled default."""
    return _config or ObservabilityConfig(enabled=False)


def configure(config: ObservabilityConfig) -> None:
    """Bootstrap the LangFuse client singleton. Call once at agent startup."""
    global _client, _config
    _config = config
    if not config.is_active:
        _client = None
        return
    try:
        import langfuse  # noqa: F401

        # langfuse v3 SDK: tracing is enabled by default; the v2 `enabled=`
        # kwarg was removed (renamed to `tracing_enabled`). Passing the old
        # name raises TypeError and silently disables the client → no traces.
        kwargs: dict[str, Any] = {
            "public_key": config.public_key,
            "secret_key": config.secret_key,
            "tracing_enabled": True,
        }
        if config.host:
            kwargs["host"] = config.host
        lf = langfuse.Langfuse(**kwargs)
        _client = lf
    except Exception:
        _client = None


def langfuse_callback_handler() -> Any:
    """Return a LangFuse CallbackHandler for LangGraph node tracing, or None."""
    if _client is None:
        return None
    try:
        from langfuse.langchain import CallbackHandler

        cfg = get_config()
        kwargs: dict[str, Any] = {
            "public_key": cfg.public_key,
            "secret_key": cfg.secret_key,
        }
        if cfg.host:
            kwargs["host"] = cfg.host
        return CallbackHandler(**kwargs)
    except Exception:
        return None


def flush() -> None:
    """Flush pending telemetry; no-op when client is None."""
    import contextlib

    if _client is not None:
        with contextlib.suppress(Exception):
            _client.flush()
