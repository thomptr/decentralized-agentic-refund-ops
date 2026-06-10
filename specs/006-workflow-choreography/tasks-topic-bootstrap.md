# Tasks: Topic Bootstrap Script (`scripts/create-topics.sh`)

**Input**: Design documents from `/specs/006-workflow-choreography/`
**Feature**: 006-workflow-choreography — operator/demo wiring increment (gap #5 "runnable demo wiring", SC-008)

**Scope note**: This task list is scoped to the **topic bootstrap script** requested via `/speckit-tasks`,
not the full 006 choreography feature. It is a self-contained operational deliverable whose three
acceptance criteria are mapped below to three independently-testable user stories. The broader 006 tasks
(reaper, replay harness, e2e suite, trace tool) are out of scope here and can be generated separately.

**Tests**: Tests were not explicitly requested. Because the three acceptance criteria are themselves
assertions, each story includes one lightweight verification task that proves the criterion; these reuse
the existing `pytest` harness and are kept minimal.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which acceptance-criterion story this task belongs to (US1, US2, US3)
- Exact file paths are included in every task.

## Acceptance criteria → User stories

| Story | Acceptance criterion |
|-------|----------------------|
| **US1 (P1)** | Topic names use shared resolver rules (`topic_for()` / `resolve_topic()` — no hardcoded strings) |
| **US2 (P2)** | Topics are versioned (`.v{major}` produced by the resolver) |
| **US3 (P3)** | Future topics can be added declaratively (append one entry to a single source-of-truth list) |

## Requested topics (14) & current codebase status

The script must create these 14 topics. Status against `packages/contracts/topics.py` today:

| Requested topic | Existing constant | Status |
|---|---|---|
| `local.support.ticket.created.v1` | `_TICKET_CREATED` | ✅ exists |
| `local.resolution.customer-issue.classified.v1` | `TOPIC_ISSUE_CLASSIFIED` | ✅ exists |
| `local.resolution.refund-review.requested.v1` | `TOPIC_REFUND_REVIEW_REQUESTED` | ✅ exists |
| `local.billing.refund-analysis.completed.v1` | `TOPIC_BILLING_RESULT` | ✅ exists |
| `local.risk.review.completed.v1` | `TOPIC_RISK_RESULT` | ✅ exists |
| `local.resolution.customer-resolution.decided.v1` | `TOPIC_RESOLUTION_DECIDED` = `local.customer.resolution.decided.v1` | ⚠️ **name mismatch** (see T012) |
| `local.resolution.customer-response.drafted.v1` | `TOPIC_RESPONSE_DRAFTED` | ✅ exists |
| `local.resolution.case.closed.v1` | — | ❌ no constant (T003) |
| `local.resolution.case.escalated.v1` | — | ❌ no constant (T003) |
| `local.audit.agent-task.requested.v1` | — | ❌ no constant (T003) |
| `local.audit.agent-task.accepted.v1` | — | ❌ no constant (T003) |
| `local.audit.agent-task.completed.v1` | — | ❌ no constant (T003) |
| `local.audit.agent-task.failed.v1` | — | ❌ no constant (T003) |
| `local.audit.agent-task.rejected.v1` | — | ❌ no constant (T003) |

> ⚠️ **Plan note**: `plan.md` states 006 introduces "no new topic." The five `audit.agent-task.*`
> topics and the two `resolution.case.*` lifecycle topics in the request do **not** exist yet. T003
> adds them declaratively; if they are *not* wanted, trim the declarative list in T003 instead.

---

## Phase 1: Setup

**Purpose**: Create the script location and skeleton.

- [ ] T001 Create the repo-root `scripts/` directory and add an executable `scripts/create-topics.sh` skeleton — `#!/usr/bin/env bash`, `set -euo pipefail`, and env defaults `AGENT_ENVIRONMENT="${AGENT_ENVIRONMENT:-local}"` and `KAFKA_BROKER_URL="${KAFKA_BROKER_URL:-localhost:9092}"`, following the conventions in `infra/local/run-demo-agents.sh`.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The script is a thin runner over a single declarative Python topic registry; that registry must hold all 14 requested topics before the script can create them.

**⚠️ CRITICAL**: No story work can begin until the registry holds the full requested set.

- [ ] T002 Reconcile the requested 14-topic list against existing constants in `packages/contracts/topics.py` and record the 3 discrepancies (decided-topic name mismatch; missing `resolution.case.{closed,escalated}`; missing five `audit.agent-task.*`) as a comment block at the top of `scripts/create-topics.sh`.
- [ ] T003 Add the missing topic constants to `packages/contracts/topics.py` using the shared resolver `topic_for(...)` ONLY (no literal strings): `TOPIC_CASE_CLOSED = topic_for("resolution","case","closed")`, `TOPIC_CASE_ESCALATED = topic_for("resolution","case","escalated")`, and `TOPIC_AUDIT_TASK_REQUESTED/ACCEPTED/COMPLETED/FAILED/REJECTED = topic_for("audit","agent-task", <action>)`.
- [ ] T004 Register the new topics declaratively as `NewTopic(name=<constant>, num_partitions=1, replication_factor=1, topic_configs=...)` entries appended to `_CANONICAL_TOPICS` in `src/agent_foundation/transport/topics.py` (retention `7d` for lifecycle/result topics, `compact` for the `audit.agent-task.*` topics to match the existing audit-topic policy).

**Checkpoint**: `_CANONICAL_TOPICS` now resolves to a superset that includes all 14 requested topics.

---

## Phase 3: User Story 1 — Topic names use shared resolver rules (Priority: P1) 🎯 MVP

**Goal**: The script creates every topic via the shared resolver, with zero hardcoded topic strings.

**Independent Test**: Run `scripts/create-topics.sh` against a broker and confirm all 14 requested topics exist; grep the script + registry to confirm no literal `local.*.v1` strings are used (only `topic_for(...)`).

### Implementation for User Story 1

- [ ] T005 [US1] Add a `create-topics` entrypoint that calls the existing async `create_topics(broker)` — add a `create_topics` Typer command to `src/agent_foundation/cli.py` (alongside the existing `health` command that already imports `create_topics` from `agent_foundation.transport.topics`), reading the broker from `KAFKA_BROKER_URL`.
- [ ] T006 [US1] Implement `scripts/create-topics.sh` to `cd` to repo root and invoke the entrypoint via `uv run agent-foundation create-topics`, passing the resolved broker; the script MUST contain no Kafka topic name literals — all names originate from `topic_for(...)` in the Python registry.
- [ ] T007 [P] [US1] Add a verification task/test in `tests/unit/test_topic_bootstrap.py` asserting that the names in `_CANONICAL_TOPICS` are exactly those produced by `topic_for(...)` calls (no literal-string topics), and that the 14 requested topics are all present in the resolved set.

**Checkpoint**: Running the script creates all 14 topics, all names sourced from the shared resolver.

---

## Phase 4: User Story 2 — Topics are versioned (Priority: P2)

**Goal**: Every created topic carries an explicit `v{major}` suffix produced by the resolver, not appended by hand.

**Independent Test**: Assert every topic in the bootstrap set matches `^[a-z]+(\.[a-z0-9-]+){3}\.v\d+$` and that its version segment equals the `version` argument passed to `topic_for(...)`.

### Implementation for User Story 2

- [ ] T008 [US2] Add a parametrized check in `tests/unit/test_topic_bootstrap.py` asserting each canonical topic name ends with `.v{major}` and matches the `{env}.{domain}.{entity}.{action}.v{major}` regex from `docs/architecture/topic-naming.md`; confirm the `version` flows through `topic_for(...)` (default `"1"`) rather than being concatenated in any caller.

**Checkpoint**: Versioning is enforced and proven for the full bootstrap set.

---

## Phase 5: User Story 3 — Future topics can be added declaratively (Priority: P3)

**Goal**: Adding a future topic requires editing exactly one declarative list; the script picks it up with no script changes.

**Independent Test**: Append a throwaway `NewTopic(name=topic_for("system","scratch","created"))` to `_CANONICAL_TOPICS`, run the script, confirm the new topic is created without touching `scripts/create-topics.sh`; then remove it.

### Implementation for User Story 3

- [ ] T009 [US3] Document the declarative add-a-topic procedure (one `NewTopic(name=topic_for(...))` entry in `_CANONICAL_TOPICS`) in the header comment of `scripts/create-topics.sh` and in the "How to register a new topic" section of `docs/architecture/topic-naming.md`.
- [ ] T010 [P] [US3] Add a regression test in `tests/unit/test_topic_bootstrap.py` asserting the bootstrap creates exactly the declared set (count + names) so that appending to `_CANONICAL_TOPICS` is automatically reflected — guarding against a hand-maintained duplicate list in the shell script.

**Checkpoint**: New topics require a single declarative edit; the script and tests adapt automatically.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T011 Make `scripts/create-topics.sh` idempotent and operator-friendly: rely on `create_topics()` already swallowing "topic exists" errors, and echo the resolved `AGENT_ENVIRONMENT`/broker plus the count of topics created on success.
- [ ] T012 Resolve the decided-topic naming discrepancy: confirm with the requester whether the intended name is the existing `local.customer.resolution.decided.v1` (`TOPIC_RESOLUTION_DECIDED`) or a new `local.resolution.customer-resolution.decided.v1`; align the constant in `packages/contracts/topics.py` accordingly (do not silently create both).
- [ ] T013 Update the "Topic creation policy" section of `docs/architecture/topic-naming.md` to reference `scripts/create-topics.sh` as the operator entrypoint for local topic bootstrap.
- [ ] T014 Run `bash scripts/create-topics.sh` against the local broker (`docker compose -f infra/local/docker-compose.yml up -d`) and verify via `uv run agent-foundation health` that all 14 topics exist; re-run to confirm idempotency (no errors, no duplicates).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Foundational (Phase 2)**: Depends on Setup — **blocks all stories** (the registry must hold all 14 topics).
- **User Stories (Phase 3–5)**: All depend on Foundational. US1 is the MVP; US2 and US3 build on the registry US1 wires up and can then proceed in parallel.
- **Polish (Phase 6)**: Depends on US1–US3.

### Story Dependencies

- **US1 (P1)**: Core — script + entrypoint + resolver compliance. No dependency on other stories.
- **US2 (P2)**: Versioning proof over the same registry US1 uses; independently testable.
- **US3 (P3)**: Declarative-extensibility proof + docs; independently testable.

### Parallel Opportunities

- T007, T008, T010 all add cases to `tests/unit/test_topic_bootstrap.py` — write them together but commit as one file (same-file, so not strictly `[P]` against each other; `[P]` marks independence from non-test tasks).
- T003 and T002 touch different files and can proceed in parallel.

---

## Parallel Example

```bash
# After Foundational (T001–T004) completes, the MVP path:
Task: "T005 Add create-topics CLI entrypoint in src/agent_foundation/cli.py"
Task: "T006 Implement scripts/create-topics.sh runner"
# Then the proof tasks across stories share one test file:
Task: "T007/T008/T010 add resolver/version/declarative assertions in tests/unit/test_topic_bootstrap.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1: Setup (T001)
2. Phase 2: Foundational (T002–T004) — **blocks everything**
3. Phase 3: US1 (T005–T007) — script creates all 14 topics via the shared resolver
4. **STOP and VALIDATE**: run the script against a local broker; confirm topics exist
5. Demo-ready (satisfies the "shared resolver rules" criterion)

### Incremental Delivery

1. Setup + Foundational → registry holds all 14 topics
2. US1 → script + resolver compliance → **MVP**
3. US2 → versioning proof
4. US3 → declarative-extensibility proof + docs
5. Polish → idempotency, decided-topic reconciliation, docs, live verification

---

## Notes

- [P] tasks = different files, no dependencies.
- The shell script stays a thin runner; the **single source of truth** for topics is `_CANONICAL_TOPICS` in `src/agent_foundation/transport/topics.py`, with names from `topic_for(...)` in `packages/contracts/topics.py`.
- This deliverable adds **no new dependency** (reuses `aiokafka` admin + existing `create_topics()`), consistent with Constitution Principle V.
- ⚠️ It DOES add new *topic declarations* (`audit.agent-task.*`, `resolution.case.*`); reconcile against `plan.md`'s "no new topic" statement (T003/T012) before merge.
</content>
</invoke>
