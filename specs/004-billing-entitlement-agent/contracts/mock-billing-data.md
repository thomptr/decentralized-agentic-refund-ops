# Contract: Owned Mock Billing Data (seeded fixtures)

The agent owns its billing facts as an **in-process seeded dataset** (`mock_data.py`). No external
billing system, database, or service (spec Assumption, FR-003). The dataset is illustrative but
sufficient to exercise every policy branch.

## Lookup

```
load_facts(purchase_reference: str, customer_id: str) -> BillingFacts | None
```

- Primary key: `purchase_reference` (the charge a refund targets).
- Fallback: `customer_id`.
- **Miss → `None`** → the agent takes the missing-data path: `requires_human_review` with reason
  "no billing record for purchase_reference=…", `confidence = 0.2` (FR-010, never a fabricated verdict).

## Seed cases (drives SC-004 single-fact matrix + SC-005 fault cases)

Each row is a `BillingFacts` bundle; columns list the salient fact. Expected verdict assumes a
well-formed request for that `purchase_reference`.

| purchase_reference | window | invoice paid | payment reversed | entitlement delivered | usage_ratio | subscription | expected |
|--------------------|--------|--------------|------------------|-----------------------|-------------|--------------|----------|
| `PR-APPROVE` | within (5d) | paid | 0 | not delivered | 0.10 (light) | active | **approve** |
| `PR-WINDOW-EXPIRED` | outside (45d) | paid | 0 | not delivered | 0.10 | active | **deny** (RP-001) |
| `PR-UNPAID` | within | **unpaid** | 0 | not delivered | 0.10 | active | **deny** (RP-002) |
| `PR-ALREADY-REFUNDED` | within | paid | **full** | not delivered | 0.10 | cancelled | **deny** (RP-002 already reversed) |
| `PR-HEAVY-USAGE` | within | paid | 0 | delivered | **0.95 (heavy)** | active | **deny** (RP-004) |
| `PR-CONTRADICTION` | within | paid | **partial>0 but claimed unrefunded** | active entitlement on **cancelled** sub | 0.10 | cancelled | **requires_human_review** (contradiction gate) |
| `PR-BORDERLINE` | exactly 30d | paid | 0 | not delivered | exactly 0.80 | active | **approve** (within inclusive; usage below heavy) conf=0.6 |
| *(unknown ref)* | — | — | — | — | — | — | **requires_human_review** (missing data) |

> The single-fact matrix (SC-004) is built by varying exactly one column at a time off `PR-APPROVE`
> and asserting the verdict flips consistently with that fact, with the change reflected in the
> evidence.

## Single-fact isolation property (SC-003 / FR-009)

The dataset contains **only** subscription/invoice/payment/entitlement/usage facts — no risk score,
fraud signal, or customer-workflow field exists in the schema, so the agent **cannot** read foreign
data even by accident. The `test_domain_isolation.py` test asserts every produced `EvidenceItem.source`
is in `{subscription, invoice, payment, entitlement, product_usage, refund_policy}`.
