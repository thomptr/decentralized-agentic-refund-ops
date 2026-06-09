# Quickstart: A2A Runtime Contract

**Feature**: 002-a2a-runtime-contract

This guide proves the runtime end-to-end: stand up two independent agents, discover capabilities
without a central registry, delegate a task peer-to-peer, and inspect the full task-lifecycle audit
trail. It assumes the `001-event-foundation` local stack and dev environment are already working.

## Prerequisites

- The foundation's local Kafka stack is running:
  ```bash
  docker compose -f infra/local/docker-compose.yml up -d
  uv run agent-foundation health        # expect overall status "ok"
  ```
- Dev dependencies installed: `uv sync --extra dev`.
- No new third-party dependency is required by this feature.

## Scenario 1 — Stand up an agent with its own endpoint (US1, US2)

Start the example echo agent in its own terminal. It publishes its Agent Card and begins serving
its endpoint topic.

```bash
uv run agent-foundation serve-echo --agent-id echo.alpha
# logs: agent-card.published, endpoint.serving (topic local.agent.echo.alpha.task.requested.v1)
```

**Expected**: structured logs show the card published to `local.agent.agent-card.published.v1` and
the agent consuming its endpoint topic.

## Scenario 2 — Discover capabilities without a central registry (US3)

In a second terminal:

```bash
uv run agent-foundation discover
# prints the echo.alpha AgentCard with its 'echo' capability

uv run agent-foundation discover --capability echo
# prints only agents that declare the 'echo' capability
```

**Expected**: `echo.alpha` appears with capability `echo`. No registry service is running — the
listing is built purely by reading the compacted card topic.

## Scenario 3 — Delegate a task peer-to-peer and get a structured result (US1, US2)

```bash
uv run agent-foundation submit-task --target echo.alpha --capability echo --text "hello"
# prints a TaskResult: status=completed, output echoes "hello", performer_agent_id=echo.alpha
```

**Expected**: a `TaskResult` with `status: "completed"` and the echoed output. The request went
directly to `echo.alpha`'s endpoint topic — no supervisor/router in the path (FR-011).

### 3a — Rejection (unsupported capability)

```bash
uv run agent-foundation submit-task --target echo.alpha --capability nonexistent --text "hi"
# prints TaskResult: status=rejected, error.category=unsupported_capability
```

### 3b — Failure (handler errors)

```bash
uv run agent-foundation submit-task --target echo.alpha --capability echo --text "FAIL"
# echo agent raises on the sentinel "FAIL"; prints TaskResult: status=failed,
# error.category=handler_error
```

**Expected**: rejection and failure are distinct outcomes with distinct `error.category` values
(FR-007).

## Scenario 4 — Inspect the full task lifecycle audit trail (US4)

Take the `task_id` printed by any `submit-task` run (or copy it from the logs) and query the audit
topic:

```bash
uv run agent-foundation query-task-audit --task-id <uuid>
```

**Expected**, ordered by Kafka offset:
- For a completed task: `accepted` then `completed`.
- For a failed task: `accepted` then `failed` (with a `reason`).
- For a rejected task: a single `rejected` (with a `reason`); no `accepted`.

This demonstrates FR-008/FR-009: exactly one of {rejected} or {accepted + one terminal} per task.

## Scenario 5 — Idempotency (FR-010)

Re-submit the **same** `task_id` twice (the integration test does this directly via `A2AClient`;
manually, replay the request envelope from the endpoint topic):

```bash
uv run agent-foundation replay --topic local.agent.echo.alpha.task.requested.v1 --from-offset earliest
```

**Expected**: the re-delivered request is recorded as `duplicate_skipped` in the audit trail; the
echo handler does **not** run a second time and no second `TaskResult` terminal outcome is produced.

## Scenario 6 — No supervisor / central router (US5)

```bash
# Start a second agent and confirm cross-agent delegation is direct.
uv run agent-foundation serve-echo --agent-id echo.beta
uv run agent-foundation submit-task --target echo.beta --capability echo --text "from a peer"
```

**Expected**: `echo.beta` answers directly. Inspect the running components — only agents,
`A2AClient` callers, and Kafka exist; there is no dispatcher/router/orchestrator process. Tracing
any task shows requester → performer endpoint with no intermediary.

## Automated verification

```bash
# Fast suite (no broker): contracts + runtime state machine
uv run pytest tests/unit/test_task_contracts.py tests/unit/test_runtime_state.py \
              tests/contract/test_runtime_schemas.py

# Full end-to-end (requires Docker/Kafka via testcontainers)
uv run pytest -m integration tests/integration/test_runtime_a2a.py
```

The integration test asserts, per task, the exact audit-event sequence and that a re-submitted
`task_id` does not re-execute — the machine-checked version of Scenarios 3–5.

## Success criteria mapping

| Scenario | Spec criteria |
|----------|---------------|
| 1 | SC-001 (expose endpoint + card with zero transport/audit code) |
| 2 | SC-006 (discover + delegate, no router) |
| 3, 3a, 3b | SC-002, SC-003, SC-004 (lifecycle outcomes; rejection vs failure) |
| 4 | SC-002, SC-007 (audit per transition; reconstruct lifecycle by task id) |
| 5 | SC-005 (idempotent re-delivery) |
| 6 | SC-008 (no supervisor/router/orchestrator) |
