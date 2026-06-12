# Contract: Observability Public API

Module: `src/agent_foundation/observability/__init__.py`. This is the only surface other code imports.
Every function is **fail-open**: when observability is disabled, unconfigured, or the LangFuse SDK is
absent/erroring, calls become no-ops and never raise (FR-008).

**Instrumentation base / exporter posture (FR-015)**: spans are created with OpenTelemetry-compatible
semantics. The **only wired exporter** is LangFuse (its v3 SDK is OTel-based). `AGENT_OBSERVABILITY_EXPORTER`
defaults to `langfuse`; `cloudwatch`/`otlp` are documented future values for AWS (AgentCore/CloudWatch)
deploys and are **not** built or tested in this PoC.

## `configure_observability(config: ObservabilityConfig | None = None) -> None`

Initialize the process-wide LangFuse client once, at startup, beside `configure_logging()`.

- `config is None` ⇒ build from `ObservabilityConfig.from_env()`.
- Idempotent: a second call is a no-op.
- If `config.enabled` is False, keys are missing, or `langfuse` is not importable ⇒ switches to
  **no-op mode** and returns normally (logs one debug line). Never raises.
- Registers a `flush()` on interpreter shutdown / graceful agent stop.

## `span(name: str, *, agent_id: str, attributes: Mapping[str, Any] | None = None) -> ContextManager`

Open a generic span around a unit of work (used by seam wrappers; callers rarely use directly).

- Yields a span handle exposing `set_attribute(k, v)` and `record_exception(exc)`.
- On `__exit__` with an exception, marks the span `status=error`, records the exception, and
  **re-raises** the original exception (observability must not swallow domain errors), but any error
  *inside the span machinery itself* is swallowed.
- No-op mode ⇒ yields a null handle; the wrapped body still runs normally.

## `generation(name: str, *, agent_id: str, model: str | None, attributes: Mapping[str, Any] | None = None) -> ContextManager`

Specialized span for an LLM call. Same semantics as `span()` plus helpers to set usage:

- `.set_usage(input_tokens, output_tokens, cache_read_tokens, cache_write_tokens)`
- `.set_cache_hit(bool)`
- `.link_prompt(name, version)` (no-op if prompt unmanaged — see prompt-management contract)

## `traced(span_name: str) -> Callable`

Decorator for **pure** domain engine entry points (FR-013 domain spans — see span-catalog.md). Opens
`span_name`, runs the wrapped function, returns its value **unchanged**, marks `status=error` + re-raises
on exception. No-op (direct call) when observability is off. Applied to `classify`, `evaluate`,
`assess_signals`, `decide` — one annotation line each, no handler logic.

## `score(name: str, value: float | bool, *, comment: str | None = None) -> None`

Attach a non-binding evaluation score to the **current** generation/trace (R7). Write-only; no return
value is ever consumed by agent code.

## `current_trace_context() -> dict[str, str] | None`

Return the W3C carrier (`{"traceparent": ..., "tracestate"?: ...}`) for the active span, or `None` in
no-op mode / no active span. Used by the publish seam to populate `EventEnvelope.trace_context`.

## `start_consumer_span(envelope, *, agent_id, operation) -> ContextManager`

Convenience used by the consume seam: extracts `envelope.trace_context`, sets it as parent (or starts
a new root if absent — FR-010), and opens a `consume {operation}` span carrying
`correlation_id`/`causation_id` (FR-011).

## `flush(timeout_s: float | None = None) -> None`

Force background export (used on shutdown and in integration tests). No-op when disabled.

## Guarantees

| Guarantee | Mechanism |
|-----------|-----------|
| Never raises into caller (FR-008) | every public call wrapped in guarded try/except; only domain exceptions inside `span()` bodies propagate |
| < 5% overhead (SC-005) | no-op fast path when off; background-thread batched export when on |
| Disable without code change (FR-012) | `AGENT_OBSERVABILITY_ENABLED=false` |
| Backend-down safe (SC-006) | SDK best-effort delivery; helper-level guards |

## Fail-open / Backend-down Behaviour (FR-008/SC-006/FR-015)

The observability layer is **non-blocking and fail-open**:

- When the LangFuse backend is unavailable, all  /  calls are no-ops.
  Agent processing continues normally (SC-006).
- When the toggle is off () or keys are missing, the client
  is  and every observability call short-circuits immediately.
- The  package is an optional extra; its absence produces the same no-op behaviour.

## Exporter Posture (FR-015)

The only **locally-wired exporter** is the self-hosted LangFuse backend.
Export to AgentCore / CloudWatch is **configuration-only** — not wired or tested locally.
To switch exporters, set  or  and supply the
required AWS config. No code changes are needed.

See  for the full AWS export reference.
