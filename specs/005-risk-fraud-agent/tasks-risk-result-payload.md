# Tasks (addendum): Risk Result Payload Definition — Phase R (T101–T110)

> **Why this is a separate file.** This is the realization of the **"Highlighted scope — Risk result
> payload definition (this run's input)"** section in `tasks.md` (Phase R, T101–T110). It was written to
> a sibling file because, during this `/speckit-tasks` run, a **concurrent session** (the
> `…_worktrees/Create-Risk-Agent` worktree) was continuously regenerating/appending to `tasks.md` in real
> time — growing it past 1100 lines and leaving 14 duplicate `T0xx` ids — so every read-then-append to the
> shared file lost the race. The highlighted-scope decisions (1–4) **did** land in `tasks.md` and point
> here. **Merge these tasks into `tasks.md` (after the last Phase) once the concurrent session settles.**

**Input**: `/specs/005-risk-fraud-agent/` (plan.md, spec.md, research.md, data-model.md, contracts/) +
this run's input: *"Define risk result payload … risk levels low|medium|high|unknown; recommendations
approve_risk_clearance|allow_with_caution|deny_or_escalate|manual_review|request_more_information."*

## The two decisions confirmed with the requester (govern these tasks)

1. **Evolve the shared contract + update feature 003** — `RiskReviewCompletedPayload` is expanded and the
   003 consumer is updated to read it. **SC-009's "consumer unchanged" is superseded** (consumer updated,
   not untouched). This also **supersedes** the earlier "action vocabulary" highlighted scope that kept
   the verbs internal (`recommended_action`) and the wire `recommendation = risk_level.value`.
2. **Risk-level vocabulary is `low | medium | high | unknown`** (replaces the plan/data-model
   `low/elevated/high`). `medium` replaces `elevated`; `unknown` is the missing-data path.

### Evolved wire shape — `RiskReviewCompletedPayload` (`packages/contracts/events/payloads.py`)

| Field | Type | Source |
|-------|------|--------|
| `case_id` | `str` | `request.case_id` (**new**) |
| `ticket_id` | `str` | `request.ticket_id` |
| `customer_id` | `str` | `request.customer_id` (**new**) |
| `risk_level` | `str` | `low \| medium \| high \| unknown` (**new**) |
| `risk_score` | `int` | `round(score*100)`, `0..100` (**new**) |
| `recommendation` | `str` | action verb (**redefined** — was `risk_level.value`) |
| `confidence` | `float` | `assessment.confidence` (`0..1`) |
| `evidence` | `list[EvidenceItem]` | non-empty; ≥1 `source="fraud_policy"` |
| `reasoning_summary` | `str` | `assessment.reasoning_summary` |
| `requires_human_review` | `bool` | `assessment.requires_human_review` |

### Risk-level mapping (agent)

blocklist / score ≥ `HIGH_THRESHOLD` → `high`; score ≥ `ELEVATED_THRESHOLD` → `medium`; clean → `low`;
missing/unanalyzable → `unknown` (+ `requires_human_review`); contradiction gate → `medium` (+ review).

### `recommendation` action-verb derivation (on the wire)

| Condition | `risk_level` | `recommendation` |
|-----------|--------------|------------------|
| Clean signals, no rule fired | `low` | `approve_risk_clearance` |
| Score ≥ `ELEVATED_THRESHOLD`, no review gate | `medium` | `allow_with_caution` |
| Blocklist / score ≥ `HIGH_THRESHOLD` | `high` | `deny_or_escalate` |
| Contradiction / explicit human-review | `medium`/`high` | `manual_review` |
| Missing/unresolvable signals | `unknown` | `request_more_information` |

### Consumer (003) mapping after update

Read `risk_level` first — `low→low`, `medium→elevated`, `high→high`, `unknown→low + requires_human_review`;
fall back to the action-verb `recommendation` (`approve_risk_clearance→low`, `allow_with_caution→elevated`,
`deny_or_escalate→high`, `manual_review`/`request_more_information→requires_human_review`) for back-compat
with the legacy stub shape. `RiskFinding.level` stays `low|elevated|high` (its `elevated` == `medium`).

> **Numbering note**: **T101–T110** is a deliberately collision-free range (the shared `tasks.md` already
> has duplicate `T0xx` ids from concurrent runs). Earlier tasks this run **modifies** are referenced by
> id + file/role: `RiskLevel` enum ("T004", `models.py`), `RiskAssessment` ("T006", `models.py`), scoring
> ("T015", `scoring.py`), uncertainty ("T025", `service.py`), result mapper ("T019", `service.py`), A2A
> output ("T017", `main.py`), result-contract test ("T018"), e2e ("T039").

## Format: `[ID] [P?] [Story] Description`

---

## Phase R1: Evolve the Shared Contract (Foundational — blocks R2–R5)

- [ ] T101 Evolve `RiskReviewCompletedPayload` in `packages/contracts/events/payloads.py` to the
  ten-field shape: add `case_id: str`, `customer_id: str`, `risk_level: str`,
  `risk_score: Annotated[int, Field(ge=0, le=100)]`; keep `ticket_id`, `confidence` (`ge=0,le=1`),
  `evidence: list[EvidenceItem]`, `reasoning_summary`, `requires_human_review`; `recommendation: str` now
  carries an action verb. Preserve `model_config = ConfigDict(frozen=True, extra="forbid")` and the
  `__all__` export. (Only edit to `packages/contracts/`; supersedes the reuse-unchanged note in
  `contracts/risk-result-contract.md`.)
- [ ] T102 Verify the registry binding survives T101 in `src/agent_foundation/payloads/__init__.py`:
  `PAYLOAD_REGISTRY[TOPIC_RISK_RESULT] is RiskReviewCompletedPayload` (re-export unchanged; **no new
  topic** — `TOPIC_RISK_RESULT` stays resolver-derived). Adjust the re-export only if required.

## Phase R2: Adopt the New Vocabularies in the Agent

- [ ] T103 Modify the `RiskLevel` StrEnum in `apps/agents/risk_fraud/models.py` (prior "T004") to
  `LOW="low"`, `MEDIUM="medium"`, `HIGH="high"`, `UNKNOWN="unknown"` (replaces `elevated` with `medium`,
  adds `unknown`). Add a `Recommendation` StrEnum (`APPROVE_RISK_CLEARANCE`, `ALLOW_WITH_CAUTION`,
  `DENY_OR_ESCALATE`, `MANUAL_REVIEW`, `REQUEST_MORE_INFORMATION`) — the **wire** `recommendation`,
  retiring the internal-only `recommended_action`.
- [ ] T104 Modify the `RiskAssessment` model in `apps/agents/risk_fraud/models.py` (prior "T006"): add
  `risk_score: int` (0..100) and make `recommendation: Recommendation` the published action verb (drop or
  alias the old `recommended_action`). Keep `risk_level: RiskLevel`, `confidence`, non-empty `evidence`,
  `policy_references`, `reasoning_summary`, `requires_human_review`.
- [ ] T105 Modify the scoring/gate mapping in `apps/agents/risk_fraud/scoring.py` (prior "T015") and the
  uncertainty paths in `scoring.py`/`service.py` (prior "T025"): threshold mapping yields `high` (score ≥
  HIGH or blocklist), `medium` (score ≥ ELEVATED), `low` (clean); missing/unresolvable → `unknown` +
  `requires_human_review`; contradiction → `medium` + `requires_human_review`. Set `risk_score =
  round(score*100)` (cap 100) and derive `recommendation` per the action-verb table. Preserve determinism
  (FR-012). Update the truth-table tests in `apps/agents/risk_fraud/tests/test_scoring.py` (prior "T014")
  from `low/elevated/high` to `low/medium/high/unknown`.

## Phase R3: Map to the Evolved Payload + A2A Output

- [ ] T106 Modify the result mapper `to_result_payload(assessment, request)` in
  `apps/agents/risk_fraud/service.py` (prior "T019") to populate the evolved payload: `case_id`,
  `customer_id`, `ticket_id`, `risk_level=assessment.risk_level.value`, `risk_score`,
  `recommendation=assessment.recommendation.value`, `confidence`, `evidence`, `reasoning_summary`,
  `requires_human_review`; ≥1 `source="fraud_policy"` evidence item.
- [ ] T107 Modify the A2A output data part in `apps/agents/risk_fraud/service.py` /
  `apps/agents/risk_fraud/main.py` (prior "T017") to carry `risk_level`, `risk_score`, the action-verb
  `recommendation`, `confidence`, `evidence`, `policy_references`, `reasoning_summary`,
  `requires_human_review` (keep a numeric `score==confidence` for stub-compatible consumers).

## Phase R4: Update the Feature-003 Consumer (decision 1)

- [ ] T108 Update `apps/agents/customer_resolution/event_handlers.py` — `normalize_risk_result` and
  `risk_result_handler`: prefer the explicit `risk_level` field (`low→low`, `medium→elevated`,
  `high→high`, `unknown→low + requires_human_review`); fall back to the action-verb `recommendation`
  mapping (`approve_risk_clearance→low`, `allow_with_caution→elevated`, `deny_or_escalate→high`,
  `manual_review`/`request_more_information→requires_human_review`), keeping the legacy stub-shape
  (`recommendation` ∈ low/elevated/high, or `risk`) path for back-compat. `RiskFinding.level` stays
  `low|elevated|high`.
- [ ] T109 Grep `recommendation`/`risk_level` across `apps/agents/customer_resolution/` and reconcile any
  other call site that reads `payload.recommendation` as a level (e.g. `a2a_handlers.py`, `state_store.py`
  parked-result consumers, `tests/conftest.py` fixtures) to the `risk_level`-first logic from T108.

## Phase R5: Contract & Consumer Round-Trip Tests

- [ ] T110 Update the round-trip/consumer tests for the evolved contract: (a) modify
  `apps/agents/risk_fraud/tests/test_result_contract.py` (prior "T018") to assert all ten fields populate,
  `risk_level ∈ {low,medium,high,unknown}`, `recommendation` ∈ the five action verbs, `0 ≤ risk_score ≤
  100`, ≥1 `fraud_policy` evidence item, and registry membership; (b) update
  `apps/agents/customer_resolution/tests/test_adapters.py` for the `risk_level`→`RiskFinding.level`
  mapping (`medium→elevated`, `unknown→low+review`) and the action-verb fallbacks, keeping legacy cases
  green; (c) extend the e2e `apps/agents/risk_fraud/tests/test_risk_agent_e2e.py` (prior "T039") so the
  **updated** 003 consumer reaches a decision from the evolved `RiskReviewCompletedPayload` (SC-009
  reinterpreted: consumer updated in T108, not unchanged).

## Dependencies, Parallelism & Strategy

- **R1 (T101–T102)**: foundational contract edit. Blocks R2–R5. T102 follows T101.
- **R2 (T103–T105)**: depends on R1 + existing US1/US4 impl. T103 (enums) → T104 (model) → T105 (scoring),
  same-file/sequential.
- **R3 (T106–T107)**: depends on R2 (needs the evolved `RiskAssessment`).
- **R4 (T108–T109)**: depends on R1 (the wire shape); runs in parallel with R2/R3 (different package).
- **R5 (T110)**: depends on R3 (publish) + R4 (consume) — proves the round-trip.

### Parallel opportunities

- After T101/T102, the agent side (R2→R3) and the consumer side (R4) run in parallel (different packages),
  converging on T110. T110's three sub-updates touch three different test files → parallel.

### Deliverable MVP

T101 → T103 → T104 → T105 → T106 → T108 → T110 proves the evolved contract end to end: the agent publishes
a ten-field `RiskReviewCompletedPayload` with `risk_level ∈ {low,medium,high,unknown}` and an action-verb
`recommendation`, and the **updated** 003 consumer reaches the same decisions from it.
