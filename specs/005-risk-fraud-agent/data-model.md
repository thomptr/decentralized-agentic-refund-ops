# Phase 1 Data Model: Risk and Fraud Agent

All models are Pydantic v2. **Reused** contracts (`RiskReviewCompletedPayload`, `EvidenceItem`,
`TaskRequest`/`TaskResult`, `A2AMessage`/`A2APart`, `AgentCard`/`Capability`) are imported unchanged
from `packages/contracts` and `agent_foundation`; this feature adds only the **agent-internal** domain
models below (in `apps/agents/risk_fraud/models.py`). No model in `packages/`, `src/`, or feature 003
changes.

---

## 1. Inbound request (validated A2A task input)

### `RiskAssessmentRequest` — the `data` part of `TaskRequest.input`

Mirrors the shape the Customer Resolution Agent already sends (`RiskAnalysisRequestInput`:
`case_id, ticket_id, customer_id, requested_refund_amount, customer_message_summary`). `extra="ignore"`
so the wire shape can evolve and the agent validates only what it needs (FR-002). Contract:
[`contracts/assess-fraud-risk.input.schema.json`](./contracts/assess-fraud-risk.input.schema.json).

| Field | Type | Rules | Notes |
|-------|------|-------|-------|
| `case_id` | `UUID` | required | Originating case correlation id; the publish `correlation_id` (R2). |
| `ticket_id` | `str` | required, non-empty | Echoed into `RiskReviewCompletedPayload.ticket_id`. |
| `customer_id` | `str` | required, non-empty | **Primary signal-lookup key** (R3). |
| `requested_refund_amount` | `float` | `>= 0` | Disputed amount; context for velocity/abuse reasoning. |
| `customer_message_summary` | `str \| None` | optional | Context only; never overrides owned signals (FR-009). |

Validation failure (missing data part / invalid types) → `ValueError`, which the runtime turns into
`TaskResult(status="failed")` (FR-011). No fabricated verdict.

---

## 2. Owned risk/fraud signals (the agent's data — FR-003)

Each is a frozen Pydantic model; `RiskSignals` bundles all five domains. Fields are illustrative PoC
values (spec Assumption). Seeded in `mock_data.py` keyed by `customer_id`; see
[`contracts/mock-risk-data.md`](./contracts/mock-risk-data.md).

### `AccountStanding`
| Field | Type | Notes |
|-------|------|-------|
| `account_id` | `str` | Owned account identifier. |
| `tenure_days` | `int` (`>= 0`) | Account age; long tenure lowers baseline (FP-005). |
| `status` | `Literal["good", "watch", "restricted"]` | Standing flag. |

### `RefundDisputeHistory`
| Field | Type | Notes |
|-------|------|-------|
| `prior_refunds` | `int` (`>= 0`) | Count of prior refunds. |
| `prior_disputes` | `int` (`>= 0`) | Count of prior disputes. |
| `chargebacks` | `int` (`>= 0`) | Count of prior chargebacks (FP-002). |

### `PaymentInstrumentSignal`
| Field | Type | Notes |
|-------|------|-------|
| `instrument_id` | `str` | Owned instrument reference. |
| `billing_details_match` | `bool` | Mismatch raises risk (FP-004). |
| `instrument_age_days` | `int` (`>= 0`) | Very new instrument is riskier. |
| `card_testing_pattern` | `bool` | Card-testing indicator (FP-004). |

### `BehavioralSignal`
| Field | Type | Notes |
|-------|------|-------|
| `refund_requests_in_window` | `int` (`>= 0`) | Recent refund/dispute velocity (FP-003). |
| `velocity_window_days` | `int` (`> 0`) | Window the count is measured over. |
| `anomaly_score` | `float` (`0.0..1.0`) | Deviation vs. normal behavior (FP-006). |

### `KnownFraudIndicator`
| Field | Type | Notes |
|-------|------|-------|
| `on_blocklist` | `bool` | Blocklist match → hard `high` floor (FP-001). |
| `indicator_source` | `str \| None` | Which list/source matched (decisive evidence). |

### `RiskSignals` (aggregate)
| Field | Type | Notes |
|-------|------|-------|
| `account_standing` | `AccountStanding \| None` | |
| `refund_history` | `RefundDisputeHistory \| None` | |
| `payment_instrument` | `PaymentInstrumentSignal \| None` | |
| `behavioral` | `BehavioralSignal \| None` | |
| `known_fraud` | `KnownFraudIndicator \| None` | |

A `mock_data.load_signals(customer_id)` miss returns `None` → missing-data path (FR-010): a
`requires_human_review` assessment with a recorded reason, never a fabricated level.

---

## 3. Policy models (`policy.py`) — named, citable

| Model | Fields | Notes |
|-------|--------|-------|
| `PolicyRule` (frozen dataclass) | `id: str`, `name: str`, `description: str` | Stable `FP-00x` ids cited in evidence (FR-005). |
| `FraudPolicy` (frozen dataclass) | `policy_name: str`, `policy_version: str`, `rules: list[PolicyRule]` | `poc-fraud-policy` v1.0.0. |

Module constants (PoC thresholds): `ELEVATED_THRESHOLD = 0.5`, `HIGH_THRESHOLD = 0.8`,
`CHARGEBACK_ELEVATED`, `CHARGEBACK_HIGH`, `VELOCITY_ELEVATED`, `VELOCITY_HIGH`,
`ANOMALY_ELEVATED`, `NEW_ACCOUNT_DAYS`. Full table in
[`contracts/fraud-policy.md`](./contracts/fraud-policy.md).

---

## 4. Verdict (domain output)

### `RiskLevel` (StrEnum)
`LOW = "low"`, `ELEVATED = "elevated"`, `HIGH = "high"` — the FR-004 minimum set; the string value is
what the published `recommendation` carries (R5).

### `RiskAssessment`
| Field | Type | Rules | Notes |
|-------|------|-------|-------|
| `risk_level` | `RiskLevel` | required | The verdict. |
| `confidence` | `float` | `0.0..1.0` | Per-path value, lowered on uncertainty (R6, FR-006). |
| `evidence` | `list[EvidenceItem]` | non-empty (SC-002) | Each cites an owned signal **or** the policy. |
| `policy_references` | `list[str]` | ≥1 unless missing-data | Fired `FP-00x` rule ids (FR-005). |
| `reasoning_summary` | `str` | non-empty | Human-readable explanation (FR-006). |
| `requires_human_review` | `bool` | required | True on missing/contradictory/no-applicable-rule. |

`EvidenceItem` (reused): `{ source: str, description: str, value: Any }`.
`source ∈ {account_standing, refund_history, payment_instrument, behavioral, known_fraud,
fraud_policy}` — always an owned signal domain or the policy (SC-003, FR-009). **Policy references are
surfaced into the result event as `EvidenceItem`s with `source="fraud_policy"`** (the reused
`RiskReviewCompletedPayload` has no dedicated `policy_references` field — see the contract note), so
SC-002's "at least one policy reference" is satisfied via evidence.

---

## 5. Published result event (REUSED — no change)

### `RiskReviewCompletedPayload` (from `packages/contracts/events/payloads.py`)
| Field | Type | Source |
|-------|------|--------|
| `ticket_id` | `str` | `request.ticket_id` |
| `recommendation` | `str` | `risk_level.value` — `"low" \| "elevated" \| "high"` (R5) |
| `confidence` | `float` (0..1) | `assessment.confidence` |
| `evidence` | `list[EvidenceItem]` | `assessment.evidence` (includes the `fraud_policy` items) |
| `reasoning_summary` | `str` | `assessment.reasoning_summary` |
| `requires_human_review` | `bool` | `assessment.requires_human_review` |

Published to `TOPIC_RISK_RESULT` (`local.risk.review.completed.v1`) with `correlation_id = case_id`,
`causation_id = task_id`. Already registered in `PAYLOAD_REGISTRY` and `_CANONICAL_TOPICS`. See
[`contracts/risk-result-contract.md`](./contracts/risk-result-contract.md).

---

## 6. State transitions (per assessment)

```text
request received ──validate──► (invalid) ─────────────► FAILED (TaskResult.failed, FR-011)
        │ valid
        ▼
 load signals(customer_id) ──miss──► HUMAN_REVIEW (requires_human_review=True, reason, FR-010)
        │ hit
        ▼
 known-fraud indicator? ──yes──► HIGH (FP-001 floor, decisive evidence)
        │ no
        ▼
 contradiction? ──yes──► ELEVATED + lowered confidence + requires_human_review (FR-010 edge)
        │ no
        ▼
 score FP-002..FP-006 ──► level by thresholds (borderline → upper band) ──► LOW | ELEVATED | HIGH
        │ no resolvable signal/rule
        ▼
 HUMAN_REVIEW (no-applicable-policy default stance — never clear by omission)
```

Idempotency: a redelivered `task_id` is short-circuited by the runtime **before** validation, audited
`duplicate_skipped`; no second transition, no duplicate publish (FR-013, R7).
