# Contract: Evaluation Scores

Covers the "evaluations" half of the steering input (R7). All scores are **non-binding**: write-only
observability that never re-enters any decision path (assistive-only boundary from 008 + constitution).

## Layer 1 — Programmatic scores (always on when observability is on)

Module: `observability/scores.py`, called from the `reason()` wrap.

### `emit_scores(result: AssistiveResult) -> None`

| Score name | Value | Source |
|------------|-------|--------|
| `schema_valid` | `1`/`0` | output passed the validate-and-repair loop |
| `used_fallback` | `1`/`0` | result came from the agent's pre-LLM fallback |
| `cache_hit` | `1`/`0` | `AssistiveResult.cache_hit` |
| `latency_ms` | float ≥ 0 | `AssistiveResult.latency_ms` |

- Attached to the current generation/trace via `score()` (observability-api.md).
- Emitted for **every** run, including offline stub runs, giving CI a quality/health signal.
- Best-effort: a scoring failure never affects `reason()`.

## Layer 2 — LLM-as-judge (opt-in, UI-configured)

- A small seeded **dataset** of representative assistive tasks (e.g., classify samples, draft prompts,
  summary inputs) is created in LangFuse (documented script / quickstart step).
- LLM-as-judge evaluators (e.g., draft faithfulness/tone, summary grounding) are configured in the
  LangFuse UI to run over new traces and/or the dataset.
- Output scores appear alongside Layer-1 scores on the same traces.

## Invariants

- **No score is read by agent code.** Grep target for review: no import of `observability.scores`
  outside the runtime emit path; no agent reads a LangFuse score.
- Eval results never alter a binding refund outcome or any agent verdict.
- Layer 2 is optional; the default offline suite relies only on Layer 1.

## LangFuse Dashboard Derivations (T038)

Per-agent metrics are derived from LangFuse span/generation data grouped by the `agent_id`
metadata attribute. The following panels are available out of the box:

| Panel | Source | Group by |
|-------|--------|----------|
| Request count | span count | `agent_id` |
| Latency p50/p95/p99 | span duration | `agent_id` |
| Error rate | spans with `level=ERROR` / total | `agent_id` |
| LLM call count | generation count | `agent_id` |
| Token usage (input/output) | `usage.input` / `usage.output` | `agent_id` |
| Cache hit rate | generations where `metadata.cache_hit=true` / total | `agent_id` |
| LLM latency | generation `metadata.latency_ms` | `agent_id` |
| Estimated cost | generation `cost_details.total` | `agent_id` |

All panels are configured in the LangFuse UI; no code changes are required to add or modify them.
