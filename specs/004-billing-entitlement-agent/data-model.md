# Phase 1 Data Model: Billing and Entitlement Agent

All models are Pydantic v2 with `extra="forbid"` unless noted. **Domain-internal** models live in
`apps/agents/billing_entitlement/models.py`; the **published result contract** is the existing
`packages/contracts/events/payloads.py:BillingRefundAnalysisCompletedPayload` (reused, not redefined).

---

## 1. Inbound — `RefundEligibilityRequest` (validated task input)

The `data` part of the incoming A2A `TaskRequest.input` (FR-002). The requester (`003`) sends a
`BillingAnalysisRequestInput`-shaped object; this agent validates the fields it needs and is lenient
on extras (`extra="ignore"`) so the wire contract can evolve without breaking the agent.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `case_id` | UUID | yes | Equals the originating case correlation id; used as the publish `correlation_id` (research R2). |
| `ticket_id` | str | yes | Carried into the result event (`BillingRefundAnalysisCompletedPayload.ticket_id`). |
| `customer_id` | str | yes | Fallback fact-lookup key. |
| `requested_refund_amount` | float ≥ 0 | yes | The disputed amount; compared against invoice/payment facts. |
| `purchase_reference` | str | yes | **Primary** fact-lookup key (the charge a refund targets). |
| `customer_message_summary` | str | no | Context only; never overrides billing facts. |
| `policy_context` | str | no | Optional hint; the agent always applies its own published policy. |

**Validation outcomes**:
- Missing/empty required field, or non-`data` input part → **invalid input** → handler raises →
  runtime emits `TaskResult(status="failed", error.category="handler_error")` and `failed` audit
  (FR-011). No fabricated recommendation.
- Valid input → proceed to fact lookup.

---

## 2. Owned billing facts (the five domains)

Loaded from `mock_data.py` keyed by `purchase_reference` (then `customer_id`). A miss → missing-data
path (FR-010). Bundled as `BillingFacts`.

### `Subscription`
| Field | Type | Notes |
|-------|------|-------|
| `subscription_id` | str | |
| `status` | `Literal["active","cancelled","lapsed"]` | drives RP-005 |
| `term` | `Literal["monthly","annual"]` | |
| `started_at` | datetime | |
| `renewed_at` | datetime \| None | |

### `Invoice`
| Field | Type | Notes |
|-------|------|-------|
| `invoice_id` | str | |
| `purchase_reference` | str | lookup key; ties to the disputed charge |
| `amount` | float | |
| `currency` | str | |
| `issued_at` | datetime | drives RP-001 (refund window) |
| `paid` | bool | drives RP-002 |

### `Payment`
| Field | Type | Notes |
|-------|------|-------|
| `payment_id` | str | |
| `invoice_id` | str | |
| `captured` | bool | a real charge occurred |
| `amount` | float | |
| `reversed_amount` | float | ≥0; a recorded refund/reversal already applied (RP-002, contradiction) |

### `Entitlement`
| Field | Type | Notes |
|-------|------|-------|
| `entitlement_id` | str | |
| `subscription_id` | str | |
| `status` | `Literal["active","revoked"]` | contradiction signal vs. cancelled subscription |
| `delivered` | bool | drives RP-003 (delivered value) |

### `ProductUsage`
| Field | Type | Notes |
|-------|------|-------|
| `usage_units` | float | consumption in the billing period |
| `allotment_units` | float | included allotment; `usage_ratio = usage_units/allotment_units` |
| `heavy` | bool (derived) | `usage_ratio >= USAGE_HEAVY_THRESHOLD` → drives RP-004 |

### `BillingFacts` (aggregate)
`subscription`, `invoice`, `payment`, `entitlement`, `usage` — any may be `None` to represent a
partial record. **Completeness** and **consistency** are computed by the rules engine, not assumed.

---

## 3. Policy — `RefundPolicy` / `PolicyRule`

`policy.py` exposes a named, versioned policy. See [`contracts/refund-policy.md`](./contracts/refund-policy.md).

| Element | Type | Notes |
|---------|------|-------|
| `policy_name` | str | e.g. `"poc-refund-policy"` |
| `policy_version` | str | e.g. `"1.0.0"` |
| `REFUND_WINDOW_DAYS` | int | 30 |
| `USAGE_HEAVY_THRESHOLD` | float | 0.8 (ratio) |
| `rules` | list[`PolicyRule`] | each: `id` (`RP-00x`), `name`, `description` |

A **policy reference** cited in the result is the rule `id` (+ `policy_name@policy_version`).

---

## 4. Evaluation output — `EligibilityRecommendation` (domain)

Produced by `rules_engine.evaluate(facts, request, policy)`. Pure; deterministic (FR-012).

| Field | Type | Notes |
|-------|------|-------|
| `recommendation` | `Literal["approve","deny","requires_human_review","partial_refund"]` | FR-004 (core three + optional partial) |
| `confidence` | float `[0,1]` | fixed per rule path (research R6) |
| `evidence` | list[`EvidenceItem`] | each cites an owned fact / policy rule (FR-005) |
| `policy_references` | list[str] | rule ids applied (subset of `RP-00x`) |
| `reasoning_summary` | str | human-readable derivation (FR-006) |
| `requires_human_review` | bool | `True` for the human-review path or low-confidence verdicts (FR-010) |

`EvidenceItem` is the **existing** `packages/contracts/events/payloads.py:EvidenceItem`
(`source`, `description`, `value`), reused. `source ∈ {subscription, invoice, payment, entitlement,
product_usage, refund_policy}` — **always an owned domain or the policy**, never a foreign domain
(SC-003, FR-009).

---

## 5. Published result — `BillingRefundAnalysisCompletedPayload` (REUSED, not redefined)

Already defined and registered in the foundation (`PAYLOAD_REGISTRY[TOPIC_BILLING_RESULT]`). The
agent maps `EligibilityRecommendation` → this payload 1:1:

| Payload field | Source |
|---------------|--------|
| `ticket_id` | request `ticket_id` |
| `recommendation` | `EligibilityRecommendation.recommendation` |
| `confidence` | `EligibilityRecommendation.confidence` |
| `evidence` | `EligibilityRecommendation.evidence` (non-empty, SC-002) |
| `reasoning_summary` | `EligibilityRecommendation.reasoning_summary` |
| `requires_human_review` | `EligibilityRecommendation.requires_human_review` |

Published to `TOPIC_BILLING_RESULT` with `correlation_id = request.case_id`, `causation_id` derived
from the request envelope/task. The **same** recommendation/confidence/evidence/reasoning/human-review
fields are placed in the A2A `TaskResult.output` `data` part (the runtime path), satisfying FR-008's
dual delivery and `003`'s `normalize_billing_result` adapter.

---

## State / lifecycle

The agent is **stateless across requests** apart from the runtime's `task_id` idempotency ledger.
Each request: validate → load facts → evaluate → publish result event → return A2A output. There is
no per-case working state (unlike `003`); the verdict is a pure function of `(facts, request, policy)`.

```
TaskRequest ──▶ [runtime] reject?  ── invalid/wrong-target/unsupported ─▶ TaskResult(rejected) + audit:rejected
                   │ accept + audit:accepted
                   ▼
             [handler] validate input ── invalid ─▶ raise ─▶ TaskResult(failed) + audit:failed
                   │ valid
                   ▼
             load owned facts ── miss/contradiction ─▶ recommendation=requires_human_review
                   │
                   ▼
             rules_engine.evaluate → EligibilityRecommendation
                   │
                   ├─▶ publish BillingRefundAnalysisCompletedPayload → TOPIC_BILLING_RESULT (corr=case_id)
                   └─▶ return A2AMessage(data=…) ─▶ runtime ─▶ TaskResult(completed) + audit:completed
```

Redelivery of the same `task_id` is short-circuited by the runtime → audit `duplicate_skipped`, no
re-publish (FR-013).
