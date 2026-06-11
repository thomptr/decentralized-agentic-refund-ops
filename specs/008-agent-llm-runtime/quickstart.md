# Quickstart: Agent LLM Runtime — Validation Guide

This guide proves the runtime works end to end **offline** (stub model, no AWS), then shows how to
flip to real Bedrock. It validates each user story / success criterion without duplicating
implementation detail — see [data-model.md](./data-model.md) and [contracts/](./contracts/).

## Prerequisites

- Repo deps installed: `pip install -e '.[dev]'` (offline path needs nothing more).
- Kafka available for the audit + result-store reuse (the existing local stack / testcontainers, as
  in prior features). No AWS credentials required for any step below.
- Optional cloud path: `pip install -e '.[llm]'` and AWS credentials for the Bedrock step only.

## 0. Default mode is offline

```bash
echo "${AGENT_LLM_MODE:-stub}"   # → stub  (no AWS, no credentials)
```

Every step below runs with `AGENT_LLM_MODE=stub` unless stated otherwise. (SC-006)

## 1. Perform an assistive reasoning task (US1)

Run the runtime unit suite that drives a `classify` / `extract_intent` / `draft_response` /
`summarize_reasoning` call against the stub and asserts a populated, schema-valid result:

```bash
pytest tests/unit/llm/test_runtime_reason.py -q
```

**Expected**: a structured `AssistiveResult.value` conforming to the caller's `output_schema`;
meaningfully different grounding inputs yield meaningfully different results. (SC-001)

## 2. Binding decisions stay deterministic (US2 — the central guardrail)

```bash
pytest apps/agents/customer_resolution/tests/ -q -k "guardrail or no_supervisor"
pytest apps/agents/billing_entitlement/tests/ -q -k "guardrail or result_contract"
pytest apps/agents/risk_fraud/tests/ -q -k "guardrail or result_contract"
```

**Expected**: each agent's binding verdict (`decide` / `evaluate` / `assess_signals`) is unchanged
even when the stub is forced to emit a contradictory "decision". (SC-002)

## 3. Schema & domain bounds (US3)

```bash
pytest tests/unit/llm/test_structured_validation.py -q
```

**Expected**: forced out-of-schema / out-of-enum / hallucinated-fact stub output is repaired within
budget or rejected — an invalid `AssistiveResult` is never returned. (SC-001)

## 4. Idempotent on replay (US4)

```bash
pytest tests/unit/llm/test_idempotency_replay.py -q
```

**Expected**: re-issuing the same `idempotency_key` returns an identical `value`, triggers **zero**
additional model invocations, and records a `served_from_cache` audit step. (SC-003)

## 5. Safe degradation (US5)

```bash
pytest tests/unit/llm/test_fallback_paths.py -q
```

**Expected**: forced unreachable/timeout/persistently-invalid model returns a `fallback`
`AssistiveResult` with a recorded `failure_reason`, within the time budget, binding outcome
unaffected. (SC-004)

## 6. Audit end to end (US6)

Drive one assistive call, then query the audit trail by correlation id:

```bash
pytest tests/integration/llm/test_e2e_runtime_backed_agents.py -q -k audit
```

**Expected**: the reasoning step appears via `audit.store.query_by_correlation` with agent identity,
model/path, validated result, token usage, timestamp, and causal link — reconstructable with no live
model, distinguishable from the binding decision. (SC-005)

## 7. Prompt caching observable (US7)

```bash
pytest tests/unit/llm/test_prompt_cache.py -q
```

**Expected**: repeated calls sharing a large stable instruction block expose cache reuse in
reasoning metadata (`cache_hit`, `cache_read_tokens`) on warm calls. (SC-008)

## 8. Per-agent model profiles (FR-017/018)

```bash
pytest tests/unit/llm/test_model_profiles.py -q
```

**Expected**: `resolve_profile(agent_id, task_kind)` returns the registered per-agent profile;
`AGENT_LLM_*` env vars override it — no model selection hard-coded at call sites.

## 9. All three agents adopt the runtime (US-level, SC-007)

```bash
pytest tests/integration/llm/test_e2e_runtime_backed_agents.py -q
```

**Expected**: the end-to-end choreography passes with CRA (classify + draft), billing (reasoning
summary), and risk (reasoning summary) all routed through the runtime — each agent's published result
contract and downstream consumers unchanged. (SC-007)

## 10. Flip to real Bedrock (US8.2) — optional, requires AWS

```bash
pip install -e '.[llm]'
export AGENT_LLM_MODE=bedrock
export AGENT_LLM_REGION=us-east-1
export AGENT_LLM_MODEL=<bedrock-claude-model-id>
pytest tests/integration/llm/ -q -k bedrock   # skipped automatically without credentials
```

**Expected**: the same calls route to Bedrock with prompt caching enabled — **no calling-agent code
change** between stub and Bedrock. (US8.2, FR-014)

## 11. No new agent / contract / topic / orchestrator (SC-009)

Confirm by inspection: the feature adds only `src/agent_foundation/llm/` and in-place edits to the
three agents' assistive seams; the agent roster, event contracts, and Kafka topics are unchanged
before and after. The runtime is invoked only in-process. (FR-015, SC-009)

---

### Success-criteria coverage map

| Step | User Story | Success Criteria |
|------|-----------|------------------|
| 1 | US1 | SC-001 |
| 2 | US2 | SC-002 |
| 3 | US3 | SC-001 |
| 4 | US4 | SC-003 |
| 5 | US5 | SC-004 |
| 6 | US6 | SC-005 |
| 7 | US7 | SC-008 |
| 8 | FR-017/018 | — |
| 9 | all agents | SC-007 |
| 10 | US8 | SC-006 (offline default) / Bedrock opt-in |
| 11 | — | SC-009 |


---

## Developer Quickstart Snippets

The sections below show how to use the runtime from code.

### 12. build_runtime() + reason() — offline stub

```python
import asyncio
from uuid import uuid4
from pydantic import BaseModel
from agent_foundation.llm import (
    build_runtime, AssistiveRequest, TaskKind, AssistiveResult,
)

class TicketClassification(BaseModel):
    category: str
    needs_refund_review: bool

async def main():
    runtime = build_runtime()  # AGENT_LLM_MODE=stub (default, no AWS)

    request = AssistiveRequest(
        task_kind=TaskKind.classify,
        agent_id="customer-resolution-agent",
        correlation_id=uuid4(),
        causation_id=uuid4(),
        instructions="Classify the support ticket.",
        grounding_inputs={"subject": "Refund for order 12345", "body": "I want a refund."},
        output_schema=TicketClassification,
        fallback=lambda: TicketClassification(category="unknown", needs_refund_review=False),
    )

    result: AssistiveResult = await runtime.reason(request)
    print(result.value)             # TicketClassification(...)
    print(result.reasoning_path)    # "model" (or "cache" on replay)
    print(result.latency_ms)        # e.g. 2

asyncio.run(main())
```

### 13. config/model-profiles.yaml

The per-agent model profile YAML controls which model, token budget, and temperature each agent
uses. The file is loaded from `AGENT_LLM_PROFILES_PATH` (default `config/model-profiles.yaml`).

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
    max_tokens: 1200          # richer classify + draft

  billing-entitlement-agent:
    model_id: anthropic.claude-3-haiku-20240307-v1:0
    max_tokens: 600           # lightweight summaries

  risk-fraud-agent:
    model_id: anthropic.claude-3-haiku-20240307-v1:0
    max_tokens: 600
```

Each agent section inherits `default:` values and overrides specific fields. Environment variables
(`AGENT_LLM_MODEL`, `AGENT_LLM_REGION`, etc.) take highest priority.

### 14. invoke_structured usage

```python
from agent_foundation.llm import invoke_structured, select_provider, ModelProfile

provider = select_provider("stub")
profile = ModelProfile(max_repairs=2)

outcome = await invoke_structured(
    "Classify this ticket. GROUNDING_INPUTS: {\"subject\": \"Refund\"}",
    TicketClassification,
    provider=provider,
    profile=profile,
    grounding_inputs={"subject": "Refund"},
    max_repairs=2,
)

if outcome.ok:
    print(outcome.value)          # validated TicketClassification
else:
    print(outcome.error)          # StructuredError with attempt details
```

### 15. create_langgraph_llm_node usage

```python
from agent_foundation.llm import build_runtime, create_langgraph_llm_node, TextResult

runtime = build_runtime()

node = create_langgraph_llm_node(
    agent_id="risk-fraud-agent",
    prompt_template="Summarize the risk assessment for this case: {risk_signals}",
    output_schema=TextResult,
    runtime=runtime,
    task_kind="summarize_reasoning",
    state_key="risk_summary",
)

# Use in a LangGraph StateGraph:
# graph.add_node("summarize_risk", node)
# The node reads state["risk_signals"], writes state["risk_summary"].
```

### 16. Risk agent enrichment snippet

```python
from agent_foundation.llm import assist_or_fallback, TextResult

result = await assist_or_fallback(
    runtime,
    agent_id="risk-fraud-agent",
    task_kind="summarize_reasoning",
    correlation_id=case.correlation_id,
    causation_id=event.event_id,
    instructions="Summarize the fraud risk assessment.",
    grounding_inputs={
        "risk_level": assessment.risk_level,
        "signals": [s.model_dump() for s in assessment.signals],
        "score": assessment.score,
    },
    output_schema=TextResult,
    fallback=lambda: TextResult(text="Risk summary unavailable."),
)
# result.value.text -> "Low risk. No fraud signals detected."
# The binding verdict remains scoring.assess_signals() output.
```

### 17. Billing agent enrichment snippet

```python
result = await assist_or_fallback(
    runtime,
    agent_id="billing-entitlement-agent",
    task_kind="summarize_reasoning",
    correlation_id=case.correlation_id,
    causation_id=event.event_id,
    instructions="Summarize the billing eligibility analysis.",
    grounding_inputs={
        "eligible": analysis.eligible,
        "reason": analysis.reason,
        "refund_amount": str(analysis.refund_amount),
    },
    output_schema=TextResult,
    fallback=lambda: TextResult(text="Billing summary unavailable."),
)
# The binding eligibility check remains rules_engine.evaluate() output.
```

### 18. CRA classify + draft snippet

```python
# Step 1: Classify
classify_result = await assist_or_fallback(
    runtime,
    agent_id="customer-resolution-agent",
    task_kind="classify",
    correlation_id=ticket.correlation_id,
    causation_id=ticket.event_id,
    instructions="Classify the customer support ticket.",
    grounding_inputs={"subject": ticket.subject, "body": ticket.body},
    output_schema=TicketClassification,
    fallback=lambda: TicketClassification(category="unknown", needs_refund_review=False),
)

# Step 2: Draft response (after decision_engine.decide())
draft_result = await assist_or_fallback(
    runtime,
    agent_id="customer-resolution-agent",
    task_kind="draft_response",
    correlation_id=case.correlation_id,
    causation_id=decision_event_id,
    instructions="Draft a customer response.",
    grounding_inputs={
        "outcome": decision.outcome,
        "explanation": decision.explanation,
        "customer_name": ticket.customer_name,
    },
    output_schema=TextResult,
    fallback=lambda: TextResult(text="Your case has been reviewed."),
)
```

### 19. Safety & redaction env vars

| Variable | Default | Purpose |
|----------|---------|---------|
| `REDACT_PII` | `true` | Scrub PII (emails, cards, SSNs, phones) from audit records. |
| `LOG_RAW_LLM_PROMPTS` | `false` | Include full prompt text in structured logs (disable in prod). |
| `LOG_RAW_LLM_OUTPUTS` | `false` | Include full model output text in structured logs. |
| `AGENT_LLM_AUDIT_LOG_RAW_PROMPTS` | `false` | Include rendered prompt in optional audit events. |

```bash
# Production defaults (safe)
export REDACT_PII=true
export LOG_RAW_LLM_PROMPTS=false
export LOG_RAW_LLM_OUTPUTS=false

# Local debugging (more detail, never in prod)
export LOG_RAW_LLM_PROMPTS=true
export LOG_RAW_LLM_OUTPUTS=true
```

### 20. AgentCore local dev step

```bash
# 1. Install AgentCore
pip install bedrock-agentcore

# 2. Set mode
export AGENT_LLM_MODE=agentcore
export AGENT_LLM_REGION=us-east-1

# 3. Ensure AWS credentials (any standard method)
aws configure

# 4. Run the agents -- LLM calls route through AgentCore
python -m apps.agents.customer_resolution.main

# 5. Verify provider loads
python -c "from agent_foundation.llm import select_provider; print(type(select_provider('agentcore')))"
```

### 21. Enabling optional LLM audit events

The runtime always emits `ReasoningAuditRecord` via the standard audit subsystem. For additional
fine-grained observability events on dedicated topics, enable the optional audit events:

```bash
export AGENT_LLM_AUDIT_EVENTS_ENABLED=true

# To include rendered prompts in audit events (use only for debugging):
export AGENT_LLM_AUDIT_LOG_RAW_PROMPTS=true
```

When enabled, each invocation emits either `audit.llm.invocation.completed` or
`audit.llm.invocation.failed` on their respective topics. These events carry agent identity, model
id, prompt id, task kind, latency, token usage, and cache hit status.

```bash
# Verify events appear on the audit topics
pytest tests/unit/llm/test_audit_events.py -q
```