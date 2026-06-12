# Contract: LLM Generation Attributes & Scores

Satisfies FR-005 (LLM-specific metrics: call count, token usage, latency, cache-hit) and the stub
edge case. Hook point: `LLMRuntime.reason()` in `src/agent_foundation/llm/runtime.py`.

## Wrapping `reason()`

```text
generation("llm.invoke", agent_id=request.agent_id, model=profile.model_id):
    raw = await provider.invoke(prompt, profile)      # existing 008 call
    result = validate_and_repair(raw, schema)         # existing 008 logic
    gen.set_usage(raw.token_usage.input_tokens, raw.token_usage.output_tokens,
                  raw.token_usage.cache_read_tokens, raw.token_usage.cache_write_tokens)
    gen.set_cache_hit(raw.cache_hit)
    gen.set_attribute("provider_mode", config.mode)   # stub|bedrock|agentcore
    gen.set_attribute("task_kind", request.task_kind)
    gen.set_attribute("latency_ms", result.latency_ms)
    # PII (FR-017/SC-007): capture prompt/completion ONLY after redaction (default), raw only if LOG_RAW_*
    gen.set_input(redactor.scrub(prompt) if config.redact_pii else prompt)   if config.log_raw_prompts or config.redact_pii else None
    gen.set_output(redactor.scrub(result.text) if config.redact_pii else result.text) if config.log_raw_outputs or config.redact_pii else None
    if result.failure_reason: gen.set_status("error", result.failure_reason)
    emit_scores(result)                                # see evaluation-scores.md
```

The span name is the canonical `llm.invoke` (FR-013). Prompt/completion capture (FR-016) passes the
existing 008 `Redactor` before export (FR-017/SC-007); span attributes never carry PII.

The wrap **reads** existing 008 fields only — it adds no new measurement:

| Generation attr | Existing source |
|-----------------|-----------------|
| `model` | `ModelProfile.model_id` / `RawCompletion.model_id` / `AssistiveResult.model_id` |
| `usage.input/output/cache_read/cache_write` | `TokenUsage` (`llm/result.py`) |
| `cache_hit` | `RawCompletion.cache_hit` / `AssistiveResult.cache_hit` |
| `latency_ms` | `AssistiveResult.latency_ms` |
| `task_kind` / `agent_id` | `AssistiveRequest` |
| `provider_mode` | `RuntimeConfig.mode` |
| status / message | `AssistiveResult.failure_reason` |
| prompt link | LangFuse prompt name+version (see prompt-management.md) or none |

## Stub edge case

When `provider_mode == "stub"`, the generation is still emitted with `provider_mode=stub` and
zero/no token usage, so traces show the deterministic fallback invocation distinctly (spec edge case:
"LLM runtime falls back to the deterministic stub").

## Non-interference invariants

- The generation wrap MUST NOT change `reason()`'s return value, idempotency key, audit record, or
  control flow. The existing `ReasoningAuditRecord` emission is unchanged (it remains the system of
  record); the generation is an additional, out-of-band view.
- If observability is off, `reason()` is byte-identical to 008.
