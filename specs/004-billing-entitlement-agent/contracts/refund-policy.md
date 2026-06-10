# Contract: PoC Refund Policy (named, citable, deterministic)

`policy_name = "poc-refund-policy"`, `policy_version = "1.0.0"`. Illustrative PoC values chosen to be
auditable and to drive distinct outcomes (spec Assumption). The mapping facts→recommendation is
**deterministic**: identical facts under this policy yield the same verdict (FR-012). Each fired rule
contributes a **policy reference** (`RP-00x`) to the result's `policy_references` and an
`EvidenceItem` to its `evidence`.

## Thresholds

| Constant | Value | Used by |
|----------|-------|---------|
| `REFUND_WINDOW_DAYS` | `30` | RP-001 |
| `USAGE_HEAVY_THRESHOLD` | `0.8` (usage_units / allotment_units) | RP-004 |

## Rules

| Id | Name | Condition | Contribution |
|----|------|-----------|--------------|
| `RP-001` | refund-window | `now - invoice.issued_at <= REFUND_WINDOW_DAYS` | within → eligible-supporting; outside → **deny** |
| `RP-002` | paid-invoice | `invoice.paid AND payment.captured AND payment.reversed_amount == 0` | satisfied → refundable; unpaid/uncaptured → **deny** (nothing to refund); already fully reversed → **deny** (already refunded) |
| `RP-003` | entitlement-delivered | `entitlement.delivered` | delivered → weakens claim; not delivered → **approve-supporting** |
| `RP-004` | usage-threshold | `usage_ratio >= USAGE_HEAVY_THRESHOLD` | heavy → materially weakens → **deny** (or `partial_refund` when policy-configured) |
| `RP-005` | subscription-status | `subscription.status` | `cancelled` within window → supports refund; `active` + heavy usage → weakens |

## Evaluation order (deterministic precedence)

1. **Data-completeness gate** — if any required fact for the claim is missing/unresolvable (e.g.
   unknown `purchase_reference`, no invoice/payment record) → `requires_human_review` with a recorded
   reason. **No fabricated verdict** (FR-010). `confidence = 0.2`.
2. **Contradiction gate** — if facts conflict (e.g. `payment.reversed_amount > 0` on a `paid` invoice
   claimed unrefunded; `entitlement.status == "active"` on a `cancelled` subscription) →
   `requires_human_review`, `confidence = 0.3`, conflict captured in evidence/reasoning (FR-010).
3. **Hard denials** — RP-001 outside window **or** RP-002 unpaid/uncaptured/already-reversed →
   `deny`. `confidence = 0.9`.
4. **Usage gate** — RP-004 heavy usage → `deny` (or `partial_refund` if enabled). `confidence = 0.9`
   (`0.6` if also borderline on the window).
5. **Approve** — within window (RP-001) **and** paid/unreversed (RP-002) **and** entitlement not
   delivered (RP-003) **and** light usage (RP-004) → `approve`. `confidence = 0.9`.
6. **No applicable rule** — if none of the above resolves the case → `requires_human_review` with the
   stated reason "no applicable policy rule". **Never approve-by-omission** (spec edge). `confidence = 0.2`.

## Borderline resolution (documented side)

- Exactly `REFUND_WINDOW_DAYS` since `issued_at` → counts as **within** the window (inclusive).
- `usage_ratio` exactly `USAGE_HEAVY_THRESHOLD` → counts as **below** heavy (claim not yet materially
  weakened); RP-004 does **not** fire.
- Borderline cases set `confidence = 0.6` and record the boundary decision in `reasoning_summary`
  (spec edge "borderline within policy thresholds" — never left undecided).

## Confidence summary (research R6)

| Path | confidence |
|------|-----------|
| Clear approve/deny, all facts present & consistent | 0.9 |
| Borderline on a policy boundary | 0.6 |
| Contradiction | 0.3 |
| Missing/unresolvable data, or no applicable rule | 0.2 |

## Determinism & isolation guarantees

- Pure function of `(BillingFacts, RefundEligibilityRequest, RefundPolicy)`; no clock-dependent
  branching beyond comparing `now` to `issued_at` for the window (the window comparison is monotone
  and recorded in evidence).
- Every `EvidenceItem.source` is one of the five owned domains or `refund_policy`. **No** risk, fraud,
  or customer-workflow input participates (FR-009, SC-003).
