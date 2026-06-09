---
name: aiokafka-async-for-blocks-forever
description: aiokafka `async for msg in consumer` never stops on idle; consumer_timeout_ms does not terminate iteration
metadata:
  type: project
---

In aiokafka, `async for msg in consumer` (i.e. `__anext__`) loops on `getone()` and only
raises `StopAsyncIteration` on `ConsumerStoppedError`. It does **not** honor
`consumer_timeout_ms` to stop on idle (that's a kafka-python behavior). So any
"drain everything currently on the topic then return" loop written as `async for`
blocks forever once the topic is drained, waiting for a next message that never comes.

**Why:** This caused all audit-querying integration tests to hang to the 180s pytest
timeout (`consume_all_audit_records` in `src/agent_foundation/audit/store.py`). It was
likely also the real cause behind the "kafka testcontainer timeout" the team disabled
integration tests for in CI (commit a760c66) — misattributed to testcontainers.

**How to apply:** To drain a topic to its current end, poll with
`await consumer.getmany(timeout_ms=N)` and `break` on the first empty result (`if not batch`).
Use `group_id=None`, `auto_offset_reset="earliest"`, `enable_auto_commit=False`.
`idempotency.py:_rebuild_from_topic` is the canonical example; `audit/store.py:consume_all_audit_records`
now matches it.
