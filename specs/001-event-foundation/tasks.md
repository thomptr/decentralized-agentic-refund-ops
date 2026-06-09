---
description: "Task list for Decentralized Agent Event Foundation"
---

# Tasks: Decentralized Agent Event Foundation

**Feature Branch**: `001-event-foundation`

**Input**: Design documents from `/specs/001-event-foundation/`

**Topic Naming Convention**: `{environment}.{domain}.{entity}.{action}.v{version}`
- Environment prefix for local dev: `local`
- Business-event oriented — never named after consumers; add agents by adding domains/event types
- Domains: `support`, `resolution`, `billing`, `risk`, `audit`, `system`, `agent`
- Good: `local.billing.refund-analysis.completed.v1`, `local.audit.agent-task.accepted.v1`
- Foundation topics: `local.agent.message.sent.v1`, `local.audit.envelope.recorded.v1`, `local.system.sample.published.v1`, `local.system.processed-id.{consumer_name}.recorded.v1`
- See `specs/001-event-foundation/contracts/topics.md` for the full convention and implementation spec

**Organization**: Tasks grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2)
- Exact file paths included in all task descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project scaffolding, dependency config, and local event infrastructure

- [X] T001 Create top-level directory structure: `src/agent_foundation/`, `src/agent_foundation/payloads/`, `src/agent_foundation/transport/`, `src/agent_foundation/audit/`, `packages/contracts/`, `tests/unit/`, `tests/integration/`, `tests/contract/`, `infra/local/`
- [X] T002 Create `pyproject.toml` at repo root with runtime deps (`pydantic>=2`, `aiokafka`, `structlog`, `typer`) and dev extras (`pytest`, `pytest-asyncio`, `testcontainers[kafka]`); set `asyncio_mode = "auto"` under `[tool.pytest.ini_options]`; define package as `agent_foundation` under `src/`
- [X] T003 [P] Configure ruff lint + format and mypy strict mode in `pyproject.toml`; add `.python-version` pinned to `3.12`
- [X] T004 Create `infra/local/docker-compose.yml` with: Redpanda broker (Kafka-compatible, single broker, listening on `localhost:9092` with `auto.create.topics.enable=true`), Kafkbat Kafka UI (`ghcr.io/kafbat/kafka-ui`) at `localhost:8080` connected to Redpanda, and an optional Postgres 16 service (commented out, for future audit persistence)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core `agent_foundation` package that ALL user stories depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T005 Create `src/agent_foundation/__init__.py`, `src/agent_foundation/payloads/__init__.py`, `src/agent_foundation/transport/__init__.py`, `src/agent_foundation/audit/__init__.py`, and `packages/contracts/__init__.py` package init files; create `tests/unit/__init__.py`, `tests/integration/__init__.py`, `tests/contract/__init__.py`
- [X] T006 [P] Create `src/agent_foundation/envelope.py` with `EventEnvelope` (Pydantic v2, `frozen=True`, `extra="forbid"`) and `AgentIdentity` models per data-model.md; include `ROOT_EVENT_TYPES` set, `causation_id` conditional validator (non-root events must have it), and field regex patterns for `agent_id` and `tenant_id`
- [X] T007 [P] Create `src/agent_foundation/a2a.py` with `A2APart`, `A2AMessage`, and `A2ATask` Pydantic v2 models matching `contracts/a2a-message.schema.json`; use `Literal` discriminators and conditional `required` validators per schema `allOf` rules
- [X] T008 Create `src/agent_foundation/payloads/sample.py` with `SamplePayload` (message: str, 1–200 chars) and `AuditPayload` (original_envelope: EventEnvelope, outcome: Literal, reason: str | None, recorded_at: datetime) matching `contracts/audit-payload.schema.json`
- [X] T009 Register all payload types in `src/agent_foundation/payloads/__init__.py`: map `agent.message.v1` → `A2AMessage`, `agent.audit.v1` → `AuditPayload`, `agent.sample.v1` → `SamplePayload`; define `UnknownEventType` and `PayloadValidationError` exceptions; expose `lookup(event_type)` function
- [X] T010 [P] Create `src/agent_foundation/logging.py` with structlog configuration (JSON output to stdout, per-call binding of `agent_id`, `event_id`, `correlation_id`, `causation_id`); define module-level constants for all mandatory event names (`event.published`, `event.received`, `event.rejected`, `event.duplicate_skipped`, `consumer.error`)
- [X] T011 [P] Create `packages/contracts/topics.py` implementing the `{environment}.{domain}.{entity}.{action}.v{version}` convention from `specs/001-event-foundation/contracts/topics.md`: (1) `resolve_topic(environment, domain, entity, action, version="1") -> str` returning `f"{environment}.{domain}.{entity}.{action}.v{version}"`; (2) `AGENT_ENVIRONMENT` from `os.environ.get("AGENT_ENVIRONMENT", "local")`; (3) `topic_for(domain, entity, action, version="1", environment=None) -> str` using `AGENT_ENVIRONMENT` when `environment` is `None`; (4) `processed_id_topic(consumer_name) -> str` factory; (5) `TOPIC_AUDIT = topic_for("audit", "envelope", "recorded")`, `TOPIC_MESSAGE = topic_for("agent", "message", "sent")`, `TOPIC_SAMPLE = topic_for("system", "sample", "published")`. Create `src/agent_foundation/transport/topics.py` importing these constants and implementing `create_topics()` async via aiokafka `AIOKafkaAdminClient` with compaction for `local.audit.envelope.recorded.v1` keyed by `event_id` and for `local.system.processed-id.*.recorded.v1`. Acceptance: `resolve_topic("local", "billing", "refund-analysis", "completed") == "local.billing.refund-analysis.completed.v1"`
- [X] T012 Create `tests/conftest.py` with shared pytest fixtures (e.g., sample `AgentIdentity`, valid `EventEnvelope` factory, `correlation_id` factory)

**Checkpoint**: `uv sync` succeeds; `python -c "from agent_foundation.envelope import EventEnvelope"` imports cleanly; `pytest tests/unit/` passes with zero tests (empty suite is OK at this stage)

---

## Phase 3: User Story 1 — Stand Up the Local Event Backbone (Priority: P1) 🎯 MVP

**Goal**: Single-command infrastructure startup with verifiable health signal

**Independent Test**: Run `docker compose -f infra/local/docker-compose.yml up -d`, wait 30s, run `python -m agent_foundation health`; exit code 0 and JSON lines showing `status: "ok"` for broker and all four topics

- [X] T013 [US1] Create `src/agent_foundation/cli.py` with typer app and `health` command: check Redpanda broker connectivity via aiokafka `AIOKafkaAdminClient`, verify all four canonical topics exist (call `create_topics()` for any missing), emit one structured JSON log line per component and one `health.overall` line; exit non-zero if any component fails
- [X] T014 [P] [US1] Add `__main__.py` to `src/agent_foundation/` (`python -m agent_foundation` entry point) and register CLI entry point in `pyproject.toml` as `agent-foundation = "agent_foundation.cli:app"`

**Checkpoint**: US1 fully testable — `docker compose -f infra/local/docker-compose.yml up -d && python -m agent_foundation health` exits 0

---

## Phase 4: User Story 2 — Publish and Consume a Structured Agent Event (Priority: P1)

**Goal**: Round-trip a well-formed event through schema validation, transport, and audit

**Independent Test**: Start `python -m agent_foundation consume-sample --consumer-group demo` in terminal A; run `python -m agent_foundation publish-sample --message "hello"` in terminal B; terminal A prints received event within 1s; `publish-sample --message ""` exits non-zero before sending

### Publisher Abstraction (src/agent_foundation/transport/publisher.py)

- [X] T015 [P] [US2] Create `Publisher` async context manager class with `__init__(self, agent_identity: AgentIdentity, bootstrap_servers: str = "localhost:9092")` storing identity; implement `async __aenter__` that constructs and starts `AIOKafkaProducer`; implement `async __aexit__` that stops the producer in `src/agent_foundation/transport/publisher.py`
- [X] T016 [P] [US2] Add `_build_envelope(self, payload: BaseModel, event_type: str, correlation_id: UUID, causation_id: UUID | None = None) -> EventEnvelope` to `Publisher`: call `payloads.lookup(event_type)` (raises `UnknownEventType`), assert `payload` is an instance of the registered model (raises `PayloadValidationError`), construct `EventEnvelope(event_id=uuid4(), timestamp=datetime.now(UTC), agent_id=self._identity.agent_id, tenant_id=self._identity.tenant_id, payload=payload.model_dump(mode="json"), ...)` — the envelope model_validator raises `MissingCausation` for non-root events missing `causation_id` in `src/agent_foundation/transport/publisher.py`
- [X] T017 [P] [US2] Add `_resolve_topic(self, event_type: str) -> str` to `Publisher` that returns the Kafka topic name from `TOPIC_NAMES` in `transport/topics.py`; raises `UnknownEventType(event_type)` if the key is absent in `src/agent_foundation/transport/publisher.py`
- [X] T018 [P] [US2] Add `_serialize(self, envelope: EventEnvelope) -> bytes` to `Publisher` that calls `envelope.model_dump_json(mode="json")` (forces ISO 8601 strings for all datetime fields) and encodes to UTF-8 bytes in `src/agent_foundation/transport/publisher.py`
- [X] T019 [US2] Implement `async publish(self, payload: BaseModel, event_type: str, correlation_id: UUID, causation_id: UUID | None = None) -> EventEnvelope` on `Publisher`: call `_build_envelope()` then `_resolve_topic()` then `_serialize()` then `await self._producer.send_and_wait(topic, value=data, key=str(envelope.event_id).encode())`; all validation exceptions propagate to caller without publishing in `src/agent_foundation/transport/publisher.py`
- [X] T020 [US2] Add structlog logging to `Publisher`: at `__aenter__` bind `agent_id` and `tenant_id` to a module-level structlog logger; in `publish()` emit `event.published` with `event_id`, `correlation_id`, `event_type`, and `topic` on successful `send_and_wait`; emit `event.publish_failed` with `error` field on any exception before re-raising in `src/agent_foundation/transport/publisher.py`

### Consumer, Idempotency, and CLI

- [X] T021 [US2] Create `src/agent_foundation/idempotency.py` with `IdempotencyTracker`: in-process LRU cache (maxsize=10000) of processed `event_id`s plus Kafka-backed persistence to `local.system.processed-id.{consumer_name}.recorded.v1` (use `processed_id_topic(consumer_name)` from `topics.py`); expose `async is_duplicate(event_id) -> bool` and `async mark_processed(event_id)`; rebuild LRU from compacted topic on init
- [X] T022 [US2] Create `src/agent_foundation/transport/consumer.py` with `Consumer` async class: validates incoming envelope and payload via registry; calls `IdempotencyTracker`; emits `event.received` or `event.duplicate_skipped` structured log; delegates to user-provided async handler; calls audit write on any rejection path
- [X] T023 [US2] Create `src/agent_foundation/audit/store.py` with `write_audit(publisher, envelope, outcome, reason)` async function that constructs and publishes an `AuditPayload` envelope to `local.audit.envelope.recorded.v1` (use `TOPIC_AUDIT` from `topics.py`) keyed by `envelope.event_id` for log compaction
- [X] T024 [P] [US2] Add `publish-sample` CLI command to `src/agent_foundation/cli.py`: accepts `--message TEXT`, `--omit-causation/--no-omit-causation`, `--non-root/--no-non-root` flags; constructs a valid `agent.sample.v1` `EventEnvelope` and publishes to `local.system.sample.published.v1` (use `TOPIC_SAMPLE`) via `Publisher`; exits non-zero on validation failure
- [X] T025 [P] [US2] Add `consume-sample` CLI command to `src/agent_foundation/cli.py`: accepts `--consumer-group TEXT`; runs `Consumer` subscribed to `local.system.sample.published.v1` (use `TOPIC_SAMPLE`); prints each received event as a structured log line; runs until Ctrl-C (graceful shutdown on SIGINT)

**Checkpoint**: US2 independently functional — schema rejection, round-trip, and audit write all work end-to-end

---

## Phase 5: User Story 3 — Trace a Logical Workflow via Correlation and Causation (Priority: P2)

**Goal**: Publish a causal event chain and retrieve the complete ordered chain by correlation ID

**Independent Test**: `python -m agent_foundation publish-chain --length 3` prints a correlation_id; `python -m agent_foundation query-audit --correlation <id>` returns three records in causal offset order, each with correct causation pointer to predecessor

- [X] T026 [US3] Add `publish-chain` CLI command to `src/agent_foundation/cli.py`: accepts `--length INT` (default 3); generates a fresh correlation ID; publishes N events as a causal chain (event N names event N-1 as `causation_id`); prints the shared correlation_id on completion
- [X] T027 [US3] Implement `query_by_correlation(publisher_or_bootstrap, correlation_id) -> list[AuditPayload]` in `src/agent_foundation/audit/store.py`: creates a temporary consumer on `local.audit.envelope.recorded.v1` (use `TOPIC_AUDIT`) from earliest offset; filters records where `original_envelope.correlation_id == correlation_id`; returns sorted by Kafka partition offset (true causal order)
- [X] T028 [P] [US3] Add `query-audit` CLI command to `src/agent_foundation/cli.py`: accepts `--correlation UUID`; calls `query_by_correlation`; prints each returned audit record as a structured JSON line including `event_id`, `causation_id`, `outcome`, and `recorded_at`

**Checkpoint**: US3 testable per quickstart.md section 5 — three-event chain recoverable in order

---

## Phase 6: User Story 4 — Replay an Event Stream from a Known Point (Priority: P2)

**Goal**: Re-deliver events from a chosen offset; idempotent consumers deduplicate automatically

**Independent Test**: `python -m agent_foundation replay --topic local.system.sample.published.v1 --from-offset earliest --consumer-group demo-replay` delivers all prior events; re-running with the same consumer-group produces zero handler invocations (idempotency absorbs all re-deliveries)

- [X] T029 [US4] Add `seek_to_beginning()` and `seek_to_offset(offset: int)` methods to `src/agent_foundation/transport/consumer.py`; call before entering the consume loop when `from_offset` is set; use aiokafka `TopicPartition` + `seek()` / `seek_to_beginning()`
- [X] T030 [US4] Add `replay` CLI command to `src/agent_foundation/cli.py`: accepts `--topic TEXT`, `--from-offset TEXT` (earliest/latest/integer), `--consumer-group TEXT`; creates a `Consumer` at the chosen offset using the seek methods from T029; idempotency tracker naturally deduplicates re-delivered events

**Checkpoint**: SC-005 and SC-006 verifiable — replay to same consumer-group produces identical final state

---

## Phase 7: User Story 5 — Inspect the Canonical Audit Record (Priority: P3)

**Goal**: Every published and rejected event captured once in `local.audit.envelope.recorded.v1` with full envelope

**Independent Test**: After `publish-chain --length 5`, querying audit records returns exactly 5 accepted entries with full envelopes; after `publish-sample --message ""`, a rejected record with `reason: "payload_invalid"` is present

- [X] T031 [US5] Implement `query_by_window(bootstrap, start_dt, end_dt) -> list[AuditPayload]` in `src/agent_foundation/audit/store.py`: consumes `local.audit.envelope.recorded.v1` (use `TOPIC_AUDIT`) from earliest, filters `recorded_at` within `[start_dt, end_dt]`, returns list
- [X] T032 [P] [US5] Add `query-rejections` CLI command to `src/agent_foundation/cli.py`: consumes `local.audit.envelope.recorded.v1` (use `TOPIC_AUDIT`), filters for `outcome == "rejected"`, prints each rejection record as a JSON line with `event_id`, `reason`, and `recorded_at`

**Checkpoint**: US5 testable per quickstart.md section 7 — all five outcomes (accepted, rejected, duplicate_skipped) visible in Kafkbat UI at http://localhost:8080

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Test suite, documentation, and end-to-end quickstart validation

- [X] T033 [P] Write unit tests in `tests/unit/test_envelope.py`: validate `EventEnvelope` rejects missing fields, bad `agent_id` regex, non-root event with `causation_id=None`, extra fields; validate frozen immutability; test `payloads.lookup()` returns correct model and raises `UnknownEventType`
- [X] T034 [P] Write contract tests in `tests/contract/test_schemas.py`: round-trip each schema (`EventEnvelope`, `A2AMessage`, `AuditPayload`, `SamplePayload`) through `model → model_dump_json() → model_validate_json()` and assert all fields equal; validate JSON output matches `contracts/*.schema.json` structure
- [X] T035 Write integration test in `tests/integration/test_transport.py` using `testcontainers[kafka]`: publish a `agent.sample.v1` event, consume it, assert all envelope fields survive round-trip; trigger schema rejection, assert audit record written with `outcome: "rejected"`; mark with `@pytest.mark.integration`
- [X] T036 [P] Write integration test in `tests/integration/test_idempotency.py` using `testcontainers[kafka]`: publish one event, replay same stream twice, assert handler called exactly once; confirm `IdempotencyTracker` recovery from compacted Kafka topic on simulated restart; mark with `@pytest.mark.integration`
- [X] T037 [P] Update `README.md` with one-paragraph summary of the foundation and link to `specs/001-event-foundation/quickstart.md`; include `docker compose -f infra/local/docker-compose.yml up -d` as the canonical start command
- [X] T038 Run quickstart.md end-to-end validation: execute all 8 steps against the live stack, confirm each produces the documented output, correct any discrepancies in `specs/001-event-foundation/quickstart.md`
- [X] T042 [P] Audit hardcoded topic strings: grep `src/` and `apps/` for string literals matching `agent\.[a-z_]+\.v\d+` or any bare topic-name pattern; every match outside `packages/contracts/topics.py` MUST be replaced with a `topic_for()` call imported from `packages.contracts.topics`; environment configurability verified by running `AGENT_ENVIRONMENT=staging python -m agent_foundation health` and confirming log lines reference `staging.*` topic names

---

## Phase 9: Dev Tools — Sample Event Producer

**Purpose**: Standalone dev script for publishing `local.support.ticket.created.v1` events, used for manual testing and demo. Introduces a domain event type outside the foundation's `agent.*` namespace, requiring an updated `event_type` regex and a new payload model.

- [X] T039 [P] Update `event_type` field validator in `src/agent_foundation/envelope.py`: change the pattern from `^agent\.[a-z_]+\.v\d+$` to `^[a-z][a-z0-9_-]*(\.[a-z][a-z0-9_-]*)+\.v\d+$` to allow multi-segment domain event types like `local.support.ticket.created.v1`; add `"local.support.ticket.created.v1"` to `ROOT_EVENT_TYPES` frozenset (ticket creation initiates a new workflow — no causation parent)
- [X] T040 [P] Create `packages/__init__.py`, `packages/contracts/__init__.py`, `packages/contracts/events/__init__.py` stub files; create `packages/contracts/events/payloads.py` with all domain event payload models: (1) `EvidenceItem(BaseModel, frozen=True, extra="forbid")`: `source: str`, `description: str`, `value: Any`; (2) `SupportTicketCreatedPayload(BaseModel, frozen=True, extra="forbid")`: `ticket_id: str`, `customer_id: str`, `amount: float`, `currency: str`, `reason: str`, `created_at: datetime` (tz-aware); (3) `RefundReviewRequestedPayload(BaseModel, frozen=True, extra="forbid")`: `ticket_id: str`, `customer_id: str`, `amount: float`, `currency: str`, `review_type: Literal["billing","risk","combined"]`, `requested_by_agent_id: str`; (4) `BillingRefundAnalysisCompletedPayload(BaseModel, frozen=True, extra="forbid")`: `ticket_id: str`, `recommendation: str`, `confidence: Annotated[float, Field(ge=0.0, le=1.0)]`, `evidence: list[EvidenceItem]`, `reasoning_summary: str`, `requires_human_review: bool`; (5) `RiskReviewCompletedPayload(BaseModel, frozen=True, extra="forbid")`: `ticket_id: str`, `recommendation: str`, `confidence: Annotated[float, Field(ge=0.0, le=1.0)]`, `evidence: list[EvidenceItem]`, `reasoning_summary: str`, `requires_human_review: bool`; (6) `AgentTaskAcceptedPayload(BaseModel, frozen=True, extra="forbid")`: `task_id: UUID`, `accepted_by_agent_id: str`, `accepted_at: datetime` (tz-aware); (7) `AgentTaskCompletedPayload(BaseModel, frozen=True, extra="forbid")`: `task_id: UUID`, `recommendation: str`, `confidence: Annotated[float, Field(ge=0.0, le=1.0)]`, `evidence: list[EvidenceItem]`, `reasoning_summary: str`, `requires_human_review: bool`; (8) `AgentTaskFailedPayload(BaseModel, frozen=True, extra="forbid")`: `task_id: UUID`, `error_message: str`, `error_code: str | None = None`, `failed_at: datetime` (tz-aware); update `packages/contracts/events/__init__.py` to re-export all 8 classes; NOTE: forward-looking contracts for future business agents — NOT added to foundation `PAYLOAD_REGISTRY`; future agents import from `contracts.events.payloads` and register their own event types
- [X] T041 Create `apps/__init__.py`, `apps/api/__init__.py`, and `apps/api/dev_publish_ticket.py`: shebang `#!/usr/bin/env python3`; module docstring `"Dev-only script: publishes a sample local.support.ticket.created.v1 event. Requires Kafka at localhost:9092 (docker compose -f infra/local/docker-compose.yml up -d)."`; imports: `asyncio`, `uuid4` from `uuid`, `configure_logging` + `get_logger` from `agent_foundation.logging`, `AgentIdentity` from `agent_foundation.envelope`, `Publisher` from `agent_foundation.transport.publisher`, `SupportTicketCreatedPayload` from `agent_foundation.payloads.support_ticket`; `async def main() -> None` calls `configure_logging()`; builds `AgentIdentity(agent_id="dev.ticket-producer", display_name="Dev Ticket Producer", tenant_id="local")`; creates `SupportTicketCreatedPayload(ticket_id="TKT-001", customer_id="CUST-42", issue_type="billing", description="Charged twice for monthly subscription", amount=29.99, currency="USD")`; publishes via `Publisher` to `"local.support.ticket.created.v1"` with `correlation_id=uuid4()` (causation_id is None — root event); prints `{"event_id": str(envelope.event_id), "correlation_id": str(envelope.correlation_id), "topic": "local.support.ticket.created.v1"}` to stdout; ends with `if __name__ == "__main__": asyncio.run(main())`
- [X] T043 [P] Create `apps/api/dev_consume_events.py` (requires T041 for `apps/api/__init__.py`; requires T022 for `Consumer`): shebang `#!/usr/bin/env python3`; module docstring `"Dev-only script: subscribes to all initial canonical topics and prints each validated EventEnvelope as formatted JSON. Requires Kafka at localhost:9092 (docker compose -f infra/local/docker-compose.yml up -d). Run with: python apps/api/dev_consume_events.py"`; imports: `asyncio`, `json`, `os`, `configure_logging` from `agent_foundation.logging`, `AgentIdentity` + `EventEnvelope` from `agent_foundation.envelope`, `Consumer` from `agent_foundation.transport.consumer`, `TOPIC_SAMPLE`, `TOPIC_AUDIT`, `TOPIC_MESSAGE` from `agent_foundation.transport.topics`; define `SUBSCRIBED_TOPICS: list[str] = [TOPIC_MESSAGE, TOPIC_AUDIT, TOPIC_SAMPLE]` (all three initial canonical topics from `contracts/topics.md`; excludes per-consumer `agent.processed.*`); `async def handler(envelope: EventEnvelope) -> None` calls `print(json.dumps(envelope.model_dump(mode="json"), indent=2))` then `print("---")`; `async def main() -> None` calls `configure_logging()`, prints startup banner `f"[dev_consume_events] Subscribing to: {', '.join(SUBSCRIBED_TOPICS)}\nPress Ctrl-C to stop.\n"`, builds `AgentIdentity(agent_id="dev.consumer", display_name="Dev Consumer", tenant_id="local")`, creates `Consumer(broker_url=os.getenv("KAFKA_BROKER_URL", "localhost:9092"), group_id="dev.consumer", agent_identity=identity, idempotent=False)`, calls `consumer.subscribe(SUBSCRIBED_TOPICS)`, wraps `await consumer.run(handler)` in `try/KeyboardInterrupt/finally` that calls `await consumer.stop()`; ends with `if __name__ == "__main__": asyncio.run(main())`

**Checkpoint**: `python apps/api/dev_publish_ticket.py` against a running local stack exits 0 and emits a JSON line with `event_id` and `correlation_id`; the event appears in Kafkbat UI under a new `local.support.ticket.created.v1` topic. `python apps/api/dev_consume_events.py` prints the startup banner listing all three topic names, then prints each incoming event as indented JSON terminated by `---`; Ctrl-C shuts down cleanly with no traceback.

---

## Phase 10: Architecture Documentation

**Purpose**: Reference docs for the event-contract layer, topic-naming conventions, and a step-by-step guide for adding a new agent. Create the docs/architecture/ directory as part of T044.

- [X] T044 [P] Create docs/architecture/event-contracts.md: (1) opening paragraph — every inter-agent message uses EventEnvelope as the canonical wrapper, immutable once published; (2) EventEnvelope field-reference table with all nine fields (event_id, correlation_id, causation_id, agent_id, tenant_id, timestamp, event_type, schema_version, payload), types, required/conditional status, and validation rules sourced from data-model.md §1.1; (3) root-event rule — causation_id may be None only when event_type ∈ ROOT_EVENT_TYPES (defined in src/agent_foundation/envelope.py); (4) payload registry table mapping each registered event_type to its Pydantic model (agent.message.v1 → A2AMessage, agent.audit.v1 → AuditPayload, agent.sample.v1 → SamplePayload, local.support.ticket.created.v1 → SupportTicketCreatedPayload) with a note that business agents add entries to src/agent_foundation/payloads/__init__.py; (5) A2A payload conventions — A2AMessage and A2APart field reference with discriminator rules, and the note that transport is always Kafka, never bare A2A-HTTP; (6) validation lifecycle — publisher enforces UnknownEventType / PayloadValidationError / MissingCausation before Kafka write; consumer re-validates on receipt and writes AuditPayload(outcome="rejected") on failure; (7) concrete JSON example of a valid EventEnvelope carrying an agent.sample.v1 SamplePayload; (8) pointer to JSON schemas in specs/001-event-foundation/contracts/
- [X] T045 [P] Create docs/architecture/topic-naming.md: (1) naming rule — agent.<purpose>.v<major> (lowercase, dot-separated; <major> mirrors the MAJOR of schema_version; a breaking schema change increments the suffix and leaves the old topic intact for cutover); (2) canonical-topics table with columns Topic, Owner, Payload schema, Partitions, Retention, Compaction key — sourced from contracts/topics.md; (3) per-consumer processed-event topic — pattern agent.processed.<consumer_name>.v1, created lazily by IdempotencyTracker, log-compacted, minimal payload {"event_id": "<uuid>"}; (4) topic creation policy — auto-created by create_topics() on first Publisher.start() in dev; explicitly created with correct configs in integration tests to remove cold-start race conditions; (5) out-of-scope items for this feature (ACLs, multi-partition routing keys, cross-broker replication); (6) how to register a new topic — add a TopicConfig entry to CANONICAL_TOPICS in src/agent_foundation/transport/topics.py and add the corresponding event type to PAYLOAD_REGISTRY in src/agent_foundation/payloads/__init__.py
- [X] T046 Create docs/architecture/adding-new-agent.md as a numbered step-by-step guide; each step names the exact file to edit: **Step 1 — Add AgentDefinition**: instantiate AgentIdentity(agent_id="<your-agent-id>", display_name="...", tenant_id="poc") — agent_id must match ^[a-z][a-z0-9_.-]{1,62}$; pass to Publisher and Consumer constructors; call configure_logging() at startup. **Step 2 — Add new capabilities (event payloads)**: create src/agent_foundation/payloads/<your_payload>.py with a BaseModel subclass; all fields must be JSON-serializable. **Step 3 — Add new event type constants**: add string constants to packages/contracts/events/types.py; add the event_type string to ROOT_EVENT_TYPES in src/agent_foundation/envelope.py only if this event initiates a new workflow (no causation parent). **Step 4 — Register in payload registry**: import your payload model in src/agent_foundation/payloads/__init__.py and add "<your.event.type>": YourPayload to PAYLOAD_REGISTRY. **Step 5 — Add topic mapping**: if the event type needs its own topic, add a TopicConfig entry to CANONICAL_TOPICS in src/agent_foundation/transport/topics.py following the agent.<purpose>.v<major> naming rule (see docs/architecture/topic-naming.md); skip if publishing to an existing topic. **Step 6 — Add consumer subscriptions**: create Consumer(broker_url, group_id="<your-agent-id>", agent_identity=identity, idempotent=True), call .subscribe(["<topic>"]), then .run(your_handler); retrieve the typed payload inside the handler with PAYLOAD_REGISTRY[envelope.event_type].model_validate(envelope.payload). **Step 7 — Add tests**: (a) unit — tests/unit/test_<your_payload>.py: validate the payload model with valid and invalid inputs; (b) contract — tests/contract/test_<your_event>.py: round-trip serialize/deserialize and validate against the JSON schema in specs/001-event-foundation/contracts/; (c) integration (@pytest.mark.integration) — tests/integration/test_<your_agent>.py: use KafkaContainer, publish a well-formed event, consume and assert envelope round-trip + audit record written; publish an invalid event and assert AuditPayload(outcome="rejected"); replay same stream to same consumer group and assert zero handler invocations. Close with a constitution compliance reminder: Principle I (single responsibility, no direct agent calls), Principle II (Kafka-only comms), Principle III (idempotent handler), Principle IV (structured log per action), Principle V (justify new deps in plan.md Complexity Tracking table).

**Checkpoint**: Architecture documentation complete — a new developer can onboard to event contracts, topic conventions, and agent authoring without reading source code.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Requires Phase 1 — blocks all user story phases
- **Phase 3 (US1)**: Requires Phase 2 — uses topics.py and aiokafka
- **Phase 4 (US2)**: Requires Phase 2 — can run in parallel with US1 once Phase 2 is done
- **Phase 5 (US3)**: Requires Phase 4 complete — uses audit/store.py and Publisher built in US2
- **Phase 6 (US4)**: Requires Phase 4 complete — extends Consumer from US2
- **Phase 7 (US5)**: Requires Phase 4 complete — extends audit/store.py from US2
- **Phase 8 (Polish)**: Requires all story phases complete
- **Phase 9 (Domain Contracts + Dev Tools)**: Requires Phase 4 complete (uses Publisher); T040 (payload models) can run in parallel with Phases 3–7
- **Phase 10 (Docs)**: Requires all other phases complete

### User Story Dependencies

- **US1 (P1)**: Can start after Phase 2 — no other story dependencies
- **US2 (P1)**: Can start after Phase 2 — can run in parallel with US1
- **US3 (P2)**: Requires US2 complete (uses Publisher + audit/store.py)
- **US4 (P2)**: Requires US2 complete (extends Consumer with seek)
- **US5 (P3)**: Requires US2 complete (extends audit/store.py)
- US3, US4, US5 can proceed in parallel once US2 is complete

---

## Parallel Execution Examples

### Phase 2 (Foundational) — Maximum Parallelism

```bash
# Batch 1: all write to different files, no dependencies on each other
Task T006: "Create src/agent_foundation/envelope.py"
Task T007: "Create src/agent_foundation/a2a.py"
Task T010: "Create src/agent_foundation/logging.py"
Task T011: "Create packages/contracts/topics.py and transport/topics.py"

# Batch 2: depend on T006+T007 — run after batch 1
Task T008: "Create src/agent_foundation/payloads/sample.py"
Task T009: "Register payload types in payloads/__init__.py"
```

### Phase 4 (US2) — Publisher Abstraction and CLI Commands

```bash
# Publisher internals T015-T018 are independent (different methods, same file):
Task T015: "Create Publisher async context manager (init, __aenter__, __aexit__)"
Task T016: "Add _build_envelope() to Publisher"
Task T017: "Add _resolve_topic() to Publisher"
Task T018: "Add _serialize() to Publisher"

# T019 depends on T015-T018 (calls all four helpers); T020 depends on T019:
Task T019: "Implement async publish() on Publisher"
Task T020: "Add structlog logging to Publisher"

# T021-T023 must run sequentially (IdempotencyTracker → Consumer → audit/store):
Task T021: "Create IdempotencyTracker in idempotency.py"
Task T022: "Create Consumer in transport/consumer.py"
Task T023: "Create write_audit() in audit/store.py"

# Once T023 is done, T024 and T025 are independent:
Task T024: "Add publish-sample CLI command"
Task T025: "Add consume-sample CLI command"
```

### Phase 9 (Domain Contracts + Dev Tools)

```bash
# T039 and T040 can run in parallel (independent files):
Task T039: "Update event_type validator in envelope.py"
Task T040: "Create packages/contracts/events/payloads.py (all domain models)"

# After T039 + T040 complete:
Task T041: "Create apps/api/dev_publish_ticket.py"
Task T043: "Create apps/api/dev_consume_events.py"
```

---

## Implementation Strategy

### MVP Scope (US1 + US2 Only — 25 tasks)

1. Complete Phase 1: Setup (T001–T004)
2. Complete Phase 2: Foundational (T005–T012) including domain payload contracts (T040)
3. Complete Phase 3: US1 — health check + docker compose (T013–T014)
4. Complete Phase 4: US2 — full publish/consume round-trip (T015–T025)
5. **STOP and VALIDATE**: publish-sample → consume-sample → audit record visible in Kafkbat UI
6. Demo: Redpanda running, events flowing, schema rejection working, audit written

### Incremental Delivery

1. Phase 1 + 2 → Package installable, models pass mypy; domain payload contracts importable
2. Phase 3 → docker compose up -d + health command green (US1 done)
3. Phase 4 → Full round-trip proven, rejection paths verified (US2 done — **primary demo point**)
4. Phase 5 → Correlation chains traceable (US3 done)
5. Phase 6 → Replay + idempotency proven (US4 done)
6. Phase 7 → Audit store queryable (US5 done)
7. Phase 8 → Test suite green, quickstart validated
8. Phase 9 → Domain payload contracts published; dev ticket producer works end-to-end
9. Phase 10 → Architecture docs complete

---

## Notes

- **Redpanda**: infra/local/docker-compose.yml uses Redpanda (Kafka-API-compatible) for local POC simplicity — aiokafka connects identically to real Kafka; no code changes needed if switching to native Kafka later
- **Kafkbat UI**: image ghcr.io/kafbat/kafka-ui, accessible at http://localhost:8080; use to inspect topics and audit records for US5 validation
- **Domain payload contracts (T040)**: packages/contracts/events/payloads.py defines Pydantic schemas for future business agents; NOT registered in foundation PAYLOAD_REGISTRY; future agents import from contracts.events.payloads and register event types in their own registry
- **Integration tests**: use testcontainers[kafka] (native Kafka container) not the local docker-compose Redpanda, to avoid test coupling to local stack state
- **Start command**: docker compose -f infra/local/docker-compose.yml up -d (not cd infra && docker compose up -d); update quickstart.md in T038 if needed
- **No business agents**: zero domain-specific refund logic ships in this feature (Principle V / SC-007)
