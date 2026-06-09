# Interface Contract: A2A Runtime API

**Feature**: 002-a2a-runtime-contract

This is the public Python interface the runtime exposes to agent authors. It is the contract future
business agents (customer resolution, billing, risk) will depend on. Signatures are normative;
bodies are illustrative and belong to the implementation phase, not this contract.

All types live under `src/agent_foundation/runtime/`. The runtime composes the foundation's
`Publisher`, `Consumer`, `IdempotencyTracker`, and `audit.store` — it introduces no parallel
transport (FR-014).

---

## 1. `AgentRuntime` — expose an endpoint, serve tasks, audit the lifecycle

```python
class AgentRuntime:
    def __init__(
        self,
        identity: AgentIdentity,
        card: AgentCard,
        broker_url: str = "localhost:9092",
    ) -> None: ...

    def handler(self, capability_id: str) -> Callable[[TaskHandler], TaskHandler]:
        """Decorator: register an async handler for one declared capability.
        Raises ValueError if capability_id is not in self.card.capabilities."""

    async def serve(self, stop_event: asyncio.Event | None = None) -> None:
        """Ensure topics exist, publish the Agent Card, then consume this agent's
        endpoint topic and drive each TaskRequest through the lifecycle:
          validate -> (reject | accept) -> run handler -> (complete | fail),
        emitting the corresponding audit event(s) and publishing exactly one
        TaskResult. Idempotent by task_id. Runs until stop_event is set."""
```

- `TaskHandler = Callable[[TaskRequest], Coroutine[Any, Any, A2AMessage]]` — the author returns the
  success `output` message; raising any exception yields a `failed` result + `failed` audit.
- The runtime publishes the `AgentCard` to `TOPIC_AGENT_CARD` on `serve()` start and whenever
  `republish_card()` is called (FR-013).
- **Lifecycle guarantees** (FR-008/FR-009, see data-model §4):
  - Unknown/malformed request or unsupported capability → audit `rejected` + `TaskResult(rejected)`;
    handler not run.
  - Valid request → audit `accepted`; on handler success → audit `completed` + `TaskResult(completed)`;
    on handler exception → audit `failed` + `TaskResult(failed)`.
  - Duplicate `task_id` → audit `duplicate_skipped`; no re-run, no second terminal outcome (FR-010).
  - Exactly one of {rejected} or {accepted + one terminal} per task.

```python
    async def republish_card(self, card: AgentCard | None = None) -> None:
        """Publish an updated Agent Card (latest-wins by agent_id)."""
```

---

## 2. `A2AClient` — discover peers and delegate tasks (no router)

```python
class A2AClient:
    def __init__(self, identity: AgentIdentity, broker_url: str = "localhost:9092") -> None: ...

    async def submit(
        self,
        target_agent_id: str,
        capability: str,
        input: A2AMessage,
        *,
        correlation_id: UUID | None = None,
        causation_id: UUID | None = None,
        task_id: UUID | None = None,
        timeout_s: float = 30.0,
    ) -> TaskResult:
        """Publish a TaskRequest directly to target_agent_id's endpoint topic, then
        await the correlated TaskResult (filtered by task_id) from the result topic.
        No supervisor/router is involved (FR-011). Raises TimeoutError if no result
        arrives within timeout_s (note: liveness/timeout of a hung peer is a documented
        gap, spec Assumptions)."""
```

---

## 3. Discovery — capability lookup without a central registry

```python
async def discover_agents(broker_url: str = "localhost:9092") -> list[AgentCard]:
    """Read local.agent.agent-card.published.v1 from earliest and return the latest
    AgentCard per agent_id (FR-003). No central registry service is queried."""

async def find_capable(capability_id: str, broker_url: str = "localhost:9092") -> list[AgentCard]:
    """Return all currently-published agents declaring capability_id. The caller selects
    a target; the runtime does not arbitrate or load-balance (spec edge case: competing
    providers)."""
```

---

## 4. Foundation touch-points (modifications, not new transport)

| Symbol | Change | Why |
|--------|--------|-----|
| `Publisher.publish(..., topic: str \| None = None)` | New optional, backward-compatible param overriding registry topic resolution while keeping validation. | Send validated `TaskRequest`/`TaskResult` to dynamic endpoint/result topics (research R5). |
| `payloads/__init__.py` `PAYLOAD_REGISTRY` | Register `agent.task_request.v1→TaskRequest`, `agent.task_result.v1→TaskResult`, `agent.agent_card.v1→AgentCard`. | Producer/consumer validation of the new payloads. |
| `payloads/sample.py` `AuditPayload` | Add optional `task_id`; extend `outcome` with `completed`/`failed`; require `reason` on `failed`. | Carry task-lifecycle audit on the reused audit topic (research R4, FR-014). |
| `audit/store.py` | Add `write_task_audit(publisher, envelope, outcome, task_id, reason)` helper (thin wrapper over the existing write path). | Emit lifecycle audit through the existing subsystem. |
| `transport/topics.py` | Add `TOPIC_AGENT_CARD`, `TOPIC_TASK_RESULT` `NewTopic`s; `endpoint_topic` factory in `packages/contracts/topics.py`. | Create/serve the new topics. |

---

## 5. CLI contract (`agent-foundation` Typer app additions)

| Command | Purpose |
|---------|---------|
| `serve-echo --agent-id <id> [--broker]` | Start the example echo agent (exposes an endpoint, publishes its card, serves the `echo` capability). |
| `publish-card --agent-id <id> ...` | Publish/refresh an Agent Card. |
| `discover [--capability <id>] [--broker]` | List discovered agents (optionally filtered by capability). |
| `submit-task --target <id> --capability <id> --text <msg> [--broker] [--timeout]` | Delegate a task and print the returned `TaskResult`. |
| `query-task-audit --task-id <uuid> [--broker]` | Print a task's full lifecycle from the audit topic, ordered by offset. |

These exercise the runtime end-to-end and are the basis of `quickstart.md`.
