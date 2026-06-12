"""W3C traceparent inject/extract and TraceContextCarrier value object."""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

_TRACEPARENT_RE = re.compile(
    r"^[0-9a-f]{2}-([0-9a-f]{32})-([0-9a-f]{16})-[0-9a-f]{2}$"
)


@dataclass
class TraceContextCarrier:
    """W3C traceparent + optional tracestate value object."""

    traceparent: str
    tracestate: str | None = None

    # ── parsed accessors ──────────────────────────────────────────────────
    @property
    def trace_id(self) -> str | None:
        m = _TRACEPARENT_RE.match(self.traceparent)
        return m.group(1) if m else None

    @property
    def span_id(self) -> str | None:
        m = _TRACEPARENT_RE.match(self.traceparent)
        return m.group(2) if m else None

    # ── serialization ─────────────────────────────────────────────────────
    def to_envelope_dict(self) -> dict[str, str]:
        d: dict[str, str] = {"traceparent": self.traceparent}
        if self.tracestate is not None:
            d["tracestate"] = self.tracestate
        return d

    @classmethod
    def from_envelope_dict(cls, d: Mapping[str, str] | None) -> TraceContextCarrier | None:
        """Parse from EventEnvelope.trace_context; returns None on absent/malformed input."""
        if not d:
            return None
        tp = d.get("traceparent", "")
        if not tp or not _TRACEPARENT_RE.match(tp):
            return None
        return cls(traceparent=tp, tracestate=d.get("tracestate"))


def inject(context: object | None) -> dict[str, str] | None:
    """Inject active OTel span context into a traceparent dict.

    Returns None (no-op) when observability is disabled or OTel SDK absent.
    """
    try:
        from opentelemetry.propagate import inject as otel_inject

        carrier: dict[str, str] = {}
        otel_inject(carrier)
        if not carrier.get("traceparent"):
            return None
        return carrier
    except Exception:
        return None


def extract(trace_context: dict[str, str] | None) -> object | None:
    """Extract OTel context from a traceparent dict; returns None on failure."""
    if not trace_context:
        return None
    try:
        from opentelemetry.propagate import extract as otel_extract

        return otel_extract(trace_context)
    except Exception:
        return None


def current_trace_context() -> dict[str, str] | None:
    """Return the current active span's W3C trace context dict, or None."""
    return inject(None)


def start_consumer_span(
    tracer: object | None,
    span_name: str,
    trace_context: dict[str, str] | None,
    **attrs: str,
) -> object:
    """Start a consumer span, parenting off trace_context or creating a new root (FR-010)."""
    try:
        if tracer is None:
            raise RuntimeError("no tracer")
        from opentelemetry import context as otel_context

        ctx = extract(trace_context)  # None → new root
        token = otel_context.attach(ctx) if ctx is not None else None
        span = tracer.start_span(span_name)  # type: ignore[union-attr]
        for k, v in attrs.items():
            span.set_attribute(k, v)
        if token is not None:
            otel_context.detach(token)
        return span
    except Exception:
        return _NoOpSpan()


class _NoOpSpan:
    """Returned when OTel is off or errors — swallows all calls."""

    def set_attribute(self, *a: object, **kw: object) -> None:
        pass

    def record_exception(self, *a: object, **kw: object) -> None:
        pass

    def set_status(self, *a: object, **kw: object) -> None:
        pass

    def end(self) -> None:
        pass

    def __enter__(self) -> _NoOpSpan:
        return self

    def __exit__(self, *a: object) -> bool:
        return False
