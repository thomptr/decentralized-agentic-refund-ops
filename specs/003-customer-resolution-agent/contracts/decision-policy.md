# Contract: Deterministic Triage & Decision Policy

This is the **defined, auditable** policy the Customer Resolution Agent applies (FR-002, FR-009,
FR-010). It is intentionally simple and categorical (spec Assumption: illustrative PoC values).
Thresholds live as named constants in `apps/agents/customer_resolution/triage.py` and `decision.py`.
Both functions are **pure** and unit-tested against the tables below.

---

## A. Triage  — `triage.classify(ticket) -> Triage`

Input: `SupportTicketCreatedPayload` (`reason`, and any message text). Output: `Triage`
(`needs_refund_review`, `rationale`, `matched_signals`, `ambiguous`).

**Refund-intent signals** (case-insensitive substring/word match on `reason`):

```
refund, refunded, charged, charge, overcharge, overcharged, double charged,
double-charged, charged twice, dispute, disputed, chargeback, money back,
reimburse, reimbursement, billing error, wrong amount, cancel and refund
```

| Input condition | `needs_refund_review` | `ambiguous` | Notes |
|-----------------|:---------------------:|:-----------:|-------|
| ≥1 refund signal present | `true` | `false` | Advance to delegation (US1-2). |
| Clear non-refund intent (no signal; recognizable how-to/account question) | `false` | `false` | Direct response, no peers (US1-1, SC-001). |
| Empty / unrecognizable / mixed intent | `true` | `true` | **Default to review**; record ambiguity in `rationale` (spec edge: ambiguous triage). |

`rationale` always names the matched signals (or "no refund intent detected" / "ambiguous intent —
defaulted to refund review"). Recorded on the case and in the audit trail (FR-003).

---

## B. Normalizing peer results → findings

From each peer `TaskResult` (see `analysis-result-contract.md`):

- **Billing** → `BillingFinding.eligible`:
  - `true` when recommendation/data indicates eligibility (`recommendation ∈ {approve, eligible,
    refund}` **or** stub `{"eligible": true}`).
  - `false` when it indicates ineligibility (`recommendation ∈ {deny, ineligible, reject}` **or**
    stub `{"eligible": false}`).
  - `requires_human_review` carried through when present.
- **Risk** → `RiskFinding.level`:
  - `low` (acceptable) — `recommendation ∈ {low, approve, acceptable}` or stub `{"risk":"low"}` /
    `score < ELEVATED_RISK_THRESHOLD` (default `0.5`).
  - `elevated` — `0.5 ≤ score < 0.8` or `recommendation == elevated`.
  - `high` — `score ≥ 0.8` or `recommendation ∈ {high, deny, block}`.
  - `requires_human_review` carried through when present.

A `TaskResult.status ∈ {failed, rejected}` yields **no finding**; the slot is marked `failed`.

---

## C. Decision  — `decision.decide(triage, billing_slot, risk_slot) -> CustomerResponseDecisionPayload`

Evaluated **in order**; first matching row wins (escalation precedence guarantees a single outcome,
SC-003, and routes all faults to human escalation with a reason, SC-007).

| # | Condition | `outcome` | `escalation_reason` |
|---|-----------|-----------|---------------------|
| 1 | `triage.needs_refund_review == false` | `direct_response` | — |
| 2 | billing slot OR risk slot `failed` (peer failed/rejected) | `escalate_human` | `peer_failure` / `peer_rejection` |
| 3 | `billing.requires_human_review` OR `risk.requires_human_review` | `escalate_human` | `peer_requested_review` |
| 4 | `risk.level in {elevated, high}` | `escalate_human` | `elevated_risk` |
| 5 | `billing.eligible == false` | `deny_refund` | — |
| 6 | `billing.eligible == true` AND `risk.level == low` | `approve_refund` | — |
| 7 | anything else (residual conflict) | `escalate_human` | `conflicting_analyses` |

Notes:
- Rows 2–4 are the **escalation guards**; they fire before approve/deny so a high-risk-but-eligible
  case escalates rather than approves (spec edge: conflicting analyses).
- Row 5 denies on billing ineligibility regardless of low risk (spec: "deny when billing indicates
  ineligibility").
- Row 6 is the only approve path: eligible **and** low risk **and** no human-review flag (rows 3–4
  already excluded those).
- Row 7 is unreachable given rows 1–6 cover the field space, but is retained as a defined default so
  the function is total (FR-010: every case resolves to a defined outcome).

**Decidability gate** (FR-008): `decide` is invoked only when the case `is_ready_to_decide` — both
slots `received` (finding or `failed`) — **except** that a `failed`/`rejected` slot makes the case
immediately decidable via row 2 even if the other slot is still outstanding (US3-3).

**Customer response draft**: a templated message per outcome (approve: refund confirmation; deny:
explanation; escalate: "forwarded to a specialist"; direct_response: the direct answer). Templates
live in `decision.py`; exact wording is illustrative.

---

## D. Worked examples (acceptance mapping)

| Scenario | billing | risk | Outcome | Spec ref |
|----------|---------|------|---------|----------|
| "how do I change my email" | — | — | `direct_response` | US1-1, SC-001 |
| Eligible, low risk | eligible | low | `approve_refund` | US3-1 |
| Ineligible, low risk | ineligible | low | `deny_refund` | FR-009 |
| Eligible, high risk | eligible | high | `escalate_human` (elevated_risk) | edge: conflicting |
| Billing returns failure | failed | low | `escalate_human` (peer_failure) | US3-3, SC-007 |
| Risk rejects request | eligible | rejected | `escalate_human` (peer_rejection) | US2-3, SC-007 |
| Only billing returned | eligible | (none) | **no decision; case stays open** | US3-2, FR-008 |
| Late risk result after decision | — | — | recorded, **not** applied | US3-4, FR-012 |
