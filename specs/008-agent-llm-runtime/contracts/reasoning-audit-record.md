# Contract: Reasoning Audit Record

Every `reason()` call emits exactly one reasoning audit step through the **existing** audit subsystem
(`agent_foundation.audit.store.write_audit`), on the **existing** `agent.audit.v1` topic. No new
topic or event contract is introduced (FR-015). The record is an `AuditPayload` whose
`outcome`/`reason` encode the reasoning step, plus the structured `ReasoningAuditRecord` fields
(data-model.md §10) carried in the payload.

## Required fields (FR-011/012)

- `agent_id` — calling agent (attribution).
- `correlation_id` — case identity; the query key.
- `causation_id` — the triggering step (causal order in the case trace).
- `task_kind`, `model_id`, `model_params` — what was asked and with what model/params.
- `prompt_ref` + `grounding_digest` — enough to reconstruct what the model was asked, **without a
  live model session**.
- `reasoning_path` (`model` | `cache` | `fallback`) + `outcome`
  (`produced` | `served_from_cache` | `fallback` | `unable_to_produce`) + `failure_reason`.
- `result_summary` — the validated result (or its summary).
- `token_usage`, `cache_hit` — usage tracking + prompt-cache observability (US7, SC-008).
- `latency_ms`, `recorded_at`.

## Query & reconstructability

- Retrievable via `audit.store.query_by_correlation(bootstrap_servers, correlation_id)` in causal
  order alongside the rest of the case (SC-005: under 30s, single documented query, no live model).
- The reasoning step MUST be **distinguishable from the binding decision** record: a reviewer can see
  which steps were assistive (this record) and that the binding verdict came from the deterministic
  engine (FR-012, US2.3, SC-002).

## Guarantees

- **One record per call** — including cache replays (records `served_from_cache`) and fallbacks
  (records the `failure_reason`). (US4.3, US5.3, US6.2)
- **Immutable & correlated** — appended to the audit topic, never mutated.
- **Model-free reconstruction** — `prompt_ref` + `grounding_digest` + `model_params` let a reviewer
  see what was asked without invoking the model. (FR-012, US6.3)
