---
description: "Task list: Risk and Fraud Agent — Architecture Documentation (standalone)"
---

# Tasks: Risk and Fraud Agent — Architecture Documentation

**Input**: Design documents from `/specs/005-risk-fraud-agent/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Why this is a separate file**: The feature's implementation task list (`tasks.md`) was being rewritten
by multiple concurrent `/speckit-tasks` sessions, producing colliding task IDs and duplicate phases.
This documentation deliverable is therefore kept in its own self-contained file with its own task
numbering (T001–T013) so it stays stable and unambiguous.

**Scope**: Author five architecture documents under `docs/architecture/` that explain the **shipped**
Risk and Fraud Agent without requiring a code read:

| File | Documents | Primary story |
|------|-----------|---------------|
| `risk-fraud-agent.md` | Agent overview / hub | US1, US3, US7 |
| `risk-result-contract.md` | Published result event + dual-path delivery | US2 |
| `mock-risk-data.md` | Owned seeded signal dataset | US3 |
| `risk-scoring-rules.md` | Fraud policy, thresholds, scoring, human-review | US3, US4 |
| `agentcore-local-risk-agent.md` | AgentCore CLI / HTTP local-dev path | Operational (R9) |

**Tests**: Not applicable — documentation deliverable. "Validation" tasks confirm each doc matches its
source-of-truth artifact rather than executing code tests.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: The user story / concern the doc primarily documents
- Every task names an exact file path

## Path Conventions

- Documentation root: `docs/architecture/` (already exists; siblings: `event-contracts.md`,
  `adding-new-agent.md`, `topic-naming.md`)
- Source-of-truth artifacts: `specs/005-risk-fraud-agent/` (spec, plan, research, data-model, contracts)
- Link from `docs/architecture/*.md` back to artifacts with relative paths, e.g.
  `../../specs/005-risk-fraud-agent/contracts/fraud-policy.md`

**Derivative-only rule**: every threshold, `FP-00x` id, payload field, topic, capability id, and FR/SC
citation in these docs MUST trace to a `specs/005-risk-fraud-agent/` artifact. Introduce no new facts.

---

## Phase 1: Setup (Documentation Conventions)

**Purpose**: Match the house style of the existing `docs/architecture/` set before authoring.

- [ ] T001 Review `docs/architecture/event-contracts.md`, `docs/architecture/adding-new-agent.md`, and `docs/architecture/topic-naming.md` to capture the house style (H1 title, H2 sections, fenced `python`/`text` blocks, relative links) and confirm `docs/architecture/` is the target directory for all five new files.
- [ ] T002 Adopt a shared "Sources" convention for the five new docs: each opens with a one-line summary and a **Sources** note linking the authoritative `specs/005-risk-fraud-agent/` artifact(s) it derives from (spec FR/SC ids, `research.md` R-numbers, `data-model.md` sections, `contracts/*`). Record the convention to reuse across T004–T008.

---

## Phase 2: Foundational (Cross-Reference Map)

**Purpose**: One blocking prerequisite — a single authoritative mapping of each doc to its source
artifacts and its sibling links — so cross-links and FR/SC citations stay consistent.

**⚠️ CRITICAL**: Complete before authoring any doc.

- [ ] T003 Build the documentation cross-reference map (in the PR description or a scratch note, not a shipped file): for each doc list (a) its primary story/concern, (b) source artifact(s), (c) sibling docs it must link to. Map: `risk-fraud-agent.md` → US1/US3/US7, from `plan.md`+`spec.md`, hub linking the other four; `risk-result-contract.md` → US2, from `contracts/risk-result-contract.md`+`data-model.md` §5; `mock-risk-data.md` → US3, from `contracts/mock-risk-data.md`+`data-model.md` §2; `risk-scoring-rules.md` → US3/US4, from `contracts/fraud-policy.md`+`research.md` R4/R6+`data-model.md` §3/§6; `agentcore-local-risk-agent.md` → operational/R9, from `research.md` R9+`quickstart.md` §C+`plan.md` AgentCore decision.

**Checkpoint**: Source map agreed — the five docs can be authored in parallel.

---

## Phase 3: Agent Overview Doc — US1/US3/US7 (Priority: P1) 🎯 MVP

**Goal**: A single landing doc explaining what the agent is, its one capability, how it fits the event
foundation, and the guardrails that keep it independent. The hub the other four docs hang off.

**Independent Test**: A reader can, from this doc alone, state the agent's single responsibility, its
capability id and agent id, its inputs/outputs, the dual-path result delivery, and the two hard
guardrails — and follow links to the four detail docs.

- [ ] T004 [P] [US1] Create `docs/architecture/risk-fraud-agent.md` (the hub doc) derived from `plan.md` + `spec.md`, sections: (1) **Purpose & single responsibility** — risk/fraud assessment only; replaces the prior `apps/agents/risk_fraud/main.py` stub that returned a fixed `{"risk":"low","score":0.1}` (plan Summary); (2) **Capability** — `assess_fraud_risk`, agent id `risk-fraud-agent`, advertised via shared discovery, with the `assess_refund_risk` naming note (research R0; FR-002/FR-018); (3) **Input & output** — `RiskAssessmentRequest` fields and the `RiskAssessment` verdict shape (data-model §1/§4); (4) **Architecture** — reused `001`/`002` runtime+transport, handler-owned `Publisher` dual-path (research R2), `apps/agents/risk_fraud/` package layout (plan Project Structure); (5) **Guardrails** — domain isolation FR-009 (no billing/customer-resolution data, no synchronous peer call) and no-supervisor FR-016 (US7); (6) **Idempotency & audit** — `task_id` dedup before handler (FR-013) and the runtime's `accepted`/`completed`/`failed`/`rejected`/`duplicate_skipped` lifecycle events (FR-014); (7) **Related documents** — link `risk-scoring-rules.md`, `mock-risk-data.md`, `risk-result-contract.md`, `agentcore-local-risk-agent.md`.
- [ ] T005 [US1] In `docs/architecture/risk-fraud-agent.md`, add a "How an assessment flows" subsection summarizing the per-assessment state machine from `data-model.md` §6 (validate → load signals → known-indicator gate → contradiction gate → score → level / human-review) as a high-level prose + `text` diagram, deferring rule detail to `risk-scoring-rules.md`.

**Checkpoint**: The hub doc is complete and links the four detail docs.

---

## Phase 4: Risk Result Contract Doc — US2 (Priority: P1)

**Goal**: Document the structured, reused result the agent publishes — payload, dual-path delivery,
envelope correlation, consumer compatibility, and audit.

**Independent Test**: A reader can name the topic and payload model, list every published field and its
source, explain why there is no dedicated `policy_references` field (and how policy refs ride as
evidence), and confirm the existing `003` consumer is unchanged (SC-009).

- [ ] T006 [P] [US2] Create `docs/architecture/risk-result-contract.md` derived from `contracts/risk-result-contract.md` + `data-model.md` §5, sections: (1) **Reused, not new** — no new contract/topic; `TOPIC_RISK_RESULT` = `local.risk.review.completed.v1`, already in `_CANONICAL_TOPICS`/`TOPIC_NAMES` and `PAYLOAD_REGISTRY` (FR-019); (2) **Payload** — `RiskReviewCompletedPayload` field table (`ticket_id`, `recommendation` = level string, `confidence` 0–1, `evidence`, `reasoning_summary`, `requires_human_review`) and `EvidenceItem` `{source, description, value}` with `source ∈ {account_standing, refund_history, payment_instrument, behavioral, known_fraud, fraud_policy}`; (3) **Policy references as evidence** — no dedicated field, so fired `FP-00x` ids ride as `source="fraud_policy"` evidence (FR-005/SC-002); (4) **Envelope fields** — `correlation_id = case_id`, `causation_id = task_id`, `agent_id = "risk-fraud-agent"`, `tenant_id = "poc"`; (5) **Dual-path delivery** — A2A `TaskResult.output` vs domain-event table (research R2/R8, FR-008); (6) **Consumer mapping** — `recommendation` → `003` risk-level table and the SC-009 "consumer unchanged" guarantee; (7) **Audit** — per-request lifecycle events and `query_by_correlation` (FR-014/FR-015).

**Checkpoint**: The published-result contract is documented and cross-linked from the hub.

---

## Phase 5: Mock Risk Data Doc — US3 (Priority: P1)

**Goal**: Document the in-process seeded signal dataset the agent owns — the five signal domains, the
lookup contract, the seed coverage matrix, and the isolation guarantee.

**Independent Test**: A reader can describe `load_signals(customer_id)` hit/miss behavior, list the five
signal models with fields, and predict the expected verdict for each seeded `customer_id` — and confirm
the dataset carries no foreign-domain fields (SC-003/FR-009).

- [ ] T007 [P] [US3] Create `docs/architecture/mock-risk-data.md` derived from `contracts/mock-risk-data.md` + `data-model.md` §2, sections: (1) **Purpose** — in-process seeded, PoC-scope, owned dataset; no DB/external risk service (FR-003); (2) **Lookup contract** — `load_signals(customer_id) -> RiskSignals | None`, case-sensitive, by `customer_id` only (no `purchase_reference`), miss → missing-data path (`requires_human_review`, confidence 0.2, recorded reason — FR-010); (3) **Signal models** — field tables for `AccountStanding`, `RefundDisputeHistory`, `PaymentInstrumentSignal`, `BehavioralSignal`, `KnownFraudIndicator`, and the `RiskSignals` aggregate (all five optional), each field annotated with the `FP-00x` rule it feeds; (4) **Seed coverage matrix** — the full `customer_id` → scenario → key signal → expected verdict table (`CUS-CLEAN`, `CUS-CHARGEBACKS`, `CUS-ONE-CHARGEBACK`, `CUS-VELOCITY`, `CUS-INSTRUMENT`, `CUS-CARD-TESTING`, `CUS-NEW-ACCOUNT`, `CUS-ANOMALY`, `CUS-BLOCKLIST`, `CUS-CONTRADICTION`, `CUS-BORDERLINE`, unknown), noting how it drives the SC-004 single-signal matrix and SC-005 fault cases; (5) **Isolation guarantee** — `RiskSignals` contains only risk/fraud fields, no billing/entitlement/customer-resolution state, no peer call (SC-003/FR-009). Link to `risk-scoring-rules.md`.

**Checkpoint**: The owned-signal dataset is documented and cross-linked.

---

## Phase 6: Risk Scoring Rules Doc — US3/US4 (Priority: P1)

**Goal**: Document the named, deterministic fraud policy — thresholds, `FP-001..FP-006` rules,
evaluation order, additive scoring, borderline resolution, confidence scheme, and the human-review /
determinism guarantees — so a reader can reproduce any verdict by hand.

**Independent Test**: Given any seeded signal set, a reader can apply the documented evaluation order and
scoring to derive the same `(risk_level, confidence, requires_human_review)`, including the borderline
upper-band rule and the missing/contradictory/no-applicable-rule human-review paths.

- [ ] T008 [P] [US3] Create `docs/architecture/risk-scoring-rules.md` derived from `contracts/fraud-policy.md` + `research.md` R4/R6 (+ `data-model.md` §3/§6), sections: (1) **Policy identity** — `poc-fraud-policy` v1.0.0, illustrative PoC values, implemented in `policy.py`, evaluated by `scoring.py`; (2) **Thresholds** — the module-constant table (`ELEVATED_THRESHOLD` 0.5, `HIGH_THRESHOLD` 0.8, `CHARGEBACK_ELEVATED` 1/`CHARGEBACK_HIGH` 2, `VELOCITY_ELEVATED` 3/`VELOCITY_HIGH` 5, `ANOMALY_ELEVATED` 0.7, `NEW_ACCOUNT_DAYS` 30); (3) **Rules** — the `FP-001..FP-006` table (id, name, fires-when, contribution), including FP-001 known-indicator hard floor → `high`; (4) **Evaluation order** — the five deterministic gates (data-completeness → known-indicator → contradiction → additive scoring FP-002..FP-006 → no-applicable default) with the score→level mapping; (5) **Additive scoring** — sum of fired contributions capped at 1.0, and why cumulative (vs billing's single-decisive-rule precedence); (6) **Borderline resolution** — score exactly on a threshold resolves upward (inclusive-upper), confidence 0.6, recorded in reasoning; (7) **Confidence per path** — the 0.95 / 0.9 / 0.6 / 0.3 / 0.2 table (FR-006/R6); (8) **Human-review & honesty** — missing/contradictory/no-applicable-rule never fabricate a verdict (FR-010, US4); (9) **Determinism guarantee** — `scoring.evaluate(...)` is pure; identical signals under v1.0.0 yield identical output (FR-012). Link to `mock-risk-data.md` and `risk-result-contract.md`.

**Checkpoint**: The deterministic policy is fully documented and reproducible by hand.

---

## Phase 7: AgentCore Local Dev Doc — Operational (Priority: P2)

**Goal**: Document how to run the agent's standalone A2A entrypoint under the AWS AgentCore CLI
(`agentcore dev`) and the CLI-free FastAPI path, and how this differs from the Kafka entrypoint.

**Independent Test**: An operator can start `agentcore dev`, invoke the local agent with a sample
request, read the expected single-artifact response, and explain why this path does **not** publish the
`risk.review.completed` Kafka event.

- [ ] T009 [P] Create `docs/architecture/agentcore-local-risk-agent.md` derived from `research.md` R9, `quickstart.md` §C, and the plan's AgentCore decision, sections: (1) **Purpose** — run under `agentcore dev` + inspector UI, mirroring feature 004; (2) **Footprint** — `agentcore/` config (`agentcore.json`, `aws-targets.json`, `.env.local`, `README.md`) and `app/RiskFraud/` (`main.py` → `serve_a2a(RiskFraudExecutor(), CARD)`, `pyproject.toml`, `README.md`), plus `http_app.py` (FastAPI) and `dev_a2a_client.py`; (3) **Two distinct A2A surfaces** — AgentCore's `a2a-sdk` JSON-RPC (`message/send`/`message/stream`) vs this repo's internal A2A-over-Kafka runtime (feature 002); (4) **Code reuse** — reuses `service.assess` unchanged, monorepo on `sys.path` from source, deps (`bedrock-agentcore[a2a]`, `a2a-sdk[all]`, `pydantic`, `structlog`) already introduced by 004 (no new dependency); (5) **Standalone behavior** — does NOT publish the Kafka `risk.review.completed` event (that stays the Kafka entrypoint's job); both paths share the card via `identity.py`; (6) **Commands** — `agentcore validate`, `agentcore dev`, a sample `agentcore dev '{...CUS-BLOCKLIST...}'` invocation with the expected `{"recommendation":"high","confidence":0.95,...}` artifact, and the `http_app` / `dev_a2a_client` CLI-free path; (7) **Deferred** — `agentcore deploy` (CodeZip) is out of scope, documented as a future target.

**Checkpoint**: All five documents exist, each grounded in its source artifact.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Make the five docs a coherent, cross-linked, accurate set and reconcile with the existing
`docs/architecture/` index.

- [ ] T010 [P] Verify bidirectional cross-links: `risk-fraud-agent.md` links to the other four; `mock-risk-data.md` ↔ `risk-scoring-rules.md`; `risk-scoring-rules.md` → `risk-result-contract.md`. Fix any broken relative paths to `specs/005-risk-fraud-agent/` artifacts.
- [ ] T011 [P] Validate each doc against its source-of-truth artifact: confirm thresholds, `FP-00x` ids, confidence values, seed `customer_id`s, payload field names, topic name, capability/agent ids, and FR/SC citations exactly match `contracts/fraud-policy.md`, `contracts/mock-risk-data.md`, `contracts/risk-result-contract.md`, `data-model.md`, `research.md`, and `spec.md`. Correct any drift in the docs.
- [ ] T012 If a `docs/` or `docs/architecture/` index/landing page exists, add entries linking the five new docs alongside `event-contracts.md`, `adding-new-agent.md`, `topic-naming.md`; if none exists, note no index update is needed.
- [ ] T013 Final read-through across all five docs for consistent terminology (risk levels `low`/`elevated`/`high`, `requires_human_review`, capability `assess_fraud_risk`, agent id `risk-fraud-agent`), house style, and no contradictions.

---

## Dependencies & Execution Order

- **Setup (Phase 1)** → **Foundational (Phase 2)** blocks all authoring (shared link/citation scheme).
- **Doc phases (3–7)**: after Foundational, the five docs are in different files and author fully in
  parallel — **T004, T006, T007, T008, T009** are mutually `[P]`. T005 follows T004 (same file).
- **Polish (Phase 8)**: after all five docs exist. T010 and T011 run in parallel; T012/T013 follow.

### Parallel Example

```text
# After T003 (cross-reference map), launch the five docs together:
Task: "T004 docs/architecture/risk-fraud-agent.md (hub)"
Task: "T006 docs/architecture/risk-result-contract.md"
Task: "T007 docs/architecture/mock-risk-data.md"
Task: "T008 docs/architecture/risk-scoring-rules.md"
Task: "T009 docs/architecture/agentcore-local-risk-agent.md"
```

---

## Implementation Strategy

### MVP First (Agent Overview Doc)

1. Phase 1 Setup → 2. Phase 2 Foundational (cross-reference map) → 3. Phase 3 `risk-fraud-agent.md`.
4. **STOP and VALIDATE**: a reader can understand the agent and navigate to the detail docs.

### Incremental Delivery

1. Setup + Foundational → conventions and link map ready.
2. Hub doc (`risk-fraud-agent.md`) → readable overview (MVP).
3. `risk-result-contract.md`, `mock-risk-data.md`, `risk-scoring-rules.md`, `agentcore-local-risk-agent.md`
   in parallel → full detail set.
4. Polish → cross-links validated, docs reconciled with source artifacts and the docs index.

---

## Notes

- `[P]` = different files, no dependencies.
- `[Story]` maps each doc to the user story / concern it primarily documents.
- These docs are **derivative**: every fact must trace to a `specs/005-risk-fraud-agent/` artifact — do
  not introduce thresholds, ids, or field names not present in the source contracts.
- Keep docs in sync if the underlying contracts change before the agent code lands.
- Commit after each doc or logical group.
