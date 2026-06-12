"""ObservabilityConfig — process-level observability configuration."""
from __future__ import annotations

import os


class ObservabilityConfig:
    """Immutable config snapshot read once at startup via from_env()."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        public_key: str | None = None,
        secret_key: str | None = None,
        host: str | None = None,
        sample_rate: float = 1.0,
        environment: str = "local",
        service_name: str = "agent",
        heartbeat_interval_s: float = 10.0,
        exporter: str = "langfuse",
        redact_pii: bool = True,
        log_raw_prompts: bool = False,
        log_raw_outputs: bool = False,
        disabled_spans: frozenset[str] = frozenset(),
    ) -> None:
        self.enabled = enabled
        self.public_key = public_key
        self.secret_key = secret_key
        self.host = host
        self.sample_rate = max(0.0, min(1.0, sample_rate))
        self.environment = environment
        self.service_name = service_name
        self.heartbeat_interval_s = heartbeat_interval_s
        self.exporter = exporter
        self.redact_pii = redact_pii
        self.log_raw_prompts = log_raw_prompts
        self.log_raw_outputs = log_raw_outputs
        #: Span names to suppress from export (the body still runs; nothing is
        #: sent to the backend). Lets operators silence high-volume foundation
        #: spans like ``kafka.publish`` without touching agent code.
        self.disabled_spans = disabled_spans

    @classmethod
    def from_env(cls, *, agent_id: str = "agent") -> ObservabilityConfig:
        enabled = os.environ.get("AGENT_OBSERVABILITY_ENABLED", "true").lower() not in (
            "false", "0", "no"
        )
        public_key = os.environ.get("LANGFUSE_PUBLIC_KEY") or None
        secret_key = os.environ.get("LANGFUSE_SECRET_KEY") or None
        host = os.environ.get("LANGFUSE_HOST") or None
        try:
            sample_rate = float(os.environ.get("AGENT_OBSERVABILITY_SAMPLE_RATE", "1.0"))
        except ValueError:
            sample_rate = 1.0
        environment = os.environ.get("AGENT_OBSERVABILITY_ENV", "local")
        try:
            heartbeat_interval_s = float(os.environ.get("AGENT_HEARTBEAT_INTERVAL_S", "10"))
        except ValueError:
            heartbeat_interval_s = 10.0
        exporter = os.environ.get("AGENT_OBSERVABILITY_EXPORTER", "langfuse")
        # Comma-separated span names to suppress, e.g.
        # AGENT_OBSERVABILITY_DISABLED_SPANS=kafka.publish,a2a.task.send
        disabled_spans = frozenset(
            s.strip()
            for s in os.environ.get("AGENT_OBSERVABILITY_DISABLED_SPANS", "").split(",")
            if s.strip()
        )
        redact_pii = os.environ.get("REDACT_PII", "true").lower() not in ("false", "0", "no")
        _raw_on = ("true", "1", "yes")
        log_raw_prompts = os.environ.get("LOG_RAW_LLM_PROMPTS", "false").lower() in _raw_on
        log_raw_outputs = os.environ.get("LOG_RAW_LLM_OUTPUTS", "false").lower() in _raw_on
        return cls(
            enabled=enabled,
            public_key=public_key,
            secret_key=secret_key,
            host=host,
            sample_rate=sample_rate,
            environment=environment,
            service_name=agent_id,
            heartbeat_interval_s=heartbeat_interval_s,
            exporter=exporter,
            redact_pii=redact_pii,
            log_raw_prompts=log_raw_prompts,
            log_raw_outputs=log_raw_outputs,
            disabled_spans=disabled_spans,
        )

    @property
    def is_active(self) -> bool:
        """True only when enabled AND credentials present AND langfuse importable."""
        if not self.enabled:
            return False
        if not (self.public_key and self.secret_key):
            return False
        try:
            import langfuse  # noqa: F401
            return True
        except ImportError:
            return False
