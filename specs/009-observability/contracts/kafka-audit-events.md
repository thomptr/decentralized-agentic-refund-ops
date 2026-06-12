# Contract: Kafka Audit Events & Heartbeat

Satisfies FR-018. **Kafka is the replayable system of record; LangFuse is the debugging/LLM layer.**
Adding LangFuse does not move any business truth off Kafka.

## Retained audit events (existing trail)

| Logical name | Realization | Topic | New? |
|--------------|-------------|-------|------|
| `audit.agent-task.requested` | `write_task_audit(envelope, outcome="requested", task_id=...)` | `TOPIC_AUDIT` (`agent.audit.v1`) | existing |
| `audit.agent-task.completed` | `write_task_audit(envelope, outcome="completed", task_id=...)` | `TOPIC_AUDIT` (`agent.audit.v1`) | existing |
| `audit.llm.invocation.completed` | `emit_llm_invocation_event(...)` | `audit.llm.invocation.completed` | existing |
| `audit.policy.decision.completed` | **new** thin `write_audit(...)` at the decision boundary | `TOPIC_AUDIT` (existing topic) | **new emission, no new topic** |

Only `audit.policy.decision.completed` is newly emitted; it reuses the existing `write_audit` on the
existing audit topic, so **no new event contract or topic** is introduced for audit.

## New event: `system.agent.heartbeat`

The single genuinely new event (Principle II amendment).

- **Emitter**: `observability/heartbeat.py`, driven by the foundation `runtime.serve()` loop, so every
  agent emits liveness with **no per-agent code**.
- **Cadence**: `AGENT_HEARTBEAT_INTERVAL_S` (default 10s; `0` disables).
- **Topic**: dedicated `TOPIC_HEARTBEAT` — **not** the compacted audit topic (compaction would discard
  liveness history).
- **Payload**: `{agent_id, emitted_at, interval_s}` — liveness only, no domain data.
- **Consumption**: never read by domain/coordination logic (Principle III). It is an observability and
  ops signal only; it does not constitute an orchestrator or supervisor (FR-019).

## Relationship to LangFuse

- Audit events and heartbeats are **independent** of LangFuse. With observability disabled or LangFuse
  down, these Kafka events still flow (they are not gated by `AGENT_OBSERVABILITY_ENABLED`, except the
  heartbeat cadence which the same config governs).
- LangFuse traces/scores reference the same `correlation_id`/`case_id`, so an operator can pivot from a
  Kafka audit record to the corresponding LangFuse trace and back.

## Invariants

- No business decision or audit record depends on LangFuse availability (FR-008/FR-018).
- The heartbeat is the only new event; the four audit events stay on the existing trail/topics.
