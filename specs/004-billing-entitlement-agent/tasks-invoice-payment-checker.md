---
description: "Invoice/Payment Checker task slice for the Billing and Entitlement Agent — companion addendum to tasks.md"
---

# Tasks (addendum): Invoice/Payment Checker

**Input**: Design documents from `/specs/004-billing-entitlement-agent/`
(plan.md, spec.md, research.md, data-model.md, contracts/refund-policy.md, contracts/mock-billing-data.md)

> ⚠️ **Why this is a separate file**: `tasks.md` was being **actively written by a parallel session**
> (focused on the deterministic recommendation engine + idempotency) at the time this run executed, so
> these invoice/payment-checker tasks were kept here to avoid clobbering/racing that file. They are
> written to **merge into `tasks.md` as a new phase** once that session settles — see "Merge guidance"
> at the bottom. Task IDs are `CHK-0xx` to avoid colliding with `tasks.md`'s `T0xx` numbering.

## Scope (this `/speckit-tasks` run)

Implement the **invoice/payment checker** — a slice of the US1 recommendation engine
(`apps/agents/billing_entitlement/rules_engine.py`) plus the invoice/payment facts, the policy rules
they fire, and the seed data they read. Every fact is **owned billing data** (FR-009); the checker
makes no peer call and reads no foreign domain.

**The five checks** (all from owned `Invoice`/`Payment` facts):

| # | Check | Fact | Policy rule | Outcome |
|---|-------|------|-------------|---------|
| 1 | invoice exists | `BillingFacts.invoice is not None` | data-completeness gate | miss → `requires_human_review` |
| 2 | invoice paid | `invoice.paid` | `RP-002` paid-invoice | unpaid → `deny` |
| 3 | payment succeeded | `payment.captured` | `RP-002` paid-invoice | uncaptured → `deny` |
| 4 | charge disputed | `payment.disputed` *(new fact)* | `RP-006` disputed-charge *(new rule)* | disputed → `requires_human_review` |
| 5 | refund already issued | `payment.reversed_amount > 0` | `RP-002` paid-invoice | already reversed → `deny` or `requires_human_review` |

**Acceptance criteria** (from the request) → tasks that satisfy them:

1. **Already-refunded invoice → denial or manual review** → CHK-004 (impl), CHK-001 (test)
2. **Failed payment → denial** → CHK-004 (impl), CHK-001 (test)
3. **Disputed charge → manual review** → CHK-006 + CHK-007 (new fact/rule), CHK-004 (impl), CHK-001 (test)
4. **Evidence references invoice/payment IDs, not raw sensitive data** → CHK-005 (impl), CHK-002 (test)

> **Data-model delta this run introduces** (not yet in `data-model.md` / `contracts/refund-policy.md`):
> `Payment.disputed: bool` and a new citable rule **`RP-006`** (disputed-charge → `requires_human_review`,
> confidence `0.3`). CHK-006/CHK-007 add the code; CHK-008 back-fills the docs.

## Format: `[ID] [P?] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- All paths are repo-root-relative; agent package is `apps/agents/billing_entitlement/`
- **Reused unchanged**: `packages/contracts/events/payloads.py:EvidenceItem`, the runtime, audit, topics

---

## Prerequisites (from `tasks.md`, must exist first)

These checker tasks **extend** base tasks the parallel `tasks.md` already defines. Do not re-create them:

- Foundational models — `Subscription`/`Invoice`/`Payment`/`Entitlement`/`ProductUsage`/`BillingFacts`
  in `apps/agents/billing_entitlement/models.py` (base task `T004`)
- Named policy `RP-001..RP-005` + thresholds in `apps/agents/billing_entitlement/policy.py` (base `T011`)
- Seed dataset + `load_facts` in `apps/agents/billing_entitlement/mock_data.py` (base `T012`)
- Recommendation engine `evaluate(facts, request, policy)` in
  `apps/agents/billing_entitlement/rules_engine.py` (base `T013`)

---

## Tests for the checker (write first; ensure they FAIL before implementation)

- [ ] CHK-001 [P] Add an invoice/payment checker truth table in
  `apps/agents/billing_entitlement/tests/test_invoice_payment_checker.py`: `PR-UNPAID` (unpaid invoice
  **or** uncaptured payment) → `deny` (criterion 2); `PR-ALREADY-REFUNDED` (`reversed_amount > 0`) →
  `deny` **or** `requires_human_review` (criterion 1); `PR-DISPUTED` (`payment.disputed`) →
  `requires_human_review`, `confidence≈0.3` (criterion 3); missing invoice → `requires_human_review`;
  and assert the decisive `policy_reference` (`RP-002`/`RP-006`/completeness gate) is cited.
- [ ] CHK-002 [P] Add an evidence ID-safety test in
  `apps/agents/billing_entitlement/tests/test_domain_isolation.py`: assert every invoice/payment
  `EvidenceItem` references `invoice_id` / `payment_id`, and that no evidence `value`/`description`
  contains raw sensitive data — no card/PAN-like digit runs, no full payment instrument, no PII
  (criterion 4).
- [ ] CHK-003 [P] Add a determinism assertion for the checker in
  `apps/agents/billing_entitlement/tests/test_invoice_payment_checker.py`: the same invoice/payment
  facts evaluated twice yield an identical recommendation + evidence (FR-012).

---

## Implementation for the checker

- [ ] CHK-006 [P] Extend the `Payment` model in `apps/agents/billing_entitlement/models.py` with
  `disputed: bool = False` (the new "charge disputed" fact) and validators `reversed_amount >= 0` and
  `reversed_amount <= amount`.
- [ ] CHK-007 Add policy rule **`RP-006` disputed-charge** to
  `apps/agents/billing_entitlement/policy.py`: condition `payment.disputed`, effect
  `requires_human_review`, confidence `0.3`; register it in the `RefundPolicy` rule list so it is a
  citable `policy_reference` (depends on CHK-006).
- [ ] CHK-009 [P] Extend the seed dataset in `apps/agents/billing_entitlement/mock_data.py` with
  `PR-DISPUTED` (invoice exists, paid, payment captured, `disputed=True`) and confirm `PR-UNPAID`
  (`paid=False`/`captured=False`) and `PR-ALREADY-REFUNDED` (`reversed_amount == amount`) exercise
  checks 2/3 and 5 (depends on CHK-006).
- [ ] CHK-004 Implement the five ordered invoice/payment checks in
  `apps/agents/billing_entitlement/rules_engine.py` within the documented precedence: **invoice exists**
  (completeness gate → review) → **charge disputed** (`RP-006` → `requires_human_review`) → **refund
  already issued** (`RP-002`, `reversed_amount > 0` → `deny`/review) → **invoice paid** + **payment
  succeeded** (`RP-002` → `deny` if either fails). Each fired check records its reason in
  `reasoning_summary`, cites its rule id in `policy_references`, and sets the per-path `confidence`
  (clear deny `0.9`; dispute `0.3`; missing data `0.2`) — pure/deterministic, no peer call
  (depends on CHK-006, CHK-007, CHK-009).
- [ ] CHK-005 In `apps/agents/billing_entitlement/rules_engine.py`, build invoice/payment `EvidenceItem`s
  that reference **`invoice_id` and `payment_id`** plus the boolean/derived states (`paid`, `captured`,
  `disputed`, `reversed_amount > 0`) — explicitly **excluding** raw amounts-as-PII, card/instrument
  data, and any non-ID sensitive payload; `source ∈ {invoice, payment}` (criterion 4; depends on CHK-004).
- [ ] CHK-008 Update `specs/004-billing-entitlement-agent/data-model.md` (§2 `Payment` — add `disputed`)
  and `specs/004-billing-entitlement-agent/contracts/refund-policy.md` (Rules table + confidence
  summary — add `RP-006`) so the design docs stay authoritative for the checker.

**Checkpoint**: All five checks fire from owned invoice/payment facts; the four acceptance criteria are
green (CHK-001/CHK-002); evidence is ID-based and free of raw sensitive data.

---

## Dependencies

- CHK-006 (new `disputed` field) → blocks CHK-007, CHK-009, CHK-004
- CHK-007 (`RP-006`) + CHK-009 (`PR-DISPUTED` seed) → block CHK-004
- CHK-004 (checks) → blocks CHK-005 (evidence built by the checks)
- Tests CHK-001/CHK-002/CHK-003 authored first; they pass after CHK-004/CHK-005
- CHK-008 (docs) can run any time after CHK-006/CHK-007

### Parallel opportunities

- CHK-001, CHK-002, CHK-003 (test files) in parallel
- CHK-006 ∥ (then) CHK-009; CHK-008 ∥ implementation

---

## Merge guidance (folding into `tasks.md`)

When the parallel session's `tasks.md` settles, merge this slice in as **"Phase 11: Invoice/Payment
Checker"**:

1. Renumber `CHK-0xx` → the next free `T0xx` after the last task in `tasks.md`.
2. Fold CHK-006 into base `T004`'s `Payment` model (or keep as a follow-on task).
3. Fold CHK-007 into base `T011` (policy) and CHK-009 into base `T012` (mock data), or keep as
   explicit extension tasks — both are valid.
4. CHK-004/CHK-005 extend base `T013` (`rules_engine.evaluate`); CHK-008 updates the design docs.
5. Add the four acceptance-criteria rows to `tasks.md`'s Notes/criteria-mapping section.
