---
description: "Task list for feature: Agent LLM Runtime"
---

# Tasks: Agent LLM Runtime

**Input**: Design documents from `/specs/008-agent-llm-runtime/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Unit tests are included where acceptance criteria are directly testable (repo convention: `tests/unit/llm/`).

**Organization**: Tasks are grouped by user story / capability slice to enable independent implementation and testing. This file is co-authored by parallel sessions; each slice owns a far-ahead task-ID block to avoid collisions.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story / slice this task belongs to (e.g., US1, LG)
- Include exact file paths in descriptions

## Path Conventions

- Single Python project: `src/agent_foundation/llm/` (runtime), `apps/agents/*` (adoption), `tests/unit/llm/` (tests)

<!-- SLICE:langgraph-compat-helper -->
---

## Phase LG: LangGraph Compatibility Helper (feature input; research R8)

**Goal**: Provide `create_langgraph_llm_node(agent_id, prompt_template, output_schema=None)` — an ergonomic factory that returns a graph-shaped node callable wrapping `LLMRuntime.reason()`, so graph-based agents can invoke the assistive runtime as a node without coupling the core to LangGraph.

**Independent Test**: Build a node from the factory, run it against a plain `state: dict` (no LangGraph installed): a structured call (schema given) and an unstructured call (`output_schema=None`) both return state carrying a schema-validated `AssistiveResult`; correlation/causation trace metadata from state is preserved into the emitted `ReasoningAuditRecord`; the factory returns only a node callable and constructs no graph.

**Acceptance criteria covered** (from feature input): usable inside LangGraph nodes; supports structured and unstructured calls; preserves trace metadata; does not own graph orchestration.

**Prerequisite (owned by other slices)**: core runtime must exist — `src/agent_foundation/llm/request.py` (`AssistiveRequest`, `TaskKind`), `src/agent_foundation/llm/result.py` (`AssistiveResult`, `ReasoningPath`, `TokenUsage`), `src/agent_foundation/llm/runtime.py` (`LLMRuntime.reason`), `src/agent_foundation/llm/config.py` (`resolve_profile`), and the existing `as_node()` adapter in `src/agent_foundation/llm/langgraph.py`.

### Implementation for LangGraph Helper

- [X] T960 [LG] Add an unstructured-output schema `TextResult` (single `text: str` field, frozen Pydantic v2 model) in `src/agent_foundation/llm/result.py`, used as the default `output_schema` when callers pass `output_schema=None`, so unstructured calls still return a schema-validated `AssistiveResult.value` (guarantee G1, FR-005).
- [X] T961 [LG] Implement `create_langgraph_llm_node(agent_id, prompt_template, output_schema=None)` in `src/agent_foundation/llm/langgraph.py`, returning an async node callable `(state: dict) -> dict`; build it on top of the existing `as_node()` / `LLMRuntime.reason()` rather than duplicating the runtime flow (FR-001, FR-016).
- [X] T962 [LG] In `create_langgraph_llm_node` (`src/agent_foundation/llm/langgraph.py`), map graph `state` to an `AssistiveRequest`: render `prompt_template` against `state` for `instructions`, take `grounding_inputs` from `state`, set `agent_id`, derive `task_kind` (default `summarize_reasoning`, structured callers may override), derive `idempotency_key`, and supply a default `fallback` (FR-007, data-model §1).
- [X] T963 [LG] Support structured vs unstructured calls in `src/agent_foundation/llm/langgraph.py`: when `output_schema` is provided use it as the request `output_schema` (structured); when `None`, use `TextResult` from T960 (unstructured free-text). Both return a schema-validated `AssistiveResult` (acceptance: structured + unstructured).
- [X] T964 [LG] Preserve trace metadata in `src/agent_foundation/llm/langgraph.py`: read `correlation_id`/`causation_id` from `state` and thread them into the `AssistiveRequest`; merge `reasoning_path`, `token_usage`, `model_id`, `cache_hit`, `latency_ms`, and the result `value` back into a namespaced key of the returned state without mutating the input dict in place (acceptance: preserves trace metadata; FR-010/011).
- [X] T965 [LG] Enforce the no-orchestration boundary in `src/agent_foundation/llm/langgraph.py`: the factory MUST return only a single node callable — it must not build graphs, edges, routing, or instantiate `LLMRuntime` internally (accept the runtime via closure/arg); import `langgraph` lazily and only if actually present so the callable also works on a plain state dict. Document this in the function docstring (acceptance: does not own graph orchestration; FR-015).
- [X] T966 [P] [LG] Export `create_langgraph_llm_node` (alongside `as_node`) from `src/agent_foundation/llm/__init__.py` public surface (depends on T961).

### Tests for LangGraph Helper

- [X] T967 [P] [LG] Unit test: structured call returns the caller schema instance in state, in `tests/unit/llm/test_langgraph_node.py` (stub-backed, offline).
- [X] T968 [P] [LG] Unit test: unstructured call (`output_schema=None`) returns a `TextResult` free-text value in state, in `tests/unit/llm/test_langgraph_node.py`.
- [X] T969 [P] [LG] Unit test: trace metadata — `correlation_id`/`causation_id` from state flow into the emitted `ReasoningAuditRecord` and `reasoning_path`/`token_usage` are merged into returned state, in `tests/unit/llm/test_langgraph_node.py`.
- [X] T970 [P] [LG] Unit test: no-orchestration — factory returns a plain callable that runs against a state dict with LangGraph not importable (monkeypatch import), and builds no graph object, in `tests/unit/llm/test_langgraph_node.py`.
- [X] T971 [P] [LG] Unit test: fallback path — when the provider is forced to fail, the node merges a `fallback` `AssistiveResult` into state and never raises into the graph, in `tests/unit/llm/test_langgraph_node.py`.

### Docs for LangGraph Helper

- [X] T972 [P] [LG] Add a `create_langgraph_llm_node` usage snippet (structured + unstructured) to `specs/008-agent-llm-runtime/quickstart.md`.

**Checkpoint**: `create_langgraph_llm_node` is importable, usable inside a LangGraph node and on a bare state dict, handles structured + unstructured calls, preserves trace metadata, and owns no orchestration — all unit tests green against the stub with no AWS.

### LangGraph Helper — dependencies & parallel notes

- Sequence within slice: T960 -> T961 -> T962 -> T963 -> T964 -> T965 (T961-T965 all edit `langgraph.py`, so sequential), then T966.
- T967-T972 [P] can run together once T966 is done (T967-T971 share one test file but are independent assertions; T972 edits quickstart.md).
- This slice depends only on the core runtime prerequisite above; it has no dependency on the CRA/billing/risk adoption slices.

<!-- SLICE:llm-provider-config-models -->
---

## Phase CFG: LLM Provider Config Models (feature input; data-model §7-8, contracts/model-config.md)

**Goal**: Define the externally supplied LLM provider configuration models that select where and how
reasoning is performed (FR-017) and keep the system offline-by-default on the stub (FR-014). This slice
owns `src/agent_foundation/llm/config.py` — the `config.py` / `resolve_profile` prerequisite other
slices (e.g. LangGraph, runtime, providers) depend on. The LLM is assistive only; config never carries a
binding verdict.

**Independent Test**: Construct `BedrockModelConfig` from the example env vars
(`AWS_REGION=us-east-1`, `BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0`,
`BEDROCK_TEMPERATURE=0`, `BEDROCK_MAX_TOKENS=1024`, `BEDROCK_TIMEOUT_SECONDS=30`) and assert it
validates/round-trips; with no AWS env present, `RuntimeConfig` defaults to `mode="stub"` and
`resolve_profile(agent_id, task_kind)` returns the registered per-agent profile (env vars override it) —
all offline, no cloud access (SC-006).

**Acceptance criteria covered** (from feature input): a `LLMProvider` literal and a `BedrockModelConfig`
holding `provider`, `region`, `model_id`, `temperature`, `max_tokens`, `timeout_seconds`,
`retry_max_attempts`; config-supplied (never hard-coded at call sites); stub-default with Bedrock opt-in.

**Prerequisite (owned by other slices)**: `TaskKind` enum in `src/agent_foundation/llm/request.py`
(referenced by `resolve_profile`); if not yet present, this slice may define a minimal local `TaskKind`
import shim and the request slice reconciles it.

### Implementation for LLM Provider Config Models

- [X] T1020 [CFG] Define `LLMProvider = Literal["stub","bedrock","agentcore"]` and a frozen Pydantic v2 `BedrockModelConfig` (`provider: str`, `region: str`, `model_id: str`, `temperature: float = 0.0`, `max_tokens: int`, `timeout_seconds: int`, `retry_max_attempts: int`) in `src/agent_foundation/llm/config.py` (feature input; data-model §7; FR-002/017).
- [X] T1021 [CFG] Define the provider-agnostic `ModelProfile` (`mode: LLMProvider`, `model_id`, `region: str | None`, `temperature: float = 0.0`, `max_tokens: int`, `top_p: float | None`, `timeout_seconds: float`, `max_repairs: int`) in `src/agent_foundation/llm/config.py`, defaulting to deterministic decoding (`temperature=0.0`, R5) (data-model §7).
- [X] T1022 [CFG] Define `RuntimeConfig` in `src/agent_foundation/llm/config.py` reading `AGENT_LLM_MODE`/`AGENT_LLM_MODEL`/`AGENT_LLM_REGION`/`AGENT_LLM_TIMEOUT_SECONDS`/`AGENT_LLM_MAX_REPAIRS`/`AGENT_LLM_BOOTSTRAP_SERVERS`, defaulting to offline `mode="stub"` with no AWS required (data-model §8; FR-014; SC-006).
- [X] T1023 [CFG] Implement env loading + the profile registry in `src/agent_foundation/llm/config.py`: map the Bedrock shorthands (`AWS_REGION`, `BEDROCK_MODEL_ID`, `BEDROCK_TEMPERATURE`, `BEDROCK_MAX_TOKENS`, `BEDROCK_TIMEOUT_SECONDS`) into `BedrockModelConfig`, and implement `resolve_profile(agent_id, task_kind) -> ModelProfile` with the four registered defaults (CRA `classify` max_tokens=256, CRA `draft_response` max_tokens=512, billing/risk `summarize_reasoning` max_tokens=200) plus env overrides and a stub default — no model selection hard-coded at call sites (contracts/model-config.md; FR-017/018).

### Tests for LLM Provider Config Models

- [X] T1024 [P] [CFG] Unit test `tests/unit/llm/test_model_profiles.py` (stub-backed, offline): `BedrockModelConfig` validates/round-trips the example env vars; `RuntimeConfig` defaults to `stub` with no AWS; `resolve_profile` returns per-`(agent_id, task_kind)` profiles and honors `AGENT_LLM_*` overrides.

### Provider selection wiring

- [X] T1025 [P] [CFG] Add the config-driven `select_provider(mode: LLMProvider)` scaffold (default `stub`) in `src/agent_foundation/llm/providers/__init__.py`, dispatching on `ModelProfile.mode`; concrete stub/bedrock/agentcore providers are owned by other slices (contracts/provider-protocol.md; FR-014).

**Checkpoint**: `config.py` exposes `LLMProvider`, `BedrockModelConfig`, `ModelProfile`, `RuntimeConfig`,
and `resolve_profile`; the system resolves an offline stub profile with no AWS by default and flips to
Bedrock purely via env — unblocking the runtime/provider/LangGraph slices. All config tests green offline.

### LLM Provider Config Models — dependencies & parallel notes

- Sequence within slice: T1020 -> T1021 -> T1022 -> T1023 (all edit `config.py`, so sequential), then T1024 and T1025 [P] (different files).
- This slice has no dependency on adoption slices; the LangGraph slice (T960-T972) and the runtime/provider slices consume `resolve_profile`/`RuntimeConfig` from here.


<!-- SLICE:risk-llm-summary -->
---

## Phase RK: Risk Agent — Optional LLM Reasoning-Summary Enrichment (feature input; FR-018, SC-002)

**Scope (from this slice's input)**: Integrate the Risk & Fraud agent with the shared assistive LLM
runtime **optionally**, using the runtime for exactly two bounded, text-only tasks:
(1) **risk reasoning-summary polishing** and (2) **evidence-explanation summarization**. The core risk
score, level, and recommendation stay 100% deterministic; the LLM may only produce explanation text.

**Acceptance criteria covered** (from feature input):
- Core risk scoring remains deterministic — `scoring.assess_signals` is untouched and still owns
  `risk_level`, `recommended_action`, `confidence`, `requires_human_review`, `evidence`,
  `policy_references` (FR-003/004, SC-002).
- The LLM cannot change the risk score or recommendation — enrichment only writes narrative *text*
  fields; no binding field of `RiskAssessment` / the wire payload is ever populated from an
  `AssistiveResult` (FR-004, G2).
- LLM output is constrained to explanation text — a `RiskNarrative` output schema with only `str`
  fields, grounding-checked against the deterministic assessment so no invented facts/policy/score
  leak in; invalid output is rejected and falls back to the deterministic `reasoning_summary`
  (FR-005/006, G1).

**Independent Test**: Run `assess()` to produce a deterministic `RiskAssessment`, then call the risk
enrichment seam with the stub model: the returned wire payload carries a polished `reasoning_summary`
and an evidence explanation, while `recommendation` (= `risk_level`), `confidence`,
`requires_human_review`, and the `evidence`/`policy_references` are byte-for-byte identical to the
deterministic result — verifiable offline with no AWS. Forcing the stub to emit an adversarial
"approve/deny" or a fabricated fact leaves every binding field unchanged and degrades to the
deterministic summary.

**Prerequisite (owned by the core-runtime slice)**: the shared runtime must exist —
`src/agent_foundation/llm/request.py` (`AssistiveRequest`, `TaskKind.summarize_reasoning`),
`src/agent_foundation/llm/result.py` (`AssistiveResult`, `ReasoningPath`, `FailureReason`),
`src/agent_foundation/llm/runtime.py` (`LLMRuntime.reason`, `assist_or_fallback`),
`src/agent_foundation/llm/config.py` (`resolve_profile`). This slice consumes that surface only and
does not build it.

### Phase RK.1: Setup & Foundational (risk-scoped)

- [X] T900 [RK] Register the risk profile `("risk-fraud-agent", summarize_reasoning)` (e.g. `max_tokens=200`, `temperature=0.0`) in the runtime profile registry `src/agent_foundation/llm/config.py` so risk summarization resolves via config, not a hard-coded call site (FR-017; contracts/model-config.md). Coordinate with the core-runtime slice if that file is owned there.
- [X] T901 [P] [RK] Add a risk-scoped config flag in `apps/agents/risk_fraud/config.py`: `RISK_LLM_SUMMARY_ENABLED` (env `RISK_LLM_SUMMARY_ENABLED`, default **off/false**), so the LLM enrichment is strictly opt-in and the agent's default behavior is the existing deterministic path (FR-014, "optionally").

### Phase RK.2: US-RK1 — Optional assistive enrichment of risk narrative (Priority: P1) 🎯 MVP

**Goal**: When enabled, polish the deterministic `reasoning_summary` and summarize the evidence into a
readable explanation via the runtime, attaching both as text to the published result — without
changing any binding field.

- [X] T902 [P] [RK] [US-RK1] Add `RiskNarrative` output schema (frozen Pydantic v2) in `apps/agents/risk_fraud/llm_summary.py`: exactly two text fields — `polished_summary: str` (bounded, e.g. `max_length` ~600) and `evidence_explanation: str` (bounded, e.g. `max_length` ~800). **No** score/level/action/confidence fields — explanation text only (acceptance: output constrained to explanation text; G1).
- [X] T903 [RK] [US-RK1] Implement `_build_grounding_inputs(assessment, request)` in `apps/agents/risk_fraud/llm_summary.py` that serializes ONLY the deterministic `RiskAssessment` (risk_level, recommended_action, confidence, reasoning_summary, requires_human_review, policy_references, and evidence `source`/`description`/`value`) plus `ticket_id`/`customer_id` into a JSON-serializable dict, so the model may reason only over the deterministic result (data-model.md §1 grounding; FR-005).
- [X] T904 [RK] [US-RK1] Implement `_instructions()` in `apps/agents/risk_fraud/llm_summary.py`: a large, stable instruction block telling the model to rewrite the provided `reasoning_summary` more clearly and to summarize the listed evidence in plain language, explicitly forbidding it from changing/asserting any score, level, recommendation, or fact not present in grounding inputs (cache-eligible prefix; FR-013).
- [X] T905 [RK] [US-RK1] Implement `async enrich_assessment(runtime, assessment, request) -> RiskNarrative` in `apps/agents/risk_fraud/llm_summary.py`: build the `AssistiveRequest` (`agent_id="risk-fraud-agent"`, `task_kind=summarize_reasoning`, `correlation_id=request.case_id`, `causation_id` from the task, `instructions`, grounding from T903, `output_schema=RiskNarrative`, derived `idempotency_key`, and a `fallback` returning `RiskNarrative(polished_summary=assessment.reasoning_summary, evidence_explanation=<deterministic join of evidence descriptions>)`), call `runtime.reason()` / `assist_or_fallback`, and return `result.value` (FR-001/006; llm-runtime-api.md).
- [X] T906 [RK] [US-RK1] Add `enriched_reasoning_summary: str | None` and `evidence_explanation: str | None` as **optional** fields to `RiskReviewCompletedPayload` (`packages/contracts/events/payloads.py`) defaulting to `None`, so adopting agents/consumers that ignore them are unchanged (FR-016, additive/back-compatible). If the field cannot be added without breaking the 003 consumer contract, instead overwrite `reasoning_summary` text in T907 and skip this task — record which path was taken.
- [X] T907 [RK] [US-RK1] Wire enrichment into `apps/agents/risk_fraud/service.py` `to_result_payload()` and `build_a2a_output()`: accept an optional pre-computed `narrative: RiskNarrative | None`; when present, set the narrative/explanation **text** fields only; `recommendation` stays `str(assessment.risk_level)`, `confidence`/`requires_human_review`/`evidence`/`policy_references` stay from the deterministic `assessment` (acceptance: LLM cannot change score/recommendation; FR-004).
- [X] T908 [RK] [US-RK1] In `apps/agents/risk_fraud/main.py` handler, after `assess()`, when `RISK_LLM_SUMMARY_ENABLED` is set construct an `LLMRuntime` and `await enrich_assessment(...)`, passing the resulting narrative into `to_result_payload`/`build_a2a_output`; when disabled, call them with `narrative=None` (path unchanged). Keep the existing publish/dedup flow intact (FR-015, no new topic/event).

**Checkpoint (US-RK1)**: With `RISK_LLM_SUMMARY_ENABLED=1`, a risk assessment publishes a polished
summary + evidence explanation against the stub model, offline; the binding fields are unchanged.

### Phase RK.3: US-RK2 — Binding determinism guardrail (Priority: P1)

**Goal**: Prove the LLM can never alter the score or recommendation.

- [X] T910 [P] [RK] [US-RK2] Guardrail unit test in `apps/agents/risk_fraud/tests/test_llm_summary_guardrail.py`: stub the runtime to return an adversarial `RiskNarrative` whose text claims "approve, low risk" for a HIGH-risk (e.g. blocklist FP-001) case; assert the published payload's `recommendation`/`confidence`/`requires_human_review`/`evidence`/`policy_references` exactly equal the deterministic `assess_signals` output (SC-002, FR-004).
- [X] T911 [P] [RK] [US-RK2] Test that `enrich_assessment` never reads back into scoring: assert `assess_signals` is invoked exactly once per case and its `RiskAssessment` is not re-derived from the narrative (e.g. patch `assess_signals` and confirm enrichment does not call it), in `apps/agents/risk_fraud/tests/test_llm_summary_guardrail.py`.
- [X] T912 [P] [RK] [US-RK2] Determinism test: same input case → identical binding fields whether `RISK_LLM_SUMMARY_ENABLED` is on or off (only the text narrative may differ), in `apps/agents/risk_fraud/tests/test_llm_summary_guardrail.py`.

### Phase RK.4: US-RK3 — Explanation-text bounds & grounding (Priority: P1)

**Goal**: Whatever the model returns is constrained to the `RiskNarrative` shape and traces to the
deterministic assessment; bad output is rejected, not surfaced.

- [X] T913 [P] [RK] [US-RK3] Test out-of-schema/oversized model output is rejected by the runtime and `enrich_assessment` returns the deterministic fallback narrative (polished_summary == `assessment.reasoning_summary`), in `apps/agents/risk_fraud/tests/test_llm_summary_bounds.py` (FR-005/006, G1).
- [X] T914 [P] [RK] [US-RK3] Test hallucinated-fact rejection: a narrative asserting an order/amount/policy not present in grounding inputs is rejected/repaired and never published; the evidence list/`policy_references` are unchanged, in `apps/agents/risk_fraud/tests/test_llm_summary_bounds.py` (FR-005, US3).
- [X] T915 [P] [RK] [US-RK3] Test the LLM adds no evidence: `len(payload.evidence)` and the set of `policy_references` equal the deterministic assessment's, regardless of narrative content, in `apps/agents/risk_fraud/tests/test_llm_summary_bounds.py`.

### Phase RK.5: US-RK4 — Optional + safe degradation (Priority: P1)

**Goal**: Disabled by default; on model failure the agent proceeds on the deterministic summary.

- [X] T916 [P] [RK] [US-RK4] Test default-off: with `RISK_LLM_SUMMARY_ENABLED` unset, `main`/`service` never construct a runtime and the published payload equals today's deterministic output (narrative fields `None`/deterministic), in `apps/agents/risk_fraud/tests/test_llm_summary_optional.py` (FR-014, "optionally").
- [X] T917 [P] [RK] [US-RK4] Test forced-failure fallback: force the provider to timeout/error; `enrich_assessment` returns a `fallback`-path narrative (deterministic summary) with a recorded `failure_reason`, never raises into the handler, and the binding outcome is unaffected, in `apps/agents/risk_fraud/tests/test_llm_summary_optional.py` (FR-009, SC-004, G4).
- [X] T918 [P] [RK] [US-RK4] Test offline default: with no AWS config the enrichment completes on the stub provider with no cloud access, in `apps/agents/risk_fraud/tests/test_llm_summary_optional.py` (FR-014, SC-006, G6).

### Phase RK.6: US-RK5 — Audit & idempotent replay of the risk reasoning step (Priority: P2)

**Goal**: The risk reasoning step is audited and replay-stable.

- [X] T919 [P] [RK] [US-RK5] Test the enrichment emits exactly one `ReasoningAuditRecord` attributed to `risk-fraud-agent`, with `correlation_id == case_id`, the causation link, `task_kind=summarize_reasoning`, and a `reasoning_path`, queryable by correlation id with no live model, in `apps/agents/risk_fraud/tests/test_llm_summary_audit.py` (FR-011/012, SC-005).
- [X] T920 [P] [RK] [US-RK5] Test idempotent replay: issuing the same enrichment request twice (same idempotency key) returns identical narrative text with zero second model invocations and records the replay as `cache` path, in `apps/agents/risk_fraud/tests/test_llm_summary_audit.py` (FR-007/008, SC-003, G3).

### Phase RK.7: Polish (risk slice)

- [X] T921 [P] [RK] Add a "Risk agent: optional LLM reasoning-summary enrichment" snippet (enable flag + offline stub run) to `specs/008-agent-llm-runtime/quickstart.md`.
- [X] T922 [RK] Run `ruff check`/`ruff format` and the full risk suite `pytest apps/agents/risk_fraud/tests/` to confirm all new + existing tests are green against the stub with no AWS.

**Checkpoint (risk slice)**: All risk-adoption tests green offline; binding fields provably untouched
by the LLM; enrichment is opt-in and degrades safely.

### Risk slice — dependencies & parallel notes

- Sequence within slice: T900/T901 (setup) → T902 → T903/T904 → T905 → T906 → T907 → T908. T903 and T904 are independent helpers in the same new file (write together, then T905 composes them).
- Tests T910–T920 are all `[P]` across four test files once T908 is done; T910–T912 share one file, T913–T915 another, T916–T918 another, T919–T920 another (independent assertions within each).
- Depends only on the core-runtime prerequisite above; no dependency on the CRA, billing, or LangGraph slices. `scoring.py`/`policy.py` are NOT edited by this slice.


<!-- SLICE:per-agent-model-profiles-yaml -->
---

## Phase MP: Per-Agent Model Profiles — YAML File Source (feature input; contracts/model-config.md, data-model §7-8)

**Goal**: Add a config **file** `config/model-profiles.yaml` as the editable, file-driven source of the
per-agent model-profile registry that `resolve_profile(agent_id, task_kind)` consults — a `default`
profile plus per-agent profiles (`customer-resolution-agent`, `billing-entitlement-agent`,
`risk-fraud-agent`) — so an agent's model/decoding/budgets can change without touching code, while env
vars still override YAML for local testing and a missing agent profile falls back to `default`. No model
selection is hard-coded at call sites (FR-017).

**Independent Test**: With `config/model-profiles.yaml` present, `resolve_profile("customer-resolution-agent", ...)`
returns the YAML-overridden `max_tokens=1200`; an unregistered `agent_id` returns the `default` profile;
setting `AGENT_LLM_*` env vars overrides the YAML-resolved values; with the YAML file absent the runtime
still resolves built-in defaults and runs fully offline on the stub (no AWS).

**Acceptance criteria covered** (verbatim from feature input): agents can override the default model
config; a missing agent profile falls back to the default; env vars can override YAML values for local
testing.

**Relationship to the CFG slice (T1020-T1025)**: that slice owns `src/agent_foundation/llm/config.py`
(`ModelProfile`, `RuntimeConfig`, `resolve_profile`, env-override layer, and a code-default registry).
This slice is **additive**: it supplies the YAML *file* and a *loader* (in a new module so it does not
clobber `config.py`), and adds one small, coordinated wiring task so `resolve_profile` reads the YAML
registry as the profile source with the CFG env-override layer kept on top. If CFG has not landed, T983
provides a minimal local `resolve_profile`/`ModelProfile` that CFG later reconciles.

### Implementation for Per-Agent Model Profiles (YAML)

- [X] T980 [P] [MP] Create `config/model-profiles.yaml` at repo root with a `default` profile
  (`provider: bedrock`, `region: us-east-1`, `model_id: anthropic.claude-3-5-sonnet-20241022-v2:0`,
  `temperature: 0.0`, `max_tokens: 1024`) and per-agent profiles `customer-resolution-agent`
  (`model_id` sonnet, `max_tokens: 1200`), `billing-entitlement-agent` (`model_id`
  `anthropic.claude-3-haiku-20240307-v1:0`, `max_tokens: 600`), and `risk-fraud-agent` (haiku,
  `max_tokens: 600`) — matching the feature input example and `contracts/model-config.md`.
- [X] T981 [P] [MP] Implement `load_model_profiles(path) -> dict[str, ModelProfile]` in a new module
  `src/agent_foundation/llm/profiles_yaml.py`: parse the `default` section into a base `ModelProfile`
  and each agent section into a `ModelProfile` whose unspecified fields inherit from `default` (an agent
  lists only its overrides), importing `ModelProfile` from `config.py` (data-model §7; FR-017).
- [X] T982 [MP] Implement profiles-path resolution in `src/agent_foundation/llm/profiles_yaml.py`: read
  `AGENT_LLM_PROFILES_PATH` (default `config/model-profiles.yaml`); when the file is absent return an
  empty registry so callers fall back to built-in defaults and the runtime still runs offline on the stub
  (FR-014, SC-006).
- [X] T983 [MP] Wire the YAML registry into `resolve_profile(agent_id, task_kind)` in
  `src/agent_foundation/llm/config.py`: resolve a registered agent's YAML profile, else the `default`
  profile, then apply the existing `AGENT_LLM_*` env-override layer on top (env wins over YAML). Coordinate
  with the CFG slice that owns this function (T1023); if CFG is not yet present, add a minimal
  `resolve_profile`/`ModelProfile` here for it to reconcile (acceptance: override + missing→default + env
  overrides YAML; FR-017).
- [X] T984 [P] [MP] Export `load_model_profiles` from `src/agent_foundation/llm/__init__.py` public
  surface (depends on T981).

### Tests for Per-Agent Model Profiles (YAML)

- [X] T985 [P] [MP] Unit test: a registered agent's YAML profile overrides the `default` (e.g.
  `resolve_profile("customer-resolution-agent", classify).max_tokens == 1200`), in
  `tests/unit/llm/test_model_profiles_yaml.py` (stub-backed, offline).
- [X] T986 [P] [MP] Unit test: an unregistered `agent_id` falls back to the `default` profile, in
  `tests/unit/llm/test_model_profiles_yaml.py`.
- [X] T987 [P] [MP] Unit test: `AGENT_LLM_*` env vars override the YAML-resolved profile values (e.g.
  `AGENT_LLM_MODEL` / `AGENT_LLM_TIMEOUT_SECONDS`), in `tests/unit/llm/test_model_profiles_yaml.py`.
- [X] T988 [P] [MP] Unit test: with the YAML file absent (`AGENT_LLM_PROFILES_PATH` → nonexistent),
  `resolve_profile` returns built-in defaults and the stub path runs offline with no AWS, in
  `tests/unit/llm/test_model_profiles_yaml.py`.

### Docs for Per-Agent Model Profiles (YAML)

- [X] T989 [P] [MP] Document `config/model-profiles.yaml` (default + per-agent profiles) and the
  `AGENT_LLM_PROFILES_PATH` / `AGENT_LLM_*` env overrides in `specs/008-agent-llm-runtime/quickstart.md`.

**Checkpoint**: `config/model-profiles.yaml` drives per-agent model selection through `resolve_profile`;
agents override the default, missing profiles fall back to default, env vars override YAML, and the
runtime still runs offline on the stub when the file is absent — all unit tests green with no AWS.

### Per-Agent Model Profiles (YAML) — dependencies & parallel notes

- T980 (YAML file) and T981 (`profiles_yaml.py` loader) are independent → parallel. T982 follows T981
  (same new file). T983 edits `config.py` (coordinate with CFG slice T1023), then T984 exports.
- T985–T989 [P] run together once T983/T984 are done (T985–T988 share one test file but assert
  independently; T989 edits quickstart.md).
- This slice consumes `ModelProfile`/`resolve_profile` from the CFG slice (T1020-T1025) and owns the new
  `profiles_yaml.py`, the `config/model-profiles.yaml` file, and `test_model_profiles_yaml.py`; it does
  not depend on the LangGraph or risk/CRA/billing adoption slices.

<!-- SLICE:structured-output-helper -->
---

## Phase SO: Structured Output Helper (feature input; data-model §3,§5; contracts/llm-runtime-api.md G1)

**Goal**: Provide `invoke_structured(messages=..., output_schema=TicketClassificationResult)` — a
Pydantic-schema-bounded structured-output helper that validates model output against the caller schema,
retries once on JSON/schema failure, returns a structured error on repeated failure, and never silently
accepts invalid output. This slice owns `src/agent_foundation/llm/structured.py` — the validate-and-repair
seam the runtime`'s `reason()` validate step (contract step 5) depends on. The LLM is assistive only;
this helper returns classification/extraction/draft/summary content, never a binding verdict.

**Independent Test**: Feed the helper stub output that is (a) valid -> returns the schema instance;
(b) malformed JSON / out-of-enum -> it repairs once and, on continued failure, returns a structured error
(never the invalid value). Assert exactly one retry occurs (provider invoked twice) and that an invalid
`output_schema` instance is never returned to the caller — offline, stub-backed, no AWS.

**Acceptance criteria covered** (from feature input): validates model output against schema; retries once
on JSON/schema failure; returns a structured error on repeated failure; does not silently accept invalid
output (guarantee G1, FR-005/006).

**Prerequisite (owned by other slices)**: `AssistiveResult` / `FailureReason` / `TokenUsage` in
`src/agent_foundation/llm/result.py`; `ModelProvider` / `RawCompletion` in
`src/agent_foundation/llm/providers/base.py`; `ModelProfile` / `resolve_profile` from `config.py`
(CFG slice T1020-T1025); and `LLMRuntime.reason()` in `runtime.py` for the integration task (T1105).

### Implementation for Structured Output Helper

- [X] T1100 [SO] Define the structured failure types in `src/agent_foundation/llm/structured.py`: a `StructuredError` (carrying `FailureReason.invalid_output`, `attempts`, and the accumulated parse/validation error messages) and a `StructuredOutcome` (`ok: bool`, `value: BaseModel | None`, `error: StructuredError | None`) — the explicit error surfaced on repeated failure (AC: returns structured error; FR-006).
- [X] T1101 [SO] Implement `invoke_structured(messages, output_schema, *, provider, profile, grounding_inputs=None)` in `src/agent_foundation/llm/structured.py`: invoke the provider, parse raw text -> JSON, and validate against the caller-supplied Pydantic `output_schema` via `output_schema.model_validate(...)`, returning a successful `StructuredOutcome` (AC: validates model output against schema; FR-005, G1) (depends on T1100).
- [X] T1102 [SO] Add the bounded repair/retry loop in `src/agent_foundation/llm/structured.py`: on `json.JSONDecodeError` or `pydantic.ValidationError`, re-invoke the provider once with a repair message embedding the validation error + the expected schema (default "retry once"; bounded by `profile.max_repairs`) (AC: retries once on JSON/schema failure; FR-006) (depends on T1101).
- [X] T1103 [SO] On exhausted repairs, return the `StructuredError` from T1100 (`FailureReason.invalid_output`, `attempts`, error messages) from `src/agent_foundation/llm/structured.py` and never return a partial or invalid `output_schema` instance (AC: returns structured error + does not silently accept invalid output; G1, FR-006) (depends on T1102).
- [X] T1104 [SO] Add a grounding-bounds check in `src/agent_foundation/llm/structured.py` rejecting a schema-valid result that asserts facts/values absent from `grounding_inputs` (keeps fluent-but-hallucinated output out even when it parses; R4, spec US3 acceptance 2-3) (depends on T1101).
- [X] T1105 [SO] Integrate `invoke_structured` into `LLMRuntime.reason()` in `src/agent_foundation/llm/runtime.py` (validate step): replace any inline validation, and map a returned `StructuredError` onto the fallback / `unable_to_produce` path with the `FailureReason` recorded in the `AssistiveResult` and audit record (contract step 5-7; FR-006/009) (depends on T1103).
- [X] T1106 [P] [SO] Export `invoke_structured` (and `StructuredOutcome` / `StructuredError`) from the public surface in `src/agent_foundation/llm/__init__.py` (depends on T1101).

### Tests for Structured Output Helper

- [X] T1107 [P] [SO] Unit test `tests/unit/llm/test_structured_validation.py` (stub-backed, offline): valid stub output -> `invoke_structured` returns the `TicketClassificationResult` schema instance (AC: validates against schema).
- [X] T1108 [P] [SO] Unit test in `tests/unit/llm/test_structured_validation.py`: out-of-enum / out-of-range / malformed-JSON output is repaired within one retry or, on continued failure, yields a `StructuredError` — an invalid value is never returned (AC: does not silently accept invalid output, G1).
- [X] T1109 [P] [SO] Unit test in `tests/unit/llm/test_structured_validation.py`: retry budget — exactly one repair attempt on a JSON/schema failure (assert the provider is invoked twice, no more) (AC: retries once).
- [X] T1110 [P] [SO] Unit test in `tests/unit/llm/test_structured_validation.py`: repeated failure -> a `StructuredError` with `FailureReason.invalid_output` and `attempts` recorded, and `reason()` maps it to a `fallback` / `unable_to_produce` `AssistiveResult` (AC: returns structured error on repeated failure).
- [X] T1111 [P] [SO] Unit test in `tests/unit/llm/test_structured_validation.py`: a schema-valid result asserting a fact not present in `grounding_inputs` is rejected by the grounding-bounds check (R4).

### Docs for Structured Output Helper

- [X] T1112 [P] [SO] Add an `invoke_structured` usage snippet (schema bounds + retry-once behavior) to step 3 of `specs/008-agent-llm-runtime/quickstart.md`.

**Checkpoint**: `invoke_structured` is importable, validates model output against a caller Pydantic schema,
retries exactly once on JSON/schema failure, returns a structured error on repeated failure, never surfaces
an invalid result, and is wired into `reason()`s validate step — all unit tests green against the stub with
no AWS.

### Structured Output Helper — dependencies & parallel notes

- Sequence within slice: T1100 -> T1101 -> T1102 -> T1103, with T1104 after T1101 (all edit `structured.py`, so sequential); then T1105 (edits `runtime.py`) and T1106 (edits `__init__.py`, [P]).
- T1107-T1111 [P] share one test file (`test_structured_validation.py`) but are independent assertions; T1112 edits `quickstart.md`.
- This slice consumes `resolve_profile`/`ModelProfile` from the CFG slice (T1020-T1025) and the result/provider types; it has no dependency on the CRA/billing/risk adoption slices.

<!-- SLICE:requested-test-coverage -->
---

## Phase TST: Requested Assistive-Runtime Test Coverage (user input: "Add tests") — reference map

All ten reviewer-named tests are already owned by sibling slices that landed concurrently. After the
`billing-llm-summary` slice (T1400-T1422) added the billing guardrail (T1410), there is no remaining gap,
so this slice adds **no new task** — it is the traceability map confirming each requested test exists and
where. Every listed test runs against the deterministic **stub** model, green with no AWS (SC-006).

### Requested-test coverage map

| Requested test | Owning task(s) | Slice |
|----------------|----------------|-------|
| load default model config | T1024 | CFG |
| load per-agent override | T985 / T1024 | MP / CFG |
| env vars override YAML | T987 / T1044 | MP / CFG2 |
| missing config fails clearly | T1048 | CFG2 |
| structured output parses valid JSON | T1107 | SO |
| structured output rejects invalid JSON | T1108 | SO |
| LLM audit event redacts raw prompt | T1315 / T1312 | SAF |
| Customer Resolution uses structured classification | T1306 / T1302 | CRA |
| Billing deterministic recommendation cannot be changed by LLM | T1410 | BL |
| Risk deterministic score cannot be changed by LLM | T910 | RK |

### Notes

- All ten are present as checkbox tasks in their owning slices; no duplicate is added here (this avoids
  the T104x collision the CFG2 slice already claimed).
- Determinism for billing/risk is guarded at two layers: PR-slice prompt-metadata
  (`allows_final_recommendation: false`, T1088/T1092) and the BL/RK runtime-output guardrails
  (T1410-T1413 / T910-T912) proving an adversarial assistive result never reaches a binding field.

<!-- SLICE:safety-redaction-controls -->
---

## Phase SAF: Safety & Redaction Controls (feature input; FR-011/012, contracts/reasoning-audit-record.md)

**Goal**: Add three configuration switches and the machinery behind them so sensitive LLM content (raw
prompts, raw model outputs, customer PII) is never logged or surfaced by default, the demo UI renders
only safe summaries, and audit events are safe to put in portfolio screenshots. The LLM stays assistive;
this slice only constrains what existing logging/audit/UI surfaces emit — no new agent, event, or topic
(FR-015).

```text
Config (this slice):
  LOG_RAW_LLM_PROMPTS=false   # raw prompt text is NOT logged by default
  LOG_RAW_LLM_OUTPUTS=false   # raw model output text is NOT logged by default
  REDACT_PII=true             # PII scrubbed from logs, audit records, and UI by default
```

**Acceptance criteria covered** (from feature input): (1) Sensitive content is not logged by default;
(2) Demo UI can show safe summaries; (3) Audit events are safe for portfolio screenshots.

**Independent Test**: With default config and a stub-backed `reason()` call whose grounding inputs carry
seeded PII (email, phone, card number): captured structlog records contain no raw prompt/output and no
PII; the emitted `ReasoningAuditRecord` contains placeholders (no PII, `prompt_ref` is a hash) yet stays
queryable/reconstructable by `correlation_id`; the demo UI renders the safe summary with none of the
seeded PII. Flip each `LOG_RAW_LLM_*` flag to true and confirm only its own raw content reappears.

**Prerequisite (owned by other slices)**: core runtime — `src/agent_foundation/llm/config.py`
(`RuntimeConfig`), `src/agent_foundation/llm/runtime.py` (`LLMRuntime.reason`),
`src/agent_foundation/llm/audit.py` (`ReasoningAuditRecord`), and the providers under
`src/agent_foundation/llm/providers/`. US3 also depends on `apps/demo_ui/` (007 aggregator, present). If a
prerequisite module is not yet present, the foundational tasks create the minimal surface and the owning
slice reconciles it.

### Setup / Docs for Safety & Redaction

- [X] T1900 [P] [SAF] Add a "Safety & Redaction" subsection to `specs/008-agent-llm-runtime/contracts/model-config.md` documenting `LOG_RAW_LLM_PROMPTS` (default `false`), `LOG_RAW_LLM_OUTPUTS` (default `false`), and `REDACT_PII` (default `true`), each with meaning and the secure-by-default rationale.
- [X] T1901 [P] [SAF] Document the three env vars and their safe defaults in `specs/008-agent-llm-runtime/quickstart.md` (how to flip raw logging on for local debugging, and the warning that defaults are required for portfolio screenshots).

### Foundational for Safety & Redaction (BLOCKS US1/US2/US3)

- [X] T1902 [SAF] Extend `RuntimeConfig` in `src/agent_foundation/llm/config.py` with `log_raw_prompts: bool` (env `LOG_RAW_LLM_PROMPTS`, default `False`), `log_raw_outputs: bool` (env `LOG_RAW_LLM_OUTPUTS`, default `False`), and `redact_pii: bool` (env `REDACT_PII`, default `True`); parse "false"/"0"/"no" case-insensitively; omitted env vars MUST yield the secure defaults (FR-017).
- [X] T1903 [SAF] Create `src/agent_foundation/llm/redaction.py` exposing `redact_text(text: str) -> str` and `redact_mapping(data: dict) -> dict` that scrub common PII (email, phone, credit-card/PAN, SSN-like, postal address, long digit runs) into stable typed placeholders (e.g. `[REDACTED_EMAIL]`); deterministic, offline, and idempotent (re-redacting is a no-op) so audit output stays replay-stable (Principle III).
- [X] T1904 [SAF] Add a `Redactor` policy facade in `src/agent_foundation/llm/redaction.py` — `Redactor.from_config(config)` exposing `scrub(value)` that applies `redact_*` only when `config.redact_pii` is true (pass-through, never raw secrets, when false) — one shared redaction decision point for all call sites.

### US1 — Sensitive content is not logged by default (Priority: P1)

- [X] T1905 [SAF] Gate prompt logging in `src/agent_foundation/llm/runtime.py`: in `LLMRuntime.reason()` log the prompt only when `config.log_raw_prompts`; otherwise log a safe descriptor (`prompt_ref` hash + `task_kind` + token estimate), never the prompt string.
- [X] T1906 [SAF] Gate model-output logging in `src/agent_foundation/llm/runtime.py`: log the raw completion text only when `config.log_raw_outputs`; otherwise log a safe descriptor (reasoning path, validity, length), never the completion body.
- [X] T1907 [P] [SAF] Audit `src/agent_foundation/llm/providers/bedrock.py` for incidental raw logging: request/response bodies, prompt blocks, and `RawCompletion.text` are never logged unless the corresponding flag is set; replace such calls with safe descriptors.
- [X] T1908 [P] [SAF] Audit `src/agent_foundation/llm/providers/stub.py` and `src/agent_foundation/llm/providers/base.py` for the same: no raw prompt/output strings in logs by default.
- [X] T1909 [SAF] Add a module docstring + inline note in `src/agent_foundation/llm/runtime.py` stating the secure-by-default logging contract so future log statements follow the gate.
- [X] T1910 [P] [SAF] Unit test `tests/unit/llm/test_no_raw_logging.py` (stub-backed, offline): default config emits zero log records containing the prompt body or model output body; `LOG_RAW_LLM_PROMPTS=true` / `LOG_RAW_LLM_OUTPUTS=true` each independently re-enable only their own raw content.

### US2 — Audit events are safe for portfolio screenshots (Priority: P1)

- [X] T1911 [SAF] In `src/agent_foundation/llm/audit.py`, route `grounding_digest` and `result_summary` through `Redactor.scrub(...)` before constructing the `ReasoningAuditRecord` (redaction at write time; the audit topic is append-only/immutable).
- [X] T1912 [SAF] In `src/agent_foundation/llm/audit.py`, guarantee `prompt_ref` is only the prompt hash/reference (per contracts/reasoning-audit-record.md) and no field carries the rendered prompt string; redact `model_params` of any free-text that could echo inputs.
- [X] T1913 [SAF] In `src/agent_foundation/llm/runtime.py`, construct the `Redactor` once from `RuntimeConfig` and pass it (or pre-scrubbed payloads) into the audit-write path so model / cache / fallback steps all emit redacted records consistently.
- [X] T1914 [SAF] Ensure fallback and `unable_to_produce` audit records are also scrubbed in `src/agent_foundation/llm/audit.py` — failure metadata must not echo raw grounding PII into `result_summary`/`failure_reason`.
- [X] T1915 [P] [SAF] Unit test `tests/unit/llm/test_audit_redaction.py` (stub-backed): with `REDACT_PII=true`, seeded PII in grounding inputs/model output does not appear in the `ReasoningAuditRecord` `grounding_digest`/`result_summary`; `prompt_ref` is a hash not the prompt body; the record stays queryable/reconstructable; a `REDACT_PII=false` case preserves content (explicit opt-out) while still never embedding the raw prompt text.
- [X] T1916 [P] [SAF] Unit test `tests/unit/llm/test_redaction.py`: `redact_text`/`redact_mapping` against email, phone, PAN, SSN, address, and nested-dict fixtures assert deterministic, idempotent placeholder output.

### US3 — Demo UI can show safe summaries (Priority: P2)

- [X] T1917 [SAF] Add a safe summary renderer for reasoning steps in `apps/demo_ui/reasoning_summary.py` that formats a `ReasoningAuditRecord` into a display row using only safe fields (`task_kind`, `model_id`, `reasoning_path`, `cache_hit`, redacted `result_summary`, `latency_ms`, `outcome`).
- [X] T1918 [SAF] Wire the reasoning-step summary into the case audit timeline in `apps/demo_ui/views/case_view.py` so assistive steps appear in causal order alongside the rest of the case, rendered via the safe renderer only.
- [X] T1919 [P] [SAF] Add a defensive UI-side guard in `apps/demo_ui/reasoning_summary.py` that applies `redact_text` before display even if an upstream record were unredacted — the UI never trusts the source to be clean (backstop, not primary control).
- [X] T1920 [SAF] Update `apps/demo_ui/README.md` to state the UI shows only safe LLM summaries, relies on `REDACT_PII=true` upstream, with the defensive UI guard as backstop.
- [X] T1921 [P] [SAF] Unit test `tests/unit/demo_ui/test_safe_summary_view.py`: rendering a fixture `ReasoningAuditRecord` (PII seeded upstream) exposes only `task_kind`, `reasoning_path`, redacted `result_summary`, and metadata — no raw prompt/output/PII.

### Polish for Safety & Redaction

- [X] T1922 [P] [SAF] Unit test `tests/unit/llm/test_safety_config_defaults.py`: `RuntimeConfig` from an empty environment yields `log_raw_prompts=False`, `log_raw_outputs=False`, `redact_pii=True` (secure-by-default regression guard).
- [X] T1923 [P] [SAF] Document the safety model in the `src/agent_foundation/llm/` package docstring (or `docs/`): the three switches, the write-time redaction point, and the screenshot-safe-by-default guarantee, cross-referencing FR-011/FR-012.
- [X] T1924 [SAF] Run the quickstart safety walkthrough end to end against the stub model (no AWS): default-config logs are clean, an audit record for a PII-seeded case is redacted, and the demo UI renders the safe summary; record results in `specs/008-agent-llm-runtime/quickstart.md`.
- [X] T1925 [P] [SAF] Run `ruff format` + `ruff check` over `src/agent_foundation/llm/redaction.py`, the edited runtime/audit/provider modules, and the demo UI changes to keep CI green.

**Checkpoint**: Default-config runs leak no raw prompt/output to logs; audit records on `agent.audit.v1`
are PII-free and screenshot-safe yet reconstructable by `correlation_id`; the demo UI renders assistive
reasoning safely — all unit tests green against the stub with no AWS.

### Safety slice — dependencies & parallel notes

- Sequence within slice: foundational T1902 → T1903 → T1904 (T1903/T1904 share `redaction.py`, sequential) BLOCK the three stories.
- US1 (T1905–T1910) and US2 (T1911–T1916) are both P1 and independent (logging gates vs. audit-write path) — run in parallel after foundational. Within US1, T1905/T1906/T1909/T1913 edit `runtime.py` (sequential); T1907/T1908 [P] (different provider files). Within US2, T1911/T1912/T1914 edit `audit.py` (sequential).
- US3 (T1917–T1921, P2) depends on US2's redacted records; T1917/T1919 share `reasoning_summary.py` (sequential), T1918 edits `case_view.py`.
- Test tasks marked [P] run together once their story's implementation is done. This slice has no dependency on the LG/CFG/CRA/billing/risk slices beyond the shared core-runtime prerequisite.


<!-- SLICE:cra-llm-adoption -->
---

## Phase CRA: Customer Resolution Agent — LLM Adoption (classify + draft) (feature input; FR-018, SC-002/007)

**Scope (from this slice's input)**: Integrate the **Customer Resolution Agent (CRA)** with the shared
assistive LLM runtime for exactly two bounded tasks — **ticket classification** and **customer response
drafting**. The binding outcome stays the deterministic output of `decision_engine.decide`; the LLM only
classifies and drafts.

**Acceptance criteria covered** (from feature input):
- **Classification still returns structured Pydantic output** — the LLM-backed classify path returns the
  existing `Triage` (Pydantic), validated against a `TicketClassification` schema (US-CRA1; FR-005, G1).
- **Response drafting uses allowed facts only** — drafting grounding inputs are built solely from
  `AllowedFacts`; output asserting any fact outside them (or any fraud/internal field) is rejected
  (US-CRA2; FR-005, G1).
- **Failed LLM classification escalates safely** — on classify failure the agent falls back to the
  deterministic keyword `classify()`, and ambiguous tickets route to refund/human review with the
  binding outcome unchanged (US-CRA3; FR-006/009, SC-004).
- **Failed response drafting requires human review** — on draft failure the agent returns the templated
  fallback `ResponseDraft` flagged `requires_human_approval=True`, never fabricated content (US-CRA4;
  FR-006/009).

**Independent Test**: Against the stub model, offline: (1) classify two differing tickets → both return
schema-valid `Triage`, differing accordingly; (2) draft with a populated `AllowedFacts` and feed model
output asserting an out-of-facts detail → it is rejected, never surfaced; (3) force the classify model
path to fail → deterministic fallback `Triage`, ambiguous case escalates, binding outcome unchanged;
(4) force the draft model path to fail → templated `ResponseDraft` with `requires_human_approval=True`.

**Prerequisite (owned by the core-runtime / config slices)**: the shared runtime must exist —
`src/agent_foundation/llm/request.py` (`AssistiveRequest`, `TaskKind.classify`/`draft_response`),
`src/agent_foundation/llm/result.py` (`AssistiveResult`, `ReasoningPath`, `FailureReason`),
`src/agent_foundation/llm/runtime.py` (`LLMRuntime.reason`, `assist_or_fallback`),
`src/agent_foundation/llm/config.py` (`resolve_profile`), the `PromptTemplate`
(`src/agent_foundation/llm/prompts.py`), and the validate-and-repair + grounding check
(`src/agent_foundation/llm/structured.py`). This slice consumes that surface only and does not build it.

### Phase CRA.1: Setup & Foundational (CRA-scoped)

- [X] T1500 [CRA] Register the CRA profiles `("customer-resolution", classify)` (e.g. `max_tokens=256`, `temperature=0.0`) and `("customer-resolution", draft_response)` (e.g. `max_tokens=512`, `temperature=0.0`) in the runtime profile registry `src/agent_foundation/llm/config.py` so both CRA tasks resolve via config, not hard-coded call sites (FR-017; contracts/model-config.md). Coordinate with the config slice (T1023) if that file is owned there.
- [X] T1501 [P] [CRA] Add a CRA-scoped config flag in `apps/agents/customer_resolution/config.py`: `CRA_LLM_ENABLED` (env `CRA_LLM_ENABLED`, default **on**), so the LLM-backed classify/draft path can be disabled to the pure deterministic path; the stub model keeps it offline-safe by default (FR-014).

### Phase CRA.2: US-CRA1 — Classification returns structured Pydantic output (Priority: P1) 🎯 MVP

**Goal**: Route ticket classification through `LLMRuntime.reason()` while still returning the existing
structured `Triage`, leaving the published `CustomerIssueClassifiedPayload` contract unchanged.

- [X] T1502 [P] [CRA] [US-CRA1] Add a `TicketClassification` output schema (frozen Pydantic v2) in `apps/agents/customer_resolution/ticket_classifier.py` — constrained `issue_type` enum, `needs_refund_review: bool`, `confidence: float` (0–1), `rationale: str`, optional `matched_signals: list[str]` — plus a `to_triage()` mapping onto the existing `Triage` model (acceptance: classification still returns structured Pydantic output; G1).
- [X] T1503 [CRA] [US-CRA1] Add the classify task `instructions` + a `PromptTemplate` whose stable prefix carries the refund-intent vocabulary (`config.REFUND_INTENT_SIGNALS`) + schema + examples (cache-eligible; FR-013) in `apps/agents/customer_resolution/ticket_classifier.py` (depends on T1502).
- [X] T1504 [CRA] [US-CRA1] Implement `async classify_with_llm(ticket, runtime) -> Triage` in `apps/agents/customer_resolution/ticket_classifier.py` using `assist_or_fallback(agent_id="customer-resolution", task_kind=classify, grounding_inputs={"reason": ticket.reason, ...}, output_schema=TicketClassification, fallback=lambda: classify(ticket))`, returning `TicketClassification.to_triage()` on the model path or the deterministic `Triage` on fallback (FR-001/006; depends on T1503 + prerequisite runtime).
- [X] T1505 [CRA] [US-CRA1] Wire the classification call site in `apps/agents/customer_resolution/event_handlers.py` to `classify_with_llm`, keeping `build_issue_classified_payload` and the emitted `CustomerIssueClassifiedPayload` byte-compatible (FR-016, SC-007).
- [X] T1506 [P] [CRA] [US-CRA1] Adoption test in `apps/agents/customer_resolution/tests/test_llm_classify.py`: LLM-backed classify returns a schema-valid Pydantic `Triage`; two tickets differing in intent yield correspondingly different classifications (stub-backed, offline).

**Checkpoint (US-CRA1)**: CRA classification is LLM-backed and still returns structured Pydantic output;
the published contract is unchanged.

### Phase CRA.3: US-CRA2 — Response drafting uses allowed facts only (Priority: P1)

**Goal**: Generate the customer-facing draft via the runtime grounded **solely** in `AllowedFacts`,
returning the existing structured `ResponseDraft` with no fraud/internal field leakage.

- [X] T1507 [P] [CRA] [US-CRA2] Add the draft task `instructions` + a `PromptTemplate` whose grounding suffix is built **only** from `AllowedFacts` (reuse `build_allowed_facts`, which already excludes `RiskFinding`) in `apps/agents/customer_resolution/response_drafter.py` (acceptance: drafting uses allowed facts only; FR-005).
- [X] T1508 [CRA] [US-CRA2] Implement `async draft_with_llm(outcome, allowed_facts, tone_config, runtime) -> ResponseDraft` in `apps/agents/customer_resolution/response_drafter.py` using `assist_or_fallback(agent_id="customer-resolution", task_kind=draft_response, grounding_inputs=allowed_facts.model_dump(), output_schema=ResponseDraft, fallback=lambda: draft_structured_response(...))`, then run `_assert_no_internal_leak` on the model body before returning (FR-005/006; depends on T1507 + prerequisite runtime).
- [X] T1509 [CRA] [US-CRA2] Wire the drafting call site in `apps/agents/customer_resolution/event_handlers.py` to `draft_with_llm`, keeping `build_response_drafted_payload` / `CustomerResponseDraftedPayload` unchanged (FR-016).
- [X] T1510 [P] [CRA] [US-CRA2] Grounding test in `apps/agents/customer_resolution/tests/test_llm_draft.py`: model output asserting a fact outside `AllowedFacts` (e.g. invented order detail or a risk score) is rejected by the grounding check and never returned; `FRAUD_SCORING_FIELDS`/`INTERNAL_ONLY_DRAFT_FIELDS` never appear in the draft (stub-backed, offline).

**Checkpoint (US-CRA2)**: CRA drafting is LLM-backed and provably uses only customer-safe allowed facts.

### Phase CRA.4: US-CRA3 — Failed LLM classification escalates safely (Priority: P1)

**Goal**: A classification model failure degrades to the deterministic keyword `classify()` and a safe
escalation, with the binding outcome unaffected.

- [X] T1511 [CRA] [US-CRA3] Ensure `classify_with_llm`'s `fallback` returns the deterministic `classify(ticket)` and that ambiguous fallbacks keep `ambiguous=True` → `requires_human_review`/`needs_refund_review` mapping through `build_issue_classified_payload` in `apps/agents/customer_resolution/ticket_classifier.py` (depends on T1504).
- [X] T1512 [CRA] [US-CRA3] Confirm the binding decision path in `apps/agents/customer_resolution/decision_engine.py` is driven only by billing/risk/policy/timeout inputs — never by the assistive `Triage` — and assert at the `event_handlers.py` seam that no assistive field maps onto a binding verdict (FR-003/004).
- [X] T1513 [P] [CRA] [US-CRA3] Tests in `apps/agents/customer_resolution/tests/test_llm_classify_fallback.py`: (a) forced classify model failure ⇒ deterministic fallback `Triage`, ambiguous ticket escalates safely (`requires_human_review`/refund review), `reasoning_path == fallback` recorded; (b) guardrail — an adversarial LLM classification (e.g. asserting "approve") does not change the outcome from `decision_engine.decide` (SC-002).

**Checkpoint (US-CRA3)**: Classification model failure degrades to a safe deterministic escalation; the
binding verdict stays deterministic under adversarial LLM output.

### Phase CRA.5: US-CRA4 — Failed response drafting requires human review (Priority: P1)

**Goal**: A drafting model failure returns the templated fallback flagged for human review, never
fabricated content, and propagates the flag onto the published drafted event.

- [X] T1514 [CRA] [US-CRA4] In `draft_with_llm` (`apps/agents/customer_resolution/response_drafter.py`), when `reasoning_path == fallback` force `requires_human_approval=True` on the returned `ResponseDraft`, overriding the outcome-based default (depends on T1508).
- [X] T1515 [CRA] [US-CRA4] Propagate the fallback-driven `requires_human_approval` into `build_response_drafted_payload` at the drafting call site in `apps/agents/customer_resolution/event_handlers.py` so the published `CustomerResponseDraftedPayload.requires_human_approval` reflects human-review routing (depends on T1514).
- [X] T1516 [P] [CRA] [US-CRA4] Test in `apps/agents/customer_resolution/tests/test_llm_draft_fallback.py`: forced drafting model failure ⇒ templated fallback `ResponseDraft` with `requires_human_approval=True`, `reasoning_path == fallback`, and no hallucinated facts in the body (stub-backed, offline).

**Checkpoint (US-CRA4)**: A drafting model failure produces a safe templated message explicitly routed to
human review.

### Phase CRA.6: Polish (CRA slice)

- [X] T1517 [P] [CRA] Audit test in `apps/agents/customer_resolution/tests/test_llm_audit.py`: each CRA classify/draft call emits exactly one `ReasoningAuditRecord` attributed to `customer-resolution`, with `correlation_id == case_id` and the causation link, queryable by correlation id with no live model and distinguishable from the binding decision (FR-011/012, SC-005).
- [X] T1518 [P] [CRA] Idempotent-replay test in `apps/agents/customer_resolution/tests/test_llm_classify.py` / `test_llm_draft.py`: re-issuing the same classify/draft request (same idempotency key) returns identical structured output with zero second model invocations, recorded as `cache` path (FR-007/008, SC-003, G3).
- [X] T1519 [P] [CRA] Add a "Customer Resolution agent: LLM classify + draft (offline stub)" snippet to `specs/008-agent-llm-runtime/quickstart.md`.
- [X] T1520 [CRA] Run `ruff check`/`ruff format` on the edited CRA files and the full CRA suite `pytest apps/agents/customer_resolution/tests/` to confirm all new + existing tests are green against the stub with no AWS.

**Checkpoint (CRA slice)**: All CRA-adoption tests green offline; classification returns structured
Pydantic output, drafting uses allowed facts only, classify failure escalates safely, and draft failure
routes to human review — binding outcome provably deterministic throughout.

### CRA slice — dependencies & parallel notes

- Sequence within slice: T1500/T1501 (setup) → **US-CRA1**: T1502 → T1503 → T1504 → T1505; **US-CRA2**: T1507 → T1508 → T1509 (independent of US-CRA1, different file — can run in parallel). **US-CRA3** builds on T1504 (T1511/T1512 → T1513). **US-CRA4** builds on T1508 (T1514 → T1515 → T1516).
- US-CRA1 (`ticket_classifier.py`) and US-CRA2 (`response_drafter.py`) edit different files and can be built in parallel after the runtime prerequisite is ready.
- Test tasks T1506/T1510/T1513/T1516/T1517/T1518 are `[P]` across distinct test files once their implementation tasks land.
- Depends only on the core-runtime / config prerequisites above; no dependency on the risk, billing, or LangGraph slices. `decision_engine.py` is read/asserted but not changed in authority.

<!-- SLICE:llm-audit-events -->
---

## Phase AE: Optional LLM Audit Events (feature input; FR-011/012, FR-015 note below)

**Scope (from this slice's input)**: Add two **optional, observability-only** event types the shared
LLM runtime emits around each assistive invocation, on dedicated topics:

| Event type (logical) | Topic |
|----------------------|-------|
| `audit.llm.invocation.completed` | `local.audit.llm.invocation.completed.v1` |
| `audit.llm.invocation.failed`    | `local.audit.llm.invocation.failed.v1` |

**Acceptance criteria covered** (from feature input):
- Events include **agent ID, model ID, prompt ID, latency, token usage, and correlation ID** (US-AE1).
- Events **do not include raw prompts by default** (US-AE2).
- **Raw prompt logging is disabled unless explicitly configured** (US-AE2/US-AE3).

> **Constitution / FR-015 note**: FR-015 forbids *new coordination* event contracts/topics/agents/
> supervisors. These two events are **observability/audit only**, carry no coordination semantics, add
> no agent or supervisor, and are **published only when explicitly enabled**
> (`AGENT_LLM_AUDIT_EVENTS_ENABLED`, default `false`). Default-off keeps runtime behavior, the offline
> guarantee (SC-006), and the FR-015 default surface unchanged — no extra topic traffic unless an
> operator opts in. They are an *additional, opt-in projection* of the same reasoning step recorded by
> the always-on in-process `ReasoningAuditRecord` on `agent.audit.v1`
> (contracts/reasoning-audit-record.md); they never replace it.

**Independent Test**: With `AGENT_LLM_AUDIT_EVENTS_ENABLED=true`, drive one stub-backed `reason()` to
success and assert exactly one event on `local.audit.llm.invocation.completed.v1` carrying agent ID,
model ID, prompt ID, latency, token usage, and correlation ID; force a model failure and assert exactly
one event on `local.audit.llm.invocation.failed.v1` carrying a failure reason — all offline, no AWS.
With the flag unset, assert zero messages on both topics while the `agent.audit.v1` record still writes.

**Prerequisite (owned by the core-runtime slice)**: the shared runtime must exist —
`src/agent_foundation/llm/runtime.py` (`LLMRuntime.reason`), `src/agent_foundation/llm/result.py`
(`AssistiveResult`, `ReasoningPath`, `TokenUsage`, `FailureReason`), `src/agent_foundation/llm/request.py`
(`AssistiveRequest`, `TaskKind`), `src/agent_foundation/llm/config.py` (`RuntimeConfig`), and the audit
step in `src/agent_foundation/llm/audit.py` (`ReasoningAuditRecord`). This slice consumes that surface
and the existing `Publisher` (`src/agent_foundation/transport/publisher.py`); it does not build the runtime.

### Phase AE.1: Foundational (audit-events-scoped) — blocks US-AE1/2/3

- [X] T3000 [AE] Add topic constants `TOPIC_LLM_INVOCATION_COMPLETED = topic_for("audit", "llm.invocation", "completed")` and `TOPIC_LLM_INVOCATION_FAILED = topic_for("audit", "llm.invocation", "failed")` in `packages/contracts/topics.py` (resolve to `local.audit.llm.invocation.completed.v1` / `local.audit.llm.invocation.failed.v1` under the existing `local` env prefix).
- [X] T3001 [P] [AE] Create the two frozen Pydantic v2 payload models (`extra="forbid"`) in `src/agent_foundation/llm/audit_events.py`: `LlmInvocationCompletedPayload` and `LlmInvocationFailedPayload` with required fields `agent_id: str`, `model_id: str | None`, `prompt_id: str` (prompt reference/hash, NOT raw prompt), `task_kind: str`, `correlation_id: UUID`, `causation_id: UUID`, `latency_ms: int`, `token_usage: dict | None`, `cache_hit: bool`, `reasoning_path: str`, `recorded_at: datetime`, and `raw_prompt: str | None = None` (default `None`); the `failed` payload also carries `failure_reason: str`.
- [X] T3002 [AE] Register both event types in the publisher payload registry `src/agent_foundation/payloads/__init__.py` — `TOPIC_LLM_INVOCATION_COMPLETED -> LlmInvocationCompletedPayload`, `TOPIC_LLM_INVOCATION_FAILED -> LlmInvocationFailedPayload` (event_type == topic string, matching the existing new-style convention) (depends on T3000, T3001).
- [X] T3003 [AE] Register both topics in `src/agent_foundation/transport/topics.py`: add to `TOPIC_NAMES` and append `NewTopic` entries (1 partition, replication 1, `cleanup.policy=compact`, mirroring `TOPIC_AUDIT`) to `_CANONICAL_TOPICS` so `create_topics` provisions them when present (depends on T3000).
- [X] T3004 [P] [AE] Add an `LlmAuditEventConfig` reader in `src/agent_foundation/llm/audit_events.py` (or extend `RuntimeConfig` in `src/agent_foundation/llm/config.py` — coordinate with the CFG slice) reading `AGENT_LLM_AUDIT_EVENTS_ENABLED` and `AGENT_LLM_AUDIT_LOG_RAW_PROMPTS`, both defaulting to `False` via a case-insensitive truthy parse (`"true"/"1"/"yes"`), exposing `events_enabled: bool` and `log_raw_prompts: bool`.
- [X] T3005 [P] [AE] Document the two new env knobs (`AGENT_LLM_AUDIT_EVENTS_ENABLED`, `AGENT_LLM_AUDIT_LOG_RAW_PROMPTS`, both default `false`, raw prompts never emitted unless the second is `true`) in `specs/008-agent-llm-runtime/contracts/model-config.md`.

### Phase AE.2: US-AE1 — Emit invocation events with required fields (Priority: P1) 🎯 MVP

**Goal**: Every assistive `reason()` call (when enabled) emits exactly one `completed` event on success
or one `failed` event on fallback/unable-to-produce, each carrying agent ID, model ID, prompt ID,
latency, token usage, and correlation ID.

- [X] T3006 [AE] [US-AE1] Implement `emit_llm_invocation_event(publisher, request, result, *, config)` in `src/agent_foundation/llm/audit_events.py`: build the completed-vs-failed payload from the `AssistiveRequest`/`AssistiveResult` (map `prompt_id` from the prompt_ref hash, copy `token_usage`, `latency_ms`, `reasoning_path`, `cache_hit`, `model_id`), construct an `EventEnvelope` with the request's `correlation_id`/`causation_id`, and `publisher.publish(...)` to the matching topic; select completed vs failed from `result.reasoning_path`/`failure_reason` (depends on T3000–T3004).
- [X] T3007 [AE] [US-AE1] Wire the emit call into the runtime audit step in `src/agent_foundation/llm/runtime.py` (or `llm/audit.py` where `ReasoningAuditRecord` is written) so every invocation that writes a `ReasoningAuditRecord` ALSO calls `emit_llm_invocation_event(...)`, placed after the existing audit write and never replacing it (depends on T3006).
- [X] T3008 [AE] [US-AE1] Make emission failure-safe: wrap the publish in try/except that logs a structlog warning (mirroring `audit.store.write_audit`'s `audit.write_failed` handling) and swallows transport errors, so a missing topic / broker hiccup degrades observability only and never fails the assistive call or the deterministic binding decision (depends on T3007).
- [X] T3009 [P] [AE] [US-AE1] Unit test `tests/unit/llm/test_audit_events_payloads.py`: construct both payloads, assert the six required fields are present and `extra="forbid"` rejects unknown fields (offline).
- [X] T3010 [P] [AE] [US-AE1] Integration test `tests/integration/llm/test_llm_audit_events_emit.py`: with events enabled, a stub `reason()` success yields exactly one `local.audit.llm.invocation.completed.v1` event whose six required fields match the call (agent_id / model_id / prompt_ref / latency / token_usage / correlation_id).
- [X] T3011 [P] [AE] [US-AE1] Integration test `tests/integration/llm/test_llm_audit_events_failure.py`: force the model path to fail; assert exactly one `local.audit.llm.invocation.failed.v1` event with `failure_reason`, `reasoning_path=fallback`, and the correlation id, while the `agent.audit.v1` reasoning record is still written.

**Checkpoint (US-AE1)**: With events enabled, each call emits one completed-or-failed event with all
required fields; the in-process audit record is unaffected.

### Phase AE.3: US-AE2 — Never leak raw prompts by default (Priority: P1)

**Goal**: Events carry `prompt_id` (reference/hash) but never the raw prompt text unless
`AGENT_LLM_AUDIT_LOG_RAW_PROMPTS=true`.

- [X] T3012 [AE] [US-AE2] In `emit_llm_invocation_event` (`src/agent_foundation/llm/audit_events.py`), gate `raw_prompt` strictly on `config.log_raw_prompts`: when `False` (default) leave it `None` and never read prompt text into the payload; when `True` set it from the rendered prompt. `prompt_id` (hash/ref) is always set regardless (depends on T3006, T3004).
- [X] T3013 [P] [AE] [US-AE2] Integration test `tests/integration/llm/test_llm_audit_events_no_raw_prompt.py`: with events enabled and raw logging unset, assert `payload.raw_prompt is None`, the full prompt text does not appear anywhere in the serialized envelope, and `payload.prompt_id` is non-empty.
- [X] T3014 [P] [AE] [US-AE2] In the same test file, with `AGENT_LLM_AUDIT_LOG_RAW_PROMPTS=true`, assert `payload.raw_prompt` equals the rendered prompt — proving the field is opt-in only.

**Checkpoint (US-AE2)**: Default events are PII-safe (prompt_id only); raw prompt appears only under the
explicit opt-in flag.

### Phase AE.4: US-AE3 — Optional publication, disabled by default (Priority: P2)

**Goal**: Events are published only when `AGENT_LLM_AUDIT_EVENTS_ENABLED=true`; default-off produces
zero events and unchanged offline behavior (FR-015 default posture, SC-006).

- [X] T3015 [AE] [US-AE3] In the runtime emit hook (`src/agent_foundation/llm/runtime.py` / `audit_events.py`), short-circuit before building any envelope when `config.events_enabled` is `False`, so the disabled path does zero payload construction and zero publish calls (depends on T3007, T3004).
- [X] T3016 [P] [AE] [US-AE3] Integration test `tests/integration/llm/test_llm_audit_events_disabled_by_default.py`: with the flag unset, a stub `reason()` produces zero messages on both new topics while the `agent.audit.v1` reasoning record is present.
- [X] T3017 [P] [AE] [US-AE3] Unit test `tests/unit/llm/test_audit_events_config.py`: `LlmAuditEventConfig` defaults `events_enabled=False`/`log_raw_prompts=False` and parses `"true"/"1"/"yes"` (case-insensitive) as `True`, any other value as `False`.
- [X] T3018 [AE] [US-AE3] Document an "Enabling optional LLM audit events" subsection in `specs/008-agent-llm-runtime/quickstart.md` (enable flag, the two topics, offline default-off note) (depends on T3015).

### Phase AE.5: Polish (audit-events slice)

- [X] T3019 [P] [AE] Add a contract doc `specs/008-agent-llm-runtime/contracts/llm-audit-events.md` describing the two event types, their topics, payload fields, the two config flags, the default-off posture, and the FR-015 observability-only rationale.
- [X] T3020 [P] [AE] Add an entry to `specs/008-agent-llm-runtime/data-model.md` for `LlmInvocationCompletedPayload` / `LlmInvocationFailedPayload` cross-referencing `ReasoningAuditRecord` (§10) as the same step's opt-in projection.
- [X] T3021 [AE] Run `ruff format` and `ruff check` over `src/agent_foundation/llm/audit_events.py`, `src/agent_foundation/payloads/__init__.py`, `src/agent_foundation/transport/topics.py`, `packages/contracts/topics.py`, and the new tests to satisfy the CI lint gate.
- [X] T3022 [AE] Run the slice's tests offline (`pytest tests/unit/llm/test_audit_events_payloads.py tests/unit/llm/test_audit_events_config.py tests/integration/llm/test_llm_audit_events_*.py`) with no AWS credentials and confirm all green (SC-006).

**Checkpoint (audit-events slice)**: Opt-in `completed`/`failed` events carry all required fields, are
PII-safe by default, default to OFF with zero traffic and unchanged offline behavior; all tests green
against the stub with no AWS.

### Audit-events slice — dependencies & parallel notes

- Sequence within slice: T3000 → (T3001, T3004, T3005 [P]) → T3002/T3003 → T3006 → T3007 → T3008 → T3012 → T3015. T3006/T3007/T3008/T3012/T3015 all touch `audit_events.py`/`runtime.py`, so keep sequential.
- Tests are `[P]` once their implementation lands: T3009/T3010/T3011 (US-AE1), T3013/T3014 (US-AE2), T3016/T3017 (US-AE3); docs T3018/T3019/T3020 [P].
- Depends only on the core-runtime prerequisite (runtime.py/result.py/request.py/config.py/audit.py) and the existing `Publisher`; coordinate the `config.py` flag location with the CFG slice (T1020–T1025). No dependency on the CRA/billing/risk adoption or LangGraph slices.

<!-- SLICE:prompt-template-registry -->
---

## Phase PR: Prompt Template Registry (feature input; data-model §10/§12, contracts/llm-runtime-api.md)

**Goal**: A **versioned prompt template registry** — Markdown templates under
`packages/llm-runtime/prompts/` loaded by `src/agent_foundation/llm/prompts.py`, exposing
`resolve(task_kind, agent_id) -> PromptTemplate` with a cache-eligible stable prefix
(instructions + schema + examples) plus a variable grounding suffix, and a stable
`prompt_ref = "{prompt_id}@v{version}"` recorded in reasoning metadata. The Billing and Risk summary
templates are summarize-only and cannot make final recommendations. The LLM stays assistive; no
template ever sets a binding verdict (FR-003/004, FR-013).

**Independent Test**: With no AWS present (stub), the registry loads all four templates; each carries a
`version`; `resolve(task_kind, agent_id)` returns the matching `prompt_id`; `prompt_ref` equals
`"{prompt_id}@v1"` and surfaces in the `AssistiveResult` metadata and the emitted
`ReasoningAuditRecord`; a synthetic `summarize_reasoning` template declaring
`allows_final_recommendation: true` is rejected at load time. Fully offline (SC-006).

**Acceptance criteria covered** (from feature input):
1. Prompts are versioned — T1080 (format), T1081-T1084 (each template carries `version`), T1086 (parse), T1093 (versioning test).
2. Prompt IDs recorded in metadata — T1087 (`prompt_ref = prompt_id@vN`), T1090 (threaded into result/audit), T1091/T1094 (tests).
3. Billing/Risk prompts cannot make final recommendations — T1083, T1084 (summarize-only text + `allows_final_recommendation: false`), T1088 (registry guardrail), T1092 (test).

**Prerequisite (owned by other slices)**: `TaskKind` in `src/agent_foundation/llm/request.py`;
`PromptTemplate` is consumed by `LLMRuntime.reason()` (runtime slice) and `prompt_ref` is written into
`ReasoningAuditRecord` (audit slice, data-model §10) / `AssistiveResult` (result slice). If
`prompts.py` does not yet exist, this slice owns it. The four template files are also consumed by the
CRA / billing / risk adoption slices.

### Implementation for Prompt Template Registry

- [X] T1080 [PR] Create the resource dir `packages/llm-runtime/prompts/` with a `README.md` defining the versioned-Markdown template format (YAML frontmatter keys: `prompt_id`, `version`, `task_kind`, `agent_id`, `allows_final_recommendation`; body = the stable instruction prefix).
- [X] T1081 [P] [PR] Author `packages/llm-runtime/prompts/customer_ticket_classification.md` (frontmatter `prompt_id: customer_ticket_classification`, `version: 1`, `task_kind: classify`, `agent_id: customer-resolution-agent`, `allows_final_recommendation: false`; instructions classify the ticket into the caller-supplied permitted category set only).
- [X] T1082 [P] [PR] Author `packages/llm-runtime/prompts/customer_response_drafting.md` (`prompt_id: customer_response_drafting`, `version: 1`, `task_kind: draft_response`, `agent_id: customer-resolution-agent`, `allows_final_recommendation: false`; instructions bound the draft to the supplied AllowedFacts only, never inventing order/policy facts).
- [X] T1083 [P] [PR] Author `packages/llm-runtime/prompts/billing_explanation_summary.md` (`prompt_id: billing_explanation_summary`, `version: 1`, `task_kind: summarize_reasoning`, `agent_id: billing-entitlement-agent`, `allows_final_recommendation: false`; instructions summarize the already-decided deterministic `rules_engine.evaluate` reasoning only and EXPLICITLY forbid proposing, changing, or implying any refund recommendation).
- [X] T1084 [P] [PR] Author `packages/llm-runtime/prompts/risk_explanation_summary.md` (`prompt_id: risk_explanation_summary`, `version: 1`, `task_kind: summarize_reasoning`, `agent_id: risk-fraud-agent`, `allows_final_recommendation: false`; instructions summarize the deterministic `scoring.assess_signals` assessment only and EXPLICITLY forbid proposing, changing, or implying any risk verdict).
- [X] T1085 [PR] Implement `PromptTemplate` in `src/agent_foundation/llm/prompts.py`: a frozen value holding the parsed frontmatter (`prompt_id`, `version`, `task_kind`, `agent_id`, `allows_final_recommendation`) and a `render(grounding_inputs, *, schema=None, examples=None)` that returns a cache-eligible stable prefix + a variable grounding suffix (data-model §12; FR-013).
- [X] T1086 [PR] Implement `PromptRegistry` in `src/agent_foundation/llm/prompts.py`: discover and load all `*.md` from `packages/llm-runtime/prompts/`, parse YAML frontmatter, index by `(task_kind, agent_id)`, and expose `resolve(task_kind, agent_id) -> PromptTemplate` raising a clear error on a missing template (acceptance: prompts are versioned) — depends on T1080-T1084, T1085.
- [X] T1087 [PR] On `PromptTemplate.render(...)` compute and return `prompt_ref = f"{prompt_id}@v{version}"` plus a content hash of the rendered prompt, so callers can record the prompt identity in reasoning metadata (acceptance: prompt IDs recorded in metadata; FR-012/013) — in `src/agent_foundation/llm/prompts.py`.
- [X] T1088 [PR] Enforce the no-final-recommendation guardrail in `PromptRegistry` (`src/agent_foundation/llm/prompts.py`): at load time any template with `task_kind == summarize_reasoning` (and any billing/risk template) MUST have `allows_final_recommendation: false`, else loading raises; expose `allows_final_recommendation` read-only on `PromptTemplate` (acceptance: Billing/Risk prompts cannot make final recommendations; FR-003/004).
- [X] T1089 [P] [PR] Export `PromptTemplate` and `PromptRegistry` from the `src/agent_foundation/llm/__init__.py` public surface (depends on T1086).
- [X] T1090 [PR] Thread `prompt_ref` (from T1087) into reasoning metadata: ensure `ReasoningAuditRecord.prompt_ref` (data-model §10) is populated from the registry and add/propagate `prompt_ref` onto `AssistiveResult` metadata — additive only, coordinated with the result/audit slices (FR-011/012).

### Tests for Prompt Template Registry (stub-backed, offline)

- [X] T1091 [P] [PR] Unit test `tests/unit/llm/test_prompt_registry.py`: all four templates load; each exposes a `version`; `resolve(task_kind, agent_id)` returns the expected `prompt_id`; `prompt_ref == "{prompt_id}@v1"` (acceptance: versioned + prompt IDs in metadata).
- [X] T1092 [P] [PR] Unit test `tests/unit/llm/test_prompt_registry.py`: the billing and risk templates have `allows_final_recommendation == false`, and `PromptRegistry` rejects a synthetic `summarize_reasoning` template that sets `allows_final_recommendation: true` (acceptance: Billing/Risk prompts cannot make final recommendations).
- [X] T1093 [P] [PR] Unit test `tests/unit/llm/test_prompt_registry.py`: `render()` keeps the stable prefix byte-identical across two differing `grounding_inputs` (only the suffix differs) and yields a deterministic `prompt_ref` — supporting prompt caching + versioning (FR-013).
- [X] T1094 [P] [PR] Unit test `tests/unit/llm/test_prompt_registry.py`: a stub-backed `LLMRuntime.reason()` call records the template `prompt_ref` in the emitted `ReasoningAuditRecord`, queryable with no live model (acceptance: prompt IDs recorded in metadata; FR-011/012).

### Docs for Prompt Template Registry

- [X] T1095 [P] [PR] Document the prompt-registry versioning + no-final-recommendation conventions in `packages/llm-runtime/prompts/README.md` and add a short "prompt registry" note to `specs/008-agent-llm-runtime/quickstart.md`.

**Checkpoint**: `PromptRegistry.resolve(task_kind, agent_id)` returns versioned templates; `prompt_ref`
flows into the audit trail and result metadata; billing/risk summary templates are summarize-only and the
registry rejects any that claim final-recommendation authority — all unit tests green against the stub
with no AWS.

### Prompt Template Registry — dependencies & parallel notes

- Sequence within slice: T1080 first; then T1081-T1084 [P] (four distinct template files); T1085 -> T1086 -> T1087 -> T1088 all edit `prompts.py` (sequential); then T1089 [P]; T1090 last (touches result/audit seams, additive).
- T1091-T1095 [P] can run together once T1088/T1090 land (T1091-T1094 share one test file but assert independently; T1095 edits docs).
- This slice depends only on `TaskKind` (request slice) and the `config.resolve_profile` prerequisite; the runtime/audit/result and CRA/billing/risk adoption slices consume the templates and `prompt_ref` produced here.

<!-- SLICE:agent-llm-bedrock-wrapper -->
---

## Phase AL: AgentLLM Bedrock Wrapper (feature input; data-model §9; contracts/provider-protocol.md)

**Goal**: Provide a thin, normalized client wrapper around Bedrock so the rest of the runtime never
touches boto3 request/response shapes directly.

```python
class AgentLLM:
    def invoke(self, messages, metadata=None) -> LLMResponse
    def invoke_structured(self, messages, output_schema, metadata=None) -> StructuredLLMResponse
```

**Acceptance criteria covered** (from feature input):
- Hides Bedrock-specific implementation details (callers pass Anthropic-style `messages`, never boto3 bodies).
- Returns normalized response objects (`LLMResponse` / `StructuredLLMResponse`).
- Captures model ID, latency, and token usage when available.
- Supports safe metadata for audit logging (sanitized, JSON-serializable, secrets stripped).

**Layering note (avoid overlap)**: `AgentLLM` is the **Bedrock-client primitive** that the Bedrock
`ModelProvider` uses to emit a `RawCompletion` (data-model §9). It does **not** replace the
runtime-level validate-and-repair seam owned by the **SO slice** (`structured.py`, T1100-T1112): the
wrapper performs the raw model call + JSON parse; the runtime still owns schema repair, fallback, and
the `AssistiveResult`. `AgentLLM.invoke_structured` is convenience JSON parsing at the client edge only.

**Independent Test**: With boto3 mocked (offline), `invoke(messages)` returns an `LLMResponse` carrying
`model_id`, `latency_ms`, and `token_usage` parsed from the mocked `usage` block;
`invoke_structured(messages, Schema)` returns `value` as a `Schema` instance for valid JSON and sets
`parse_error` (no raise) for malformed JSON; caller metadata is sanitized; a boto3 `ClientError`
surfaces as a typed `LLMClientError`, never raw boto3 — all with no AWS.

**Prerequisite (owned by other slices)**: `TokenUsage` in `src/agent_foundation/llm/result.py` (result
slice) and `RawCompletion` / `ModelProvider` in `src/agent_foundation/llm/providers/base.py` (provider
slice). This slice consumes those; T1202 only creates a minimal `TokenUsage` if no sibling slice has yet.

### Phase AL.1: Setup (slice prereqs — create-if-absent, shared with sibling slices)

- [X] T1200 [P] [AL] Create the runtime package scaffold `src/agent_foundation/llm/__init__.py` and `src/agent_foundation/llm/providers/__init__.py` if absent (no-op if a sibling slice already created them).
- [X] T1201 [P] [AL] Add an optional `[llm]` extra declaring `boto3` in `pyproject.toml` (idempotent; skip if a sibling slice already added it).

### Phase AL.2: Foundational (normalized value types — block the wrapper)

- [X] T1202 [P] [AL] Ensure the `TokenUsage` value model (`input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`) exists in `src/agent_foundation/llm/result.py`; reuse the sibling-owned definition if present, else add it (data-model §6). Do not duplicate the type.
- [X] T1203 [AL] Define the `LLMResponse` Pydantic v2 model in `src/agent_foundation/llm/client.py` with fields `text: str`, `model_id: str | None`, `latency_ms: int`, `token_usage: TokenUsage | None`, `cache_hit: bool`, `stop_reason: str | None`, `metadata: dict` (data-model §3/§9 alignment).
- [X] T1204 [AL] Define the `StructuredLLMResponse` model in `src/agent_foundation/llm/client.py` wrapping/extending `LLMResponse` with `value: BaseModel | None`, `raw_json: dict | None`, and `parse_error: str | None`.

### Phase AL.3: User Story 1 — Normalized `invoke()` (Priority: P1) 🎯 MVP

**Goal**: An agent or provider calls Bedrock through one method and gets a normalized `LLMResponse`, with Bedrock wire details hidden.

**Independent test**: Mock the boto3 `bedrock-runtime` client; `invoke(messages)` returns an `LLMResponse` populated with `model_id`, `latency_ms`, and `token_usage` parsed from the mocked `usage` block.

- [X] T1205 [AL] [US1] Implement `AgentLLM.__init__(self, *, config=None, profile=None)` in `src/agent_foundation/llm/client.py`: lazily build a boto3 `bedrock-runtime` client from the profile/config region + model_id; import-guard `boto3` so the module imports without the `[llm]` extra installed (FR-014/017).
- [X] T1206 [AL] [US1] Implement `_build_request_body(messages, *, max_tokens, temperature, top_p, system=None)` in `src/agent_foundation/llm/client.py` mapping `messages` to the Anthropic Messages API body (`anthropic_version`, `messages`, decoding params) — the single place the boto3/Bedrock request shape lives (acceptance: hides Bedrock details).
- [X] T1207 [AL] [US1] Implement `AgentLLM.invoke(self, messages, metadata=None) -> LLMResponse` in `src/agent_foundation/llm/client.py`: build the body, call `invoke_model` (or `converse`), wrap the call in `time.perf_counter()` timing, and return a normalized `LLMResponse` (acceptance: normalized response).
- [X] T1208 [AL] [US1] Implement `_parse_response(raw, latency_ms, metadata)` in `src/agent_foundation/llm/client.py` capturing `model_id`, `stop_reason`, the concatenated output text, and a `TokenUsage` (input/output tokens) from the response `usage` block (acceptance: captures model id, latency, token usage).

### Phase AL.4: User Story 3 — Client-level structured output (`invoke_structured`) (Priority: P1)

**Goal**: Callers get parsed, schema-shaped output without handling raw JSON, and a malformed model reply never raises into the caller (repair/fallback stays in the runtime/SO slice).

**Independent test**: Mocked valid JSON → `value` is a `Schema` instance; mocked invalid JSON → `value is None` and `parse_error` set, no exception.

- [X] T1209 [AL] [US3] Implement `AgentLLM.invoke_structured(self, messages, output_schema, metadata=None) -> StructuredLLMResponse` in `src/agent_foundation/llm/client.py`: add a JSON-output instruction for `output_schema`, call the model via `invoke`, attempt `output_schema.model_validate_json` / `model_validate`, populate `value`/`raw_json` on success and `parse_error` on failure — never raise on parse/validation failure (the SO slice T1100-T1112 owns repair + fallback).

### Phase AL.5: User Story 6 — Safe metadata for audit (Priority: P2)

**Goal**: Caller-supplied metadata is carried for audit logging without leaking secrets or unbounded blobs.

**Independent test**: Pass metadata with a credential-like key, an oversized string, and a plain tag; the credential key is dropped, the oversized value truncated, the plain tag preserved, and the result is JSON-serializable.

- [X] T1210 [AL] [US6] Implement `_safe_metadata(metadata) -> dict` in `src/agent_foundation/llm/client.py`: drop secret-like keys (token/secret/password/key/credential heuristics), enforce JSON-serializability, cap per-value and total size, and attach the sanitized dict to both `LLMResponse.metadata` and `StructuredLLMResponse.metadata` (acceptance: safe metadata for audit; FR-011/012).

### Phase AL.6: User Story 7 / 5 — Usage, cache, and typed errors (Priority: P2)

**Goal**: Token usage and prompt-cache reuse are observable, and infrastructure failures surface as a typed error the runtime can translate to a fallback.

**Independent test**: A mocked `usage` block with `cache_read_input_tokens`/`cache_creation_input_tokens` yields a populated `TokenUsage` and `cache_hit=True`; a mocked boto3 `ClientError`/timeout surfaces as `LLMClientError`, not a raw boto3 exception.

- [X] T1211 [AL] [US7] Extend `_parse_response` in `src/agent_foundation/llm/client.py` to read `cache_read_input_tokens`/`cache_creation_input_tokens` from `usage` into `TokenUsage.cache_read_tokens`/`cache_write_tokens` and set `LLMResponse.cache_hit` from a non-zero cache read (US7, SC-008).
- [X] T1212 [AL] [US5] Define `LLMClientError` and map boto3 `ClientError`/`BotoCoreError`/throttling/read-timeout to it inside `AgentLLM.invoke`/`invoke_structured` (`src/agent_foundation/llm/client.py`) so boto3 exception types never leak past the wrapper (the runtime translates `LLMClientError` to a fallback; FR-009).

### Phase AL.7: Integration — wire the wrapper into the Bedrock provider

- [X] T1213 [AL] [US1] In `src/agent_foundation/llm/providers/bedrock.py` (create the stub if the provider slice has not yet landed) construct an `AgentLLM` and adapt `LLMResponse`/`StructuredLLMResponse` to `RawCompletion` (`text`, `token_usage`, `cache_hit`, `model_id`) — adapter only, no decision logic; coordinate with the provider slice that owns `providers/base.py` (provider-protocol.md).
- [X] T1214 [P] [AL] Export `AgentLLM`, `LLMResponse`, `StructuredLLMResponse`, `LLMClientError` from the public surface in `src/agent_foundation/llm/__init__.py` (depends on T1207-T1212).

### Phase AL.8: Tests (unit, offline — boto3 mocked, no AWS)

- [X] T1215 [P] [AL] [US1] `tests/unit/llm/test_agent_llm_invoke.py`: mocked client → `invoke()` returns an `LLMResponse` with `model_id`, `latency_ms >= 0`, and `token_usage` parsed from `usage` (acceptance: captures model id/latency/usage).
- [X] T1216 [P] [AL] [US3] `tests/unit/llm/test_agent_llm_structured.py`: valid JSON → `value` is an `output_schema` instance; malformed JSON → `value is None`, `parse_error` set, no exception raised.
- [X] T1217 [P] [AL] [US6] `tests/unit/llm/test_agent_llm_metadata.py`: secret-like keys stripped, oversized values truncated, plain tags preserved, result JSON-serializable.
- [X] T1218 [P] [AL] [US7] `tests/unit/llm/test_agent_llm_usage_cache.py`: cache read/write tokens captured and `cache_hit` set from a non-zero cache read.
- [X] T1219 [P] [AL] [US5] `tests/unit/llm/test_agent_llm_errors.py`: a mocked boto3 `ClientError`/timeout surfaces as `LLMClientError`, not a raw boto3 type.

### Phase AL.9: Polish

- [X] T1220 [P] [AL] Add an `AgentLLM` usage note (a `messages` + `metadata` example, and the layering note vs. the runtime) to `specs/008-agent-llm-runtime/quickstart.md`.
- [X] T1221 [P] [AL] Run `ruff format` + `ruff check` on `src/agent_foundation/llm/client.py` and the new tests (GitHub CI parity).

**Checkpoint (AgentLLM slice)**: `AgentLLM` is importable; `invoke()` returns a normalized `LLMResponse`
with model id/latency/token usage; `invoke_structured()` returns a schema-shaped result without raising
on bad JSON; metadata is sanitized for audit; boto3 errors surface as `LLMClientError`; the Bedrock
provider emits `RawCompletion` through it — all unit tests green against mocked boto3 with no AWS.

### AgentLLM slice — dependencies & parallel notes

- Sequence within slice: T1200-T1201 (setup, [P]) → T1202-T1204 (types) → T1205-T1208 (US1 invoke; all edit `client.py`, so sequential).
- After T1208: T1209 (US3), T1210 (US6), T1211 (US7), T1212 (US5) all edit `client.py` → keep sequential among themselves, but are independent in intent.
- T1213-T1214 (integration) depend on T1207-T1212 and on the sibling-owned `RawCompletion`/`base.py` and `__init__.py` surfaces.
- All Phase AL.8 tests (T1215-T1219) are mutually [P] across separate files once their targets exist; T1220/T1221 [P].
- Consumes `TokenUsage` (result slice) and `RawCompletion`/`ModelProvider` (provider slice). No dependency on the CRA/billing/risk/LangGraph/CFG/MP/SO adoption logic beyond the shared `__init__`/types.

### MVP scope (AgentLLM slice)

T1200 → T1208 (plus T1215): a normalized `AgentLLM.invoke()` returning an `LLMResponse` with
model_id/latency/usage, boto3 fully mocked offline. That alone satisfies acceptance criteria 1-3;
T1209 (structured) and T1210 (safe metadata) complete criterion 4.

<!-- SLICE:config-loader-layering -->
---

## Phase CFG2: Config Loader `load_model_config` — Layered Resolution (feature input; FR-017, US8; research R10)

**Goal**: Provide the public entry point `load_model_config(agent_id: str) -> BedrockModelConfig` in `src/agent_foundation/llm/config.py` that resolves an agent's config by overlaying, in increasing precedence, **defaults → YAML profile → environment variables → runtime override**. This slice **extends** the LLM Provider Config Models slice (`<!-- SLICE:llm-provider-config-models -->`, T1020-T1025): it REUSES the `BedrockModelConfig`/`ModelProfile`/`RuntimeConfig` types and env mapping defined there (T1020-T1023) and adds the YAML-profile layer, the runtime-override layer, the layered loader, and a clear missing-config error. It must NOT redefine those models. The loader resolves configuration only — it reads no AWS credentials and makes no cloud calls (offline-safe, FR-014, SC-006).

**Independent Test**: Set the same field (e.g. `max_tokens`) at each of the four layers and assert the highest present layer wins; a bare offline call returns the stub defaults; `bedrock`/`agentcore` modes resolve `model_id` (region from env/YAML, else `None` deferred to the AWS default chain); a missing required field raises a clear `ModelConfigError`.

**Acceptance criteria covered** (from feature input): works locally with AWS credentials (`bedrock` mode); works under AgentCore local dev (`agentcore` mode); produces a clear error when model config is missing.

**Story lineage**: US1=precedence (FR-017/US8) · US2=clear error · US3=local AWS/bedrock (FR-002/FR-014) · US4=AgentCore local dev (R9). Labeled `[CFG2]` within this slice.

**Prerequisite (owned by the config-models slice)**: `BedrockModelConfig`, `ModelProfile`, `RuntimeConfig`, and the `AGENT_LLM_*`/Bedrock-shorthand env mapping in `src/agent_foundation/llm/config.py` (T1020-T1023). This slice composes on top of them; coordinate edits to `config.py` with that slice.

### Implementation for Layered Config Loader

- [X] T1040 [P] [CFG2] Add `pyyaml>=6` to `[project].dependencies` in `pyproject.toml` (the loader parses a YAML profile on every call; keep it a core dep so offline resolution needs no extra).
- [X] T1041 [P] [CFG2] Add `config/agent_llm.example.yaml` with a top-level `defaults:` block and an `agents:` map keyed by `agent_id` (`customer-resolution-agent`, `billing-entitlement-agent`, `risk-fraud-agent`), documenting every overridable `ModelProfile` field from data-model §7.
- [X] T1042 [CFG2] Define `ModelConfigError(ValueError)` with a message helper naming `agent_id`, resolved `mode`, and the specific missing field, in `src/agent_foundation/llm/config.py`.
- [X] T1043 [CFG2] Implement private `_merge_layers(*layers) -> dict` in `src/agent_foundation/llm/config.py` overlaying partial config dicts left-to-right (later wins; `None`/absent keys do not clobber earlier layers).
- [X] T1044 [CFG2] Implement `_load_yaml_layer(agent_id) -> dict` in `src/agent_foundation/llm/config.py`: locate the file via `AGENT_LLM_CONFIG_FILE` env or default `config/agent_llm.yaml`, return `{}` when absent, overlay the file's `defaults:` then its `agents.<agent_id>:` blocks.
- [X] T1045 [CFG2] Implement `_load_env_layer() -> dict` in `src/agent_foundation/llm/config.py` by REUSING the env mapping from the config-models slice (T1023; `AGENT_LLM_*` + Bedrock shorthands) — factor the shared mapping into one helper rather than duplicating it; omit unset vars.
- [X] T1046 [CFG2] Implement the runtime-override layer in `src/agent_foundation/llm/config.py`: a process-level registry with `register_runtime_override(agent_id, **fields)` / `clear_runtime_overrides()` and `_load_override_layer(agent_id) -> dict` consulted last (highest precedence).
- [X] T1047 [CFG2] Implement `load_model_config(agent_id: str) -> BedrockModelConfig` in `src/agent_foundation/llm/config.py`: gather the four layer dicts (defaults from T1021/`ModelProfile` stub defaults, YAML from T1044, env from T1045, override from T1046), `_merge_layers` in precedence order, and construct the `BedrockModelConfig` (depends on T1020-T1023, T1042-T1046).
- [X] T1048 [CFG2] Implement mode-aware required-field validation in `load_model_config` (`src/agent_foundation/llm/config.py`): `stub` requires nothing beyond defaults; `bedrock`/`agentcore` require `model_id`; wrap YAML-parse and numeric-coercion failures into `ModelConfigError` (with agent/mode/field/file context) instead of leaking `KeyError`/`ValidationError`/YAML errors (acceptance: clear error when config missing).
- [X] T1049 [CFG2] Finalize `bedrock`-mode resolution in `src/agent_foundation/llm/config.py`: accept `region` from env/YAML, leave `region=None` when unset (provider consults the boto3 default credential/region chain at call time), and document that the loader reads/validates no credentials (acceptance: works locally with AWS credentials; offline-safe).
- [X] T1050 [CFG2] Finalize `agentcore`-mode resolution in `src/agent_foundation/llm/config.py`: share the `bedrock` required-field path (`model_id` required) and document that `bedrock-agentcore` imports stay in the provider layer, never in `config.py`, so the loader works without the optional dep installed (acceptance: works under AgentCore local dev).
- [X] T1051 [P] [CFG2] Export `load_model_config`, `register_runtime_override`, `clear_runtime_overrides`, and `ModelConfigError` from `src/agent_foundation/llm/__init__.py` (depends on T1047-T1050).

### Tests for Layered Config Loader (stub-backed, offline, no AWS)

- [X] T1052 [P] [CFG2] [US1] Precedence tests in `tests/unit/llm/test_config_loader.py`: bare call -> stub defaults; YAML overrides defaults; env overrides YAML; runtime override beats all; per-`agent_id` YAML section overlays YAML `defaults:`.
- [X] T1053 [P] [CFG2] [US2] Error tests in `tests/unit/llm/test_config_loader_errors.py`: bedrock without `model_id` -> `ModelConfigError`; agentcore without `model_id` -> `ModelConfigError`; malformed YAML -> `ModelConfigError` naming the file; non-numeric `AGENT_LLM_TIMEOUT_SECONDS` -> `ModelConfigError`.
- [X] T1054 [P] [CFG2] [US3] Bedrock-mode tests in `tests/unit/llm/test_config_loader_bedrock.py`: explicit region honored; absent region -> `None` (defer to AWS default chain); `temperature` defaults to `0.0`; loader reads no credentials.
- [X] T1055 [P] [CFG2] [US4] AgentCore-mode tests in `tests/unit/llm/test_config_loader_agentcore.py`: agentcore mode resolves `model_id`; loader import + call succeed with `bedrock-agentcore` NOT installed; missing `model_id` raises `ModelConfigError`.

### Docs & verification for Layered Config Loader

- [X] T1056 [P] [CFG2] Update `specs/008-agent-llm-runtime/contracts/model-config.md` to document the new **YAML profile** and **runtime override** precedence layers and `AGENT_LLM_CONFIG_FILE` (the contract currently lists only defaults + env).
- [X] T1057 [CFG2] Run `ruff check`, `mypy src/agent_foundation/llm/config.py`, and `pytest tests/unit/llm` to confirm all four stories pass offline with no AWS credentials present.

**Checkpoint**: `load_model_config` resolves config via the full four-layer precedence (defaults -> YAML -> env -> runtime override), returns stub defaults offline, resolves `bedrock`/`agentcore` modes for local use, and raises a clear `ModelConfigError` on missing config — all unit tests green against the stub with no AWS.

### Layered Config Loader — dependencies & parallel notes

- T1040-T1041 [P] (different files). T1042-T1050 all edit `config.py`, so sequential in that order; they also build on the config-models slice's T1020-T1023, so that slice's model definitions must land first (or be co-developed in the same `config.py`). T1051 [P] after impl (edits `__init__.py`).
- Tests T1052-T1055 [P] together once T1051 is done (different test files). T1056 [P] (docs). T1057 runs last.
- This slice extends the config-models slice (T1020-T1025) and has no dependency on the LangGraph (T960-T972) or risk-adoption (T900-T922) slices. It introduces only new symbols (`load_model_config`, `ModelConfigError`, `register_runtime_override`, `clear_runtime_overrides`, the YAML/override layer helpers) and does not redefine `BedrockModelConfig`/`ModelProfile`/`RuntimeConfig`/`resolve_profile`.

<!-- SLICE:billing-llm-summary -->
---

## Phase BL: Billing Agent — Optional LLM Reasoning-Summary / Explanation Summarization (feature input; FR-018, SC-002)

**Scope (from this slice's input)**: Integrate the Billing & Entitlement agent with the shared
assistive LLM runtime **optionally**, using the runtime for exactly two bounded, text-only tasks:
(1) **`reasoning_summary` polishing** and (2) **explanation summarization** of the evidence. Core
refund eligibility stays 100% deterministic; the LLM may only produce explanation text.

**Acceptance criteria covered** (from feature input):
- **Core refund eligibility remains deterministic** — `rules_engine.evaluate` is untouched and still
  owns `recommendation`, `confidence`, `eligible_refund_amount`, `requires_human_review`, `evidence`,
  `policy_references`, and the derived status fields (FR-003/004, SC-002).
- **LLM cannot change the recommendation** — enrichment only writes narrative *text*; no binding field
  of `EligibilityRecommendation` / `BillingRefundAnalysisCompletedPayload` is ever populated from an
  `AssistiveResult` (FR-004, G2).
- **LLM output is constrained to explanation text** — a `BillingNarrative` output schema with only
  `str` fields, grounding-checked against the deterministic recommendation so no invented
  facts/policy/amount/verdict leak in; invalid output is rejected and falls back to the deterministic
  `reasoning_summary` (FR-005/006, G1).

**Independent Test**: Run `evaluate()` to produce a deterministic `EligibilityRecommendation`, then
call the billing enrichment seam with the stub model: the returned wire payload carries a polished
`reasoning_summary` and an evidence explanation, while `recommendation`, `confidence`,
`eligible_refund_amount`, `requires_human_review`, and the `evidence`/`policy_references` are
byte-for-byte identical to the deterministic result — verifiable offline with no AWS. Forcing the stub
to emit an adversarial "approve/deny" or a fabricated amount leaves every binding field unchanged and
degrades to the deterministic summary.

**Prerequisite (owned by the core-runtime / CFG slices)**: the shared runtime must exist —
`src/agent_foundation/llm/request.py` (`AssistiveRequest`, `TaskKind.summarize_reasoning`),
`src/agent_foundation/llm/result.py` (`AssistiveResult`, `ReasoningPath`, `FailureReason`),
`src/agent_foundation/llm/runtime.py` (`LLMRuntime.reason`, `assist_or_fallback`),
`src/agent_foundation/llm/config.py` (`resolve_profile`). This slice consumes that surface only and
does not build it. The billing profile `("billing-entitlement-agent", summarize_reasoning)` is already
registered by the CFG slice (T1023) — do **not** duplicate it here.

### Phase BL.1: Setup & Foundational (billing-scoped)

- [X] T1400 [P] [BL] Add a billing-scoped config flag in `apps/agents/billing_entitlement/config.py`: `BILLING_LLM_SUMMARY_ENABLED` (env `BILLING_LLM_SUMMARY_ENABLED`, default **off/false**), so the LLM enrichment is strictly opt-in and the agent's default behavior is the existing deterministic path (FR-014, "optionally").
- [X] T1401 [P] [BL] Confirm (do not duplicate) the billing profile `("billing-entitlement-agent", summarize_reasoning)` is registered in `src/agent_foundation/llm/config.py` by the CFG slice (T1023, `max_tokens=200`, `temperature=0.0`); if that slice has not landed, add the registration here and leave a `# coordinate with CFG slice` note (FR-017; contracts/model-config.md).

### Phase BL.2: US-BL1 — Optional assistive enrichment of the billing narrative (Priority: P1) 🎯 MVP

**Goal**: When enabled, polish the deterministic `reasoning_summary` and summarize the evidence into a
readable explanation via the runtime, attaching both as text to the published result — without
changing any binding field. `evaluate()`/`analyze()` stay pure and deterministic.

- [X] T1402 [P] [BL] [US-BL1] Add the explanation-text-only `BillingNarrative` output schema (frozen Pydantic v2, `model_config = ConfigDict(extra="forbid")`) in `apps/agents/billing_entitlement/llm_summary.py`: exactly two text fields — `polished_summary: str` (bounded, e.g. `max_length` ~600) and `evidence_explanation: str` (bounded, e.g. `max_length` ~800). **No** recommendation/amount/confidence/verdict fields — explanation text only (acceptance: output constrained to explanation text; G1, FR-005).
- [X] T1403 [BL] [US-BL1] Implement `_build_grounding_inputs(rec, request)` in `apps/agents/billing_entitlement/llm_summary.py` that serializes ONLY the deterministic `EligibilityRecommendation` (recommendation label, confidence, eligible_refund_amount, reasoning_summary, requires_human_review, policy_references, the derived status fields, and each `evidence` item's `source`/`description`/`value`) plus `ticket_id`/`customer_id` into a JSON-serializable dict, so the model may reason only over the deterministic result (data-model.md §1 grounding; FR-005).
- [X] T1404 [BL] [US-BL1] Implement `_instructions()` in `apps/agents/billing_entitlement/llm_summary.py`: a large, stable instruction block telling the model to rewrite the provided `reasoning_summary` more clearly and summarize the listed evidence in plain language, explicitly forbidding it from changing/asserting any recommendation, amount, confidence, or fact not present in grounding inputs (cache-eligible prefix; FR-013).
- [X] T1405 [BL] [US-BL1] Implement `async enrich_recommendation(runtime, rec, request, *, causation_id) -> BillingNarrative` in `apps/agents/billing_entitlement/llm_summary.py`: build the `AssistiveRequest` (`agent_id="billing-entitlement-agent"`, `task_kind=summarize_reasoning`, `correlation_id=request.case_id`, `causation_id`, `instructions`, grounding from T1403, `output_schema=BillingNarrative`, derived `idempotency_key`, and a `fallback` returning `BillingNarrative(polished_summary=rec.reasoning_summary, evidence_explanation=<deterministic join of evidence descriptions>)`), call `assist_or_fallback` / `runtime.reason()`, and return `result.value` (FR-001/006; llm-runtime-api.md).
- [X] T1406 [BL] [US-BL1] Add `enriched_reasoning_summary: str | None` and `evidence_explanation: str | None` as **optional** fields (default `None`) to `BillingRefundAnalysisCompletedPayload` (`packages/contracts/events/payloads.py`), so consumers that ignore them are unchanged (FR-016, additive/back-compatible). If they cannot be added without breaking the 003 consumer contract, instead overwrite the `reasoning_summary` text in T1407 and skip this task — record which path was taken.
- [X] T1407 [BL] [US-BL1] Wire enrichment into `apps/agents/billing_entitlement/service.py` `build_result_payload()` and `build_a2a_output()`: accept an optional pre-computed `narrative: BillingNarrative | None`; when present, set the narrative/explanation **text** fields only; `recommendation` stays `str(rec.recommendation)`, and `confidence`/`eligible_refund_amount`/`requires_human_review`/`evidence`/`policy_references` stay from the deterministic `rec` (acceptance: LLM cannot change recommendation; FR-004). Keep `analyze()` synchronous, pure, and deterministic (no LLM import on the deterministic path).
- [X] T1408 [BL] [US-BL1] In `apps/agents/billing_entitlement/main.py` `handle_eligibility`, after `analyze(...)`, when `BILLING_LLM_SUMMARY_ENABLED` is set construct an `LLMRuntime` (once at startup) and `await enrich_recommendation(...)` (causation_id=`req.task_id`), passing the resulting narrative into `build_result_payload`/`build_a2a_output`; when disabled, call them with `narrative=None` (path unchanged). Keep the existing publish/dedup flow intact (FR-015, no new topic/event).

**Checkpoint (US-BL1)**: With `BILLING_LLM_SUMMARY_ENABLED=1`, a billing analysis publishes a polished
summary + evidence explanation against the stub model, offline; the binding fields are unchanged.

### Phase BL.3: US-BL2 — Binding determinism guardrail (Priority: P1)

**Goal**: Prove the LLM can never alter the recommendation or amount.

- [X] T1410 [P] [BL] [US-BL2] Guardrail unit test in `apps/agents/billing_entitlement/tests/test_llm_summary_guardrail.py`: for representative outcomes (APPROVE_FULL_REFUND, DENY_REFUND, MANUAL_REVIEW, REQUEST_MORE_INFORMATION), stub the runtime to return an adversarial `BillingNarrative` whose text claims a different verdict/amount; assert the published payload's `recommendation`/`confidence`/`eligible_refund_amount`/`requires_human_review`/`evidence`/`policy_references` exactly equal the deterministic `evaluate()` output (SC-002, FR-004).
- [X] T1411 [P] [BL] [US-BL2] Test that `enrich_recommendation` never reads back into the rules engine: assert `evaluate` is invoked exactly once per case and its `EligibilityRecommendation` is not re-derived from the narrative (patch `evaluate` and confirm enrichment does not call it), in `apps/agents/billing_entitlement/tests/test_llm_summary_guardrail.py` (FR-003).
- [X] T1412 [P] [BL] [US-BL2] Determinism test: same input case → identical binding fields whether `BILLING_LLM_SUMMARY_ENABLED` is on or off (only the text narrative may differ), in `apps/agents/billing_entitlement/tests/test_llm_summary_guardrail.py`.
- [X] T1413 [BL] [US-BL2] Import-graph guard: assert `apps/agents/billing_entitlement/rules_engine.py` imports neither `llm_summary` nor `agent_foundation.llm` (no LLM input feeds the deterministic engine), in `apps/agents/billing_entitlement/tests/test_llm_summary_guardrail.py` (FR-003, SC-002).

### Phase BL.4: US-BL3 — Explanation-text bounds & grounding (Priority: P1)

**Goal**: Whatever the model returns is constrained to the `BillingNarrative` shape and traces to the
deterministic recommendation; bad output is rejected, not surfaced.

- [X] T1414 [P] [BL] [US-BL3] Test out-of-schema / extra-field / oversized model output is rejected by the runtime and `enrich_recommendation` returns the deterministic fallback narrative (`polished_summary == rec.reasoning_summary`), in `apps/agents/billing_entitlement/tests/test_llm_summary_bounds.py` (FR-005/006, G1).
- [X] T1415 [P] [BL] [US-BL3] Test hallucinated-fact rejection: a narrative asserting an order/amount/policy not present in grounding inputs is rejected/repaired and never published; the `evidence` list and `policy_references` are unchanged, in `apps/agents/billing_entitlement/tests/test_llm_summary_bounds.py` (FR-005, US3).
- [X] T1416 [P] [BL] [US-BL3] Test the LLM adds no evidence: `len(payload.evidence)` and the set of `policy_references` equal the deterministic recommendation's, regardless of narrative content, in `apps/agents/billing_entitlement/tests/test_llm_summary_bounds.py`.

### Phase BL.5: US-BL4 — Optional + safe degradation (Priority: P1)

**Goal**: Disabled by default; on model failure the agent proceeds on the deterministic summary.

- [X] T1417 [P] [BL] [US-BL4] Test default-off: with `BILLING_LLM_SUMMARY_ENABLED` unset, `main`/`service` never construct a runtime and the published payload equals today's deterministic output (narrative fields `None`/deterministic), in `apps/agents/billing_entitlement/tests/test_llm_summary_optional.py` (FR-014, "optionally").
- [X] T1418 [P] [BL] [US-BL4] Test forced-failure fallback: force the provider to timeout/error; `enrich_recommendation` returns a `fallback`-path narrative (deterministic summary) with a recorded `failure_reason`, never raises into the handler, and the binding outcome is unaffected, in `apps/agents/billing_entitlement/tests/test_llm_summary_optional.py` (FR-009, SC-004, G4).
- [X] T1419 [P] [BL] [US-BL4] Test offline default: with no AWS config the enrichment completes on the stub provider with no cloud access, in `apps/agents/billing_entitlement/tests/test_llm_summary_optional.py` (FR-014, SC-006, G6).

### Phase BL.6: US-BL5 — Audit & idempotent replay of the billing reasoning step (Priority: P2)

**Goal**: The billing reasoning step is audited and replay-stable.

- [X] T1420 [P] [BL] [US-BL5] Test the enrichment emits exactly one `ReasoningAuditRecord` attributed to `billing-entitlement-agent`, with `correlation_id == case_id`, the causation link, `task_kind=summarize_reasoning`, and a `reasoning_path`, queryable by correlation id with no live model, in `apps/agents/billing_entitlement/tests/test_llm_summary_audit.py` (FR-011/012, SC-005).
- [X] T1421 [P] [BL] [US-BL5] Test idempotent replay: issuing the same enrichment request twice (same idempotency key) returns identical narrative text with zero second model invocations and records the replay as `cache` path, in `apps/agents/billing_entitlement/tests/test_llm_summary_audit.py` (FR-007/008, SC-003, G3).

### Phase BL.7: Polish (billing slice)

- [X] T1422 [P] [BL] Extend `apps/agents/billing_entitlement/tests/test_result_contract.py`: assert `BillingRefundAnalysisCompletedPayload` and the A2A output shape are unchanged whether enrichment is on or off (FR-016, SC-007).
- [X] T1423 [P] [BL] Add a "Billing agent: optional LLM reasoning-summary / explanation summarization" snippet (enable flag + offline stub run) to `specs/008-agent-llm-runtime/quickstart.md`.
- [X] T1424 [BL] Run `ruff check` / `ruff format` and the full billing suite `pytest apps/agents/billing_entitlement/tests/` to confirm all new + existing tests are green against the stub with no AWS.

**Checkpoint (billing slice)**: All billing-adoption tests green offline; binding fields provably
untouched by the LLM; enrichment is opt-in and degrades safely.

### Billing slice — dependencies & parallel notes

- Sequence within slice: T1400/T1401 (setup) → T1402 → T1403/T1404 → T1405 → T1406 → T1407 → T1408. T1403 and T1404 are independent helpers in the same new file (write together, then T1405 composes them).
- Tests T1410–T1421 are all `[P]` across four test files once T1408 is done; T1410–T1413 share one file, T1414–T1416 another, T1417–T1419 another, T1420–T1421 another (independent assertions within each).
- Depends only on the core-runtime + CFG prerequisite above; no dependency on the CRA, risk, or LangGraph slices. `rules_engine.py` / `policy.py` are NOT edited by this slice.

<!-- SLICE:architecture-docs -->
---

## Phase DOC: Architecture Documentation (feature input; cross-cutting)

**Goal**: Add five `docs/architecture/` pages that explain the assistive LLM runtime to engineers
without making them read the spec artifacts — mirroring the existing architecture-doc convention
(open with an `Authoritative sources:` line citing the spec/contract files, a "Why this matters"
section, concrete `src/agent_foundation/llm/...` file paths, and FR/SC references). Documentation
only: no code under `src/`, `apps/`, or `tests/` is modified by this slice.

**Independent test**: Each page renders as valid Markdown, every relative link resolves, and a reader
can map each claim back to its cited authoritative source. This slice depends on nothing in the code
slices — the source of truth is the spec artifacts under `specs/008-agent-llm-runtime/`, all present.

- [X] T990 [P] [DOC] Create `docs/architecture/agent-llm-runtime.md` — the runtime overview. Open with `Authoritative sources: specs/008-agent-llm-runtime/plan.md, contracts/llm-runtime-api.md, data-model.md`. Cover: the single front door `LLMRuntime.reason(request) -> AssistiveResult` (`src/agent_foundation/llm/runtime.py`) and its ordered flow (idempotency lookup -> provider invoke -> validate-and-repair -> fallback -> audit); the **assistive-never-authoritative** boundary (binding verdicts stay in `decision_engine.decide`, billing `rules_engine.evaluate`, risk `scoring.assess_signals`; FR-003/004); the package layout from plan.md (`request.py`, `result.py`, `config.py`, `prompts.py`, `structured.py`, `store.py`, `audit.py`, `providers/`); and the three agent adoptions (CRA classify + draft, billing & risk reasoning summaries). Note FR-015 (no new agent/event/topic/supervisor). Include a Mermaid sequence diagram of one `reason()` call.
- [X] T991 [P] [DOC] Create `docs/architecture/bedrock-local-config.md` — provider config and the offline<->Bedrock switch. Open with `Authoritative sources: specs/008-agent-llm-runtime/contracts/model-config.md, contracts/provider-protocol.md, plan.md`. Document the env vars table (`AGENT_LLM_MODE` stub|bedrock|agentcore, `AGENT_LLM_MODEL`, `AGENT_LLM_REGION`, `AGENT_LLM_TIMEOUT_SECONDS`, `AGENT_LLM_MAX_REPAIRS`, `AGENT_LLM_BOOTSTRAP_SERVERS`); the `ModelProvider` protocol seam (`src/agent_foundation/llm/providers/base.py`) and config-driven selection (`providers/__init__.py`); the Bedrock provider (`providers/bedrock.py`: boto3 `bedrock-runtime`, Anthropic Messages API, `cache_control` prompt-cache breakpoints, token-usage accounting); per-agent `ModelProfile` resolution (`config.py`); and the guarantee that flipping `AGENT_LLM_MODE` requires **no** calling-agent code change (FR-014, FR-017, SC-006). State that `boto3` is the optional `[llm]` extra and stub is the default.
- [X] T992 [P] [DOC] Create `docs/architecture/structured-llm-outputs.md` — schema enforcement. Open with `Authoritative sources: specs/008-agent-llm-runtime/contracts/llm-runtime-api.md (guarantee G1), data-model.md sections 3 and 5, contracts/stub-model-contract.md`. Explain the validate-and-repair loop in `src/agent_foundation/llm/structured.py`: caller supplies a Pydantic v2 `output_schema`; raw completion is parsed/validated; on failure the runtime re-prompts up to `AGENT_LLM_MAX_REPAIRS` times; persistent failure degrades to the caller's `fallback` rather than surfacing bad output (FR-005/006); grounding bounds reject hallucinated facts not present in the request inputs. Note the `TextResult` default schema (`result.py`) for unstructured callers so every result is still schema-validated. Include a small before/after JSON example of a repaired output.
- [X] T993 [P] [DOC] Create `docs/architecture/llm-audit-events.md` — reasoning audit and replay. Open with `Authoritative sources: specs/008-agent-llm-runtime/contracts/reasoning-audit-record.md, data-model.md section 10, plan.md`. Document that every `reason()` call emits exactly one `ReasoningAuditRecord` via the **existing** `agent_foundation.audit.store.write_audit` on the **existing** `agent.audit.v1` topic (no new topic; FR-015); the required fields (`agent_id`, `correlation_id`, `causation_id`, `task_kind`, `model_id`/`model_params`, `prompt_ref` + `grounding_digest`, `reasoning_path` model|cache|fallback, `outcome`, `failure_reason`, `token_usage`, `latency_ms`); querying the full reasoning trace by `correlation_id` with **no live model** (FR-011/012, SC-005); and idempotent replay — a redelivered request returns the recorded `AssistiveResult` from `store.py` with zero additional model calls, recorded as the `cache` path (FR-007/008, SC-003). Cross-link `replay-and-idempotency.md`.
- [X] T994 [P] [DOC] Create `docs/architecture/agentcore-local-bedrock.md` — the local AgentCore invocation mode. Open with `Authoritative sources: specs/008-agent-llm-runtime/plan.md (Complexity Tracking + Project Structure), contracts/model-config.md, contracts/provider-protocol.md`. Explain `AGENT_LLM_MODE=agentcore` selecting `src/agent_foundation/llm/providers/agentcore.py`, which reuses the agents' existing `agentcore_app.py` / `bedrock_agentcore` entrypoints for laptop runs against Bedrock; that the dependency is the existing optional, import-guarded `bedrock-agentcore` extra (no second bespoke local-invocation path); when to choose `agentcore` vs `bedrock` vs `stub`; and that this path is opt-in and never required for tests/demo (offline stub default; FR-014, Principle V). Note it satisfies the same `ModelProvider` protocol so the runtime flow is unchanged.
- [X] T995 [DOC] Update the index in `docs/architecture/README.md`: add a new "### LLM runtime (feature 008)" subsection to the Index table with one row per page (`agent-llm-runtime.md`, `bedrock-local-config.md`, `structured-llm-outputs.md`, `llm-audit-events.md`, `agentcore-local-bedrock.md`) and a one-line description each; and add an `008 agent LLM runtime` row to the "Authoritative spec artifacts" table pointing to `specs/008-agent-llm-runtime/plan.md`, `contracts/`. Depends on T990-T994 (filenames finalized).
- [X] T996 [DOC] Add reciprocal cross-links and verify the slice: link `agent-llm-runtime.md` from the four companion pages and back; ensure `llm-audit-events.md` <-> `replay-and-idempotency.md` and `no-supervisor-verification.md` (FR-015) cross-references resolve; then confirm every relative link in the five new pages and the updated `README.md` points to an existing file (e.g. a repo-root link check). Depends on T990-T995.

### Architecture-docs slice — dependencies & parallel notes

- T990-T994 are fully parallel `[P]`: five independent new files, no shared file, no code dependency — the authoritative sources already exist under `specs/008-agent-llm-runtime/`.
- T995 (edits `README.md`) runs after T990-T994 so the indexed filenames/descriptions are final; T996 (cross-links + link check) runs last.
- This slice touches only `docs/architecture/`; it has no dependency on, and is not depended on by, the LG/CFG/RK/MP/SO code slices.

<!-- SLICE:llm-usage-tracking -->
---

## Phase UT: LLM Usage Tracking Model (feature input; data-model §3/§6, contracts/llm-runtime-api.md, contracts/reasoning-audit-record.md)

**Goal**: Add a normalized `LLMUsage` value model — `input_tokens`, `output_tokens`, `total_tokens`,
`estimated_cost_usd` (`Decimal`), `model_id`, `agent_id`, `prompt_id` — that the runtime attaches to
every assistive response so token consumption and an estimated USD cost ride along with each
reasoning step, are recorded in the audit trail, and can be rendered later by the Demo UI. Usage is
observability metadata only; it never feeds a binding verdict and never changes the reasoning path
(FR-010/011, FR-015). The model degrades gracefully when a provider returns no usage numbers.

**Independent Test**: Against the stub model, offline: (1) a model-path `LLMRuntime.reason()` call
returns an `AssistiveResult` whose `usage` carries the calling `agent_id`, the resolved `model_id`,
the prompt id, and `input_tokens`/`output_tokens`/`total_tokens`, with `total_tokens ==
input_tokens + output_tokens` and an `estimated_cost_usd` for a priced model; (2) a provider that
reports no usage (all token fields `None`, or an unknown `model_id`) yields an `LLMUsage` with
`total_tokens=None` and `estimated_cost_usd=None` and raises nothing; (3) the `LLMUsage` round-trips
through JSON (Decimal serialized) so it is carryable on the audit topic and displayable in the Demo
UI. Fully offline, no AWS (SC-006).

**Acceptance criteria covered** (verbatim from feature input):
1. **Usage is included in the normalized response** — `AssistiveResult.usage: LLMUsage | None` is
   populated by `LLMRuntime.reason()` on the model path (T2003, T2004; FR-010/016).
2. **Missing provider usage data is handled gracefully** — every `LLMUsage` token/cost field is
   optional and a missing/partial/unknown-model provider response yields `None` tokens/cost with no
   exception (T2000, T2001, T2002; FR-009 degradation posture).
3. **Data can be displayed later in the Demo UI** — `LLMUsage` is JSON-serializable and surfaced
   through the reasoning-step audit record + a Demo UI usage formatter (T2005, T2007; SC-008-adjacent
   observability).

**Prerequisite (owned by other slices)**: the result/runtime/audit surface — `TokenUsage` and
`AssistiveResult` in `src/agent_foundation/llm/result.py`, `LLMRuntime.reason()` in
`src/agent_foundation/llm/runtime.py`, `ReasoningAuditRecord` in `src/agent_foundation/llm/audit.py`,
and `RawCompletion` (`providers/base.py`, carries provider `token_usage`). The Demo UI task reuses
the reasoning-summary renderer introduced by the Safety slice (`<!-- SLICE:safety-redaction-controls -->`,
`apps/demo_ui/reasoning_summary.py`); if that file is not yet present this slice adds a standalone
`format_usage` helper the case view can call. This slice consumes those surfaces and does not build them.

### Implementation for LLM Usage Tracking

- [X] T2000 [UT] Define a frozen Pydantic v2 `LLMUsage` value model in `src/agent_foundation/llm/result.py`: `input_tokens: int | None = None`, `output_tokens: int | None = None`, `total_tokens: int | None = None`, `estimated_cost_usd: Decimal | None = None`, `model_id: str`, `agent_id: str`, `prompt_id: str | None = None`; set `model_config` so `Decimal` serializes to a JSON string (e.g. `model_config = ConfigDict(frozen=True)` + a `field_serializer` rendering `estimated_cost_usd` as `str`). All token/cost fields optional so a usage-free provider response is valid (acceptance 2; data-model §6 adjacency).
- [X] T2001 [UT] Create `src/agent_foundation/llm/pricing.py` with a per-model USD pricing table (input + output rate per 1K tokens keyed by `model_id`, covering the default Claude-on-Bedrock model ids used in `config/model-profiles.yaml`) and `estimate_cost(model_id, input_tokens, output_tokens) -> Decimal | None` that returns `None` for an unknown `model_id` or when either token count is `None` (no silent zero), using `Decimal` arithmetic throughout (acceptance 2; offline, no cloud lookup).
- [X] T2002 [UT] Implement a `build_llm_usage(token_usage, *, model_id, agent_id, prompt_id=None) -> LLMUsage` factory in `src/agent_foundation/llm/pricing.py` (or as `LLMUsage.from_token_usage(...)` in `result.py`): derive `total_tokens` as `input + output` only when both are present (else `None`), compute `estimated_cost_usd` via `estimate_cost(...)`, and accept `token_usage=None` to produce an all-`None`-tokens `LLMUsage` carrying just the identity fields (acceptance 2; depends on T2000, T2001).
- [X] T2003 [UT] Add `usage: LLMUsage | None = None` to `AssistiveResult` in `src/agent_foundation/llm/result.py` as an additive field alongside the existing `token_usage: TokenUsage | None`, so the normalized response carries the cost-annotated, identity-tagged usage without breaking existing `AssistiveResult` consumers (acceptance 1; FR-016; depends on T2000).
- [X] T2004 [UT] Populate `result.usage` in `LLMRuntime.reason()` (`src/agent_foundation/llm/runtime.py`): on the **model** path build it from the provider `RawCompletion.token_usage` + the request `agent_id` + the resolved `model_id` + the `prompt_ref`/`prompt_id`; on the **cache** path reuse the recorded result's `usage` unchanged; on the **fallback** path set `usage = build_llm_usage(None, model_id=..., agent_id=..., prompt_id=...)` (identity only, `None` tokens/cost) so the field is always present and never misattributes cost to a non-model step (acceptance 1; FR-010; depends on T2002, T2003).
- [X] T2005 [UT] Carry usage into the audit trail: add `usage: LLMUsage | None = None` to `ReasoningAuditRecord` in `src/agent_foundation/llm/audit.py` (additive; coordinate with the prompt-registry slice that also extends this record) and populate it from `result.usage` at write time, so token consumption + estimated cost are reconstructable by `correlation_id` with no live model (acceptance 3; FR-011/012; depends on T2004).
- [X] T2006 [P] [UT] Export `LLMUsage` and `estimate_cost` from the `src/agent_foundation/llm/__init__.py` public surface (depends on T2000, T2001).

### Demo UI display for LLM Usage

- [X] T2007 [UT] Surface usage in the Demo UI reasoning-step row: extend the safe renderer in `apps/demo_ui/reasoning_summary.py` (coordinate with the Safety slice's `T1917`) to add `input_tokens` / `output_tokens` / `total_tokens` / `estimated_cost_usd` / `model_id` from `ReasoningAuditRecord.usage`, rendering an em dash `—` when `usage` is `None` or a field is `None`. If `reasoning_summary.py` is not yet present, add a standalone `format_usage(usage: LLMUsage | None) -> str` helper in `apps/demo_ui/reasoning_summary.py` the case view can call (acceptance 3).

### Tests for LLM Usage Tracking (stub-backed, offline)

- [X] T2008 [P] [UT] Unit test `tests/unit/llm/test_llm_usage.py`: full provider usage → `build_llm_usage` yields `total_tokens == input + output` and a positive `estimated_cost_usd` for a priced `model_id`; identity fields (`model_id`, `agent_id`, `prompt_id`) are set (acceptance 1).
- [X] T2009 [P] [UT] Unit test in `tests/unit/llm/test_llm_usage.py`: missing/partial provider usage — `token_usage=None`, partial token counts, and an unknown `model_id` each yield `total_tokens=None` and `estimated_cost_usd=None` with no exception raised (acceptance 2).
- [X] T2010 [P] [UT] Unit test in `tests/unit/llm/test_llm_usage.py`: `LLMUsage` round-trips through `model_dump_json()` / `model_validate_json()` with `estimated_cost_usd` serialized as a string and reparsed to an equal `Decimal` — proving it is carryable on the audit topic and displayable in the UI (acceptance 3).
- [X] T2011 [P] [UT] Integration-ish unit test in `tests/unit/llm/test_runtime_usage.py` (stub-backed): a model-path `LLMRuntime.reason()` returns `AssistiveResult.usage` with the calling `agent_id`, resolved `model_id`, and token counts; a forced **fallback** path returns `usage` with identity fields set and `None` tokens/cost; a **cache** replay returns the recorded `usage` unchanged (acceptance 1; FR-010).
- [X] T2012 [P] [UT] Unit test `tests/unit/llm/test_audit_usage.py`: the emitted `ReasoningAuditRecord.usage` matches `result.usage` and is queryable by `correlation_id` with no live model (acceptance 3; FR-011/012).
- [X] T2013 [P] [UT] Demo UI test `tests/unit/demo_ui/test_usage_display.py`: the renderer/`format_usage` formats a populated `LLMUsage` into a row showing tokens + cost, and a `None`-usage record renders the safe `—` placeholder without raising (acceptance 3).

### Docs for LLM Usage Tracking

- [X] T2014 [P] [UT] Add an `LLMUsage` section to `specs/008-agent-llm-runtime/data-model.md` (fields, the `model_id`/`agent_id`/`prompt_id` identity tags, the `estimate_cost` pricing table, and the graceful-missing-data rule) and a short "usage & cost tracking" note to `specs/008-agent-llm-runtime/quickstart.md`.

**Checkpoint**: `LLMUsage` is importable, attached to every `AssistiveResult` and `ReasoningAuditRecord`,
serializes cleanly (Decimal → string), degrades to `None` tokens/cost when a provider reports no usage,
and is rendered by the Demo UI — all unit tests green against the stub with no AWS.

### LLM Usage Tracking — dependencies & parallel notes

- Sequence within slice: T2000 → T2001 → T2002 (T2000 in `result.py`, T2001/T2002 in `pricing.py`); T2003 (edits `result.py`) can follow T2000 in parallel with T2001/T2002; then T2004 (edits `runtime.py`) → T2005 (edits `audit.py`); T2006 [P] and T2007 [P] once their deps land.
- Tests T2008–T2014 are `[P]` across distinct files once their implementation tasks land (T2008–T2010 share `test_llm_usage.py` but assert independently; T2011/T2012/T2013 are separate files; T2014 edits docs).
- This slice consumes `TokenUsage`/`AssistiveResult`/`RawCompletion`/`LLMRuntime.reason`/`ReasoningAuditRecord` from the core-runtime slices and the reasoning-summary renderer from the Safety slice; it has no dependency on the CRA / billing / risk adoption or LangGraph slices. `ReasoningAuditRecord` is extended additively — coordinate the field add with the prompt-registry and safety slices that also touch `audit.py`.

<!-- SLICE:bedrock-client-factory -->
---

## Phase BR: Bedrock Client Factory (feature input; contracts/provider-protocol.md, research R3/R12)

**Goal**: Provide `create_bedrock_client(config: BedrockModelConfig)` — the single factory that builds a
region-configured boto3 `bedrock-runtime` client, so the offline→cloud switch has exactly one place that
touches the AWS SDK (FR-002, R2). The client is **model-agnostic**: the `model_id` is supplied per-call at
invoke time and is never baked into the client. The LLM remains assistive only; this factory creates
transport, never a binding verdict.

**Layering note (avoid overlap with the AL slice)**: the AgentLLM wrapper slice
(`<!-- SLICE:agent-llm-bedrock-wrapper -->`, T1200-T1221) currently builds its boto3 client inline in
`AgentLLM.__init__` (T1205) and adapts it in the provider (T1213). This slice extracts that into the one
reusable `create_bedrock_client(config)` factory; T1205 and T1213 SHOULD call it instead of constructing a
client themselves (coordinated below). This slice owns only the factory + its tests, not `AgentLLM` or the
provider's `invoke()`.

**Independent Test**: With boto3 monkeypatched (no network, no real credentials),
`create_bedrock_client(BedrockModelConfig(region="us-east-1", model_id="anthropic.claude-3-5-sonnet-20241022-v2:0", ...))`
calls `boto3.client("bedrock-runtime", region_name="us-east-1", config=<botocore Config>)`, passes **no**
explicit `aws_access_key_id`/`aws_secret_access_key` (relies on the default credential chain → local AWS
creds/role for local testing), derives connect/read timeouts from `timeout_seconds` and retry
`max_attempts` from `retry_max_attempts`, and produces byte-identical client kwargs when only `model_id`
changes (proving the model id is not hard-coded into the client). With boto3 not importable the module
still imports and the factory raises a clear typed error — all offline, no AWS.

**Acceptance criteria covered** (verbatim from feature input): uses boto3 (the AWS SDK Bedrock adapter);
supports region-specific config; does not hard-code model IDs; uses local AWS credentials during local
testing.

**Prerequisite (owned by other slices)**: `BedrockModelConfig` (`provider`, `region`, `model_id`,
`temperature`, `max_tokens`, `timeout_seconds`, `retry_max_attempts`) in
`src/agent_foundation/llm/config.py` (CFG slice T1020, also consumed by the config-loader slice); the
`ModelProvider`/`RawCompletion`/`ProviderError` seam in `src/agent_foundation/llm/providers/base.py` and
`select_provider` in `src/agent_foundation/llm/providers/__init__.py` (CFG slice T1025) for the wiring
task. If CFG has not landed, T2201 may use a minimal local `BedrockModelConfig` import shim that CFG later
reconciles.

### Implementation for Bedrock Client Factory

- [X] T2200 [BR] Ensure the optional `llm = ["boto3>=1.34"]` extra exists in `pyproject.toml` (idempotent — skip if the AL slice T1201 or CFG slice already added it), keeping `boto3` out of core deps so the default stub install needs no AWS SDK, per research R12 (FR-002, FR-014).
- [X] T2201 [BR] Implement `create_bedrock_client(config: BedrockModelConfig)` in `src/agent_foundation/llm/providers/bedrock.py`: lazily `import boto3`/`botocore` inside the function (module stays importable without the AWS SDK), and return `boto3.client("bedrock-runtime", region_name=config.region, config=<botocore Config>)`. Pass **no** explicit credential kwargs so boto3 resolves the default provider chain (env vars / shared config / SSO / instance role) — i.e. local AWS credentials during local testing (acceptance: uses boto3; uses local AWS credentials; FR-002).
- [X] T2202 [BR] Build the `botocore.config.Config` inside `create_bedrock_client` (`src/agent_foundation/llm/providers/bedrock.py`) from the config only: `region_name=config.region`, `connect_timeout`/`read_timeout` derived from `config.timeout_seconds`, and `retries={"max_attempts": config.retry_max_attempts, "mode": "standard"}` — so region and reliability budgets are config-supplied, never hard-coded at the call site (acceptance: supports region-specific config; FR-009/017) (depends on T2201).
- [X] T2203 [BR] Guarantee the client is model-agnostic in `src/agent_foundation/llm/providers/bedrock.py`: `create_bedrock_client` MUST NOT read, embed, or branch on `config.model_id` (the `model_id` is supplied later to `invoke_model`/`converse` by the provider/AgentLLM). Document in the docstring that no model id is baked into the client (acceptance: does not hard-code model IDs; FR-017) (depends on T2201).
- [X] T2204 [BR] Add the import guard in `src/agent_foundation/llm/providers/bedrock.py`: the module imports cleanly without `boto3` installed (mirroring the existing `agentcore_app.py` import-guard pattern), and `create_bedrock_client` raises a clear typed error (`ProviderError`/`ImportError` with an install hint, e.g. `pip install '...[llm]'`) only when actually invoked without boto3 present (FR-014, R12) (depends on T2201).
- [X] T2205 [BR] Make `create_bedrock_client` the single client source: have the Bedrock provider / `AgentLLM.__init__` (AL slice T1205) and the provider adapter (AL slice T1213) obtain their `bedrock-runtime` client via `create_bedrock_client(config)` — constructed/cached once at init, not per request — and pass the profile `model_id` only at `invoke_model`/`converse` call time. Coordinate with the AL slice so client construction is not duplicated (contracts/provider-protocol.md; FR-013) (depends on T2202, T2203).
- [X] T2206 [P] [BR] Export `create_bedrock_client` from the providers package surface (`src/agent_foundation/llm/providers/__init__.py`, and re-export from `src/agent_foundation/llm/__init__.py` if the package surfaces providers) (depends on T2201).

### Tests for Bedrock Client Factory

- [X] T2207 [P] [BR] Unit test `tests/unit/llm/test_bedrock_client.py` (offline, boto3 monkeypatched — no network/credentials): `create_bedrock_client` calls `boto3.client` with service `"bedrock-runtime"` and `region_name == config.region` (acceptance: supports region-specific config).
- [X] T2208 [P] [BR] Unit test in `tests/unit/llm/test_bedrock_client.py`: the factory passes **no** explicit `aws_access_key_id`/`aws_secret_access_key`/`aws_session_token` kwargs, so boto3 uses the default credential chain / local AWS creds during local testing (acceptance: uses local AWS credentials).
- [X] T2209 [P] [BR] Unit test in `tests/unit/llm/test_bedrock_client.py`: model-agnostic client — calling `create_bedrock_client` with two configs that differ only in `model_id` yields identical `boto3.client` kwargs (no `model_id` anywhere in the call), proving the model id is not hard-coded into the client (acceptance: does not hard-code model IDs).
- [X] T2210 [P] [BR] Unit test in `tests/unit/llm/test_bedrock_client.py`: the botocore `Config` carries `connect_timeout`/`read_timeout` derived from `config.timeout_seconds` and `retries["max_attempts"] == config.retry_max_attempts` (config-supplied reliability budgets).
- [X] T2211 [P] [BR] Unit test in `tests/unit/llm/test_bedrock_client.py`: import-guard — with `boto3` made non-importable (monkeypatch `sys.modules`/import), the module still imports and `create_bedrock_client` raises a clear typed error with an install hint, never a bare `ModuleNotFoundError` at import time.

### Docs for Bedrock Client Factory

- [X] T2212 [P] [BR] Add a `create_bedrock_client` snippet to `specs/008-agent-llm-runtime/quickstart.md`: switching `AGENT_LLM_MODE=bedrock` with `AWS_REGION` set uses local AWS credentials and a region-specific client, with no calling-agent code change (US8.2, FR-014).

**Checkpoint**: `create_bedrock_client(config)` builds a region-configured, model-agnostic
`bedrock-runtime` client off the default credential chain, raises clearly when boto3 is absent, and is the
single client source the Bedrock provider / `AgentLLM` use — all unit tests green offline with boto3
monkeypatched and no AWS.

### Bedrock Client Factory — dependencies & parallel notes

- Sequence within slice: T2200 (pyproject extra) ∥ T2201 → T2202/T2203/T2204 (all edit `bedrock.py`, so sequential) → T2205 (wires provider/AgentLLM) ; T2206 export after T2201.
- T2207–T2211 [P] share one test file (`tests/unit/llm/test_bedrock_client.py`) but assert independently; T2212 edits `quickstart.md` — all parallel once T2205/T2206 land.
- This slice consumes `BedrockModelConfig` from the CFG slice (T1020-T1025) and coordinates with the AgentLLM wrapper slice (T1205/T1213) and the Bedrock provider slice on `bedrock.py`; it has no dependency on the LangGraph, risk/CRA/billing adoption, structured-output, or YAML-profiles slices.

---

<!-- SLICE:agentcore-local-compatibility -->
## Phase AC: AgentCore Local Compatibility — Call Bedrock under `agentcore dev` (feature input; research R9; contracts/provider-protocol.md "AgentCore provider", contracts/model-config.md; FR-002/FR-014/FR-017)

**Goal**: Make the runtime usable under the local AgentCore dev server (`agentcore dev`) so an agent
performs its assistive reasoning by calling **Bedrock** while running locally, using the standard AWS
env (`AWS_PROFILE`, `AWS_REGION`, `BEDROCK_MODEL_ID`). Implement the concrete `agentcore` provider
(deferred by the CFG scaffold T1025), give missing/invalid AWS credentials a clear, actionable error
distinct from the missing-model-config error (CFG2 slice), and document + verify the `agentcore dev`
run path in the README and quickstart. The offline stub remains the default; everything in this slice
is opt-in via `AGENT_LLM_MODE=agentcore` and stays import-safe without `bedrock-agentcore` installed.

**Independent Test**: With `AGENT_LLM_MODE=agentcore`, `AWS_PROFILE`, `AWS_REGION`, and
`BEDROCK_MODEL_ID` set, run an agent under `agentcore dev` and confirm its assistive task reaches
Bedrock and records a `ReasoningAuditRecord` with `reasoning_path=model`; unset the credentials and
confirm a single clear error naming the missing AWS profile/region/credentials (not a stack trace);
with no env set at all, the same code path falls back to the stub offline (no AWS). The provider unit
+ credential-error tests pass with `bedrock-agentcore` NOT installed and no AWS credentials present.

**Acceptance criteria covered** (from feature input): (1) Agents can call Bedrock during local
AgentCore runs; (2) Missing AWS credentials produce a clear error; (3) README explains model-access
prerequisites and the `agentcore dev` run is documented + verified.

**Story lineage** (slice-local labels): US1 = call Bedrock under AgentCore (AC#1, FR-002/R9) ·
US2 = clear missing-credentials error (AC#2) · US3 = docs + verify `agentcore dev` (AC#3). Labeled
`[AC]` within this slice.

**Dependencies (other slices, do NOT re-implement here)**: the core `LLMRuntime`/`ModelProvider`
protocol + `RawCompletion` (data-model §9; contracts/provider-protocol.md); the `select_provider`
scaffold T1025 (`src/agent_foundation/llm/providers/__init__.py`); the Bedrock invocation wrapper from
the `[AL]` slice (`src/agent_foundation/llm/client.py` / `providers/bedrock.py`, T1200-T1221); and the
layered config loader `load_model_config` from the `[CFG2]` slice (T1040-T1057). This slice REUSES
those and only adds the `agentcore` provider, the credentials error, env-alias wiring, and docs.

### Implementation for User Story 1 (call Bedrock under AgentCore — AC#1)

- [X] T7700 [AC] [US1] Implement the concrete `AgentCoreProvider` (`ModelProvider`) in `src/agent_foundation/llm/providers/agentcore.py`: import-guard `bedrock_agentcore` exactly like `apps/agents/*/agentcore_app.py` (try/except ImportError -> module importable without the optional dep); `invoke(prompt, profile) -> RawCompletion` delegates to the Bedrock invocation path (reuse the `[AL]` wrapper / `providers/bedrock.py`) so the model call reaches Bedrock via boto3 `bedrock-runtime` while the process runs under the local AgentCore runtime; honor `profile.model_id`/`region`/`temperature` and preserve the prompt-cache breakpoints; raise `ProviderError` (not swallow) so the runtime can fall back (contracts/provider-protocol.md "AgentCore provider"; FR-002/R9).
- [X] T7701 [AC] [US1] Wire `agentcore` into `select_provider(mode)` in `src/agent_foundation/llm/providers/__init__.py` (extend the T1025 scaffold): dispatch `mode == "agentcore"` -> `AgentCoreProvider`; keep `stub` the default and the `bedrock`/`agentcore` branches import-guarded so offline imports never require boto3 or bedrock-agentcore (FR-014).
- [X] T7702 [AC] [US1] Add AWS-standard env aliases to `load_model_config` in `src/agent_foundation/llm/config.py` (EXTEND the CFG2 loader T1048-T1050, do NOT redefine its models): when `AGENT_LLM_MODEL` is unset, accept `BEDROCK_MODEL_ID` -> `model_id`; when `AGENT_LLM_REGION` is unset, accept `AWS_REGION`/`AWS_DEFAULT_REGION` -> `region`; leave AWS_PROFILE/credentials to the boto3 default chain (loader still reads no credentials). Document precedence: explicit `AGENT_LLM_*` > AWS-standard alias > YAML > default (FR-017; so the documented `agentcore dev` env resolves).
- [X] T7703 [P] [AC] [US1] Unit test `tests/unit/llm/test_agentcore_provider.py`: with `bedrock_agentcore` absent and the Bedrock client patched/stubbed, `select_provider("agentcore")` returns an `AgentCoreProvider` whose `invoke` returns a valid `RawCompletion` (text + `TokenUsage`, `model_id` from `BEDROCK_MODEL_ID`) and preserves the cache-eligible prefix; module imports cleanly without the optional dep (SC-006, offline).
- [X] T7704 [P] [AC] [US1] Env-alias test `tests/unit/llm/test_config_agentcore_env.py`: `load_model_config` with `AGENT_LLM_MODE=agentcore`, `BEDROCK_MODEL_ID=...`, `AWS_REGION=us-east-1` resolves `model_id`/`region`; explicit `AGENT_LLM_MODEL`/`AGENT_LLM_REGION` override the AWS aliases; no credentials read.

### Implementation for User Story 2 (clear missing-credentials error — AC#2)

- [X] T7710 [AC] [US2] Add a typed `ProviderCredentialsError(ProviderError)` in `src/agent_foundation/llm/providers/base.py` and raise it from `AgentCoreProvider`/`providers/bedrock.py` when boto3 credential/region resolution fails (`botocore.exceptions.NoCredentialsError`, `ProfileNotFound`, `NoRegionError`, `UnauthorizedSSOTokenError`): the message MUST name the missing piece (AWS profile / region / credentials) and the remediation (`aws configure` / `aws sso login`, set `AWS_PROFILE`/`AWS_REGION`) — never leak a raw botocore traceback. Distinct from CFG2 `ModelConfigError` (missing *model config*, not *credentials*).
- [X] T7711 [AC] [US2] In `src/agent_foundation/llm/runtime.py` (reasoning path), map `ProviderCredentialsError` to a `fallback` `AssistiveResult` with `failure_reason=model_unavailable`, copy the clear message into the `ReasoningAuditRecord` (`failure_reason` + safe note) and emit a structured `logger.error` once with the actionable text, so an operator running `agentcore dev` sees exactly what to fix without re-running (FR-009/FR-011; binding decision unaffected).
- [X] T7712 [P] [AC] [US2] Credential-error test `tests/unit/llm/test_agentcore_credentials_error.py`: with the boto3 credential chain forced empty (no `AWS_PROFILE`, no creds) and bedrock-agentcore stubbed, `AgentCoreProvider.invoke` raises `ProviderCredentialsError` whose message names AWS profile/region; the runtime returns a `fallback` result with recorded reason and logs the actionable message once; runs offline with no real AWS.

### Implementation for User Story 3 (document + verify `agentcore dev` — AC#3)

- [X] T7720 [P] [AC] [US3] Add an "LLM model-access prerequisites" section to `README.md`: (a) request Bedrock model access for the target Claude model in the AWS console (Bedrock > Model access); (b) the offline default (`AGENT_LLM_MODE` unset -> stub, no AWS); (c) the local AgentCore dev env — `AGENT_LLM_MODE=agentcore`, `AWS_PROFILE=<your-profile>`, `AWS_REGION=us-east-1`, `BEDROCK_MODEL_ID=<model-id>`; (d) the install extra `pip install -e ".[llm]"` and that `agentcore dev` needs `bedrock-agentcore`. Link to specs/008-agent-llm-runtime/quickstart.md.
- [X] T7721 [P] [AC] [US3] Add a "Run under AgentCore local dev (`agentcore dev`)" step to `specs/008-agent-llm-runtime/quickstart.md`: the exact env block above, the `agentcore dev` launch command against an agent entrypoint (e.g. `apps/agents/customer_resolution/agentcore_app.py`), the expected outcome (assistive task calls Bedrock; `ReasoningAuditRecord.reasoning_path=model`), and the missing-credentials clear-error example output. Note it is opt-in; offline stub remains the documented default (US8).
- [X] T7722 [AC] [US3] Add a guarded verification smoke `tests/integration/llm/test_agentcore_dev_smoke.py` (auto-skipped without AWS creds + bedrock-agentcore, mirroring the existing bedrock `-k bedrock` skip): assert that under `agentcore` mode an agent assistive call reaches Bedrock and records a `model`-path audit record, and that clearing credentials yields the `ProviderCredentialsError` clear message — the executable counterpart of the manual quickstart verification.
- [X] T7723 [P] [AC] [US3] Document the manual verification procedure inline in quickstart §AgentCore: start `agentcore dev` with the env set, invoke the agent, confirm Bedrock is called and audited; then unset `AWS_PROFILE`/credentials and confirm the single clear error — record both expected outputs so a reviewer can verify acceptance criteria 1 & 2 by hand.

### Polish (AgentCore slice)

- [X] T7724 [AC] Run `ruff check` / `ruff format` and `mypy src/agent_foundation/llm/providers/agentcore.py src/agent_foundation/llm/config.py`, then `pytest tests/unit/llm/test_agentcore_provider.py tests/unit/llm/test_config_agentcore_env.py tests/unit/llm/test_agentcore_credentials_error.py` — all green offline with `bedrock-agentcore` NOT installed and no AWS credentials (SC-006).

**Checkpoint (AgentCore slice)**: `agentcore` mode resolves config from the documented
`AWS_PROFILE`/`AWS_REGION`/`BEDROCK_MODEL_ID` env, an agent under `agentcore dev` reaches Bedrock and
is audited on the `model` path, missing credentials produce one clear actionable error (binding
decision unaffected), and README + quickstart document and verify the run — all unit tests green
offline; the Bedrock/AgentCore paths are exercised only by the auto-skipped integration smoke.

### AgentCore slice — dependencies & parallel notes

- Sequence within slice: T7700 (provider) -> T7701 (wire select_provider) -> T7702 (env aliases); then T7710 (typed error) -> T7711 (runtime mapping). Docs T7720/T7721 and tests T7703/T7704/T7712/T7722/T7723 are `[P]` across distinct files once their target code task lands. T7724 runs last.
- Depends on: core runtime + `ModelProvider` protocol, the `[AL]` Bedrock wrapper (T1200-T1221), the `select_provider` scaffold (T1025), and the `[CFG2]` loader (T1040-T1057). Does NOT edit any deterministic engine (`decision_engine.py`/`rules_engine.py`/`scoring.py`) — binding verdicts stay deterministic (FR-003/004).
- No dependency on the CRA/risk/billing adoption slices; this slice only adds the provider, the credentials error, env-alias wiring, and docs.

---

## Phase CORE: Shared LLM Runtime — Core Package Assembly (user input: "Create shared package"; plan.md package layout; data-model §1-6,§9-11; FR-001/006/007/009/010/011/014/015)

**Location decision**: the package lives at `src/agent_foundation/llm/` (the location plan.md and every other 008 slice already import from), *not* a standalone `packages/llm-runtime/`. The user's requested module names map onto the established surface as follows — this slice does **not** create colliding duplicates:

| User-requested file | Where it lives in this codebase | Owning slice |
|---|---|---|
| `client.py` | `runtime.py` (`LLMRuntime.reason`) is the assistive entry point; the Bedrock HTTP wrapper `client.py` (`AgentLLM`) | this slice / **AL** (T1203-T1221) |
| `models.py` | split into `request.py` (`AssistiveRequest`, `TaskKind`) + `result.py` (`AssistiveResult`, `ReasoningPath`, `FailureReason`, `TokenUsage`) | **this slice (CORE)** |
| `factory.py` | `factory.py` (`build_runtime`) | **this slice (CORE)** |
| `config.py` | `config.py` (`RuntimeConfig`, `ModelProfile`, `resolve_profile`) | **CFG** (T1020-T1025) |
| `structured.py` | `structured.py` (`invoke_structured`, validate-and-repair) | **SO** (T1100-T1112) |
| `prompts.py` | `prompts.py` (`PromptTemplate` registry) | **PR** |
| `usage.py` | `usage.py` (`LLMUsage`, `build_llm_usage`) + base `TokenUsage` in `result.py` | **UT** (T2008-T2012) / this slice |
| `errors.py` | `errors.py` (base hierarchy) | **this slice (CORE)** |
| `langgraph.py` | `langgraph.py` (`as_node` skeleton + `create_langgraph_llm_node`) | this slice / **LG** (T960-T972) |
| `tests/` | `tests/unit/llm/` | per-slice |

**This CORE slice authors the central runtime surface that every other slice lists as a "core runtime owned by other slices" prerequisite but nobody else implements**: `request.py`, `result.py`, `runtime.py`, `providers/base.py`, `providers/stub.py`, `store.py`, `audit.py`, `errors.py`, `factory.py`, the `as_node` skeleton, and the package `__init__.py`. It is the MVP front door (`LLMRuntime.reason(request) -> AssistiveResult`) on which CFG/SO/PR/AL/BR/UT/SAF/AE/LG/CRA/RK all build.

**User acceptance criteria encoded here**: the package is reusable by all agents (T3428), contains **no business-domain logic** (T3427 forbids importing `apps.agents.*` / `decision_engine` / `rules_engine` / `scoring`), and contains **no supervisor/router/orchestrator** logic (T3427 forbids `route`/`dispatch`/`orchestrate`/`supervise` symbols) — consistent with FR-003/FR-015 and SC-009.

**Coordination note (raced tasks.md)**: sibling slices co-edit some of these files. Every task below that touches a shared file uses the proven *reuse-the-sibling-owned-definition-if-present, else create it* rule (as T960/T1202 already do) so concurrent landings do not duplicate types. `src/agent_foundation/llm/` does not yet exist on disk — this slice creates it.

**Prerequisite (owned by other slices, reuse-if-present)**: `config.py` (`RuntimeConfig`/`ModelProfile`/`resolve_profile`, CFG T1020-T1025), `structured.py` (`invoke_structured`, SO T1100-T1112), `prompts.py` (`PromptTemplate`, PR), `usage.py` (`LLMUsage`/`build_llm_usage`, UT T2008-T2012). Where a prerequisite has not yet landed, the task provides a minimal inline shim and notes the sibling task that supersedes it.

### Phase CORE.1: Setup & package scaffolding

- [X] T3400 [CORE] Create the package directory `src/agent_foundation/llm/` with a placeholder `src/agent_foundation/llm/__init__.py`, the subpackage `src/agent_foundation/llm/providers/` with `providers/__init__.py`, and the test package `tests/unit/llm/__init__.py` — establishing the layout from plan.md "Source Code".
- [X] T3401 [P] [CORE] In `pyproject.toml` under `[project.optional-dependencies]`, add (only if absent) the `llm = ["boto3>=1.34"]` and `langgraph = ["langgraph>=0.2", "langchain-aws>=0.2"]` extras; leave existing `http`/`ui`/`dev` extras untouched. Coordinate with CFG/AL/BR (reuse-if-present) (plan Technical Context; Complexity Tracking).
- [X] T3402 [P] [CORE] Create `src/agent_foundation/llm/errors.py` with the base exception hierarchy `LLMRuntimeError(Exception)` and subclasses `ModelUnavailableError`, `ModelTimeoutError`, `ContextLimitExceededError`, `InvalidModelOutputError`, each carrying the `FailureReason` it maps to (data-model §5). Note siblings may home `LLMClientError` (AL), `StructuredError` (SO), `ModelConfigError` (CFG) here or import from here (FR-006/009).

### Phase CORE.2: Foundational data types (BLOCKS every CORE user story)

- [X] T3403 [CORE] Create `src/agent_foundation/llm/request.py`: a `TaskKind` str-enum (`classify`, `extract_intent`, `draft_response`, `summarize_reasoning`) and a frozen Pydantic v2 `AssistiveRequest` with the data-model §1 fields (`task_kind`, `agent_id: str`, `correlation_id: UUID`, `causation_id: UUID`, `instructions: str`, `grounding_inputs: dict[str, Any]`, `output_schema: type[BaseModel]`, `examples: list[dict] | None`, `idempotency_key: str`, `fallback: Callable[[], BaseModel]`); validators: `instructions` non-empty, `output_schema` is a `BaseModel` subclass, `grounding_inputs` JSON-serializable; when `idempotency_key` is omitted, derive it from `correlation_id + task_kind + stable hash(grounding_inputs)` (data-model §1-2; FR-001/007).
- [X] T3404 [P] [CORE] Create `src/agent_foundation/llm/result.py`: enums `ReasoningPath` (`model`/`cache`/`fallback`) and `FailureReason` (`model_unavailable`/`timeout`/`invalid_output`/`missing_inputs`/`context_limit_exceeded`/`unable_to_produce`); the frozen `TokenUsage` (`input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`) **reusing the sibling-owned definition if present (AL T1202 / UT), else adding it here as the canonical source — do not duplicate**; and the frozen `AssistiveResult` per data-model §3 (`value: BaseModel`, `reasoning_path`, `token_usage: TokenUsage | None`, `cache_hit: bool`, `failure_reason: FailureReason | None`, `model_id: str | None`, `latency_ms: int`) (data-model §3-6; FR-010).

### Phase CORE.3: US1 — Perform an assistive reasoning task (Priority: P1) 🎯 MVP

**Goal**: an agent hands the runtime grounding inputs + an output schema and gets back a populated, schema-valid structured result from the (stub) model — the front door for every other behavior.
**Independent test**: stub-backed `reason()` returns a schema-valid `AssistiveResult.value`, and meaningfully different grounding yields a correspondingly different result, with no cloud access (US1 Independent Test; SC-001/SC-006).

- [X] T3405 [CORE] [US1] Create `src/agent_foundation/llm/providers/base.py`: the `ModelProvider` Protocol (`async def invoke(self, prompt: str, profile: ModelProfile) -> RawCompletion`) and the frozen `RawCompletion` (`text`, `token_usage`, `cache_hit`, `model_id`) per data-model §9 / contracts/provider-protocol.md. Reuse-if-present (SO/AL list this as a prereq).
- [X] T3406 [CORE] [US1] Create `src/agent_foundation/llm/providers/stub.py`: a deterministic offline `StubProvider` (the default, no AWS) that returns a `RawCompletion` derived deterministically from the rendered prompt (stable hash → canned schema-shaped JSON) so identical inputs yield identical output and meaningfully different grounding yields different output (US1 acceptance 2; FR-014; contracts/stub-model-contract.md).
- [X] T3407 [CORE] [US1] In `src/agent_foundation/llm/providers/__init__.py`, provide `select_provider(profile: ModelProfile) -> ModelProvider` dispatching on `profile.mode` and defaulting to `StubProvider` — **reuse the CFG-owned `select_provider` scaffold if T1025 already created it** (coordinate; reuse-if-present), wiring the concrete stub from T3406 (FR-014; contracts/provider-protocol.md).
- [X] T3408 [CORE] [US1] Create `src/agent_foundation/llm/runtime.py` with `class LLMRuntime` and `async def reason(self, request) -> AssistiveResult` implementing the ordered happy path: `resolve_profile(agent_id, task_kind)` (config), render the prompt (`prompts.PromptTemplate` if present, else a minimal inline render), `provider.invoke()`, validate against `output_schema` (minimal inline `model_validate_json` — **SO T1105 supersedes this with `invoke_structured`**), and return a model-path `AssistiveResult` (`reasoning_path=model`, `token_usage`, `model_id`, `latency_ms` via `perf_counter`) (data-model Relationships; FR-001).
- [X] T3409 [CORE] [US1] Create `src/agent_foundation/llm/factory.py`: `build_runtime(config: RuntimeConfig | None = None) -> LLMRuntime` reading config (default offline stub), selecting the provider via `select_provider`, and injecting the result store (T3416) and audit writer (T3419) — the single assembly point so call sites never construct providers directly (user "factory.py"; FR-017).
- [X] T3410 [CORE] [US1] Populate `src/agent_foundation/llm/__init__.py` public surface exporting `LLMRuntime`, `build_runtime`, `AssistiveRequest`, `AssistiveResult`, `TaskKind`, `ReasoningPath`, `FailureReason`, `TokenUsage`; keep additions append-only so sibling exports are not clobbered (reuse-if-present) (FR-016).
- [X] T3411 [P] [CORE] [US1] Unit test `tests/unit/llm/test_runtime_reason.py` (stub-backed, offline): `reason()` returns a populated schema-valid `AssistiveResult.value`; and two requests whose grounding differs meaningfully yield results that differ accordingly (US1 acceptance 1-2; SC-001).

### Phase CORE.4: US3 — Stay within schema & domain bounds (Priority: P1)

**Goal**: a fluent-but-wrong model response can never surface as the assistive result.
**Independent test**: out-of-enum / malformed / hallucinated-fact stub output is rejected, never returned (US3 Independent Test).

- [X] T3412 [CORE] [US3] In `src/agent_foundation/llm/runtime.py`, add the validation seam: when provider output fails `output_schema` validation or asserts content absent from `grounding_inputs`, do not return it — route to repair/fallback and never surface an invalid `value`. Keep the seam delegable to `structured.invoke_structured` (SO T1105 supersedes the inline check) (FR-005/006; US3).
- [X] T3413 [P] [CORE] [US3] Unit test `tests/unit/llm/test_core_validation.py` (stub-backed): forcing the stub to emit out-of-enum / malformed / hallucinated-fact output makes `reason()` return a fallback or `unable_to_produce` result with a recorded `failure_reason`, never an invalid `value` (US3 acceptance 1-3; SC-001). The SO slice owns the exhaustive repair tests.

### Phase CORE.5: US5 — Degrade safely when the model is unavailable (Priority: P1)

**Goal**: a model outage degrades to the agent's pre-LLM behavior, never blocks, never fabricates.
**Independent test**: forced provider failure/timeout returns a fallback-flagged result with a recorded reason within the budget (US5 Independent Test; SC-004).

- [X] T3414 [CORE] [US5] In `src/agent_foundation/llm/runtime.py`, bound the model wait with `asyncio.wait_for(profile.timeout_seconds)` and wrap provider+validation in try/except mapping `errors.py` types and timeout to a `FailureReason`; on failure within the retry budget invoke `request.fallback()` and return `AssistiveResult(reasoning_path=fallback, failure_reason=..., model_id=None)`; expose `assist_or_fallback(...)` as the public convenience wrapper agents call. Never block indefinitely (FR-009; US5 acceptance 1-3; SC-004).
- [X] T3415 [P] [CORE] [US5] Unit test `tests/unit/llm/test_fallback_paths.py` (stub-backed): a provider forced to raise / time out / return persistently-invalid output yields a fallback-flagged result with a recorded reason, returns within the time budget, and is distinguishable from a model result (`reasoning_path == fallback`) (SC-004; FR-009/010).

### Phase CORE.6: US4 — Deterministic on replay / idempotent assistive results (Priority: P1)

**Goal**: re-processing the same request returns the identical recorded result with zero second model call.
**Independent test**: same idempotency key twice → identical output, provider invoked once, replay recorded as `cache` (US4 Independent Test; SC-003).

- [X] T3416 [CORE] [US4] Create `src/agent_foundation/llm/store.py`: `AssistiveResultStore` mirroring `agent_foundation.idempotency.IdempotencyTracker` (in-process LRU + compacted Kafka topic keyed by `idempotency_key`, reusing `RuntimeConfig` bootstrap servers) with `async get(key) -> AssistiveResult | None` and `async put(key, result) -> None`; JSON (de)serialize `AssistiveResult` for the topic (data-model §11; FR-008).
- [X] T3417 [CORE] [US4] In `src/agent_foundation/llm/runtime.py`, add the replay short-circuit at the top of `reason()`: `store.get(idempotency_key)` → on hit return the recorded result as `reasoning_path=cache` with **zero** provider calls; on a model-path success `store.put(...)` it (FR-007/008; US4; SC-003).
- [X] T3418 [P] [CORE] [US4] Unit test `tests/unit/llm/test_idempotency_replay.py` (stub-backed): the same request issued twice returns identical structured output, the provider is invoked exactly once (spy/counter), and the replay is reported as the `cache` path (SC-003; US4 acceptance 1-3).

### Phase CORE.7: US6 — Audit the reasoning step end to end (Priority: P2)

**Goal**: every reasoning step leaves one correlated audit record reconstructable with no live model.
**Independent test**: after one `reason()`, querying the audit trail by `correlation_id` shows the step with its path, model, validated result, and causal link (US6 Independent Test; SC-005).

- [X] T3419 [CORE] [US6] Create `src/agent_foundation/llm/audit.py`: the frozen `ReasoningAuditRecord` (data-model §10 fields) and `async write_reasoning_audit(publisher, record)` that emits it through the **existing** `agent_foundation.audit.store.write_audit` path on the **existing** `agent.audit.v1` topic (no new topic/contract; FR-011/015); build `grounding_digest` as a compact model-free digest and `prompt_ref` as a hash (never the raw prompt). Coordinate with SAF (redaction T1911-T1914) and AE (events T3007) which augment this module (reuse-if-present).
- [X] T3420 [CORE] [US6] In `src/agent_foundation/llm/runtime.py`, emit exactly one `ReasoningAuditRecord` per `reason()` across all three paths (model/cache/fallback) carrying `agent_id`, `correlation_id`, `causation_id`, `task_kind`, `model_id`/`model_params`, `prompt_ref`, `grounding_digest`, `reasoning_path`, `result_summary`, `token_usage`, `cache_hit`, `latency_ms`, `outcome`, `failure_reason` (FR-010/011/012).
- [X] T3421 [P] [CORE] [US6] Unit test `tests/unit/llm/test_runtime_audit.py` (stub-backed): one `reason()` writes one `ReasoningAuditRecord` queryable by `correlation_id` (via `audit.store.query_by_correlation`) with the reasoning path recorded, distinguishable from any binding decision, reconstructable with no live model (SC-005; FR-011/012).

### Phase CORE.8: US7 — Cache repeated context (Priority: P2)

**Goal**: cache reuse for the shared stable prefix is observable in reasoning metadata.
**Independent test**: warm vs cold calls surface `cache_hit`/cache tokens in the result and audit record (US7 Independent Test; SC-008).

- [X] T3422 [CORE] [US7] In `src/agent_foundation/llm/runtime.py`, thread prompt-cache observability end to end: take `cache_hit` + cache token counts from `RawCompletion`/`TokenUsage`, surface them on `AssistiveResult.cache_hit`/`token_usage`, and copy into the `ReasoningAuditRecord`; render via the cache-eligible stable-prefix `prompts.PromptTemplate` (PR slice) when present (FR-013; US7; SC-008).
- [X] T3423 [P] [CORE] [US7] Unit test `tests/unit/llm/test_prompt_cache.py` (stub-backed): a stub configured to report a warm prefix on the second of two calls sharing a large stable instruction block surfaces `cache_hit=True` and non-zero `cache_read_tokens` in both the result and the audit record (SC-008). BR/AL own the real Bedrock `cache_control` mapping.

### Phase CORE.9: US8 — Run locally with no cloud dependency (Priority: P2)

**Goal**: stub is the zero-config default; real providers are pure config switches with no call-site change.
**Independent test**: no AWS config → stub completes offline; switching `mode` re-routes without code change (US8 Independent Test; SC-006).

- [X] T3424 [CORE] [US8] Ensure `build_runtime`/`reason()` route purely by `RuntimeConfig`/`ModelProfile.mode` (`stub`|`bedrock`|`agentcore`) via `select_provider`, with `stub` the zero-config default and no calling-agent code change between modes; import-guard `boto3`/AgentCore so the offline path imports without the `[llm]` extra installed (FR-014/017; US8; SC-006).
- [X] T3425 [P] [CORE] [US8] Unit test `tests/unit/llm/test_offline_default.py`: with no `AGENT_LLM_*`/AWS env set, `build_runtime().reason()` completes on the stub with no cloud access; pointing `mode` at a fake non-stub provider re-routes `reason()` with no change to the call site (FR-014; SC-006; US8 acceptance 1-2).

### Phase CORE.10: LangGraph adapter skeleton (feature input; research R8)

- [X] T3426 [CORE] Create `src/agent_foundation/llm/langgraph.py` with `as_node(runtime, ...)` returning a graph-shaped async callable `(state: dict) -> dict` that calls `LLMRuntime.reason()` and merges the result into a namespaced state key; import `langgraph` lazily/optionally so the callable also runs on a plain dict and the package imports without the `[langgraph]` extra. The LG slice (T961-T972) builds `create_langgraph_llm_node` on top — reuse-if-present, do not duplicate (FR-001/015/016; plan `as_node`).

### Phase CORE.11: Polish & acceptance guardrails (user acceptance criteria)

- [X] T3427 [CORE] Guard test `tests/unit/llm/test_package_boundary.py` encoding the user acceptance criteria: assert no module under `src/agent_foundation/llm/` imports `apps.agents.*` or the binding engines (`decision_engine`, `rules_engine`, `scoring`) — **no business-domain logic** — and that the package exposes only assistive entry points (`reason`/`assist_or_fallback`/`build_runtime`/`as_node`) with **no** router/supervisor symbol (no `route`/`dispatch`/`orchestrate`/`supervise`) — **no supervisor/routing logic** (user acceptance; FR-003/015; SC-009).
- [X] T3428 [P] [CORE] Reusability test `tests/unit/llm/test_reusable_by_agents.py`: drive one `reason()` per `agent_id` (`customer-resolution`, `billing-entitlement-agent`, `risk-fraud-agent`) across each `TaskKind`, asserting the same package serves all three with only `agent_id`/`task_kind`/grounding differing and no per-agent branching inside the package (user acceptance "reusable by all agents"; FR-018 enablement).
- [X] T3429 [P] [CORE] Add a `build_runtime()` + `reason()` quickstart snippet (offline stub, one assistive call, then an audit query by `correlation_id`) to `specs/008-agent-llm-runtime/quickstart.md`.
- [X] T3430 [P] [CORE] Run `ruff format` + `ruff check` and `mypy` on the new `src/agent_foundation/llm/` core modules and `tests/unit/llm/` (GitHub CI parity); fix findings without changing the assistive boundary.

### CORE slice — dependencies & parallel notes

- **Phase order**: CORE.1 (setup) → CORE.2 (data types, blocks all) → CORE.3 (US1 MVP) → CORE.4-9 (US3/US5/US4/US6/US7/US8, each independently testable once US1 lands) → CORE.10 (LangGraph) → CORE.11 (polish/guardrails).
- **Sequential (same file `runtime.py`)**: T3408 → T3412 → T3414 → T3417 → T3420 → T3422 → T3424 all edit `runtime.py`; keep them in order. `result.py` (T3404) and `request.py` (T3403) are the only hard blockers for everything after.
- **Parallel [P]**: the test tasks (T3411, T3413, T3415, T3418, T3421, T3423, T3425, T3428) target distinct files and can run concurrently once their feature task lands; T3401/T3402 (pyproject/errors) are independent of T3400's dir creation only after the dir exists.
- **Cross-slice (reuse-if-present)**: `config.py` (CFG T1020-T1025), `structured.py` (SO T1100-T1112), `prompts.py` (PR), `usage.py`/`TokenUsage` (UT T2008-T2012 / AL T1202), `providers/__init__.py::select_provider` (CFG T1025), `providers/bedrock.py` (BR), `langgraph.py::create_langgraph_llm_node` (LG), `audit.py` augmentation (SAF T1911-T1914, AE T3007). This slice provides the minimal seam/shim and yields ownership of the richer implementation to those slices.
- **MVP**: CORE.1 + CORE.2 + CORE.3 (T3400-T3411) deliver a working, offline, stub-backed `reason()` the other slices and all three agents can build on.
