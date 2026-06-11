# Contract: `ModelProvider` Protocol + Bedrock Mapping

The provider seam is the single place where the offline/cloud switch lives (FR-014, R2). The runtime
depends only on this protocol; concrete providers are selected from config.

## Protocol

```python
class ModelProvider(Protocol):
    async def invoke(self, prompt: RenderedPrompt, profile: ModelProfile) -> RawCompletion: ...
```

- `RenderedPrompt` carries the cache-eligible stable prefix and the variable grounding suffix.
- `RawCompletion` = `{ text, token_usage, cache_hit, model_id }` (data-model.md §9).
- `invoke()` MUST NOT swallow timeouts — the runtime wraps it in `asyncio.wait_for` (FR-009). It
  SHOULD raise a typed `ProviderError` on unreachable/throttled/error so the runtime can fall back.

## Selection

`select_provider(profile.mode)` → `stub` | `bedrock` | `agentcore`. Default `stub`.

## Stub provider (default, offline)

See `stub-model-contract.md`. Deterministic, no network, no credentials.

## Bedrock provider

- Uses boto3 `bedrock-runtime` (the AWS SDK — constitution constraint, FR-002).
- Calls the Anthropic Messages API (`invoke_model` / `converse`) with `model_id` from the profile.
- **Prompt caching (FR-013)**: marks the stable prefix (system instructions + output schema +
  examples) with a cache breakpoint (`cache_control: {"type":"ephemeral"}` / `cachePoint`); the
  variable grounding suffix is uncached. Reads `usage` including
  `cache_read_input_tokens` / `cache_creation_input_tokens` → `TokenUsage`; sets `cache_hit` from a
  non-zero cache read. (US7, SC-008)
- **Structured output**: instructs JSON output matching the schema (tool-use or JSON instruction);
  raw text returned for the runtime's validate-and-repair loop (the provider does not validate).
- **Deterministic decoding**: honors `temperature` (default `0.0`) from the profile (R5).

## AgentCore provider (local CLI execution)

- Routes the call through the local `bedrock_agentcore` runtime the agents already expose
  (`agentcore_app.py`); import-guarded so the package imports without `bedrock-agentcore` installed
  (mirrors existing entrypoints). (feature input, R9)
- Same `RawCompletion` shape; same validate-and-repair downstream.

## Error contract

| Condition | Provider behavior | Runtime response |
|-----------|-------------------|------------------|
| Timeout (exceeds `profile.timeout_seconds`) | (cancelled by `wait_for`) | `fallback`, `failure_reason=timeout` |
| Unreachable / throttled / 5xx | raise `ProviderError` | `fallback`, `failure_reason=model_unavailable` |
| Context limit exceeded | raise `ProviderError(context)` | `fallback`, `failure_reason=context_limit_exceeded` |
| Valid response, bad JSON/schema | return `RawCompletion` | repair up to `max_repairs`, then `fallback`/`unable_to_produce` |

The binding decision is unaffected in every row (deterministic engine owns it). (FR-009, US5)
