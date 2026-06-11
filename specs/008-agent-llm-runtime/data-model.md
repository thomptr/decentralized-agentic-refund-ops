# Phase 1 Data Model: Agent LLM Runtime

All types are Pydantic v2 models (frozen where they are values) living under
`src/agent_foundation/llm/`. None of these are wire/event contracts — they are in-process types plus
one audit payload that rides the **existing** `agent.audit.v1` topic. No new event contract or topic
is introduced (FR-015).

---

## 1. `AssistiveRequest` (`request.py`)

The in-process call an agent makes to the runtime. Trigger for a reasoning step; never a request to
decide a binding outcome.

| Field | Type | Notes |
|-------|------|-------|
| `task_kind` | `TaskKind` (enum) | `classify` \| `extract_intent` \| `draft_response` \| `summarize_reasoning` |
| `agent_id` | `str` | Calling agent identity; selects the model profile (R10) and attributes audit. |
| `correlation_id` | `UUID` | Case identity; ties the reasoning step into the case trace. |
| `causation_id` | `UUID` | The triggering event/step this reasoning was caused by. |
| `instructions` | `str` | Task instruction text (large, stable → cache-eligible prefix). |
| `grounding_inputs` | `dict[str, Any]` | Domain-scoped facts the model may reason over **only** (R4 grounding check). |
| `output_schema` | `type[BaseModel]` | Caller-supplied expected result shape / permitted value set. |
| `examples` | `list[dict] \| None` | Optional few-shot examples (stable → part of cache-eligible prefix). |
| `idempotency_key` | `str` | Supplied, or derived from `correlation_id + task_kind + hash(grounding_inputs)`. |
| `fallback` | `Callable[[], BaseModel]` | Caller's pre-LLM behavior, invoked on failure (R6). |

**Validation**: `instructions` non-empty; `output_schema` is a `BaseModel` subclass;
`grounding_inputs` JSON-serializable (so the audit record can reconstruct what was asked).

---

## 2. `TaskKind` (enum, `request.py`)

`classify`, `extract_intent`, `draft_response`, `summarize_reasoning`. Extensible; each maps to a
default prompt template and may map to a distinct model profile per agent (R10).

---

## 3. `AssistiveResult` (`result.py`)

The validated structured output the runtime returns. **Explicitly NOT a binding refund verdict.**

| Field | Type | Notes |
|-------|------|-------|
| `value` | `BaseModel` | Instance of the caller's `output_schema`, schema-/grounding-valid (R4). |
| `reasoning_path` | `ReasoningPath` | `model` \| `cache` \| `fallback` — always recorded (FR-010). |
| `token_usage` | `TokenUsage \| None` | Present for `model` path; `None` for `cache`/`fallback`. |
| `cache_hit` | `bool` | True when the prompt's stable prefix was served from prompt cache (US7). |
| `failure_reason` | `FailureReason \| None` | Set when `reasoning_path == fallback` or `unable_to_produce`. |
| `model_id` | `str \| None` | Model identity used (None for stub-as-fallback / pure fallback). |
| `latency_ms` | `int` | Wall-clock for the reasoning step. |

**State**: a result is exactly one of — **model-produced** (validated LLM output),
**served-from-cache** (replay of a recorded result), or **fallback** (pre-LLM behavior or
`unable_to_produce`). These three are always distinguishable (FR-010, US5.3).

---

## 4. `ReasoningPath` (enum, `result.py`)

`model`, `cache`, `fallback`. The third is further qualified by `FailureReason`.

---

## 5. `FailureReason` (enum, `result.py`)

`model_unavailable`, `timeout`, `invalid_output`, `missing_inputs`, `context_limit_exceeded`,
`unable_to_produce`. Recorded in the result and the audit record (US3/US5, edge cases).

---

## 6. `TokenUsage` (`result.py`)

| Field | Type | Notes |
|-------|------|-------|
| `input_tokens` | `int` | Prompt tokens billed. |
| `output_tokens` | `int` | Completion tokens. |
| `cache_read_tokens` | `int` | Tokens served from prompt cache (warm prefix). |
| `cache_write_tokens` | `int` | Tokens written to prompt cache (cold prefix). |

Surfaced in `AssistiveResult` and copied into the audit record (token usage tracking requirement).

---

## 7. `ModelProfile` (`config.py`)

Externally supplied settings that determine where/how reasoning is performed (FR-017).

| Field | Type | Default (stub) |
|-------|------|----------------|
| `mode` | `Literal["stub","bedrock","agentcore"]` | `stub` |
| `model_id` | `str` | latest capable Claude on Bedrock (cfg) |
| `region` | `str \| None` | from `AGENT_LLM_REGION` |
| `temperature` | `float` | `0.0` (deterministic decoding, R5) |
| `max_tokens` | `int` | task-appropriate (e.g. 512) |
| `top_p` | `float \| None` | None |
| `timeout_seconds` | `float` | `AGENT_LLM_TIMEOUT_SECONDS` (e.g. 8.0) |
| `max_repairs` | `int` | `AGENT_LLM_MAX_REPAIRS` (e.g. 2) |

**Profile registry**: `resolve_profile(agent_id, task_kind) -> ModelProfile`, with a default profile
plus env overrides. No values hard-coded into call sites (FR-017).

---

## 8. `RuntimeConfig` (`config.py`)

Process-level config read from environment: `AGENT_LLM_MODE`, `AGENT_LLM_MODEL`, `AGENT_LLM_REGION`,
`AGENT_LLM_TIMEOUT_SECONDS`, `AGENT_LLM_MAX_REPAIRS`, `AGENT_LLM_BOOTSTRAP_SERVERS` (reuses the
existing Kafka bootstrap for the result store + audit). Defaults make the whole system run offline on
the stub with no AWS (FR-014, SC-006).

---

## 9. `RawCompletion` (`providers/base.py`)

Provider return type before validation.

| Field | Type | Notes |
|-------|------|-------|
| `text` | `str` | Raw model output (expected JSON for structured tasks). |
| `token_usage` | `TokenUsage` | Parsed from provider response. |
| `cache_hit` | `bool` | Whether the stable prefix hit the prompt cache. |
| `model_id` | `str` | Concrete model invoked. |

---

## 10. `ReasoningAuditRecord` (`audit.py`)

Immutable, correlated record of one reasoning step — written through the existing audit subsystem as
an `AuditPayload` on `agent.audit.v1` (no new topic). Distinguishable from the binding decision
(FR-011/012).

| Field | Type | Notes |
|-------|------|-------|
| `agent_id` | `str` | Calling agent. |
| `correlation_id` | `UUID` | Case identity (query key). |
| `causation_id` | `UUID` | Triggering step (causal order). |
| `task_kind` | `TaskKind` | What was asked. |
| `model_id` | `str \| None` | Model + provider mode. |
| `model_params` | `dict` | Decoding params (temperature, max_tokens, …). |
| `prompt_ref` | `str` | Hash/reference of the rendered prompt — enough to reconstruct the ask (FR-012). |
| `grounding_digest` | `dict` | Compact, model-free record of the grounding inputs supplied. |
| `reasoning_path` | `ReasoningPath` | model / cache / fallback. |
| `result_summary` | `dict` | Validated result (or its summary). |
| `token_usage` | `TokenUsage \| None` | When model-produced. |
| `cache_hit` | `bool` | Prompt-cache reuse observability (US7, SC-008). |
| `latency_ms` | `int` | Step latency. |
| `outcome` | `str` | `produced` \| `served_from_cache` \| `fallback` \| `unable_to_produce`. |
| `failure_reason` | `FailureReason \| None` | When degraded. |
| `recorded_at` | `datetime` | UTC. |

Queryable by `correlation_id` via the existing `audit.store.query_by_correlation`, in causal order
with the rest of the case, with no live model required (SC-005).

---

## 11. `AssistiveResultStore` (`store.py`)

Idempotent record of completed assistive results (FR-007/008). Mirrors `IdempotencyTracker`: an
in-process LRU plus a compacted Kafka topic for durability across redelivery.

- `get(idempotency_key) -> AssistiveResult | None` — returns the recorded result on replay.
- `put(idempotency_key, result) -> None` — records the model-produced result.

A `get` hit short-circuits the model path entirely (zero re-invocation, SC-003) and is recorded as a
`cache` reasoning path in the audit trail.

---

## 12. `PromptTemplate` (`prompts.py`)

Renders a prompt as a **cache-eligible stable prefix** (instructions + output schema + examples) plus
a **variable suffix** (grounding inputs), so the prefix is eligible for prompt caching across calls
that share it (FR-013). Exposes the rendered prompt + a `prompt_ref` hash for the audit record.

---

## Relationships

```
AssistiveRequest ──(reason)──▶ LLMRuntime ──┬─▶ AssistiveResultStore.get  (cache → AssistiveResult)
                                            ├─▶ ModelProvider.invoke ─▶ RawCompletion
                                            │        (stub | bedrock | agentcore)
                                            ├─▶ structured.validate_and_repair ─▶ value: output_schema
                                            ├─▶ fallback() on failure ─▶ AssistiveResult(fallback)
                                            └─▶ audit.write(ReasoningAuditRecord)  [existing audit topic]
                                                       │
Binding decision (decision_engine / rules_engine / scoring) ── unchanged, deterministic ──┘
   (consumes AssistiveResult ONLY for classification/extraction/draft/summary, never as the verdict)
```

**Invariant**: no field of any binding decision is ever populated from an `AssistiveResult`; the
deterministic engines own every binding verdict (FR-003/004, SC-002).
