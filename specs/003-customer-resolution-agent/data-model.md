# Phase 1 Data Model: Customer Resolution Agent

Entities below map the spec's Key Entities to concrete Pydantic models and in-process state. Reused
foundation models are referenced, not redefined. New/changed artifacts are marked **NEW** /
**MODIFIED**.

Conventions follow the existing codebase: Pydantic v2, `model_config = ConfigDict(frozen=True,
extra="forbid")` for contracts, `str` business IDs (e.g. `TKT-001`) and `UUID` for envelope/task IDs.

---

## 1. Inbound: Customer Support Ticket  *(reused)*

`packages/contracts/events/payloads.SupportTicketCreatedPayload` — consumed from
`support.ticket.created` (event type `local.support.ticket.created.v1`).

| Field | Type | Notes |
|-------|------|-------|
| `ticket_id` | `str` | Business key (e.g. `TKT-001`). |
| `customer_id` | `str` | |
| `amount` | `float` | Charge amount in dispute. |
| `currency` | `str` | |
| `reason` | `str` | Free-text; the triage input. |
| `created_at` | `datetime` | |

The envelope's `correlation_id` is the **case identity**; `event_id` is the causation source for the
agent's first emitted steps.

---

## 2. Triage Determination  *(NEW — internal model, `apps/agents/customer_resolution/triage.py`)*

The agent's judgment of whether a ticket needs refund review (spec entity *Triage Determination*).

```python
class Triage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    needs_refund_review: bool
    rationale: str                       # human-readable, incl. ambiguity note when defaulted
    matched_signals: list[str] = []      # which refund-intent signals fired (audit/debug)
    ambiguous: bool = False              # True when defaulted to review under unclear intent
```

**Rules** (deterministic, see `contracts/decision-policy.md`):
- Refund-intent signal in `reason`/message → `needs_refund_review=True`.
- Clear non-refund intent → `needs_refund_review=False`.
- Empty/unclear → `needs_refund_review=True, ambiguous=True` (spec edge: ambiguous triage defaults
  to review, ambiguity recorded). Never silently dropped (FR-002/FR-003).

---

## 3. Analysis Findings  *(NEW — internal, normalized from peer results)*

Normalized view the decision policy consumes, adapted from the peers' published result contracts
(see `contracts/analysis-result-contract.md`). Decouples the policy from peer wire shapes (US5-2).

```python
class BillingFinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    eligible: bool                       # mapped from recommendation / {eligible}
    requires_human_review: bool = False
    confidence: float | None = None
    summary: str = ""

class RiskFinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    level: Literal["low", "elevated", "high"]   # mapped from recommendation / {risk}
    requires_human_review: bool = False
    score: float | None = None
    summary: str = ""
```

A peer `TaskResult` with `status in {"failed","rejected"}` produces **no** finding; the slot is
marked failed on the case (forces escalation, FR-008/FR-010).

---

## 4. Resolution Case  *(NEW — in-process state, `apps/agents/customer_resolution/case.py`)*

The agent's working record for one ticket (spec entity *Resolution Case*). **One per
`correlation_id`.** Held in an in-process `CaseStore`; the durable record is the audit trail (research
R6).

```python
class CaseStatus(str, Enum):
    INTAKE = "intake"
    AWAITING_ANALYSES = "awaiting_analyses"   # ≥1 required result outstanding
    DECIDED = "decided"                       # terminal: final decision emitted
    CLOSED_DIRECT = "closed_direct"           # terminal: non-refund direct response

class AnalysisSlot(BaseModel):
    task_id: UUID | None = None               # request issued
    finding: BillingFinding | RiskFinding | None = None
    failed: bool = False                       # peer failed/rejected
    received: bool = False

class ResolutionCase(BaseModel):
    correlation_id: UUID
    ticket_id: str
    ticket: SupportTicketCreatedPayload
    triage: Triage | None = None
    billing: AnalysisSlot = AnalysisSlot()
    risk: AnalysisSlot = AnalysisSlot()
    status: CaseStatus = CaseStatus.INTAKE
    decision: "CustomerResponseDecisionPayload | None" = None
    created_at: datetime
    updated_at: datetime
```

**Completeness** (`is_ready_to_decide`): a refund case is decidable when **both** slots are
`received` (finding present **or** `failed=True`). Any `failed` slot short-circuits to escalation.

**Idempotency**: `CaseStore.get_or_create(correlation_id, ...)` returns the existing case on
re-delivery; callers check `status` to avoid duplicate delegation/decision (FR-011/FR-012).

### Case state machine

```text
            ticket.created (refund)              both slots received
  INTAKE ─────────────────────────► AWAITING_ANALYSES ──────────────► DECIDED
     │                                    │  ▲                          (terminal)
     │ ticket.created (non-refund)        │  │ one slot received        late/dup result
     ▼                                    │  │ (stay open, FR-008)      ──► recorded, not applied
  CLOSED_DIRECT (terminal)                └──┘                              (FR-012)

  Any peer slot failed/rejected at AWAITING_ANALYSES ──► DECIDED(escalate_human)
  Re-delivered ticket at any state ──► no new work; audit "duplicate" (FR-011)
```

Allowed transitions only as drawn; `DECIDED`/`CLOSED_DIRECT` are terminal (exactly one decision,
SC-003).

---

## 5. Analysis Request  *(reused contract)*

Delegation uses the runtime `agent_foundation.payloads.task.TaskRequest` (spec entity *Analysis
Request*) — **not** a new domain event (FR-016, research R2).

| Field | Value set by the agent |
|-------|------------------------|
| `task_id` | new `UUID`, recorded on the case slot |
| `capability` | `analyze_refund_eligibility` (billing) / `assess_fraud_risk` (risk) |
| `requester_agent_id` | `customer-resolution-agent` |
| `target_agent_id` | discovered via `find_capable(...)` (FR-017) |
| `input` | `A2AMessage` data part: ticket/order context only (no billing/fraud data) |

Published to `endpoint_topic(target_agent_id)` with the case `correlation_id` and `causation_id` =
ticket event id.

---

## 6. Billing / Risk Analysis Result  *(reused — consumed, never produced)*

Returned as `agent_foundation.payloads.task.TaskResult` on `TOPIC_TASK_RESULT` (spec entities
*Billing Analysis Result* / *Risk Analysis Result*). Owned by the peers; the resolution agent only
reads them. `status ∈ {completed, failed, rejected}`; on `completed`, `output` is an `A2AMessage`
whose data part conforms to `BillingRefundAnalysisCompletedPayload` / `RiskReviewCompletedPayload`
(or the demo stub shape) — normalized into `BillingFinding`/`RiskFinding` (§3).

---

## 7. Customer Response Decision  *(NEW contract — `packages/contracts/events/payloads.py`)*

The single final outcome for a ticket (spec entity *Customer Response Decision*), emitted as event
`customer.resolution.decided.v1` on `TOPIC_RESOLUTION_DECIDED`. **The only new domain contract.**

```python
class ResolutionOutcome(str, Enum):
    APPROVE_REFUND = "approve_refund"
    DENY_REFUND = "deny_refund"
    ESCALATE_HUMAN = "escalate_human"
    DIRECT_RESPONSE = "direct_response"   # non-refund ticket answered directly

class CustomerResponseDecisionPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    ticket_id: str
    correlation_id: UUID
    outcome: ResolutionOutcome
    customer_response: str                # the drafted customer-facing message
    rationale: str                        # how the outcome was reached (auditable)
    escalation_reason: str | None = None  # required when outcome == ESCALATE_HUMAN
    billing_summary: str | None = None    # traceability to billing finding (US5-2)
    risk_summary: str | None = None       # traceability to risk finding
    decided_by_agent_id: str = "customer-resolution-agent"
    decided_at: datetime
```

**Validation rules**:
- `escalation_reason` MUST be non-null iff `outcome == ESCALATE_HUMAN` (FR-010).
- For `DIRECT_RESPONSE`, `billing_summary`/`risk_summary` are null (no peers consulted, SC-001).
- For `APPROVE_REFUND`/`DENY_REFUND`, both summaries SHOULD be present (every billing/risk fact
  attributable to a peer result, SC-004/US5-2).

Registered in `agent_foundation.payloads.__init__.PAYLOAD_REGISTRY` under
`local.customer.resolution.decided.v1`.

---

## 8. Audit Records  *(reused subsystem)*

Each significant step emits an `AuditPayload` (`outcome ∈ accepted | rejected | duplicate_skipped |
completed | failed`, plus `reason`, `task_id`, `correlation_id` via the wrapping envelope) through
`agent_foundation.audit.store.write_audit` / `write_task_audit` (FR-013). Steps audited: ticket
received, triage determination, billing delegation, risk delegation, billing result consumed, risk
result consumed, final decision, duplicate re-delivery. Reconstructable via `query_by_correlation`
(FR-014, SC-006).

---

## Topic & registry deltas (see `contracts/topics.md`)

| Topic constant | Name | Disposition |
|----------------|------|-------------|
| `support.ticket.created` (existing) | `local.support.ticket.created.v1` | **consumed** (intake) |
| `TOPIC_TASK_RESULT` (existing) | `local.agent.task.result.v1` | **consumed** (results) |
| `endpoint_topic(billing/risk)` (existing) | `local.agent.<id>.task.requested.v1` | **produced** (requests) |
| `TOPIC_AUDIT` (existing) | `local.audit.envelope.recorded.v1` | **produced** (audit) |
| `TOPIC_AGENT_CARD` (existing) | `local.agent.agent-card.published.v1` | **produced** (own card) |
| `TOPIC_RESOLUTION_DECIDED` **NEW** | `local.customer.resolution.decided.v1` | **produced** (final decision) |
