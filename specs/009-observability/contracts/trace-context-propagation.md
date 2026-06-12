# Contract: Trace Context Propagation

Satisfies FR-001 (propagate across agent boundaries via the transport), FR-010 (missing context →
new root), FR-011 (spans carry correlation/causation IDs).

## Envelope change (additive, backward-compatible)

`src/agent_foundation/envelope.py`:

```python
class EventEnvelope(BaseModel):
    ...
    trace_context: dict[str, str] | None = None  # W3C carrier: {"traceparent": ..., "tracestate"?: ...}
```

- Optional, default `None`. Pre-feature envelopes deserialize unchanged (no migration).
- Not included in idempotency keys, dedup, or audit equality. Pure transport metadata.

## Publish seam (inject)

`transport/publisher.py` — `publish()` and `publish_raw()`:

1. Open a producer `span("kafka.publish", agent_id=...)` (attributes incl. `topic`, `event_id`).
2. Set `trace_context = current_trace_context()` on the envelope **before** serialization.
3. Serialize + send as today. Span closes on completion/error.

Contract: a published envelope carries the active span's W3C context when observability is on; when
off, `trace_context` stays `None` and behavior is byte-identical to pre-feature.

## Consume seam (extract)

`transport/consumer.py` — at handler dispatch (`await handler(envelope)`):

1. `with start_consumer_span(envelope, agent_id=..., operation=event_type):`
   - extracts `envelope.trace_context`; if present, the new span is a **child** of that remote span;
     if absent or unparseable, a **new trace root** is started (FR-010 — never drop the event).
   - span attributes include `correlation_id`, `causation_id` (FR-011).
2. `await handler(envelope)` runs **inside** the span context, so any spans/generations the handler
   creates nest correctly into the cross-agent trace.

## A2A seams

- `runtime/client.py` `A2AClient.submit()` ⇒ `span("a2a.task.send")` (attrs `capability`, `task_id`);
  the request is published through the publish seam, so its envelope carries the send span's context.
- `runtime/runtime.py` handler dispatch ⇒ `span("a2a.task.receive")` (attrs `capability`, `task_id`)
  opened from the incoming request envelope's `trace_context`, making the performer's work a child of
  the caller's send span. The returned `TaskResult` is published with the performer span's context so
  the caller can continue the same trace on receipt.

## Round-trip invariant (testable)

Given an active span S, `inject(S) → EventEnvelope.trace_context → extract` yields a span whose parent
is S (same trace-id, parent span-id = S's span-id). Given `trace_context = None`, extract yields a new
root (distinct trace-id). These two cases are the core unit tests (`test_traceparent_roundtrip.py`).
