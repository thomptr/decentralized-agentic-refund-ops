# Replay and Idempotency

Authoritative sources: `specs/006-workflow-choreography/contracts/replay-and-trace.md`,
`specs/001-event-foundation/plan.md`, `specs/002-a2a-runtime-contract/plan.md`.

## Why this matters

Kafka delivers events at-least-once. An operator may also replay a recorded event stream to reproduce
or debug a case. Without three layers of idempotency guards, replay and redelivery would produce
duplicate opinions, duplicate decisions, or inconsistent outcomes.

## Three idempotency layers (FR-011, FR-012, FR-013)

### Layer 1 — Event-level: IdempotencyTracker per consumer group

`src/agent_foundation/idempotency.py::IdempotencyTracker` deduplicates on `event_id` within a consumer
group. Each consumer group maintains its own compacted processed-id topic:

```
{env}.system.processed-id.{consumer_name}.recorded.v1
```

On every consumed envelope, the tracker checks whether the `event_id` has already been processed. If
yes, an `audit.envelope.recorded.v1` entry with `outcome="duplicate_skipped"` is emitted and the
handler is not invoked. This layer handles **transport-level redelivery** of any event.

### Layer 2 — Task-level: stable task_id = uuid5(correlation_id, capability)

A2A opinion requests carry a `task_id` derived deterministically:

```python
task_id = uuid5(correlation_id, capability_name)
```

Because `correlation_id` is fixed for a case and `capability_name` is fixed for a peer, the same
opinion request always has the same `task_id` — regardless of how many times it is sent. The A2A
runtime caches completed `TaskResult` by `task_id` and returns the stored result without re-running
the analysis (FR-012). This layer handles **duplicate opinion requests** at the task level.

### Layer 3 — Case-level: DECIDED/terminal guard → exactly one decision

`_apply_decision` in `apps/agents/customer_resolution/event_handlers.py` checks the case status before
emitting a decision:

```python
if case.status in TERMINAL_STATUSES:
    return   # already decided — no duplicate emission
```

The store's `asyncio.Lock` serializes concurrent calls. This guard is shared by the result loop and
the timeout reaper, so neither can double-decide a case (FR-013, FR-019). This layer handles
**aggregation triggered more than once** for the same case.

## Replay harness (FR-014, FR-015, FR-016)

The replay harness re-processes a recorded end-to-end scenario and asserts identical output with zero
additional side-effect events.

### Mechanism

1. **Record**: run a scenario against the container broker; capture the full event set for the target
   `correlation_id`s across all relevant topics.
2. **Fresh state**: instantiate a new `ResolutionService` with a fresh `InMemoryCaseStateStore`.
3. **Fresh consumer groups**: assign uniquely-named consumer groups (e.g., with a test-run UUID suffix)
   so each replay starts with an empty `IdempotencyTracker` and no committed offsets.
4. **Seek to beginning**: call `Consumer.seek_to_beginning()` on each consumer so the replay reads
   from offset 0 regardless of prior runs.
5. **Neutralize the reaper**: pass an effectively-infinite `CASE_DEADLINE_SECONDS` (or disable the
   reaper loop) so no clock-driven escalation is injected on top of the replay. This preserves
   determinism for completed-run replay (the reaper still fires in live integration tests).
6. **Feed input events**: replay the recorded ticket and peer result events into the fresh service.
7. **Assert**: compare re-derived `customer.resolution.decided` payload (outcome + explanation) against
   the originally recorded decision.

### Why decide() makes replay deterministic

`decision_engine.decide()` is a **pure, total function**: given the same triage output, billing
eligibility, and risk level, it always returns the same outcome. No LLM inference, no random sampling,
no wall-clock dependency. Combined with stable `task_id` (Layer 2) and deterministic triage
classification, identical input events always produce an identical decision.

### Replay assertions (SC-003, SC-006)

- Re-derived decision payload equals the originally recorded decision.
- Count of `customer.resolution.decided` events for the `correlation_id` is exactly 1.
- Duplicate input events are skipped (`duplicate_skipped` audit outcome) — no duplicate opinions or
  decisions emitted.
- A repeated `task_id` returns the stored result (no re-analysis).

## Idempotency layer summary

```
┌──────────────────────────────────────────────────────────────────────┐
│ Delivery layer     │ IdempotencyTracker (event_id per consumer group) │
│ Task layer         │ task_id = uuid5(correlation_id, capability)      │
│ Case decision layer│ DECIDED/terminal guard + asyncio.Lock            │
└──────────────────────────────────────────────────────────────────────┘
```

## Related docs

- [event-choreography.md](./event-choreography.md) — topic topology and async aggregation
- [failure-handling.md](./failure-handling.md) — reaper and late-opinion guard
- [decentralized-workflow.md](./decentralized-workflow.md) — end-to-end flow
