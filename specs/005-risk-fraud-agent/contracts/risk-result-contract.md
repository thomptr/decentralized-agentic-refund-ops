# Contract: Risk Review Result (REUSED — no change)

This feature **does not introduce a new result contract or topic**. It produces the project's
**existing** canonical risk result, already defined and registered in the foundation. This file
documents the reused contract and the dual-path delivery (FR-007, FR-008, FR-019).

## Published event

- **Topic**: `local.risk.review.completed.v1` — `packages/contracts/topics.py:TOPIC_RISK_RESULT`
  (already declared in `transport/topics.py:_CANONICAL_TOPICS` and `TOPIC_NAMES`).
- **Event type key**: `TOPIC_RISK_RESULT` (topic name == event type, per the new-style convention).
- **Payload model**: `packages/contracts/events/payloads.py:RiskReviewCompletedPayload`
  (already registered in `payloads/__init__.py:PAYLOAD_REGISTRY[TOPIC_RISK_RESULT]`).

```python
class RiskReviewCompletedPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    ticket_id: str
    recommendation: str                 # "low" | "elevated" | "high"  (the risk level — R5)
    confidence: float                    # 0.0 .. 1.0
    evidence: list[EvidenceItem]         # non-empty (SC-002); each cites an owned signal / policy rule
    reasoning_summary: str
    requires_human_review: bool
```

`EvidenceItem` (also reused): `{ source: str, description: str, value: Any }`.
`source ∈ {account_standing, refund_history, payment_instrument, behavioral, known_fraud,
fraud_policy}` — always an owned signal domain or the policy (SC-003, FR-009).

> **Policy references (FR-005 / SC-002).** `RiskReviewCompletedPayload` has **no dedicated
> `policy_references` field** (same as the billing payload). The fired `FP-00x` rule ids are therefore
> surfaced as `EvidenceItem`s with `source="fraud_policy"` (the rule id in `description`/`value`). At
> least one such item is present whenever a policy rule fires, satisfying SC-002's "at least one policy
> reference". The agent's internal `RiskAssessment` still carries an explicit `policy_references` list,
> which is also echoed in the A2A output data part for the requesting peer.

### Envelope fields the agent sets when publishing
- `correlation_id = request.case_id` (the originating case correlation id) — **required** so the
  consumer's `risk_result_handler` (keyed by `envelope.correlation_id`) matches the case.
- `causation_id` = the inbound request's `task_id` (causal link, FR-014/observability).
- `agent_id = "risk-fraud-agent"`, `tenant_id = "poc"`.

## Dual-path delivery (FR-008)

| Path | Transport | Topic | Correlation | Consumer in `003` |
|------|-----------|-------|-------------|-------------------|
| A2A result | runtime (`TaskResult.output`) | `local.agent.task.result.v1` (`TOPIC_TASK_RESULT`) | by `task_id` | `result_handler` → `normalize_risk_result` |
| Domain event | handler-owned `Publisher` | `TOPIC_RISK_RESULT` | by `correlation_id` (`case_id`) | `risk_result_handler` |

The A2A `TaskResult.output` is an `A2AMessage` with one `data` part carrying the **same** fields
(`recommendation`, `confidence`, `evidence`, `reasoning_summary`, `requires_human_review`, plus
`policy_references` and a numeric `score == confidence` for the stub-compatible path) so `003`'s
`normalize_risk_result` resolves it. The consumer dedups across both paths via per-slot `apply_result`,
the immediate elevated/high escalation guard, and `DECIDED`/terminal guards (research R8).

## Risk level → consumer mapping (verified, no change to `003`)

| `recommendation` | `003` risk level (`RiskFinding.level`) | Effect |
|------------------|----------------------------------------|--------|
| `low` | `low` | normal decision path |
| `elevated` | `elevated` | forces `escalate_human` (risk gate) |
| `high` | `high` | forces `escalate_human` (risk gate) |
| any + `requires_human_review=True` | (level carried) | forces `escalate_human` |

(Source: `apps/agents/customer_resolution/event_handlers.py:normalize_risk_result` and
`risk_result_handler`; the legacy stub shape `{"risk": "...", "score": ...}` also remains accepted by
the consumer, so this real agent is a drop-in replacement.)

## Audit (emitted by the reused runtime — FR-014)

Per request, the runtime publishes to `TOPIC_AUDIT` (`agent.audit.v1` / `AuditPayload`) exactly one of:
- `rejected` (invalid payload, wrong target, or unsupported capability), **or**
- `accepted` + one terminal `completed` | `failed`,
- or `duplicate_skipped` for a redelivered `task_id`.

Each carries agent identity, `task_id`, correlation/causation, timestamp, outcome, and reason; query by
correlation id via `audit/store.py:query_by_correlation` (FR-015, SC-007).
