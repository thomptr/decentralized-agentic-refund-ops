# LLM Reasoning Audit and Replay

Authoritative sources: `specs/008-agent-llm-runtime/plan.md`,
`specs/008-agent-llm-runtime/data-model.md`,
`src/agent_foundation/llm/audit.py`, `src/agent_foundation/llm/audit_events.py`.

## Overview

Every assistive reasoning step emits a `ReasoningAuditRecord` through the existing audit subsystem.
The record links the LLM invocation to the case via `correlation_id` / `causation_id`, carries token
usage, latency, model identity, and a compact result summary -- enough to reconstruct the reasoning
chain without a live model. PII is redacted by default before the record is written.

## ReasoningAuditRecord

```python
class ReasoningAuditRecord(BaseModel):
    agent_id: str                      # e.g. "customer-resolution-agent"
    correlation_id: UUID               # case correlation id
    causation_id: UUID                 # causing event id
    task_kind: TaskKind                # classify | extract_intent | draft_response | summarize_reasoning
    model_id: str | None               # e.g. "stub", bedrock model id
    model_params: dict[str, Any]       # temperature, max_tokens from the resolved profile
    prompt_ref: str                    # content-addressed prompt hash or template@version
    grounding_digest: dict[str, Any]   # compact digest of grounding inputs (truncated at 200 chars)
    reasoning_path: ReasoningPath      # model | cache | fallback
    result_summary: dict[str, Any]     # compact serialization of the validated value
    token_usage: TokenUsage | None     # input/output/cache_read/cache_write token counts
    cache_hit: bool                    # True if served from idempotency cache
    latency_ms: int                    # wall-clock time in milliseconds
    outcome: str                       # produced | served_from_cache | fallback | unable_to_produce
    failure_reason: FailureReason | None  # set on fallback paths
    recorded_at: datetime              # UTC timestamp
```

### Outcome mapping

| ReasoningPath | failure_reason | outcome |
|---------------|---------------|---------|
| `model` | None | `produced` |
| `cache` | None | `served_from_cache` |
| `fallback` | None | `fallback` |
| `fallback` | set | `unable_to_produce` |

## Audit emission

`write_reasoning_audit(publisher, record)` wraps the record in an `EventEnvelope` with
`event_type="agent.audit.v1"` and publishes it to the existing `TOPIC_AUDIT` topic. The envelope
carries the same `correlation_id` / `causation_id` as the reasoning step, so it appears in the
case's causal timeline alongside the deterministic events.

The audit write is best-effort: if publishing fails, a warning is logged but the assistive result is
still returned to the caller. Audit failures never block the agent's binding verdict.

## Querying by correlation_id

Because each reasoning audit envelope carries the case's `correlation_id`, the existing
`audit.store.query_by_correlation(broker_url, correlation_id)` returns reasoning steps alongside
all other audit entries. The `event_type="agent.llm.reasoning.v1"` inner envelope distinguishes
reasoning records from standard workflow audit records.

The `trace_case` CLI and demo UI timeline both surface reasoning steps when present, attributed with
agent identity, model path, and outcome.

## Idempotent replay

The `AssistiveResultStore` (LRU + compacted Kafka topic) caches results by `idempotency_key`. On
replay:

1. The agent re-processes the same input event, constructing an identical `AssistiveRequest` with
   the same `grounding_inputs`.
2. The `idempotency_key` is derived deterministically:
   `{correlation_id}:{task_kind}:{sha256(grounding_inputs)[:16]}`.
3. The store returns the cached result with `reasoning_path=cache` and zero model invocations.
4. The audit record shows `outcome=served_from_cache`.

This ensures replay-stable results: replaying a case always produces the same assistive output
without hitting the model again, and the audit trail records that the result was served from cache.

## Optional LLM audit events

In addition to the `ReasoningAuditRecord` (always emitted via the audit subsystem), the runtime can
emit fine-grained observability events. These are disabled by default and intended for production
monitoring, not replay.

| Event type | Payload class | Emitted when |
|------------|--------------|--------------|
| `audit.llm.invocation.completed` | `LlmInvocationCompletedPayload` | Successful invocation |
| `audit.llm.invocation.failed` | `LlmInvocationFailedPayload` | Fallback path with failure |

Enable with `AGENT_LLM_AUDIT_EVENTS_ENABLED=true`. Set `AGENT_LLM_AUDIT_LOG_RAW_PROMPTS=true` to
include the rendered prompt in the event payload (disabled by default for safety).

## PII redaction

When `REDACT_PII=true` (the default), the `Redactor` scrubs the `grounding_digest` and
`result_summary` fields before the audit record is written. Patterns redacted:

- Email addresses -> `[REDACTED_EMAIL]`
- Credit card numbers -> `[REDACTED_CARD]`
- SSNs -> `[REDACTED_SSN]`
- Phone numbers -> `[REDACTED_PHONE]`
- Long digit sequences -> `[REDACTED_NUMBER]`

## Related docs

- [agent-llm-runtime.md](./agent-llm-runtime.md) -- overall runtime flow
- [replay-and-idempotency.md](./replay-and-idempotency.md) -- the three existing idempotency layers
- [structured-llm-outputs.md](./structured-llm-outputs.md) -- how validation failures feed the audit
