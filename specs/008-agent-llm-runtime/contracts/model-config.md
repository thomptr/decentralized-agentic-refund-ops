# Contract: Model Configuration & Per-Agent Profiles

All model selection is config-supplied, never hard-coded at call sites (FR-017). Defaults make the
system run fully offline on the stub model with no AWS (FR-014, SC-006).

## Environment variables

| Variable | Default | Meaning |
|----------|---------|---------|
| `AGENT_LLM_MODE` | `stub` | `stub` \| `bedrock` \| `agentcore`. Selects the provider. |
| `AGENT_LLM_MODEL` | latest capable Claude on Bedrock | Model id used by bedrock/agentcore modes. |
| `AGENT_LLM_REGION` | unset | AWS region for Bedrock. |
| `AGENT_LLM_TIMEOUT_SECONDS` | `8.0` | Per-call wall-clock budget (FR-009). |
| `AGENT_LLM_MAX_REPAIRS` | `2` | Schema-repair retry budget (FR-006). |
| `AGENT_LLM_BOOTSTRAP_SERVERS` | existing Kafka bootstrap | Result store + audit transport (reused). |

Switching `AGENT_LLM_MODE` from `stub` to `bedrock`/`agentcore` MUST require **no** change to any
calling-agent code (US8.2, FR-014).

## `ModelProfile`

A profile bundles `mode`, `model_id`, `region`, decoding params (`temperature` default `0.0` for
deterministic decoding, `max_tokens`, `top_p`), `timeout_seconds`, and `max_repairs`. See
data-model.md §7.

## Profile registry

```python
def resolve_profile(agent_id: str, task_kind: TaskKind) -> ModelProfile: ...
```

- Returns a per-`(agent_id, task_kind)` profile when registered, else the default profile.
- Env vars override registry/default fields.
- Lets CRA drafting differ from billing/risk summarization (e.g. higher `max_tokens` for drafting)
  entirely via config. (FR-017/018, R10)

### Default registered profiles (illustrative, overridable)

| agent_id | task_kind | notable overrides |
|----------|-----------|-------------------|
| `customer-resolution-agent` | `classify` | `max_tokens=256` |
| `customer-resolution-agent` | `draft_response` | `max_tokens=512` |
| `billing-entitlement-agent` | `summarize_reasoning` | `max_tokens=200` |
| `risk-fraud-agent` | `summarize_reasoning` | `max_tokens=200` |

All four default to `temperature=0.0` (replay-determinism aid, R5) and the global timeout/repair
budgets unless overridden.

## YAML Profile File

`config/model-profiles.yaml` (path overridable via `AGENT_LLM_PROFILES_PATH`) provides an editable,
file-driven source of per-agent profiles. Structure:

```yaml
default:
  provider: bedrock
  region: us-east-1
  model_id: anthropic.claude-3-5-sonnet-20241022-v2:0
  temperature: 0.0
  max_tokens: 1024

agents:
  customer-resolution-agent:
    max_tokens: 1200
  billing-entitlement-agent:
    model_id: anthropic.claude-3-haiku-20240307-v1:0
    max_tokens: 600
```

A missing agent profile falls back to `default`. Env vars override YAML values.

## Layered Config Loader

`load_model_config(agent_id) -> BedrockModelConfig` resolves config by overlaying:
1. **Defaults** (stub, offline)
2. **YAML profile** (`config/agent_llm.yaml` via `AGENT_LLM_CONFIG_FILE`)
3. **Environment variables** (`AGENT_LLM_*`, Bedrock shorthands)
4. **Runtime overrides** (`register_runtime_override(agent_id, ...)`)

Missing required fields (e.g. `model_id` for bedrock mode) raise `ModelConfigError`.

## Safety & Redaction Controls

| Variable | Default | Meaning |
|----------|---------|---------|
| `LOG_RAW_LLM_PROMPTS` | `false` | Raw prompt text is NOT logged by default. |
| `LOG_RAW_LLM_OUTPUTS` | `false` | Raw model output text is NOT logged by default. |
| `REDACT_PII` | `true` | PII scrubbed from logs, audit records, and UI by default. |

Secure-by-default: omitted env vars yield the safe defaults. Required for portfolio screenshots.

## Optional LLM Audit Events

| Variable | Default | Meaning |
|----------|---------|---------|
| `AGENT_LLM_AUDIT_EVENTS_ENABLED` | `false` | Opt-in event publication on dedicated topics. |
| `AGENT_LLM_AUDIT_LOG_RAW_PROMPTS` | `false` | Raw prompts never emitted unless explicitly true. |

When enabled, each `reason()` call emits one `completed` or `failed` event on:
- `local.audit.llm.invocation.completed.v1`
- `local.audit.llm.invocation.failed.v1`

Default-off keeps runtime behavior, the offline guarantee (SC-006), and the FR-015 default surface
unchanged.
