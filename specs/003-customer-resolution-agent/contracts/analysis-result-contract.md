# Contract: Peer Analysis Result (consumed, never produced)

The Customer Resolution Agent depends on the **published result contracts** of the billing and risk
peers — not their internals (FR-005, US5). Results arrive as runtime `TaskResult` events on the
shared `TOPIC_TASK_RESULT` (`local.agent.task.result.v1`). This document fixes exactly what the agent
reads and how it normalizes it, so the coupling is to the contract surface only.

## Transport envelope (reused)

`agent_foundation.payloads.task.TaskResult`:

| Field | Type | Agent use |
|-------|------|-----------|
| `task_id` | `UUID` | **Correlation key** → maps to a case's billing/risk slot. |
| `status` | `"completed" \| "failed" \| "rejected"` | `failed`/`rejected` → slot marked failed → escalation. |
| `performer_agent_id` | `str` | Recorded for audit traceability. |
| `output` | `A2AMessage \| null` | On `completed`, holds the analysis data part. |
| `error` | `TaskError \| null` | On `failed`/`rejected`, the reason (category + message). |

## Billing analysis data part

On `status == completed`, `output.parts[*]` includes a `data` part. The agent accepts **either**:

1. **Canonical contract** — `BillingRefundAnalysisCompletedPayload` fields:
   `recommendation: str`, `confidence: float`, `requires_human_review: bool`, `evidence`,
   `reasoning_summary`.
2. **Demo stub shape** (current `billing_entitlement` agent): `{"eligible": bool, "reason": str}`.

Normalized → `BillingFinding`:

| Source | → `BillingFinding.eligible` |
|--------|------------------------------|
| `recommendation ∈ {approve, eligible, refund}` | `true` |
| `recommendation ∈ {deny, ineligible, reject}` | `false` |
| stub `{"eligible": true/false}` | passthrough |
| `requires_human_review` (canonical) | → `BillingFinding.requires_human_review` |

## Risk analysis data part

On `status == completed`, accepts **either**:

1. **Canonical contract** — `RiskReviewCompletedPayload`: `recommendation`, `confidence`,
   `requires_human_review`, `evidence`, `reasoning_summary`.
2. **Demo stub shape** (current `risk_fraud` agent): `{"risk": "low"|"elevated"|"high", "score": float}`.

Normalized → `RiskFinding` (see `decision-policy.md §B` for thresholds): `level ∈ {low, elevated,
high}`, `requires_human_review`, `score`.

## Normalization rules (agent-side adapter)

- Live in `apps/agents/customer_resolution/service.py` (or a small `adapters` helper); pure and
  unit-tested.
- Unknown/malformed data part on a `completed` result → treat the slot as `failed` with reason
  `unparseable_result` → escalation (never crash, never fabricate a finding — US5/FR-005).
- The agent reads **only** these published fields; it issues **no** query to any billing, payment, or
  fraud/risk data store (FR-005, SC-004).

## Forward note

When the real billing/risk agents land, they emit the **canonical** contract above and the demo-stub
branch can be retired without changing the resolution agent's decision policy or its event contracts.
