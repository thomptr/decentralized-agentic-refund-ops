# Phase 1 Data Model: Observability (LangFuse)

This feature adds **telemetry** entities, not domain entities. Nothing here participates in refund
decisions, idempotency keys, or the audit topic. Entities live in two places: (a) small in-process
config/value objects in `src/agent_foundation/observability/`, and (b) telemetry records produced into
the out-of-band LangFuse backend (Trace / Span / Generation / Score), which we do not persist
ourselves.

## In-process entities

### ObservabilityConfig

Process-level configuration, read once at startup (`config.py`, `from_env()`).

| Field | Type | Default | Source env var | Notes |
|-------|------|---------|----------------|-------|
| `enabled` | `bool` | `True` | `AGENT_OBSERVABILITY_ENABLED` | FR-012 toggle; default on |
| `public_key` | `str \| None` | `None` | `LANGFUSE_PUBLIC_KEY` | required to actually emit |
| `secret_key` | `str \| None` | `None` | `LANGFUSE_SECRET_KEY` | required to actually emit |
| `host` | `str \| None` | `None` | `LANGFUSE_HOST` | e.g. `http://localhost:3000`; defaults to SDK default if unset |
| `sample_rate` | `float` | `1.0` | `AGENT_OBSERVABILITY_SAMPLE_RATE` | 0.0–1.0; trace sampling for high volume (spec edge case) |
| `environment` | `str` | `"local"` | `AGENT_OBSERVABILITY_ENV` | LangFuse environment tag |
| `service_name` | `str` | per-agent | derived from `agent_id` | span/resource attribution |
| `heartbeat_interval_s` | `float` | `10.0` | `AGENT_HEARTBEAT_INTERVAL_S` | period for `system.agent.heartbeat` (0 disables) |
| `exporter` | `str` | `"langfuse"` | `AGENT_OBSERVABILITY_EXPORTER` | wired exporter; `cloudwatch`/`otlp` are documented future values (FR-015) |

**PII controls (reused, not redefined)**: redaction reuses the 008 LLM-runtime config —
`REDACT_PII` (default `true`), `LOG_RAW_LLM_PROMPTS` / `LOG_RAW_LLM_OUTPUTS` (default `false`) — and the
`Redactor` (`llm/redaction.py`). Prompts/completions are scrubbed before LangFuse export (FR-017/SC-007).

**Validation rules**:
- `enabled` is effectively `False` (no-op mode) if `enabled is True` but `public_key`/`secret_key`
  are missing, or if the `langfuse` package is not importable. The toggle never raises.
- `sample_rate` clamped to `[0.0, 1.0]`.

**Derivation**: mirrors `RuntimeConfig.from_env()` (008) and the agent boolean-flag pattern
(`BILLING_LLM_SUMMARY_ENABLED`).

### TraceContextCarrier

Value object representing the W3C headers that ride the event envelope.

| Field | Type | Notes |
|-------|------|-------|
| `traceparent` | `str` | W3C `traceparent` (`version-traceid-spanid-flags`) |
| `tracestate` | `str \| None` | optional vendor state |

- Serialized form is exactly the `EventEnvelope.trace_context` dict: `{"traceparent": ..., "tracestate": ...}`.
- Absent/empty → consumer starts a new trace root (FR-010).

## Modified existing entity

### EventEnvelope (additive change)

`src/agent_foundation/envelope.py` — **add one optional, backward-compatible field**:

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `trace_context` | `dict[str, str] \| None` | `None` | W3C carrier (`traceparent`/`tracestate`); transport metadata only |

**Rules**:
- Default `None` ⇒ envelopes serialized before this feature still validate (no migration).
- Populated by the publish-seam wrapper at emit time; read by the consume-seam wrapper at dispatch.
- **Not** part of any idempotency/dedup key, equality for audit purposes, or domain payload — purely
  carries span parentage. Replaying an event with a stale `trace_context` produces an identical
  outcome (Principle III).

## Telemetry records (produced into LangFuse — not persisted by us)

These are the shapes we emit; LangFuse stores them. Documented so the mapping is explicit.

### Trace

One per top-level workflow execution (typically one refund case, keyed by `correlation_id`).

| Attribute | Source | FR |
|-----------|--------|----|
| `id` / trace id | W3C trace-id derived from first envelope (or new root) | FR-001/010 |
| `name` | top operation (e.g., `refund.case`) | FR-003 |
| `metadata.correlation_id` | `EventEnvelope.correlation_id` | FR-011 |
| `metadata.causation_id` | `EventEnvelope.causation_id` | FR-011 |
| `tags` | `[agent_id, tenant_id, environment]` | FR-004 grouping |

### Span (named operations — FR-013)

Exactly eight named spans. Five from foundation seams, three from the `@traced` decorator on pure
engine entry points (R12). LLM is the `llm.invoke` generation specialization below.

| Span name | Seam / entry point | FR |
|-----------|--------------------|----|
| `event.consume` | `transport/consumer.py` handler dispatch | FR-002/013 |
| `kafka.publish` | `transport/publisher.py` `publish()`/`publish_raw()` | FR-002/013 |
| `a2a.task.send` | `runtime/client.py` `A2AClient.submit()` | FR-002/013 |
| `a2a.task.receive` | `runtime/runtime.py` handler dispatch | FR-002/013 |
| `llm.invoke` | `llm/runtime.py` `reason()` (generation) | FR-005/013 |
| `ticket.classify` | `ticket_classifier.classify` via `@traced` | FR-013 |
| `policy.evaluate` | `rules_engine.evaluate` / `scoring.assess_signals` via `@traced` | FR-013 |
| `case.decision` | `decision_engine.decide` via `@traced` | FR-013 |

**Common span fields**: `parent` (extracted `traceparent`, else new root — FR-001/010);
`start`/`end`/`duration`; `status` `ok`/`error` (+ exception detail — FR-003).

**FR-014 attributes** (assembled in `observability/attributes.py`, included **where applicable** to the
operation; IDs + non-PII metadata only — R15):

| Attribute | Source | Notes |
|-----------|--------|-------|
| `correlation_id` | envelope | always (FR-011) |
| `causation_id` | envelope | consume spans (FR-011) |
| `event_id` | envelope | transport spans |
| `case_id` | `ResolutionCase` / task input | case-scoped spans |
| `ticket_id` | `ResolutionCase` / task input | classify/decision spans |
| `task_id` | `TaskRequest`/`TaskResult` | a2a/llm spans |
| `capability` | `TaskRequest.capability` | a2a/policy spans |
| `agent_id` | calling/performing agent | always |
| `model_id` | `AssistiveResult.model_id` | `llm.invoke` only |
| `topic` | resolved Kafka topic | transport spans |

### Generation (LLM operation) — specialization of Span

One per `LLMRuntime.reason()` call.

| Attribute | Source (008 object) | FR |
|-----------|---------------------|----|
| `model` | `AssistiveResult.model_id` / `RawCompletion.model_id` | FR-005 |
| `usage.input` | `TokenUsage.input_tokens` | FR-005 |
| `usage.output` | `TokenUsage.output_tokens` | FR-005 |
| `usage.cache_read` | `TokenUsage.cache_read_tokens` | FR-005 |
| `usage.cache_write` | `TokenUsage.cache_write_tokens` | FR-005 |
| `metadata.cache_hit` | `AssistiveResult.cache_hit` / `RawCompletion.cache_hit` | FR-005 |
| `metadata.task_kind` | `AssistiveRequest.task_kind` | FR-003 |
| `metadata.agent_id` | `AssistiveRequest.agent_id` | FR-004 |
| `latency` | `AssistiveResult.latency_ms` | FR-005 |
| `prompt` (link) | LangFuse prompt name+version (R6) or `None` on fallback | prompts |
| `level`/`status_message` | `AssistiveResult.failure_reason` if any | FR-003 |
| `metadata.provider_mode` | `stub` / `bedrock` / `agentcore` | stub edge case |
| `input` (prompt) | rendered prompt, **`Redactor.scrub`-ed** before export | FR-017/SC-007 |
| `output` (completion) | model completion, **`Redactor.scrub`-ed** before export | FR-017/SC-007 |

> PII rule: `input`/`output` are sent only after redaction (default), and only as raw text if the
> developer sets `LOG_RAW_LLM_PROMPTS` / `LOG_RAW_LLM_OUTPUTS` (R15). Span attributes never carry PII.

### Score (evaluation) — attached to a Generation/Trace

Programmatic, non-binding (R7).

| Score name | Type | Source | Range |
|------------|------|--------|-------|
| `schema_valid` | numeric/boolean | validate-and-repair loop result | 0/1 |
| `used_fallback` | numeric/boolean | `AssistiveResult` fallback flag | 0/1 |
| `cache_hit` | numeric/boolean | `AssistiveResult.cache_hit` | 0/1 |
| `latency_ms` | numeric | `AssistiveResult.latency_ms` | ≥0 |
| (UI) `llm_judge_*` | numeric/categorical | LangFuse LLM-as-judge over seeded dataset | configured in UI |

**Invariant**: no Score value is ever read back by agent code; scores are write-only observability.

## Kafka-side entities (system of record — FR-018)

These live in Kafka, not LangFuse. They are the replayable business record; LangFuse is the debug view.

### AuditEvent (logical names → existing trail)

| Logical name | Realization | Topic |
|--------------|-------------|-------|
| `audit.agent-task.requested` | `write_task_audit(outcome="requested")` | `TOPIC_AUDIT` (`agent.audit.v1`) |
| `audit.agent-task.completed` | `write_task_audit(outcome="completed")` | `TOPIC_AUDIT` (`agent.audit.v1`) |
| `audit.llm.invocation.completed` | existing `emit_llm_invocation_event` | `audit.llm.invocation.completed` |
| `audit.policy.decision.completed` | **new** `write_audit` at decision boundary | `TOPIC_AUDIT` (existing topic, no new contract) |

### Heartbeat (the single new event)

`system.agent.heartbeat` — emitted periodically from the foundation `runtime.serve()` loop.

| Field | Type | Notes |
|-------|------|-------|
| `agent_id` | `str` | which agent is alive |
| `emitted_at` | `datetime` | timestamp |
| `interval_s` | `float` | configured cadence (diagnostic) |

- Topic: new dedicated `TOPIC_HEARTBEAT` (not the compacted audit topic).
- Liveness only; **never** consumed by domain logic (Principle III); not a coordination back-channel.

## Metric views (derived in LangFuse dashboards — not stored by us)

FR-004/FR-007 are satisfied by LangFuse dashboards aggregating the above, grouped by the `agent_id`
tag/metadata:

| Metric (spec) | Derivation |
|---------------|------------|
| per-agent request count (FR-004) | count of spans grouped by `agent_id` + operation |
| per-agent latency distribution (FR-004) | span duration percentiles grouped by `agent_id` |
| per-agent error count (FR-004) | count of spans with `status=error` by `agent_id` |
| LLM call count / token usage / latency / cache-hit rate (FR-005) | generation aggregates by `agent_id` |

## Relationships

```
EventEnvelope.trace_context ──(extract)──▶ OTel context
        │                                      │
     (inject on publish)                 (parent of)
        ▼                                      ▼
   Trace ──contains──▶ Span ──specializes──▶ Generation ──has──▶ Score
     │                                          │
  metadata.correlation_id/causation_id     prompt link (R6)
     │
  dashboards group by agent_id ▶ Metric views (FR-004/007)
```

## State transitions

No domain state machine is introduced. The only lifecycle is a span's `start → end(ok|error)`,
managed by the seam context managers and always closed (including on exception) so a failed operation
yields an `error` span rather than a lost trace (FR/AC US1-2).
