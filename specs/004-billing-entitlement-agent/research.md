# Phase 0 Research: Billing and Entitlement Agent

All Technical Context unknowns are resolved below. No `NEEDS CLARIFICATION` remains.

---

## R1 — Reasoning approach: deterministic rules engine (LLM deferred)

**Decision**: Map billing facts to a recommendation with a **pure deterministic rules engine**. No
LLM, Bedrock, or `boto3` is introduced.

**Rationale**: FR-012 requires identical facts under the same policy to yield the same verdict, and
the constitution mandates idempotency/determinism and PoC-scope discipline. The spec Assumptions
explicitly permit either a rule-based or LLM-assisted approach so long as determinism holds, and the
externally observable behavior is unchanged. The `003` agent already established a deterministic
decision engine; matching that keeps the demo consistent and the verdict reproducible and auditable
without prompt-caching or model wiring. The codebase currently has no LLM dependency.

**Alternatives considered**:
- *LLM reasoning step (Bedrock)*: defers cleanly to a future iteration; would require deterministic
  guards/caching to satisfy FR-012 and adds a dependency with no PoC benefit now. Deferred.
- *Hybrid (LLM drafts reasoning summary, rules decide)*: still adds a dependency; the reasoning
  summary is adequately generated from the fired rules. Deferred.

---

## R2 — Publishing the domain result event from a reused runtime

**Decision**: The agent **owns a domain `Publisher`** created in its async entrypoint
(`async with Publisher(identity, BROKER_URL) as domain_pub`) and registers a handler **closure that
captures it**. Inside the handler, after evaluating eligibility, the agent calls
`domain_pub.publish(payload, event_type=TOPIC_BILLING_RESULT, correlation_id=<case_id>,
causation_id=<task_id-derived>)`. The runtime is reused **unchanged**.

**Rationale**: `AgentRuntime`'s handler signature is `(TaskRequest) -> A2AMessage` and exposes
neither a publisher nor the request envelope (it only returns the A2A output, which the runtime wraps
as `TaskResult` on `TOPIC_TASK_RESULT`). FR-008 requires a **second** delivery path — a published
`billing.refund-analysis.completed` event. Changing the generic `001`/`002` runtime to thread a
publisher/envelope into handlers would broaden the shared contract for a single agent's need
(Principle V). The `003` resolution agent already demonstrates the simpler pattern: an agent owns its
own `Publisher` for domain events. `Publisher` is a standalone async context manager
(`transport/publisher.py`), so the billing agent opens one for the process lifetime and the handler
publishes through it.

**Correlation source**: the published event must carry `correlation_id == the originating case's
correlation id` so `003`'s `billing_result_handler` (keyed by `envelope.correlation_id`) matches the
case. The requester sets the request input field **`case_id` equal to that correlation id**
(confirmed in `apps/agents/customer_resolution/models.py:build_billing_request_input`, which passes
`case_id=case.correlation_id`). The handler reads `case_id` from the validated input and uses it as
the publish `correlation_id`.

**Entrypoint**: use a small async `main` for this agent instead of the shared `run_agent` (which owns
the loop and creates only the runtime's internal publisher), so the domain `Publisher` shares the same
event loop and lifetime as `runtime.serve(stop_event)`. Signal handling mirrors `apps/agents/common.py`.

**Alternatives considered**:
- *Lazy singleton publisher inside the handler*: works without an entrypoint change but lacks clean
  startup/shutdown and hides lifecycle; the explicit `async with` entrypoint is clearer. Rejected.
- *Extend the runtime to pass a context (publisher+envelope) to handlers*: more general but mutates
  the shared `001`/`002` contract and the echo/stub handler signatures for one feature's need.
  Rejected on Principle V.

---

## R3 — Owned billing facts: in-process seeded fixtures + lookup

**Decision**: Billing facts live in an **in-process seeded dataset** (`mock_data.py`) the agent owns,
bundling the five domains (subscription, invoice, payment, entitlement, product usage) per case.
Lookup is **by `purchase_reference`** (the invoice/charge the refund claim targets), falling back to
`customer_id`. A lookup miss yields the **missing-data path** (FR-010): `requires_human_review` with a
recorded reason, never a fabricated verdict.

**Rationale**: PoC scope (spec Assumption) — no real billing system. A keyed fixture is sufficient to
exercise every policy branch and is fully deterministic. `purchase_reference` is the natural key
because the request carries it and a refund targets a specific charge.

**Seed coverage** (drives the SC-004 single-fact matrix and SC-005 fault cases):
- within-window + paid + entitlement-not-delivered + light usage → **approve**
- outside-window (otherwise identical) → **deny**
- unpaid / no captured payment → **deny** (nothing to refund)
- already-fully-reversed payment → **deny** (already refunded)
- heavy product usage above threshold → **deny** (or partial, policy-configurable)
- contradictory (active entitlement on cancelled subscription; paid invoice + recorded full reversal)
  → **requires_human_review** with lowered confidence
- unknown `purchase_reference` → **requires_human_review** (missing data)

**Alternatives considered**: SQLite/JSON file fixtures — unnecessary I/O and setup for a PoC; an
in-process dict is simpler and equally deterministic. Rejected.

---

## R4 — Refund policy: named, citable, deterministic rules

**Decision**: A small, named ruleset (`policy.py`) with documented thresholds and a fixed evaluation
order, each rule carrying a stable **policy reference id** cited in evidence. Full detail in
[`contracts/refund-policy.md`](./contracts/refund-policy.md). Summary:

| Rule id | Name | Effect |
|---------|------|--------|
| `RP-001` | refund-window | Refund only if invoice issued within `REFUND_WINDOW_DAYS` (30) of the request; else deny. |
| `RP-002` | paid-invoice | Requires a captured payment and no prior full reversal; unpaid → deny; already reversed → deny. |
| `RP-003` | entitlement-delivered | Fully-delivered entitlement weakens/denies; not-yet-delivered supports approve. |
| `RP-004` | usage-threshold | Usage at/above `USAGE_HEAVY_THRESHOLD` materially weakens the claim → deny (or partial). |
| `RP-005` | subscription-status | Cancelled-within-window supports refund; active heavy-usage weakens. |

**Evaluation order (deterministic)**: (1) data-completeness gate → human review on missing;
(2) contradiction gate → human review + lowered confidence; (3) hard denials (RP-001 window,
RP-002 unpaid/reversed); (4) usage gate (RP-004); (5) approve when within-window + paid +
entitlement-not-delivered + light usage; (6) **no applicable rule → human review** (FR edge:
"no applicable policy" takes a defined default stance, never approve-by-omission).

**Borderline resolution**: boundaries resolve to a **documented inclusive side** and are recorded in
the reasoning — exactly day `REFUND_WINDOW_DAYS` counts as *within* the window; usage exactly at the
threshold counts as *below* (claim not yet materially weakened). Never left undecided
(spec edge "borderline within policy thresholds").

**Rationale**: Illustrative PoC values chosen to be auditable and to drive distinct outcomes
(spec Assumption). Stable ids make the result event's `policy references` meaningful (FR-005).

**Alternatives considered**: weighted scoring across all rules — harder to explain and to cite a
single decisive rule; a fixed precedence is more auditable for a PoC. Rejected.

---

## R5 — Recommendation vocabulary & consumer compatibility

**Decision**: `recommendation ∈ {"approve", "deny", "requires_human_review"}` (the spec's minimum
outcome set, FR-004), with `"partial_refund"` available as an optional policy outcome. The
`requires_human_review` boolean flag on the payload is set `True` whenever the recommendation is
`requires_human_review` (and may also accompany a low-confidence approve/deny per FR edge cases).

**Rationale**: must be consumable by `003` **without contract change** (FR-019). The resolution
agent's `normalize_billing_result` / `billing_result_handler` map: `approve|eligible|refund →
eligible`, `deny|ineligible|reject → ineligible`, `partial_refund → partial`, else `→ indeterminate`;
and route `requires_human_review=True` to escalation. So `"requires_human_review"` maps to
`indeterminate` *and* trips the escalate path — both consistent with "needs human review." Verified
against `apps/agents/customer_resolution/event_handlers.py`.

**Alternatives considered**: emitting `"escalate"`/`"unknown"` — not in the consumer's known map and
no clearer than `requires_human_review`. Rejected.

---

## R6 — Confidence scoring (bounded, lowered on uncertainty)

**Decision**: Confidence is a deterministic function of the fired rule path, on `[0.0, 1.0]`
(matches `BillingRefundAnalysisCompletedPayload.confidence` `ge=0, le=1`): clear approve/deny with all
facts present & consistent → **0.9**; borderline (on a policy boundary) → **0.6**; contradiction →
**0.3**; missing/unresolvable data (human review) → **0.2**. Values are fixed per path, not random,
preserving FR-012 determinism.

**Rationale**: FR-006 requires a bounded confidence that is *present, in range, and lowered on
uncertainty/contradiction*; the exact computation is a planning detail (spec Assumption). A fixed
per-path mapping is the simplest scheme satisfying all of these.

**Alternatives considered**: probabilistic/continuous confidence — adds tuning with no PoC value.
Rejected.

---

## R7 — Idempotency & determinism boundary

**Decision**: Rely on the runtime's `IdempotencyTracker` keyed by `task_id`: a redelivered request is
skipped (audited `duplicate_skipped`) **before** the handler runs, so there is no second analysis and
**no duplicate domain result event** (FR-013). Determinism of facts→verdict (R1/R4) guarantees that
even an independent re-analysis with the same facts produces the same verdict (FR-012).

**Known gap (documented, PoC-acceptable)**: the runtime marks a task processed **after** the handler
returns. If the process crashes between the domain publish and `mark_processed`, a redelivery could
re-run and re-publish. This matches the runtime's existing at-least-once posture and is out of scope
(consistent with `002`/`003` liveness deferral). Consumers tolerate it via per-case idempotency (R8).

---

## R8 — Dual-path delivery interaction with the `003` consumer

**Decision**: Publishing on **both** `TOPIC_TASK_RESULT` (via the runtime) and `TOPIC_BILLING_RESULT`
(via the domain publisher) is safe. `003` registers a handler on each, but its state store's per-slot
`apply_result` (`AttachOutcome`) and `DECIDED`/terminal guards ensure the billing finding is attached
once and exactly **one** decision is emitted per case; the later of the two deliveries is recorded,
not re-applied.

**Rationale**: FR-008 requires both paths; the consumer is already built to dedup. Verified in
`event_handlers.py` (`result_handler` + `billing_result_handler` both gate on case status).
This is exercised by the SC-009 end-to-end test.

**Alternatives considered**: publishing only the domain event (dropping the A2A output) — violates
FR-008's "returned to the requesting peer correlated to its request" and breaks the generic A2A
result path. Rejected.

---

## Resolved Technical Context

| Unknown | Resolution |
|---------|-----------|
| Reasoning mechanism | Deterministic rules engine; no LLM/Bedrock (R1) |
| How the domain event is published from a `(TaskRequest)->A2AMessage` handler | Handler-owned `Publisher` captured in an async entrypoint; runtime reused as-is (R2) |
| Where billing facts come from | In-process seeded fixtures keyed by `purchase_reference` (R3) |
| Refund policy & thresholds | Named ruleset `RP-001..RP-005`, fixed precedence, documented borderline side (R4) |
| Recommendation values & consumer fit | approve/deny/requires_human_review (+optional partial_refund); compatible with `003` normalizer (R5) |
| Confidence scheme | Fixed per-path value on `[0,1]`, lowered on uncertainty (R6) |
| Idempotency | Runtime `task_id` dedup before handler; deterministic verdict; documented crash-window gap (R7) |
| Consumer double-delivery | Tolerated by `003` per-case idempotency (R8) |
