"""T017: Trace-context round-trip: inject→envelope.trace_context→extract parents correctly."""

from __future__ import annotations

from agent_foundation.observability.propagation import (
    TraceContextCarrier,
)


def test_carrier_roundtrip_with_tracestate() -> None:
    tp = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    ts = "rojo=00f067aa0ba902b7"
    carrier = TraceContextCarrier(traceparent=tp, tracestate=ts)
    d = carrier.to_envelope_dict()
    assert d == {"traceparent": tp, "tracestate": ts}
    restored = TraceContextCarrier.from_envelope_dict(d)
    assert restored is not None
    assert restored.traceparent == tp
    assert restored.tracestate == ts


def test_carrier_roundtrip_without_tracestate() -> None:
    tp = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    carrier = TraceContextCarrier(traceparent=tp)
    d = carrier.to_envelope_dict()
    assert "tracestate" not in d
    restored = TraceContextCarrier.from_envelope_dict(d)
    assert restored is not None
    assert restored.tracestate is None


def test_from_envelope_dict_none_input() -> None:
    assert TraceContextCarrier.from_envelope_dict(None) is None


def test_from_envelope_dict_empty_dict() -> None:
    assert TraceContextCarrier.from_envelope_dict({}) is None


def test_from_envelope_dict_malformed_traceparent() -> None:
    assert TraceContextCarrier.from_envelope_dict({"traceparent": "not-valid"}) is None


def test_from_envelope_dict_short_ids() -> None:
    assert TraceContextCarrier.from_envelope_dict({"traceparent": "00-abc-def-01"}) is None


def test_trace_id_accessor() -> None:
    tp = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    c = TraceContextCarrier(traceparent=tp)
    assert c.trace_id == "4bf92f3577b34da6a3ce929d0e0e4736"
    assert c.span_id == "00f067aa0ba902b7"


def test_trace_id_accessor_malformed() -> None:
    c = TraceContextCarrier(traceparent="bad")
    assert c.trace_id is None
    assert c.span_id is None


def test_new_root_on_absent_trace_context() -> None:
    """Absent trace_context → from_envelope_dict returns None → new trace root (FR-010)."""
    result = TraceContextCarrier.from_envelope_dict(None)
    assert result is None
