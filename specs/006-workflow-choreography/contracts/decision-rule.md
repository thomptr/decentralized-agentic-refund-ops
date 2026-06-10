# Contract: Combined Decision Rule (006) — reference

006 **reuses** the deterministic decision engine shipped in 003 unchanged. The authoritative truth table
lives in `specs/003-customer-resolution-agent/contracts/decision-policy.md` and is implemented in
`apps/agents/customer_resolution/decision_engine.py::decide`. This file restates only the **combined
rule** that the spec (FR-010, Assumption "Decision rule") asks 006 to document explicitly, including
conflicting combinations.

Inputs: `triage`, `billing.eligibility ∈ {eligible, partial, ineligible, indeterminate}`,
`risk.level ∈ {low, elevated, high}`, plus `requires_human_review`, confidence, and a `TimeoutStatus`.
First matching row wins (escalation has precedence).

| Order | Condition | Outcome | Reason |
|---|---|---|---|
| 0 | `triage.needs_refund_review == False` | `direct_response` | non-refund ticket |
| 1 | any opinion **missing** (timeout/never-arrived) | `escalate_human` | `analysis_timeout` if deadline exceeded else `missing_analysis` |
| 2 | a slot **failed/rejected**, or peer `requires_human_review` | `escalate_human` | `peer_failure` / `peer_requested_review` |
| 3 | combined confidence `< CONFIDENCE_THRESHOLD` (0.6) | `escalate_human` | `low_confidence` |
| 4 | `eligible` **AND** `low` risk | `approve_refund` | clean, low-risk, eligible |
| 5 | `ineligible` **AND** risk `elevated`/`high` | `deny_refund` | ineligible + risky |
| 6 | `partial` **AND** risk `low`/`elevated` | `offer_partial_credit` | partial eligibility, acceptable risk |
| 7 | `indeterminate` billing | `request_more_information` | inconclusive billing |
| 8 | residual **conflict** (e.g. `eligible`+`high`, `ineligible`+`low`) | `escalate_human` | `conflicting_analyses` |

Notes:
- **High/elevated risk never auto-approves** (rows 1/2/5/8 + the risk-result fast path in
  `risk_result_handler`) — refund-safety default (spec Assumption, US3 AC3).
- A **missing or failed** opinion escalates rather than deciding on partial information (spec Assumption).
- The mapping from the peers' richer vocabularies (billing 5-value recommendation; risk
  low/elevated/high) into these inputs is done by `normalize_billing_result` / `normalize_risk_result`
  and the domain-result handlers — unchanged in 006.

006 adds **no new outcome and no threshold change**; it adds tests asserting the full table end-to-end
across the three real agents (SC-007).
