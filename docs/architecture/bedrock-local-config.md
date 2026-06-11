# Bedrock & Local Provider Configuration

Authoritative sources: `specs/008-agent-llm-runtime/plan.md`,
`specs/008-agent-llm-runtime/data-model.md`,
`src/agent_foundation/llm/config.py`.

## Overview

The runtime defaults to the deterministic offline **stub** provider (no AWS credentials, no network).
Switching to real Bedrock or local AgentCore is a single env-var change with zero code changes at
call sites.

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `AGENT_LLM_MODE` | `stub` | Provider selection: `stub`, `bedrock`, or `agentcore`. |
| `AGENT_LLM_MODEL` | `anthropic.claude-3-5-sonnet-20241022-v2:0` | Bedrock model id override. |
| `AGENT_LLM_REGION` | `us-east-1` (via `AWS_REGION`) | AWS region for Bedrock calls. |
| `AGENT_LLM_TIMEOUT_SECONDS` | `8.0` | Per-call timeout (seconds). |
| `AGENT_LLM_MAX_REPAIRS` | `2` | Max validate-and-repair retries for structured output. |
| `AGENT_LLM_BOOTSTRAP_SERVERS` | `localhost:9092` | Kafka broker for the idempotency store. |
| `AGENT_LLM_PROFILES_PATH` | `config/model-profiles.yaml` | Path to the per-agent profile YAML. |
| `AGENT_LLM_CONFIG_FILE` | `config/agent_llm.yaml` | Legacy layered config path. |
| `BEDROCK_MODEL_ID` | (fallback for `AGENT_LLM_MODEL`) | Legacy Bedrock model id. |
| `BEDROCK_TIMEOUT_SECONDS` | (fallback for timeout) | Legacy timeout. |
| `BEDROCK_TEMPERATURE` | `0.0` | Temperature override. |
| `BEDROCK_MAX_TOKENS` | `1024` | Max tokens override. |
| `LOG_RAW_LLM_PROMPTS` | `false` | Log full prompt text (disable in production). |
| `LOG_RAW_LLM_OUTPUTS` | `false` | Log full model output text. |
| `REDACT_PII` | `true` | Redact PII from audit records and logs. |

## ModelProvider protocol

All providers implement the `ModelProvider` protocol defined in
`src/agent_foundation/llm/providers/base.py`:

```python
@runtime_checkable
class ModelProvider(Protocol):
    async def invoke(self, prompt: str, profile: object) -> RawCompletion: ...
```

`RawCompletion` carries `text`, `token_usage` (input/output/cache tokens), `cache_hit`, and
`model_id`. The runtime never touches provider internals -- it only sees `RawCompletion`.

## Provider selection

`select_provider(mode)` in `src/agent_foundation/llm/providers/__init__.py` returns the appropriate
provider:

| Mode | Provider class | Requirements |
|------|---------------|--------------|
| `stub` | `StubProvider` | None (offline, deterministic) |
| `bedrock` | `BedrockProvider` | `pip install -e '.[llm]'` + AWS credentials |
| `agentcore` | `AgentCoreProvider` | `pip install bedrock-agentcore` + AWS credentials |

## Bedrock provider

`BedrockProvider` creates a boto3 `bedrock-runtime` client on first use with the configured region,
timeouts, and retry policy. The model id is supplied per-call from the resolved `ModelProfile`, not
baked into the client. Credentials resolve via the standard boto3 provider chain (env vars, AWS
profile, instance role).

Prompt caching: the provider reads `cache_read_input_tokens` and `cache_creation_input_tokens` from
the Bedrock response `usage` block and populates `TokenUsage.cache_read_tokens` /
`cache_write_tokens`. A `cache_hit` flag is set when `cache_read_tokens > 0`.

## Per-agent ModelProfile resolution

`resolve_profile(agent_id, task_kind)` merges configuration from multiple layers (highest priority
last):

1. **Hardcoded registry** -- `_PROFILE_REGISTRY` in `config.py`, keyed by `(agent_id, TaskKind)`.
2. **YAML config** -- `config/model-profiles.yaml`, with `default:` and per-agent sections.
3. **Environment overrides** -- `AGENT_LLM_MODE`, `AGENT_LLM_MODEL`, `AGENT_LLM_REGION`,
   `AGENT_LLM_TIMEOUT_SECONDS`, `AGENT_LLM_MAX_REPAIRS`.

The `ModelProfile` carries:

```python
class ModelProfile(BaseModel):
    mode: LLMProvider = "stub"        # stub | bedrock | agentcore
    model_id: str = "anthropic.claude-3-5-sonnet-20241022-v2:0"
    region: str | None = None
    temperature: float = 0.0
    max_tokens: int = 1024
    top_p: float | None = None
    timeout_seconds: float = 8.0
    max_repairs: int = 2
```

### YAML profile example (`config/model-profiles.yaml`)

```yaml
default:
  provider: bedrock
  region: us-east-1
  model_id: anthropic.claude-3-5-sonnet-20241022-v2:0
  temperature: 0.0
  max_tokens: 1024

agents:
  customer-resolution-agent:
    model_id: anthropic.claude-3-5-sonnet-20241022-v2:0
    max_tokens: 1200

  billing-entitlement-agent:
    model_id: anthropic.claude-3-haiku-20240307-v1:0
    max_tokens: 600

  risk-fraud-agent:
    model_id: anthropic.claude-3-haiku-20240307-v1:0
    max_tokens: 600
```

Each agent section inherits from `default:` and overrides specific fields. The CRA uses Sonnet for
richer classification and drafting; billing and risk use Haiku for lightweight summaries.

## Switching from offline to Bedrock

```bash
# Offline (default) -- no credentials needed
export AGENT_LLM_MODE=stub
pytest tests/unit/llm/ -q

# Bedrock -- requires AWS credentials
pip install -e '.[llm]'
export AGENT_LLM_MODE=bedrock
export AGENT_LLM_REGION=us-east-1
pytest tests/integration/llm/ -q -k bedrock
```

No calling-agent code changes between stub and Bedrock. The same `runtime.reason(request)` call
works in both modes.

## Related docs

- [agent-llm-runtime.md](./agent-llm-runtime.md) -- runtime overview
- [agentcore-local-bedrock.md](./agentcore-local-bedrock.md) -- local AgentCore mode
