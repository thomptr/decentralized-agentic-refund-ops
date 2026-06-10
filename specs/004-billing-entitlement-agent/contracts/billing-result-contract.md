# Contract: Billing Refund-Analysis Result (REUSED — no change)

This feature **does not introduce a new result contract or topic**. It produces the project's
**existing** canonical billing result, already defined and registered in the foundation. This file
documents the reused contract and the dual-path delivery (FR-007, FR-008, FR-019).

## Published event

- **Topic**: `local.billing.refund-analysis.completed.v1` — `packages/contracts/topics.py:TOPIC_BILLING_RESULT`
  (already declared in `transport/topics.py:_CANONICAL_TOPICS` and `TOPIC_NAMES`).
- **Event type key**: `TOPIC_BILLING_RESULT` (topic name == event type, per the new-style convention).
- **Payload model**: `packages/contracts/events/payloads.py:BillingRefundAnalysisCompletedPayload`
  (already registered in `payloads/__init__.py:PAYLOAD_REGISTRY[TOPIC_BILLING_RESULT]`).

```python
class BillingRefundAnalysisCompletedPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    ticket_id: str
    recommendation: str                 # "approve" | "deny" | "requires_human_review" | "partial_refund"
    confidence: float                    # 0.0 .. 1.0
    evidence: list[EvidenceItem]         # non-empty (SC-002); each cites an owned fact / policy rule
    reasoning_summary: str
    requires_human_review: bool
```

`EvidenceItem` (also reused): `{ source: str, description: str, value: Any }`.
`source ∈ {subscription, invoice, payment, entitlement, product_usage, refund_policy}` — always an
owned domain or the policy (SC-003, FR-009).

### Envelope fields the agent sets when publishing
- `correlation_id = request.case_id` (the originating case correlation id) — **required** so the
  consumer's `billing_result_handler` (keyed by `envelope.correlation_id`) matches the case.
- `causation_id` = the inbound request envelope's `event_id` (causal link, FR-014/observability).
- `agent_id = "billing-entitlement-agent"`, `tenant_id = "poc"`.

## Dual-path delivery (FR-008)

| Path | Transport | Topic | Correlation | Consumer in `003` |
|------|-----------|-------|-------------|-------------------|
| A2A result | runtime (`TaskResult.output`) | `local.agent.task.result.v1` (`TOPIC_TASK_RESULT`) | by `task_id` | `result_handler` → `normalize_billing_result` |
| Domain event | handler-owned `Publisher` | `TOPIC_BILLING_RESULT` | by `correlation_id` (`case_id`) | `billing_result_handler` |

The A2A `TaskResult.output` is an `A2AMessage` with one `data` part carrying the **same** fields
(`recommendation`, `confidence`, `evidence`, `reasoning_summary`, `requires_human_review`) so
`003`'s `normalize_billing_result` resolves it. The consumer dedups across both paths via per-slot
`apply_result` + `DECIDED`/terminal guards (research R8).

## Recommendation → consumer mapping (verified, no change to `003`)

| `recommendation` | `003` billing eligibility | `requires_human_review=True` effect |
|------------------|---------------------------|-------------------------------------|
| `approve` | `eligible` | — |
| `deny` | `ineligible` | — |
| `partial_refund` | `partial` | — |
| `requires_human_review` | `indeterminate` | routes the case to `escalate_human` |

(Source: `apps/agents/customer_resolution/event_handlers.py:normalize_billing_result` and
`billing_result_handler`.)

## Audit (emitted by the reused runtime — FR-014)

Per request, the runtime publishes to `TOPIC_AUDIT` (`agent.audit.v1` / `AuditPayload`) exactly one
of:
- `rejected` (invalid payload, wrong target, or unsupported capability), **or**
- `accepted` + one terminal `completed` | `failed`,
- or `duplicate_skipped` for a redelivered `task_id`.

Each carries agent identity, `task_id`, correlation/causation, timestamp, outcome, and reason; query
by correlation id via `audit/store.py:query_by_correlation` (FR-015, SC-007).
