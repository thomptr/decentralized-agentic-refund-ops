# Contract: Fraud Policy (`poc-fraud-policy` v1.0.0)

Named, citable, **deterministic** fraud-risk policy applied by the Risk and Fraud Agent (FR-012,
FR-005). All thresholds are illustrative PoC values chosen to be auditable and to drive distinct
outcomes (spec Assumption) — not production fraud policy. Implemented in
`apps/agents/risk_fraud/policy.py`; evaluated by `apps/agents/risk_fraud/scoring.py`.

## Thresholds (module constants)

| Constant | Value | Meaning |
|----------|-------|---------|
| `ELEVATED_THRESHOLD` | `0.5` | Cumulative score ≥ this → at least `elevated` (matches consumer band). |
| `HIGH_THRESHOLD` | `0.8` | Cumulative score ≥ this → `high` (matches consumer band). |
| `CHARGEBACK_ELEVATED` | `1` | ≥1 prior chargeback contributes elevated weight. |
| `CHARGEBACK_HIGH` | `2` | ≥2 prior chargebacks contribute high weight. |
| `VELOCITY_ELEVATED` | `3` | ≥3 refund requests in window contributes elevated weight. |
| `VELOCITY_HIGH` | `5` | ≥5 refund requests in window contributes high weight. |
| `ANOMALY_ELEVATED` | `0.7` | `behavioral.anomaly_score` ≥ this contributes elevated weight. |
| `NEW_ACCOUNT_DAYS` | `30` | `tenure_days` < this is treated as a new (riskier) account. |

## Rules (each carries a stable id cited in evidence)

| Rule id | Name | Fires when | Contribution |
|---------|------|------------|--------------|
| `FP-001` | known-fraud-indicator | `known_fraud.on_blocklist == True` | **Hard floor → `high`** (bypasses scoring); decisive evidence; never silently ignored. |
| `FP-002` | chargeback-history | `refund_history.chargebacks ≥ CHARGEBACK_*` | `+0.5` at `CHARGEBACK_ELEVATED`, `+0.8` at `CHARGEBACK_HIGH`. |
| `FP-003` | refund-velocity | `behavioral.refund_requests_in_window ≥ VELOCITY_*` | `+0.4` at `VELOCITY_ELEVATED`, `+0.7` at `VELOCITY_HIGH`. |
| `FP-004` | instrument-mismatch | `payment_instrument.billing_details_match == False` or `card_testing_pattern == True` | `+0.4` (mismatch) / `+0.6` (card-testing). |
| `FP-005` | account-standing | `account_standing.status != "good"` or `tenure_days < NEW_ACCOUNT_DAYS` | `+0.3` (watch/new), `+0.6` (restricted); long-tenured `good` sets a low baseline (`0.0`). |
| `FP-006` | behavioral-anomaly | `behavioral.anomaly_score ≥ ANOMALY_ELEVATED` | `+0.4`. |

Score is the **sum** of fired contributions, **capped at `1.0`**. (Additive scoring is used because
fraud risk is cumulative — several weak signals together justify elevation — unlike the billing
single-decisive-rule precedence.)

## Evaluation order (deterministic)

1. **Data-completeness gate** — if `load_signals(customer_id)` returned `None` (no record at all):
   `requires_human_review=True`, confidence `0.2`, evidence records the missing-data reason. **Stop.**
   (FR-010; spec edge "missing risk signals".)
2. **Known-fraud-indicator gate (FP-001)** — if on blocklist: `risk_level=high`, confidence `0.95`,
   decisive `known_fraud` + `fraud_policy:FP-001` evidence. **Stop.** (spec edge "known-fraud indicator
   present".)
3. **Contradiction gate** — if strongly-low signals (e.g. long tenure + `good` standing + zero
   chargebacks) coexist with strongly-high signals (e.g. velocity ≥ `VELOCITY_HIGH` on a mismatched
   instrument): `risk_level=elevated`, confidence `0.3`, `requires_human_review=True`, the conflict
   captured in evidence/reasoning. **Stop.** (FR-010; spec edge "contradictory signals" — never
   silently pick a side.)
4. **Score FP-002..FP-006** → cumulative score → level:
   - `score ≥ HIGH_THRESHOLD` → `high`
   - `score ≥ ELEVATED_THRESHOLD` → `elevated`
   - else → `low`
   confidence `0.9` (clear) or `0.6` (borderline — see below).
5. **No applicable resolution** — if signals exist but none map to any rule and nothing is clearly
   clean: `requires_human_review=True` with the stated reason (no-applicable-policy default stance —
   never clear by omission). (spec edge "no applicable policy".)

A fully clean signal set (all rules silent, all owned signals present and benign) resolves to `low`
with confidence `0.9` and at least one `fraud_policy` evidence item recording that no risk rule fired.

## Borderline resolution

A cumulative score landing **exactly** on a threshold resolves **upward** to the higher band
(documented inclusive-upper boundary): exactly `0.5` → `elevated`, exactly `0.8` → `high`. The
borderline is recorded in the reasoning and confidence is lowered to `0.6`. Never left undecided (spec
edge "borderline within policy thresholds").

## Confidence per path (FR-006, research R6)

| Path | confidence |
|------|------------|
| known-indicator → high (FP-001) | `0.95` |
| clear low/elevated/high (all signals present & consistent) | `0.9` |
| borderline (score exactly on a threshold) | `0.6` |
| contradiction | `0.3` |
| missing/unresolvable signals (human review) | `0.2` |

## Determinism guarantee (FR-012)

`scoring.evaluate(signals, request, policy)` is a pure function: no clock-dependent branch beyond the
fixed velocity window already encoded in the seeded signals, no randomness, no I/O. Identical signals
under `poc-fraud-policy` v1.0.0 always yield the identical `(risk_level, confidence, evidence,
policy_references, reasoning_summary, requires_human_review)`.
