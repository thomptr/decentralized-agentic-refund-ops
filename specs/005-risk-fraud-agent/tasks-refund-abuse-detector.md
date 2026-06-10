---
description: "Refund Abuse Detector task slice for the Risk and Fraud Agent — companion addendum to tasks.md"
---

# Tasks (addendum): Refund Abuse Detector

**Input**: Design documents from `/specs/005-risk-fraud-agent/`
(plan.md, spec.md, research.md, data-model.md, contracts/fraud-policy.md, contracts/mock-risk-data.md)

> ⚠️ **Why this is a separate file**: `tasks.md` was being **actively written by one or more parallel
> sessions** (adding the AgentCore-local, Local-A2A-startup, Local-Config, Customer-Resolution-integration,
> and Behavioral-Risk-Analyzer deliverables) at the time this run executed — it grew from ~330 to ~980
> lines mid-run with task IDs being renumbered on each pass. To avoid clobbering/racing that file, these
> refund-abuse-detector tasks are kept here. They are written to **merge into `tasks.md` as a new phase**
> once those sessions settle — see "Merge guidance" at the bottom. Task IDs are `RAD-0xx` to avoid
> colliding with `tasks.md`'s `T0xx` numbering. This mirrors the precedent set by feature 004's
> `tasks-invoice-payment-checker.md` (`CHK-0xx`) addendum.

## Scope (this `/speckit-tasks` run)

Implement the **refund abuse detector** — a pure, deterministic component that surfaces the six
requested abuse signals as a **structured signal set**, each carrying its own evidence, and folds them
into the existing deterministic fraud verdict (`apps/agents/risk_fraud/scoring.py`) as a named,
citable policy rule. Every signal is **owned risk/fraud data** (FR-003/FR-009); the detector makes no
peer call and reads no foreign domain. It reuses the owned-signal models, the `poc-fraud-policy` engine,
and the `EvidenceItem` contract — **no new shared contract, topic, or dependency** (Principle V).

**The six abuse signals** (all from owned `RefundDisputeHistory` / `BehavioralSignal` facts):

| # | Requested signal | Owned source (`models.py`) | New field? | Policy rule |
|---|------------------|----------------------------|-----------|-------------|
| 1 | prior refund count | `RefundDisputeHistory.prior_refunds` | existing | FP-007 |
| 2 | refund frequency | `BehavioralSignal.refund_requests_in_window` / `velocity_window_days` | existing | FP-003 (+FP-007 surface) |
| 3 | refund amount vs. historical purchases | `RefundDisputeHistory.refund_amount_to_historical_ratio` | **NEW** | FP-007 |
| 4 | duplicate refund attempts | `RefundDisputeHistory.duplicate_refund_attempts` | **NEW** | FP-007 |
| 5 | prior chargebacks | `RefundDisputeHistory.chargebacks` | existing | FP-002 (+FP-007 surface) |
| 6 | support abuse flags | `RefundDisputeHistory.support_abuse_flags` | **NEW** | FP-007 |

**Acceptance criteria** (from the request) → tasks that satisfy them:

1. **Detector returns structured signals** → RAD-001 (`RefundAbuseReport.signals: list[RefundAbuseSignal]`,
   one entry per requested signal) + RAD-005 (impl); asserted by RAD-004 (test).
2. **Signals include evidence** → RAD-005 (each `RefundAbuseSignal` carries a non-empty `EvidenceItem`
   citing the concrete owned signal); asserted by RAD-004 (test).
3. **Rule output is deterministic** → RAD-005 (pure function — no clock/random/IO; identical signals →
   identical report) + RAD-006 (folded determinism preserved); asserted by RAD-004 (twice-called
   identity) and FR-012.

> **Data-model delta this run introduces** (not yet in `data-model.md` / `contracts/fraud-policy.md`):
> three new owned fields on `RefundDisputeHistory` (`refund_amount_to_historical_ratio: float >= 0`,
> `duplicate_refund_attempts: int >= 0`, `support_abuse_flags: int >= 0`), the new `FP-007 refund-abuse`
> policy rule + thresholds, and the structured detector output models `RefundAbuseSignal` /
> `RefundAbuseReport`. RAD-007 back-fills the spec docs.

---

## Phase 1: Refund-Abuse Signals, Policy Rule & Seeds (Foundational)

- [ ] RAD-001 [P] Extend `apps/agents/risk_fraud/models.py`: add the three new owned fields to
  `RefundDisputeHistory` — `refund_amount_to_historical_ratio: float` (`>= 0`),
  `duplicate_refund_attempts: int` (`>= 0`), `support_abuse_flags: int` (`>= 0`) — and define the
  **structured detector output** models: `RefundAbuseSignal` (`signal_name: str`, `triggered: bool`,
  `severity: Literal["none","elevated","high"]`, `evidence: EvidenceItem`) and `RefundAbuseReport`
  (`signals: list[RefundAbuseSignal]` — exactly one entry per requested signal, `abuse_score: float`
  0..1, `policy_references: list[str]`), importing `EvidenceItem` unchanged from `packages/contracts`
  (acceptance 1; data-model §2/§4).
- [ ] RAD-002 [P] Extend `apps/agents/risk_fraud/policy.py` with the **`FP-007` refund-abuse** rule and
  its thresholds — `PRIOR_REFUND_ELEVATED` / `PRIOR_REFUND_HIGH`, `REFUND_RATIO_ELEVATED`,
  `DUPLICATE_ATTEMPTS_ELEVATED`, `SUPPORT_ABUSE_ELEVATED` — with documented additive contributions
  (summed with the other FP-00x weights, capped at `1.0`), and register `FP-007` in the
  `poc-fraud-policy` v1.0.0 `rules` list so it is a citable `policy_reference` (FR-005/FR-012;
  `contracts/fraud-policy.md`).
- [ ] RAD-003 Extend `apps/agents/risk_fraud/mock_data.py`: seed a `CUS-REFUND-ABUSER` customer
  exercising **all six** abuse signals (high `prior_refunds`, high `refund_requests_in_window`, high
  `refund_amount_to_historical_ratio`, non-zero `duplicate_refund_attempts`, non-zero `chargebacks`,
  non-zero `support_abuse_flags`) and confirm `CUS-CLEAN` leaves every abuse signal untriggered (FR-003).
  Depends on RAD-001's new fields.

**Checkpoint**: The abuse fields, the `FP-007` rule, and a triggering + a clean seed exist.

---

## Phase 2: Refund-Abuse Detector (Priority: P1) 🎯 MVP

**Goal**: A pure, deterministic `detect_refund_abuse(signals, request) -> RefundAbuseReport` returning
one structured, evidence-bearing signal per requested input.

**Independent Test**: `pytest apps/agents/risk_fraud/tests/test_refund_abuse_detector.py -q` (no broker)
proves structured signals, per-signal evidence, and run-to-run determinism.

- [ ] RAD-004 [P] **TDD** Write `apps/agents/risk_fraud/tests/test_refund_abuse_detector.py` (failing
  first; **no broker**): assert `detect_refund_abuse` returns a `RefundAbuseReport` whose `signals` list
  has **exactly one structured entry per requested signal** (prior refund count, refund frequency,
  refund-amount-vs-historical ratio, duplicate attempts, prior chargebacks, support abuse flags)
  [acceptance 1]; each entry carries a **non-empty `EvidenceItem`** whose `source` ∈ the owned-signal
  set (`refund_history`/`behavioral`) and whose `value` cites the concrete signal [acceptance 2];
  calling it **twice** on identical signals returns an **identical** report [acceptance 3 — determinism];
  an absent `refund_history` yields **untriggered** entries (`triggered=False`), never omitted and never
  a fabricated trigger.
- [ ] RAD-005 Implement the pure detector in **new module** `apps/agents/risk_fraud/refund_abuse.py`:
  `detect_refund_abuse(signals: RiskSignals, request: RiskAssessmentRequest) -> RefundAbuseReport`
  evaluates each of the six abuse signals against the `FP-007` thresholds (RAD-002), emits a structured
  `RefundAbuseSignal` per signal with its `EvidenceItem` and `severity`, sums the additive `abuse_score`
  (capped `1.0`), and lists `FP-007` in `policy_references` when any signal triggers — **no
  clock/random/IO**; make RAD-004 pass (FR-005/FR-006/FR-012).

**Checkpoint**: The detector is independently testable, returns structured evidence-bearing signals, and
is deterministic — proving all three acceptance criteria with no broker.

---

## Phase 3: Integrate into the Verdict & Validate (Polish)

- [ ] RAD-006 Integrate the detector into the rules engine `apps/agents/risk_fraud/scoring.py`: fold the
  `RefundAbuseReport.abuse_score` in as the **FP-007 contribution** to the cumulative risk score, merge
  its per-signal `EvidenceItem`s into `RiskAssessment.evidence`, and add `FP-007` to `policy_references`
  when any abuse signal triggers — preserving the additive-score determinism and the
  known-fraud/contradiction gate precedence; extend the scoring single-signal matrix (SC-004) with the
  three new abuse fields (each shifts the level in the documented direction with the change cited in
  evidence).
- [ ] RAD-007 [P] Run `pytest apps/agents/risk_fraud/tests/test_refund_abuse_detector.py -q` (and the
  scoring matrix), confirm the three acceptance criteria, and back-fill the spec docs:
  `specs/005-risk-fraud-agent/data-model.md` (§2 the three new `RefundDisputeHistory` fields; §4
  `RefundAbuseReport`/`RefundAbuseSignal`) and `specs/005-risk-fraud-agent/contracts/fraud-policy.md`
  (the `FP-007` rule row + thresholds).

**Checkpoint**: The refund-abuse signals drive the fraud verdict through a citable `FP-007` rule with
traceable evidence, and the spec contracts document the delta.

---

## Dependencies & Execution Order

- **Phase 1 (RAD-001..003)**: RAD-001 (models) + RAD-002 (policy) are different files → parallel;
  RAD-003 (seeds) depends on RAD-001's new fields. Blocks Phase 2.
- **Phase 2 (RAD-004..005)**: TDD RAD-004 is written and must FAIL before RAD-005 implements the
  detector. The MVP — independently testable with no broker.
- **Phase 3 (RAD-006..007)**: RAD-006 folds the detector into `scoring.py` (depends on RAD-005 + the
  existing scoring engine); RAD-007 validates and updates the spec contracts last.

### Parallel Opportunities

- Phase 1: RAD-001 ∥ RAD-002; RAD-003 after RAD-001.
- Phase 2: RAD-004 (test) before RAD-005 (impl).
- Phase 3: RAD-006 then RAD-007.

### MVP

RAD-001 → RAD-002 → RAD-004 → RAD-005 proves all three acceptance criteria: the detector returns **one
structured signal per requested input**, **each with evidence**, **deterministically** — independently
of the Kafka transport and the full verdict path (which RAD-006 then folds it into).

---

## Merge guidance (fold into `tasks.md` once the parallel sessions settle)

When `tasks.md` stops being actively rewritten, merge this slice as a new phase:

1. Renumber `RAD-001..007` to the next free `T0xx` block after the then-current max id in `tasks.md`.
2. Map the phases: RAD Phase 1 → extend the existing **Foundational** phase (models/policy/mock-data
   tasks); RAD Phase 2 → a new **"Refund Abuse Detector (US3)"** user-story phase; RAD Phase 3 → extend
   **US1 scoring integration** + **Polish**.
3. Reconcile the data-model/policy delta: if the parallel **"Behavioral Risk Analyzer"** deliverable
   already added overlapping velocity/behavioral fields or an `FP-007`/`FP-008` rule, align the new
   `RefundDisputeHistory` fields and the refund-abuse rule id to avoid a duplicate rule number (keep one
   citable id per distinct rule).
4. Keep the structured-signal + evidence + determinism acceptance mapping intact — it is this run's
   contribution and is not covered by the other deliverables.
