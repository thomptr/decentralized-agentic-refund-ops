"""span() and generation() context managers — OTel-compatible, fail-open."""
from __future__ import annotations

import time
from collections.abc import Generator
from contextlib import contextmanager, suppress
from typing import Any

from agent_foundation.observability.client import flush as _flush
from agent_foundation.observability.client import get_client, get_config


@contextmanager
def span(
    name: str,
    *,
    attrs: dict[str, str] | None = None,
    trace_id: str | None = None,
) -> Generator[Any, None, None]:
    """Context manager emitting a named span. Fail-open — body always runs."""
    cfg = get_config()
    client = get_client()
    lf_span: Any = None

    if client is not None and cfg.enabled and name not in cfg.disabled_spans:
        try:
            kwargs: dict[str, Any] = {"name": name}
            if trace_id:
                kwargs["trace_id"] = trace_id
            lf_span = client.start_span(**kwargs)
            if attrs:
                for k, v in attrs.items():
                    lf_span.update(metadata={k: v}) if hasattr(lf_span, "update") else None
        except Exception:
            lf_span = None

    try:
        yield lf_span
        if lf_span is not None:
            with suppress(Exception):
                lf_span.end()
    except Exception as exc:
        if lf_span is not None:
            try:
                lf_span.update(level="ERROR", status_message=str(exc))
                lf_span.end()
            except Exception:
                pass
        raise


@contextmanager
def generation(
    name: str,
    *,
    model: str | None = None,
    input: str | None = None,
    attrs: dict[str, str] | None = None,
    trace_id: str | None = None,
) -> Generator[Any, None, None]:
    """Context manager emitting a LangFuse generation (LLM span). Fail-open."""
    cfg = get_config()
    client = get_client()
    lf_gen: Any = None
    start_ns = time.perf_counter_ns()

    if client is not None and cfg.enabled and name not in cfg.disabled_spans:
        try:
            kwargs: dict[str, Any] = {"name": name}
            if model:
                kwargs["model"] = model
            if input:
                kwargs["input"] = input
            if trace_id:
                kwargs["trace_id"] = trace_id
            lf_gen = client.start_generation(**kwargs)
            if attrs:
                for k, v in (attrs or {}).items():
                    with suppress(Exception):
                        lf_gen.update(metadata={k: v})
        except Exception:
            lf_gen = None

    try:
        yield lf_gen
        if lf_gen is not None:
            latency_ms = (time.perf_counter_ns() - start_ns) // 1_000_000
            try:
                lf_gen.update(metadata={"latency_ms": latency_ms})
                lf_gen.end()
            except Exception:
                pass
    except Exception as exc:
        if lf_gen is not None:
            latency_ms = (time.perf_counter_ns() - start_ns) // 1_000_000
            try:
                lf_gen.update(
                    level="ERROR",
                    status_message=str(exc),
                    metadata={"latency_ms": latency_ms},
                )
                lf_gen.end()
            except Exception:
                pass
        raise


def flush() -> None:
    _flush()
