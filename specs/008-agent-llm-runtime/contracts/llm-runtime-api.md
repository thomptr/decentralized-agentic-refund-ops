# Contract: LLM Runtime API (`agent_foundation.llm`)

The in-process capability every agent calls. This is the feature's only public surface. It is **not**
a wire contract — there is no new event, topic, or HTTP endpoint (FR-015).

## Entry point

```python
class LLMRuntime:
    def __init__(self, config: RuntimeConfig | None = None) -> None: ...

    async def reason(self, request: AssistiveRequest) -> AssistiveResult: ...
```

`reason()` is the single front door (US1). It is `async` to bound the model call with a timeout and
to reuse the async audit/idempotency I/O already in the foundation.

## Behavioral contract for `reason()`

Given a valid `AssistiveRequest`, `reason()` MUST, in order:

1. **Idempotency check** — if `AssistiveResultStore.get(request.idempotency_key)` hits, return the
   recorded `AssistiveResult` with `reasoning_path == cache`, **no** model invocation, and an audit
   step recording the replay. (FR-007/008, US4, SC-003)
2. **Resolve profile** — `resolve_profile(request.agent_id, request.task_kind)` → `ModelProfile`.
   (FR-017, R10)
3. **Render prompt** — `PromptTemplate` builds a cache-eligible stable prefix (instructions + schema
   + examples) and a variable suffix (grounding inputs); compute `prompt_ref`. (FR-013)
4. **Invoke provider with timeout** — `await asyncio.wait_for(provider.invoke(...), profile.timeout_seconds)`.
   On timeout/unreachable/error → go to step 7 (fallback). (FR-009)
5. **Validate & repair** — parse output, validate against `request.output_schema` + grounding check;
   on failure retry up to `profile.max_repairs`. (FR-005/006, US3)
6. **On success** — record the result in the store keyed by `idempotency_key`, build an
   `AssistiveResult` with `reasoning_path == model`, token usage, and `cache_hit`; emit audit; return.
7. **On failure (timeout/error/exhausted repairs)** — invoke `request.fallback()`, build an
   `AssistiveResult` with `reasoning_path == fallback` and a `failure_reason`; emit audit; return.
   Never raise into the caller, never block past the budget, never fabricate content. (FR-006/009, US5)
8. **Always** — emit exactly one `ReasoningAuditRecord` through the existing audit subsystem. (FR-011)

### Hard guarantees (testable)

- **G1 — Schema-bounded**: every returned `AssistiveResult.value` is an instance of
  `request.output_schema`, within all enum/range bounds, with no asserted facts outside
  `grounding_inputs`. Invalid output is never returned. (SC-001)
- **G2 — Assistive only**: `reason()` returns classification / extraction / draft / summary content
  only. It has no parameter for, and returns no, binding refund verdict. Calling agents MUST NOT map
  any `AssistiveResult` field onto a binding decision. (FR-003/004, SC-002)
- **G3 — Replay-stable**: same `idempotency_key` ⇒ identical `value` and zero additional model calls.
  (SC-003)
- **G4 — Bounded & safe**: a forced model failure returns a `fallback` result with a recorded reason
  within the time budget; the binding outcome is unaffected. (SC-004)
- **G5 — Audited**: one correlated, model-free-reconstructable audit step per call, distinguishable
  from the binding decision. (SC-005)
- **G6 — Offline default**: with no AWS config, `reason()` uses the stub provider and completes with
  no cloud access. (SC-006)

## Adoption helper (per agent)

```python
async def assist_or_fallback(
    runtime: LLMRuntime,
    *, agent_id, task_kind, correlation_id, causation_id,
    instructions, grounding_inputs, output_schema, fallback,
) -> AssistiveResult: ...
```

A thin convenience that builds the `AssistiveRequest` (deriving the idempotency key) and calls
`reason()`. Agents use the returned `value` for classification/draft/summary **only**; the binding
verdict stays in `decision_engine` / `rules_engine` / `scoring` unchanged. (FR-016/018)

## LangGraph adapter

```python
def as_node(runtime: LLMRuntime, request_builder: Callable[[dict], AssistiveRequest]) \
    -> Callable[[dict], Awaitable[dict]]: ...
```

Returns a graph-shaped node `(state) -> state` that calls `reason()` and merges the result into
state. Imports LangGraph lazily; usable by any state-dict graph. (feature input; R8)
