# Phase 0 Research: Risk and Fraud Agent

All Technical Context unknowns are resolved below. No `NEEDS CLARIFICATION` remains.

---

## R0 — Capability id: `assess_fraud_risk` (not `assess_refund_risk`)

**Decision**: Advertise and handle the capability id **`assess_fraud_risk`** (agent id
`risk-fraud-agent`), not `assess_refund_risk`.

**Rationale**: The feature request phrased the capability as `assess_refund_risk`, but the existing
Customer Resolution Agent (003) discovers and calls the risk peer by
`config.py:RISK_CAPABILITY_ID = "assess_fraud_risk"` and `RISK_PEER_AGENT_ID = "risk-fraud-agent"`,
and the spec's FR-002 / Assumptions reference the same `assess_fraud_risk` id. SC-009 requires the
consumer to keep working with **no changes**. Keeping the id `assess_fraud_risk` satisfies SC-009 with
zero edits to 003 and keeps the spec authoritative; `assess_refund_risk` is treated as the descriptive
intent of the same fraud-risk-assessment capability. (Confirmed with the requester during planning.)

**Alternatives considered**:
- *Rename to `assess_refund_risk` and edit 003's `RISK_CAPABILITY_ID`*: cleaner name but mutates the
  prior feature, so SC-009's "consumer unchanged" no longer holds literally. Rejected.
- *Advertise both ids (alias handler)*: honors the new name and keeps SC-009, but adds a second
  capability/handler with no behavioral benefit for the PoC. Rejected as unnecessary complexity
  (Principle V).

---

## R1 — Reasoning approach: deterministic rules engine (LLM deferred)

**Decision**: Map risk/fraud signals to a risk level with a **pure deterministic rule-based scoring
engine**. No LLM, Bedrock, or `boto3` is introduced.

**Rationale**: FR-012 requires identical signals under the same policy to yield the same verdict, and
the constitution mandates idempotency/determinism and PoC-scope discipline. The spec Assumptions
explicitly permit either a rule-based or LLM-assisted approach so long as determinism holds, and the
externally observable behavior is unchanged. The `003` decision engine and the `004` billing rules
engine already established a deterministic pattern; matching it keeps the demo consistent and the
verdict reproducible and auditable without prompt-caching or model wiring. The codebase currently has
no LLM dependency.

**Alternatives considered**:
- *LLM reasoning step (Bedrock)*: defers cleanly to a future iteration; would require deterministic
  guards/caching to satisfy FR-012 and adds a dependency with no PoC benefit now. Deferred.
- *Hybrid (LLM drafts reasoning summary, rules decide)*: still adds a dependency; the reasoning
  summary is adequately generated from the fired rules. Deferred.

---

## R2 — Publishing the domain result event from a reused runtime

**Decision**: The agent **owns a domain `Publisher`** created in its async entrypoint
(`async with Publisher(identity, BROKER_URL) as domain_pub`) and registers a handler **closure that
captures it**. Inside the handler, after scoring risk, the agent calls
`domain_pub.publish(payload, event_type=TOPIC_RISK_RESULT, correlation_id=<case_id>,
causation_id=<task_id>)`. The runtime is reused **unchanged**, mirroring `004`.

**Rationale**: `AgentRuntime`'s handler signature is `(TaskRequest) -> A2AMessage` and exposes neither
a publisher nor the request envelope (it only returns the A2A output, which the runtime wraps as
`TaskResult` on `TOPIC_TASK_RESULT`). FR-008 requires a **second** delivery path — a published
`risk.review.completed` event. Changing the generic `001`/`002` runtime to thread a publisher/envelope
into handlers would broaden the shared contract for a single agent's need (Principle V). The
`003`/`004` agents already demonstrate the simpler pattern: an agent owns its own `Publisher` for
domain events.

**Correlation source**: the published event must carry `correlation_id == the originating case's
correlation id` so `003`'s `risk_result_handler` (keyed by `envelope.correlation_id`) matches the
case. The requester sets the request input field **`case_id` equal to that correlation id** (confirmed
in `apps/agents/customer_resolution/models.py:build_risk_request_input`, which passes
`case_id=case.correlation_id`). The handler reads `case_id` from the validated input and uses it as the
publish `correlation_id`.

**Entrypoint**: use a small async `main` for this agent (as `004` does) instead of the shared
`run_agent`, so the domain `Publisher` shares the same event loop and lifetime as
`runtime.serve(stop_event)`. Signal handling mirrors `apps/agents/common.py`.

**Alternatives considered**:
- *Lazy singleton publisher inside the handler*: works without an entrypoint change but lacks clean
  startup/shutdown and hides lifecycle; the explicit `async with` entrypoint is clearer. Rejected.
- *Extend the runtime to pass a context (publisher+envelope) to handlers*: more general but mutates
  the shared `001`/`002` contract and the stub handler signatures for one feature's need. Rejected on
  Principle V.

---

## R3 — Owned risk/fraud signals: in-process seeded fixtures + lookup by customer_id

**Decision**: Risk/fraud signals live in an **in-process seeded dataset** (`mock_data.py`) the agent
owns, bundling the five signal domains per customer: **account standing**, **refund/dispute history**,
**payment-instrument signal**, **behavioral/velocity signal**, and **known-fraud indicator**. Lookup
is **by `customer_id`** (the request carries `customer_id`, `case_id`, `ticket_id`,
`requested_refund_amount`, `customer_message_summary` — and, unlike billing, **no
`purchase_reference`**, so the customer is the natural risk subject). A lookup miss yields the
**missing-data path** (FR-010): `requires_human_review` with a recorded reason, never a fabricated
verdict.

**Rationale**: PoC scope (spec Assumption) — no real fraud system. A keyed fixture is sufficient to
exercise every policy branch and is fully deterministic. `customer_id` is the natural key because risk
attaches to the account/customer, and the consumer-supplied risk input is customer-centric (confirmed
in `RiskAnalysisRequestInput`: `case_id, ticket_id, customer_id, requested_refund_amount,
customer_message_summary`).

**Seed coverage** (drives the SC-004 single-signal matrix and SC-005 fault cases):
- clean account: long tenure, good standing, no chargebacks, low velocity, matched instrument, not on
  blocklist → **low**
- prior chargeback(s) above the policy threshold (otherwise clean) → **elevated/high**
- high refund/dispute velocity in window (otherwise clean) → **elevated/high**
- mismatched / card-testing payment instrument (otherwise clean) → **elevated**
- behavioral/velocity anomaly vs. normal (otherwise clean) → **elevated**
- known-fraud indicator / blocklist match → **high** (hard floor; appears as decisive evidence)
- contradictory (long-tenured good-standing account **and** a sudden high-velocity refund burst on a
  mismatched instrument) → **elevated with lowered confidence + `requires_human_review`** (never
  silently cleared, spec edge "contradictory signals")
- unknown `customer_id` → **requires_human_review** (missing data, spec edge "missing risk signals")

**Alternatives considered**: SQLite/JSON file fixtures — unnecessary I/O and setup for a PoC; an
in-process dict is simpler and equally deterministic. Rejected.

---

## R4 — Fraud policy: named, citable, deterministic rules

**Decision**: A small, named ruleset (`policy.py`, `poc-fraud-policy` v1.0.0) with documented
thresholds and a fixed evaluation order, each rule carrying a stable **policy reference id** cited in
evidence. Full detail in [`contracts/fraud-policy.md`](./contracts/fraud-policy.md). Summary:

| Rule id | Name | Effect |
|---------|------|--------|
| `FP-001` | known-fraud-indicator | Blocklist match forces **high** (hard floor) and is recorded as decisive evidence — never silently ignored. |
| `FP-002` | chargeback-history | Prior chargebacks at/above `CHARGEBACK_HIGH`/`CHARGEBACK_ELEVATED` push risk up. |
| `FP-003` | refund-velocity | Refund/dispute count in window at/above `VELOCITY_HIGH`/`VELOCITY_ELEVATED` push risk up. |
| `FP-004` | instrument-mismatch | Mismatched billing details / card-testing pattern push risk up (elevated). |
| `FP-005` | account-standing | New / poor-standing account adds risk; long-tenured good standing sets a low baseline. |
| `FP-006` | behavioral-anomaly | Velocity/behavior anomaly vs. normal pushes risk up (elevated). |

**Evaluation order (deterministic)**: (1) data-completeness gate → human review on missing signals;
(2) known-fraud-indicator gate (FP-001) → **high** + decisive evidence; (3) contradiction gate →
elevated + lowered confidence + human review; (4) rule-based scoring across FP-002..FP-006 → cumulative
score → level via thresholds; (5) **no applicable rule fired and signals all clean → low**, but **no
signals resolvable to any rule → human review** (FR edge "no applicable policy" takes a defined default
stance, never clearing by omission).

**Scoring → level mapping**: each fired rule contributes deterministic points; the cumulative score
maps to a level by fixed thresholds `ELEVATED_THRESHOLD` (0.5) and `HIGH_THRESHOLD` (0.8) — consistent
with the consumer's own `_risk_level_from_score(score, 0.5, 0.8)`. FP-001 (known indicator) bypasses
scoring and forces `high`.

**Borderline resolution**: a score landing **exactly** on a threshold resolves **upward** to the
higher band (documented inclusive-upper boundary) and is recorded in the reasoning — never left
undecided (spec edge "borderline within policy thresholds").

**Rationale**: Illustrative PoC values chosen to be auditable and to drive distinct outcomes (spec
Assumption). Stable ids make the result event's policy references meaningful (FR-005). Thresholds align
with the consumer's existing risk bands so the verdict normalizes cleanly (R5).

**Alternatives considered**: a single decisive-rule precedence (as billing uses) — risk is naturally
*cumulative* (several weak signals together justify elevation), so additive scoring with a hard
known-indicator floor is more faithful and still fully deterministic. A continuous/probabilistic model
adds tuning with no PoC value. Rejected.

---

## R5 — Risk-level vocabulary & consumer compatibility

**Decision**: The verdict level is `risk_level ∈ {"low", "elevated", "high"}` (the spec's minimum set,
FR-004), plus a `requires_human_review` boolean. The published payload's `recommendation` field is set
to the **risk level string** (`"low"` / `"elevated"` / `"high"`).

**Rationale**: must be consumable by `003` **without contract change** (FR-019). The resolution agent's
`normalize_risk_result` / `risk_result_handler` map `recommendation`: `low|approve|acceptable → low`,
`elevated → elevated`, `high|deny|block → high`, else score-based via `confidence`; and route
`requires_human_review=True` (or any `elevated`/`high`) to escalation. Emitting the level string
directly hits the exact branch and trips the escalation path for elevated/high — both consistent with
the fraud verdict. Verified against `apps/agents/customer_resolution/event_handlers.py`
(`normalize_risk_result`, `risk_result_handler`).

**Alternatives considered**: emitting `"acceptable"`/`"block"` synonyms — handled by the consumer but
less clear than the canonical `low`/`elevated`/`high`. Rejected.

---

## R6 — Confidence scoring (bounded, lowered on uncertainty)

**Decision**: Confidence is a deterministic function of the fired rule path, on `[0.0, 1.0]` (matches
`RiskReviewCompletedPayload.confidence` `ge=0, le=1`): known-indicator high → **0.95**; clear
low/elevated/high with all signals present & consistent → **0.9**; borderline (score on a threshold) →
**0.6**; contradiction → **0.3**; missing/unresolvable signals (human review) → **0.2**. Values are
fixed per path, not random, preserving FR-012 determinism.

**Note on the consumer's score mapping**: when `recommendation` is one of `low/elevated/high` the
consumer uses that level directly and only reads `confidence` as the surfaced score, so confidence
doubling as the "score" does not change the normalized level. The level always comes from the explicit
`recommendation` string (R5).

**Rationale**: FR-006 requires a bounded confidence that is *present, in range, and lowered on
uncertainty/contradiction*; the exact computation is a planning detail (spec Assumption). A fixed
per-path mapping is the simplest scheme satisfying all of these and mirrors `004` R6.

**Alternatives considered**: probabilistic/continuous confidence — adds tuning with no PoC value.
Rejected.

---

## R7 — Idempotency & determinism boundary

**Decision**: Rely on the runtime's `IdempotencyTracker` keyed by `task_id`: a redelivered request is
skipped (audited `duplicate_skipped`) **before** the handler runs, so there is no second assessment and
**no duplicate domain result event** (FR-013). Determinism of signals→verdict (R1/R4) guarantees that
even an independent re-assessment with the same signals produces the same verdict (FR-012).

**Known gap (documented, PoC-acceptable)**: the runtime marks a task processed **after** the handler
returns. If the process crashes between the domain publish and `mark_processed`, a redelivery could
re-run and re-publish. This matches the runtime's existing at-least-once posture and is out of scope
(consistent with `002`/`003`/`004` liveness deferral). Consumers tolerate it via per-case idempotency
(R8).

---

## R8 — Dual-path delivery interaction with the `003` consumer

**Decision**: Publishing on **both** `TOPIC_TASK_RESULT` (via the runtime) and `TOPIC_RISK_RESULT` (via
the domain publisher) is safe. `003` registers a handler on each (`result_handler` and
`risk_result_handler`), but its state store's per-slot `apply_result` (`AttachOutcome`), the immediate
elevated/high-risk escalation guard, and the `DECIDED`/terminal guards ensure the risk finding is
attached/escalated once and exactly **one** decision is emitted per case; the later of the two
deliveries is recorded, not re-applied.

**Rationale**: FR-008 requires both paths; the consumer is already built to dedup. Verified in
`event_handlers.py` (`result_handler` + `risk_result_handler` both gate on case status). This is
exercised by the SC-009 end-to-end test.

**Alternatives considered**: publishing only the domain event (dropping the A2A output) — violates
FR-008's "returned to the requesting peer correlated to its request" and breaks the generic A2A result
path. Rejected.

---

## R9 — AgentCore CLI local development parity (mirror 004)

**Decision**: Provide the same AgentCore footprint `004` ships: an `agentcore/` project-config folder
(`agentcore.json`, `aws-targets.json`, `.env.local`, `README.md`) whose project root is
`apps/agents/risk_fraud/`, and an `app/RiskFraud/` code package (`main.py` calling
`serve_a2a(RiskFraudExecutor(), CARD)`, plus `pyproject.toml` + `README.md`). Add a hand-rolled
`http_app.py` (FastAPI) and `dev_a2a_client.py` for a CLI-free local path. `agentcore dev` builds a
dev venv from `app/RiskFraud/pyproject.toml`, serves the A2A card + protocol endpoints, and opens the
AgentCore inspector UI.

**Rationale**: The operational requirement is to run under `agentcore dev` and inspect in the
AgentCore UI. AgentCore's A2A is the standard `a2a-sdk` wire protocol (JSON-RPC
`message/send`/`message/stream`), **distinct** from this repo's internal A2A-over-Kafka runtime
(feature 002). The AgentCore entrypoint is a thin shell that **reuses `service.assess` unchanged** and
adapts I/O; the monorepo (`apps/`, `packages/`, `src/`) is put on `sys.path` from source so the dev
venv only needs `bedrock-agentcore[a2a]`, `a2a-sdk[all]`, `pydantic`, `structlog` — all already used by
`004`, so **no new repo dependency**. The AgentCore path is standalone and does **not** publish the
`risk.review.completed` event (US2 publication stays the Kafka entrypoint's job); both paths share the
identical card via `identity.py`.

**Alternatives considered**:
- *Only the Kafka entrypoint (no AgentCore)*: fails the explicit `agentcore dev` / inspector
  requirement. Rejected.
- *Vendor the monorepo into `codeLocation` now (for `agentcore deploy`)*: out of scope for local run;
  `agentcore deploy` (CodeZip) packaging is deferred exactly as in `004`. Documented, not built.

---

## Resolved Technical Context

| Unknown | Resolution |
|---------|-----------|
| Capability id (`assess_refund_risk` vs existing) | `assess_fraud_risk` (agent `risk-fraud-agent`) — keeps SC-009, matches spec (R0) |
| Reasoning mechanism | Deterministic rule-based scoring; no LLM/Bedrock (R1) |
| How the domain event is published from a `(TaskRequest)->A2AMessage` handler | Handler-owned `Publisher` captured in an async entrypoint; runtime reused as-is (R2) |
| Where risk signals come from | In-process seeded fixtures keyed by `customer_id` (R3) |
| Fraud policy & thresholds | Named ruleset `FP-001..FP-006`, fixed precedence, additive scoring, known-indicator floor, documented borderline side (R4) |
| Risk-level values & consumer fit | low/elevated/high emitted as `recommendation`; compatible with `003` normalizer (R5) |
| Confidence scheme | Fixed per-path value on `[0,1]`, lowered on uncertainty/contradiction (R6) |
| Idempotency | Runtime `task_id` dedup before handler; deterministic verdict; documented crash-window gap (R7) |
| Consumer double-delivery | Tolerated by `003` per-case idempotency + escalation guard (R8) |
| AgentCore CLI local dev | Mirror `004`: `agentcore/` config + `app/RiskFraud/` serve_a2a shell + http_app; no new dependency (R9) |
