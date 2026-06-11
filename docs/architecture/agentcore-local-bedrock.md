# Local AgentCore Mode

Authoritative sources: `specs/008-agent-llm-runtime/plan.md`,
`src/agent_foundation/llm/providers/agentcore.py`,
`src/agent_foundation/llm/config.py`.

## Overview

The `agentcore` provider mode lets developers run the same LLM reasoning calls against Bedrock
through the Amazon Bedrock AgentCore local development environment. It delegates to the
`BedrockProvider` under the hood, adding the AgentCore-specific client initialization path.

## Enabling AgentCore mode

```bash
pip install bedrock-agentcore
export AGENT_LLM_MODE=agentcore
export AGENT_LLM_REGION=us-east-1
```

No code changes at agent call sites. `build_runtime()` selects `AgentCoreProvider` via
`select_provider("agentcore")`.

## When to choose each mode

| Mode | When to use | Requirements |
|------|-------------|--------------|
| `stub` | Local development, CI, unit tests, demos. Deterministic, offline, zero-cost. | None |
| `bedrock` | Integration tests with real models, pre-production validation, cost analysis. | `pip install -e '.[llm]'` + AWS credentials |
| `agentcore` | Local AgentCore dev environment where Bedrock access is proxied through the AgentCore runtime. | `pip install bedrock-agentcore` + AWS credentials |

### Stub (default)

The `StubProvider` returns deterministic, schema-shaped output derived from a SHA-256 hash of the
prompt. Identical inputs produce identical output; meaningfully different grounding produces
different output. No network calls, no credentials, no cost. All unit tests and the offline demo run
against stub.

### Bedrock

The `BedrockProvider` calls Bedrock via boto3 with prompt caching support. Use for validating real
model behavior, measuring token usage, and testing cache hit rates. Requires AWS credentials
resolved via the standard boto3 provider chain (env vars, `~/.aws/credentials`, instance role).

### AgentCore

The `AgentCoreProvider` wraps `BedrockProvider` to run under the AgentCore local development
runtime. Use when developing within an AgentCore project that manages Bedrock access and agent
lifecycle. The provider requires the `bedrock-agentcore` package and valid AWS credentials.

## Provider architecture

```
AgentCoreProvider
  |-- delegates to BedrockProvider
        |-- boto3 bedrock-runtime client
```

`AgentCoreProvider.invoke()` calls `BedrockProvider.invoke()` directly. Credential errors
(`ProviderCredentialsError`) propagate with actionable messages. Other errors are wrapped in
`ProviderError`.

## AgentCore local dev step

1. Install AgentCore: `pip install bedrock-agentcore`
2. Set mode: `export AGENT_LLM_MODE=agentcore`
3. Configure region: `export AGENT_LLM_REGION=us-east-1`
4. Ensure AWS credentials are available (`aws configure` or env vars)
5. Run the agents normally -- the runtime routes LLM calls through AgentCore

```bash
# Verify the provider loads
python -c "from agent_foundation.llm import select_provider; p = select_provider('agentcore'); print(type(p))"
```

## Related docs

- [agent-llm-runtime.md](./agent-llm-runtime.md) -- runtime overview
- [bedrock-local-config.md](./bedrock-local-config.md) -- env vars and profile resolution
