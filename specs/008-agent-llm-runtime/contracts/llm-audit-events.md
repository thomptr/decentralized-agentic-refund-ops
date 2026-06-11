# Contract: Optional LLM Audit Events

Two **observability-only** event types the runtime optionally emits around each assistive invocation.

## Events

| Event type | Topic |
|------------|-------|
| `audit.llm.invocation.completed` | `local.audit.llm.invocation.completed.v1` |
| `audit.llm.invocation.failed` | `local.audit.llm.invocation.failed.v1` |

## Payload Fields

Both payloads carry:

| Field | Type | Notes |
|-------|------|-------|
| `agent_id` | `str` | Calling agent identity |
| `model_id` | `str \| None` | Model used (None for stub/fallback) |
| `prompt_id` | `str` | Prompt reference/hash, NOT raw prompt |
| `task_kind` | `str` | classify, draft_response, summarize_reasoning, etc. |
| `correlation_id` | `UUID` | Case identity |
| `causation_id` | `UUID` | Triggering step |
| `latency_ms` | `int` | Step latency |
| `token_usage` | `dict \| None` | Token counts when available |
| `cache_hit` | `bool` | Prompt-cache reuse |
| `reasoning_path` | `str` | model, cache, or fallback |
| `recorded_at` | `datetime` | UTC timestamp |
| `raw_prompt` | `str \| None` | Only set when `AGENT_LLM_AUDIT_LOG_RAW_PROMPTS=true` |

The `failed` payload also carries `failure_reason: str`.

## Config Flags

| Variable | Default | Meaning |
|----------|---------|---------|
| `AGENT_LLM_AUDIT_EVENTS_ENABLED` | `false` | Must be `true` for any events to publish |
| `AGENT_LLM_AUDIT_LOG_RAW_PROMPTS` | `false` | Raw prompt text only appears when explicitly set |

## FR-015 Rationale

These events carry no coordination semantics, add no agent or supervisor, and are published only when
explicitly enabled. They are an additional, opt-in projection of the same reasoning step already
recorded by the always-on `ReasoningAuditRecord` on `agent.audit.v1`. Default-off keeps runtime
behavior and the offline guarantee (SC-006) unchanged.
