# Contract: Mock Risk/Fraud Signal Dataset

The Risk and Fraud Agent owns an **in-process, seeded** signal dataset (`mock_data.py`), keyed by
`customer_id` (R3). It is illustrative PoC data (spec Assumption), sufficient to exercise every policy
branch deterministically. No database or external risk service is integrated.

## Lookup contract

```python
def load_signals(customer_id: str) -> RiskSignals | None: ...
```

- **Hit** → a `RiskSignals` bundling the five owned domains for that customer.
- **Miss** (unknown `customer_id`) → `None`, which the service maps to the **missing-data path**
  (`requires_human_review=True`, confidence `0.2`, recorded reason — FR-010). Never a fabricated
  verdict.

Lookup is **by `customer_id` only** — the risk input carries no `purchase_reference` (the consumer's
`RiskAnalysisRequestInput` is customer-centric). Lookup is case-sensitive and does not fall back to
foreign-domain data (FR-009).

## Seed coverage (drives SC-004 single-signal matrix + SC-005 fault cases)

| customer_id | Scenario | Key signal differences | Expected verdict |
|-------------|----------|------------------------|------------------|
| `CUS-CLEAN` | clean baseline | long tenure, `good` standing, 0 chargebacks, low velocity, matched instrument, not blocklisted | `low` (conf 0.9) |
| `CUS-CHARGEBACKS` | repeat chargebacks | `chargebacks = 2` (else clean) | `high` (FP-002) |
| `CUS-ONE-CHARGEBACK` | single chargeback | `chargebacks = 1` (else clean) | `elevated` (FP-002) |
| `CUS-VELOCITY` | refund-abuse burst | `refund_requests_in_window = 5` (else clean) | `high` (FP-003) |
| `CUS-INSTRUMENT` | instrument mismatch | `billing_details_match = False` (else clean) | `elevated` (FP-004) |
| `CUS-CARD-TESTING` | card testing | `card_testing_pattern = True` (else clean) | `elevated`/`high` (FP-004) |
| `CUS-NEW-ACCOUNT` | new / poor standing | `tenure_days = 5`, `status = "watch"` (else clean) | `elevated` (FP-005) |
| `CUS-ANOMALY` | behavioral anomaly | `anomaly_score = 0.85` (else clean) | `elevated` (FP-006) |
| `CUS-BLOCKLIST` | known-fraud indicator | `on_blocklist = True` | `high` (FP-001 floor, conf 0.95) |
| `CUS-CONTRADICTION` | conflicting signals | long tenure + `good` standing + 0 chargebacks **and** velocity = 5 on a mismatched instrument | `elevated` + `requires_human_review` (conf 0.3) |
| `CUS-BORDERLINE` | exactly on a threshold | signals summing to score exactly `0.5` (or `0.8`) | `elevated` (or `high`), conf 0.6 (upper-band rule) |
| *(unknown)* | missing data | no record | `requires_human_review` (conf 0.2, FR-010) |

The customer ids above are the demo seeds; the single-signal matrix test (SC-004) varies exactly one
signal at a time from `CUS-CLEAN` and asserts the level changes in the documented direction with the
change cited in evidence.

## Isolation guarantee (SC-003 / FR-009)

`RiskSignals` contains **only** risk/fraud-domain fields. It carries no billing-eligibility facts
(subscriptions, invoices, payments-as-eligibility, entitlements, product usage) and no
customer-resolution state. The agent reads its verdict solely from these owned signals and the
`poc-fraud-policy`; it makes no synchronous call to any peer to obtain a fact.
