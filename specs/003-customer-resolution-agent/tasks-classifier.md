---
description: "Focused task list for the Ticket Classifier slice of the Customer Resolution Agent"
---

# Tasks: Ticket Classifier (Customer Resolution Agent)

**Input**: Design documents from `/specs/003-customer-resolution-agent/`

**Prerequisites**: plan.md (required), spec.md (US1 Triage), research.md (R1), data-model.md (§2), contracts/decision-policy.md (§A)

> **Companion file**: The full-feature task list lives in `tasks.md` (US1–US6 end-to-end agent). This
> file is a **focused slice** covering only the ticket classifier and intentionally **supersedes the
> triage tasks** (T011/T013 in `tasks.md`) with a richer, structured classification output. When the
> classifier here is built, the broader `tasks.md` should consume `Classification`/`classify()` instead
> of the simpler `Triage` model. `tasks.md` is otherwise unchanged.

**Scope**: This list covers **only the ticket classifier** — the deterministic front-door that turns a
`support.ticket.created` ticket into a structured classification. It is the richer, testable form of the
`Triage` seam in `data-model.md §2` / `research.md R1` (`classify(ticket) -> ...`). Downstream
delegation, result aggregation, the decision policy, and the final `customer.resolution.decided` event
are **out of scope here** and remain in `tasks.md`.

**Classifier output contract** (from user input):

| Field | Type | Meaning |
|-------|------|---------|
| `issue_type` | enum: `refund_request`, `cancellation_request`, `billing_question`, `technical_issue`, `unknown` | Primary ticket category |
| `requires_billing_review` | `bool` | True ⟺ a billing peer analysis is needed |
| `requires_risk_review` | `bool` | True ⟺ a risk peer analysis is needed |
| `requires_human_review` | `bool` | True ⟺ escalate to a human (low confidence / unsupported / unknown) |
| `confidence` | `float` (0.0–1.0) | Classifier confidence in `issue_type` |
| `reasoning_summary` | `str` | Human-readable, auditable rationale (matched signals, chosen type, flag reasons) |

**Tests**: REQUESTED — acceptance criterion "Classifier output is structured and testable." Unit
tests are written per story and **must fail before** the corresponding implementation.

**Organization**: Grouped by user story; each story maps to one of the four acceptance criteria and is
independently testable. Most logic lives in a single module (`classifier.py`), so cross-story
file-level parallelism is limited and called out honestly below.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1–US4)
- Exact file paths are included in every task

## Acceptance-criteria → user-story map

| Acceptance criterion (user input) | Story |
|-----------------------------------|-------|
| Classifier output is structured and testable | US1 |
| Refund requests trigger Billing and Risk review | US2 |
| Non-refund tickets can be marked unsupported for this POC | US3 |
| Low-confidence classification escalates to human review | US4 |

## Path Conventions

Single Python project (per `plan.md`). Classifier lives under
`apps/agents/customer_resolution/`; tests under `tests/unit/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the classifier module and its unit-test file so all later work has a home.

- [ ] T001 [P] Create `apps/agents/customer_resolution/classifier.py` with a module docstring, `from __future__ import annotations`, and imports (`enum.Enum`, `pydantic.BaseModel`/`ConfigDict`/`Field`, and `SupportTicketCreatedPayload` from `packages/contracts/events/payloads.py`). Lay out `# --- model ---`, `# --- constants ---`, `# --- logic ---` sections. No behavior yet.
- [ ] T002 [P] Create `tests/unit/test_classifier.py` with pytest scaffolding: module docstring, imports of the classifier symbols, and a `_ticket(reason: str) -> SupportTicketCreatedPayload` helper that builds a valid `SupportTicketCreatedPayload` (ticket_id `TKT-TEST`, dummy customer_id/amount/currency/created_at) reused by every test below.

**Checkpoint**: Module and test file exist and import cleanly.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Define the structured output type and the deterministic vocabulary every story depends on.

**⚠️ CRITICAL**: No classification behavior can be implemented until the model and constants exist.

- [ ] T003 [US1] Define `IssueType(str, Enum)` with exactly five members `REFUND_REQUEST="refund_request"`, `CANCELLATION_REQUEST="cancellation_request"`, `BILLING_QUESTION="billing_question"`, `TECHNICAL_ISSUE="technical_issue"`, `UNKNOWN="unknown"` in `apps/agents/customer_resolution/classifier.py`.
- [ ] T004 [US1] Define the `Classification` Pydantic v2 model (`model_config = ConfigDict(frozen=True, extra="forbid")`) in `apps/agents/customer_resolution/classifier.py` with fields `issue_type: IssueType`, `requires_billing_review: bool`, `requires_risk_review: bool`, `requires_human_review: bool`, `confidence: float = Field(ge=0.0, le=1.0)`, `reasoning_summary: str`. Depends on T003.
- [ ] T005 [US1] Add deterministic classification constants in `apps/agents/customer_resolution/classifier.py`: per-issue-type signal tuples (`REFUND_SIGNALS`, `CANCELLATION_SIGNALS`, `BILLING_QUESTION_SIGNALS`, `TECHNICAL_SIGNALS`) sourced from `contracts/decision-policy.md §A` (refund vocabulary) and the spec edge cases, plus `CONFIDENCE_HUMAN_REVIEW_THRESHOLD = 0.6`, `CONFIDENCE_STRONG = 0.9`, `CONFIDENCE_WEAK = 0.5`, `CONFIDENCE_UNKNOWN = 0.3`. Depends on T003.

**Checkpoint**: `Classification` is importable and round-trips; constants are defined. User stories can begin.

---

## Phase 3: User Story 1 - Structured, Testable Classification Output (Priority: P1) 🎯 MVP

**Goal**: A pure `classify(ticket) -> Classification` that turns a ticket's `reason` text into the full
structured output (all six fields populated), so the classifier is deterministic and unit-testable.
Maps to acceptance criterion *"Classifier output is structured and testable."* and spec US1 (Triage).

**Independent Test**: Call `classify(_ticket("Please refund the duplicate charge"))` and a clear
non-refund ticket; assert each returns a fully-populated `Classification` with a sensible `issue_type`,
`confidence` in `[0,1]`, and a non-empty `reasoning_summary` — purely in-process, no Kafka.

### Tests for User Story 1 (write first, ensure they FAIL) ⚠️

- [ ] T006 [US1] In `tests/unit/test_classifier.py`, add tests asserting `classify()` returns a `Classification` for a refund ticket and a clear non-refund ticket, that all six fields are present and well-typed, `0.0 <= confidence <= 1.0`, and `reasoning_summary` is non-empty and names the matched signal(s). Run and confirm they FAIL (no `classify` yet).

### Implementation for User Story 1

- [ ] T007 [US1] Implement the keyword-scoring core in `apps/agents/customer_resolution/classifier.py`: a private `_score(reason: str) -> dict[IssueType, int]` that lower-cases the ticket `reason` and counts case-insensitive signal matches per issue type using the Phase-2 constants. Depends on T005.
- [ ] T008 [US1] Implement `classify(ticket: SupportTicketCreatedPayload) -> Classification` in `apps/agents/customer_resolution/classifier.py`: pick the highest-scoring `issue_type` (tie/zero-match → `UNKNOWN`), derive `confidence` from match strength (`CONFIDENCE_STRONG` for a clear single-category match, `CONFIDENCE_WEAK` for weak/mixed, `CONFIDENCE_UNKNOWN` for no match), set the three review flags (stub as `False` for now; US2–US4 fill them in), and build `reasoning_summary` naming the matched signals and chosen type. Depends on T007. Make T006 pass.
- [ ] T009 [US1] In `tests/unit/test_classifier.py`, add a frozen-model test asserting `Classification` rejects extra fields and out-of-range `confidence` (e.g. `2.0`) with a `ValidationError`, proving the output contract is enforced. Depends on T004.

**Checkpoint**: `classify()` returns a complete, validated `Classification`; output is structured and unit-tested. MVP reached.

---

## Phase 4: User Story 2 - Refund Requests Trigger Billing and Risk Review (Priority: P1)

**Goal**: A ticket classified as `refund_request` sets `requires_billing_review = True` **and**
`requires_risk_review = True`; all non-refund types leave both `False`. Maps to acceptance criterion
*"Refund requests trigger Billing and Risk review."* and spec US1-2 → US2.

**Independent Test**: `classify(_ticket("I want a refund, I was charged twice"))` yields
`issue_type == REFUND_REQUEST`, `requires_billing_review is True`, `requires_risk_review is True`; a
billing-question ticket yields both flags `False`.

### Tests for User Story 2 (write first, ensure they FAIL) ⚠️

- [ ] T010 [US2] In `tests/unit/test_classifier.py`, add a parametrized test over several refund-intent phrasings (from `contracts/decision-policy.md §A`: "refund", "charged twice", "double-charged", "money back", "dispute", "chargeback") asserting `issue_type == REFUND_REQUEST` and both `requires_billing_review` and `requires_risk_review` are `True`; plus a negative case (non-refund ticket) asserting both are `False`. Confirm it FAILS against the US1 stub.

### Implementation for User Story 2

- [ ] T011 [US2] In `classify()` in `apps/agents/customer_resolution/classifier.py`, implement the billing/risk flag rule: `requires_billing_review = requires_risk_review = (issue_type == IssueType.REFUND_REQUEST)`, and extend `reasoning_summary` to state that a refund request routes to billing **and** risk review. Make T010 pass. Depends on T008.

**Checkpoint**: Refund tickets fan out to both reviews; non-refund tickets request neither.

---

## Phase 5: User Story 3 - Non-Refund Tickets Marked Unsupported for the PoC (Priority: P2)

**Goal**: Tickets classified as `cancellation_request`, `billing_question`, or `technical_issue` are
recognized and explicitly marked **unsupported for this PoC** — no billing/risk review, and the
`reasoning_summary` records that the category is out of PoC scope. Maps to acceptance criterion
*"Non-refund tickets can be marked unsupported for this POC."*

**Independent Test**: `classify()` on a cancellation, a billing-question, and a technical-issue ticket
each returns the correct `issue_type`, both review flags `False`, and a `reasoning_summary` containing
an explicit "unsupported in this PoC" note.

### Tests for User Story 3 (write first, ensure they FAIL) ⚠️

- [ ] T012 [US3] In `tests/unit/test_classifier.py`, add parametrized tests mapping representative phrasings to `CANCELLATION_REQUEST` ("cancel my subscription", "close my account"), `BILLING_QUESTION` ("why was I charged", "where is my invoice"), and `TECHNICAL_ISSUE` ("the app keeps crashing", "I can't log in"); assert each has both review flags `False` and a `reasoning_summary` flagging the ticket as unsupported in the PoC. Confirm it FAILS.

### Implementation for User Story 3

- [ ] T013 [US3] Extend `_score`/`classify()` in `apps/agents/customer_resolution/classifier.py` so the cancellation, billing-question, and technical-issue signal sets are matched and select their issue types; add a module-level `SUPPORTED_ISSUE_TYPES = {IssueType.REFUND_REQUEST}` constant and append an "unsupported in this PoC" clause to `reasoning_summary` whenever `issue_type not in SUPPORTED_ISSUE_TYPES`. Make T012 pass. Depends on T011.

**Checkpoint**: All five issue types are recognized; the four non-refund types are clearly marked unsupported.

---

## Phase 6: User Story 4 - Low-Confidence Classification Escalates to Human Review (Priority: P2)

**Goal**: When `confidence` falls below `CONFIDENCE_HUMAN_REVIEW_THRESHOLD` (or the ticket is
`UNKNOWN`/ambiguous), `requires_human_review = True` and the reason is recorded. Maps to acceptance
criterion *"Low-confidence classification escalates to human review."* and the spec's ambiguous-triage
edge case.

**Independent Test**: `classify(_ticket(""))` and `classify(_ticket("hmm something is weird"))` both
return `requires_human_review is True`, `issue_type == UNKNOWN` (or low confidence), and a
`reasoning_summary` naming the low-confidence/ambiguity reason; a high-confidence refund ticket returns
`requires_human_review is False`.

### Tests for User Story 4 (write first, ensure they FAIL) ⚠️

- [ ] T014 [US4] In `tests/unit/test_classifier.py`, add tests: (a) empty/garbled `reason` → `issue_type == UNKNOWN`, `confidence <= CONFIDENCE_UNKNOWN`, `requires_human_review is True`; (b) a clear high-confidence refund ticket → `requires_human_review is False`; (c) a boundary case confirming the comparison is `confidence < CONFIDENCE_HUMAN_REVIEW_THRESHOLD`. Confirm it FAILS.

### Implementation for User Story 4

- [ ] T015 [US4] In `classify()` in `apps/agents/customer_resolution/classifier.py`, implement the escalation rule: `requires_human_review = confidence < CONFIDENCE_HUMAN_REVIEW_THRESHOLD or issue_type == IssueType.UNKNOWN`, and append the escalation reason ("low confidence" / "unknown intent") to `reasoning_summary`. Make T014 pass. Depends on T013.

**Checkpoint**: Low-confidence and unknown tickets escalate to human review with a recorded reason; confident classifications do not.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Wire the classifier into the existing triage seam, export it, document it, and verify quality gates.

- [ ] T016 [US1] Bridge the classifier to the `data-model.md §2` triage seam: in `apps/agents/customer_resolution/classifier.py` add a `needs_refund_review` derivation (`issue_type == REFUND_REQUEST`) — a property on `Classification` or a `to_triage()` helper — so downstream delegation (`tasks.md` US2) consumes the classifier without a contract change. Reference `research.md R1` (preserved LLM-swap seam). Depends on T015.
- [ ] T017 Export the classifier symbols (`IssueType`, `Classification`, `classify`) from `apps/agents/customer_resolution/__init__.py` so the intake loop can import them.
- [ ] T018 [P] Add a short "Ticket Classifier" subsection to `specs/003-customer-resolution-agent/quickstart.md` documenting the six output fields, the confidence threshold, and the acceptance-criteria→behavior mapping.
- [ ] T019 Run `uv run pytest tests/unit/test_classifier.py`, then `uv run mypy apps/agents/customer_resolution/classifier.py` and `uv run ruff check apps/agents/customer_resolution/classifier.py tests/unit/test_classifier.py`; fix any failures. Depends on all prior tasks.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories (defines `Classification` + constants).
- **User Stories (Phases 3–6)**: All depend on Foundational. They mostly edit the **same** `classify()` body, so they are best done **sequentially in priority order** (US1 → US2 → US3 → US4); each adds one rule and its test.
- **Polish (Phase 7)**: Depends on US1–US4 being complete.

### User Story Dependencies

- **US1 (P1)**: Establishes `classify()` and the structured output — foundation for the rest.
- **US2 (P1)**: Fills in the billing/risk flag rule inside `classify()` (builds on US1).
- **US3 (P2)**: Adds non-refund issue-type recognition + unsupported marking (builds on US2).
- **US4 (P2)**: Adds the human-review escalation rule (builds on US3).

### Within Each User Story

- Write the unit test first and confirm it FAILS, then implement.
- Constants/model (Phase 2) before logic.
- Each rule is added to the single pure `classify()` function and verified in isolation.

### Parallel Opportunities

- **Setup**: T001 (classifier.py) and T002 (test_classifier.py) are different files → run in parallel.
- **Foundational**: T003 must precede T004/T005; T004 and T005 touch the same file → sequential.
- **User-story logic** (T007/T008, T011, T013, T015) all edit `classify()` in one file → **sequential**, not parallel.
- **Polish**: T018 (docs) is independent of T016/T017/T019 → can run in parallel with them.
- Honest note: because the classifier is one cohesive module, this slice is largely linear; the main
  parallelism is Setup and writing each story's test while reviewing the prior implementation.

---

## Parallel Example: Setup

```bash
# Different files, no dependencies — run together:
Task: "Create apps/agents/customer_resolution/classifier.py skeleton (T001)"
Task: "Create tests/unit/test_classifier.py scaffolding (T002)"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1: Setup (T001–T002)
2. Phase 2: Foundational — `Classification` model + constants (T003–T005)
3. Phase 3: User Story 1 — `classify()` returns the full structured output (T006–T009)
4. **STOP and VALIDATE**: `classify()` is deterministic, fully-typed, and unit-tested — the
   "structured and testable" acceptance criterion is met on its own.

### Incremental Delivery

1. Setup + Foundational → classifier scaffolding ready.
2. US1 → structured output (MVP) → validate.
3. US2 → refund → billing + risk review → validate.
4. US3 → non-refund types marked unsupported → validate.
5. US4 → low-confidence → human review → validate.
6. Polish → wire to triage seam, export, docs, mypy/ruff green.

Each step adds one auditable rule to a single pure function without breaking the previous tests.

---

## Notes

- `[P]` = different files, no dependencies on incomplete tasks.
- `[Story]` label maps each task to its acceptance criterion for traceability.
- The classifier is **deterministic and rule-based** per `research.md R1`; the `classify(ticket) -> …`
  signature is the intentional seam for a future LLM swap — keep it pure (no Kafka, no I/O).
- The agent must read **no** billing/fraud data (FR-005); the classifier consumes only the ticket
  `reason`/message text.
- This file supersedes the simple triage tasks (T011/T013) in `tasks.md`; the rest of `tasks.md` is unchanged.
- Commit after each story checkpoint; verify each story's tests fail before implementing.
