# Feature Specification: Agent LLM Runtime

**Feature Branch**: `008-agent-llm-runtime`

**Created**: 2026-06-10

**Status**: Draft

**Input**: User description: "Agent LLM Runtime"

## Overview

Every domain agent in this PoC (customer resolution, billing entitlement, risk & fraud) reaches its
verdict today through hand-written deterministic logic — a decision matrix, a rules engine, an additive
scoring table. That proves the *choreography* works, but the agents do no actual language understanding:
intent is matched against a keyword list, and the customer-facing outcome is assembled mechanically. The
constitution mandates that agent intelligence be provided by Bedrock LLMs (via the AWS SDK) with prompt
caching enabled.

This feature introduces a **shared, reusable LLM reasoning runtime** in the agent foundation: a single
capability any agent can call to perform bounded, *assistive* cognitive tasks over its own domain inputs —
classifying a ticket, extracting customer intent, drafting a customer-facing message, summarizing the
reasoning behind a decision — and receive a grounded, schema-validated, prompt-cached, fully audited
result. The runtime is the deliverable; all three agents adopt it.

**The LLM is assistive, never authoritative.** The binding refund outcomes — `approve_refund`,
`deny_refund`, `offer_partial_credit`, `escalate_to_human`, and each agent's equivalent domain verdict —
remain the exclusive output of the existing deterministic engines, driven by billing results, risk
results, policy rules, and timeout rules in code. The runtime helps agents *understand and communicate*;
it does not decide. This boundary is what lets a non-deterministic model live inside a system that the
constitution requires to be idempotent, replayable, and auditable: the binding decision stays
deterministic, and the assistive LLM outputs are recorded against an idempotency key so replay is stable.

The runtime introduces no new agent, no new event contract, no new topic, and no supervisor — it is a
local library capability the existing agents invoke in-process, preserving the decentralized, event-only
coordination guarantee.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Perform an Assistive Reasoning Task (Priority: P1)

As a domain agent, when I need language understanding the deterministic code cannot give me — classify
this ticket, extract the customer's intent, draft the customer-facing message, summarize why this
decision was reached — I want to hand the runtime my grounding inputs and the shape of the answer I
expect, and receive a structured result produced by an LLM reasoning over exactly those inputs, so that
my agent actually understands and communicates in natural language rather than matching keywords.

**Why this priority**: This is the runtime's reason to exist and the front door for every other behavior.
Until an agent can call the runtime and get back a usable, structured assistive result, none of the
caching, fallback, idempotency, or audit behavior is reachable. This slice proves the foundation can turn
grounded domain inputs into an LLM-reasoned, schema-valid result an agent can use.

**Independent Test**: Call the runtime with an assistive task (e.g. classify a ticket / extract intent /
draft a reply / summarize a decision), grounding inputs, and an expected output schema; confirm it returns
a populated, schema-valid structured result consistent with the inputs — verifiable end to end with a
stubbed model so no cloud access is required.

**Acceptance Scenarios**:

1. **Given** an assistive reasoning request carrying a task instruction, grounding inputs, and an expected
   output schema, **When** the agent invokes the runtime, **Then** it receives a structured result that
   conforms to the requested schema (e.g. a classification label, an extracted-intent object, a drafted
   message, or a summary).
2. **Given** two requests whose grounding inputs differ in a meaningful way, **When** each is reasoned,
   **Then** the returned results differ in a way explained by that difference.
3. **Given** an assistive result produced by the runtime, **When** the calling agent uses it (e.g. feeds
   the extracted intent into triage or attaches the drafted message to its result), **Then** doing so
   requires no change to the agent's published result contract or its consumers.

---

### User Story 2 - Keep Binding Decisions Deterministic (LLM Never Decides) (Priority: P1)

As a reviewer of the PoC, I want every binding refund outcome to remain the output of deterministic code —
never of the LLM — so that the model can assist with understanding and wording without ever being able to
approve, deny, partially credit, or escalate a refund on its own.

**Why this priority**: This is the central guardrail of the whole feature and a direct consequence of the
constitution's idempotency, safety, and auditability principles. An LLM that could set the binding outcome
would make refund decisions non-deterministic and unauditable. Establishing — and proving — the assistive
boundary is what makes adopting the runtime safe; it is as important as the assistive capability itself.

**Independent Test**: Trace each agent's decision path and confirm the binding outcome
(`approve_refund` / `deny_refund` / `offer_partial_credit` / `escalate_to_human`, and each agent's domain
verdict) is produced by the deterministic engine from billing/risk/policy/timeout inputs; confirm that
forcing the LLM to emit a different or adversarial "decision" does not change the binding outcome.

**Acceptance Scenarios**:

1. **Given** any case, **When** its binding outcome is produced, **Then** that outcome is determined by the
   deterministic engine (from billing result, risk result, policy rules, and timeout rules), not by any
   LLM output.
2. **Given** an assistive LLM result that suggests or implies a different outcome, **When** the agent
   reaches its decision, **Then** the binding outcome is unchanged — the LLM result is used only for
   classification, extraction, drafting, or summarization.
3. **Given** the audit trail for a case, **When** it is inspected, **Then** the binding decision and the
   assistive LLM contributions are distinguishable, and the decision is attributable to the deterministic
   policy.

---

### User Story 3 - Stay Within Schema and Domain Bounds (Validated Output) (Priority: P1)

As a domain agent, I want the runtime to guarantee that whatever the model returns is constrained to the
shape and choices my task allows — a label only from the permitted set, fields within their defined ranges,
no invented policy or facts — so that a fluent-but-wrong model response can never silently corrupt my
inputs or my customer-facing message.

**Why this priority**: A generative model can produce plausible text that violates the task's allowed
outputs or hallucinates content. Without enforced bounds, a bad assistive result could mislead triage or
put false statements in front of a customer. This slice makes the LLM's output safe to use.

**Independent Test**: Feed the runtime model output that is malformed, out-of-enum, or references content
not present in the grounding inputs; confirm the runtime rejects/repairs it and never surfaces an invalid
assistive result to the caller — returning a validated result or an explicit unable-to-produce signal.

**Acceptance Scenarios**:

1. **Given** model output that does not match the requested schema, **When** the runtime processes it,
   **Then** the runtime does not return an invalid result; it repairs within its defined retry budget or
   returns an explicit unable-to-produce outcome with a recorded reason.
2. **Given** model output proposing a classification label outside the permitted set, or asserting facts
   not present in the grounding inputs, **When** the runtime validates it, **Then** that output is rejected
   and never returned as the assistive result.
3. **Given** any returned result, **When** it is inspected, **Then** every field is within its defined range
   and any claims trace to the grounding inputs the caller supplied.

---

### User Story 4 - Deterministic on Replay (Idempotent Assistive Results) (Priority: P1)

As a reviewer of the PoC, I want re-processing the same assistive request to yield the exact same result
with no second model invocation, so that the event-driven, at-least-once workflow remains replayable and
idempotent even though the underlying model is generative.

**Why this priority**: Idempotency and replayability are constitutional requirements. A naive model call
would return different wording each time, breaking replay and producing inconsistent drafts/classifications
for one case. This slice lets a non-deterministic model live inside a deterministic, auditable system.

**Independent Test**: Issue the same assistive request (same idempotency key) twice; confirm the second
call returns the identical recorded result, that the model is not invoked a second time, and that the
replay is recorded in the audit trail.

**Acceptance Scenarios**:

1. **Given** an assistive request the runtime has already completed, **When** an identical request (same
   idempotency key) arrives, **Then** the runtime returns the previously recorded result and does not
   invoke the model again.
2. **Given** a redelivered request, **When** it is served from the recorded result, **Then** the structured
   output is identical to the original.
3. **Given** a redelivered request, **When** it is handled, **Then** the reuse is recorded in the audit
   trail so a reviewer can see the replay was served from cache rather than re-reasoned.

---

### User Story 5 - Degrade Safely When the Model Is Unavailable (Priority: P1)

As a domain agent, when the model is unreachable, times out, errors, or repeatedly returns unusable output,
I want the runtime to fall back to a safe, defined path — skip the assistive enrichment and proceed on the
deterministic decision, falling back to the existing non-LLM behavior (e.g. keyword intent matching, a
templated message) — rather than blocking the workflow or fabricating content, so that a model outage
degrades the demo gracefully instead of halting refund processing.

**Why this priority**: The PoC must run locally and reliably, including with no cloud access at all. Because
the binding decision is already deterministic, the agent can always proceed without the LLM; the runtime
must make that degradation explicit and safe. This guardrail keeps the system live under model failure and
makes the runtime adoptable without forcing every test to reach AWS.

**Independent Test**: Force the model path to fail (unreachable / timeout / persistently invalid output);
confirm the runtime returns a fallback result flagged as such, the calling agent proceeds on its
deterministic path with the pre-LLM default behavior, and the failure reason is recorded.

**Acceptance Scenarios**:

1. **Given** the model is unreachable or exceeds the configured time budget, **When** the runtime is
   invoked, **Then** it returns a fallback result marked as model-unavailable with a recorded reason, and
   never blocks indefinitely.
2. **Given** the model returns unusable output beyond the retry budget, **When** the runtime gives up on the
   model path, **Then** it returns the defined fallback (the agent's pre-LLM default behavior) rather than
   fabricated content.
3. **Given** any fallback occurred, **When** the result is inspected, **Then** it is clearly distinguishable
   from a model-produced result (the reasoning path used is recorded), and the binding outcome is unaffected.

---

### User Story 6 - Audit the Reasoning Step End to End (Priority: P2)

As a reviewer evaluating the PoC, I want every assistive reasoning step the runtime performs — request
received, prompt used, model and parameters invoked, raw response, validated result, reasoning path (model
vs. cache vs. fallback), latency, and any failure — to leave an immutable, correlated audit record, so I
can reconstruct *how an agent reasoned* without reading code or holding a live model session.

**Why this priority**: Observability is a constitutional requirement, and a reasoning step is exactly the
part of an autonomous agent most in need of transparency. It builds on the prior stories, which produce the
reasoning events being audited.

**Independent Test**: Drive one assistive call end to end, then query the audit trail by the case's
correlation identifier and confirm the reasoning step is present with its prompt reference, model identity,
reasoning path, validated result, and outcome — attributed to the calling agent and in causal order with
the rest of the case.

**Acceptance Scenarios**:

1. **Given** a completed assistive call, **When** the audit trail is queried by correlation identifier,
   **Then** the reasoning step appears with the calling agent's identity, the model/path used, the validated
   result, a timestamp, and the causal link to its triggering request.
2. **Given** a fallback or unable-to-produce outcome, **When** the audit trail is queried, **Then** the
   reason (model unavailable, invalid output, missing inputs) is recoverable from the trail.
3. **Given** an audited reasoning step, **When** it is inspected, **Then** it records enough about the prompt
   and inputs to reconstruct what the model was asked, without requiring a live model.

---

### User Story 7 - Cache Repeated Context to Cut Latency and Cost (Priority: P2)

As an operator of the PoC, I want the runtime to reuse cached prompt context across assistive calls that
share large, stable instructions (task instructions, output schema, examples), so that repeated reasoning
is faster and cheaper, demonstrating the constitution's prompt-caching requirement.

**Why this priority**: Prompt caching for multi-turn/repeated agent interactions is an explicit
constitutional technology constraint. It is not the core assistive path (hence P2), but the runtime is the
natural and only place to satisfy it once, for all agents.

**Independent Test**: Issue multiple assistive calls that share a large stable instruction block and confirm
the shared context is presented to the model in a cache-eligible way, with cache reuse observable in the
runtime's recorded reasoning metadata.

**Acceptance Scenarios**:

1. **Given** repeated assistive calls that share a large, stable instruction/context block, **When** they are
   issued, **Then** the runtime structures the request so the shared portion is eligible for prompt caching
   rather than resent uncached each time.
2. **Given** prompt caching is in effect, **When** reasoning metadata is inspected, **Then** cache reuse
   (vs. a cold prompt) is observable for a reviewer.

---

### User Story 8 - Run Locally With No Cloud Dependency (Priority: P2)

As a developer running the PoC, I want the runtime to operate fully offline by default using a deterministic
stub model, with real Bedrock invocation enabled only by explicit configuration, so that the whole
choreography, its tests, and the demo run on a laptop with no AWS credentials.

**Why this priority**: Local-first, testable-before-deploy is a constitutional principle, and every other
story above must be verifiable without cloud access. This story makes the runtime safe to depend on in CI
and the local demo. It is P2 because it constrains *how* the prior behaviors are delivered rather than adding
a new user-visible capability.

**Independent Test**: With no AWS configuration present, run an assistive call and the full agent test suite;
confirm everything passes against the stub model. Then enable real-model configuration and confirm the same
call routes to the real provider without code changes.

**Acceptance Scenarios**:

1. **Given** no real-model configuration is present, **When** the runtime is invoked, **Then** it uses a
   deterministic local stub model and completes without any cloud access.
2. **Given** real-model configuration is supplied, **When** the runtime is invoked, **Then** it routes to the
   configured provider without changing any calling agent's code.

---

### Edge Cases

- **Model implies a binding outcome**: An assistive result that suggests an approve/deny/partial/escalate
  decision MUST NOT change the binding outcome; the deterministic engine remains the sole decider (US2).
- **Model returns out-of-schema or out-of-enum output**: A classification outside the permitted set, or a
  malformed object, MUST be rejected by validation and never returned (US3).
- **Model output unparseable after retries**: When repair/retry within the configured budget cannot yield
  schema-valid output, the runtime MUST return the defined fallback (pre-LLM behavior) or an
  unable-to-produce outcome, never fabricated content (US3, US5).
- **Model hallucinates facts**: An assistive result asserting facts not present in the grounding inputs
  (e.g. inventing an order detail in a drafted reply) MUST be rejected or constrained, not surfaced to a
  customer (US3).
- **Model timeout / unreachable / throttled**: The runtime MUST bound its wait, fall back to the agent's
  deterministic pre-LLM behavior, and record the reason — never block the case indefinitely (US5).
- **Redelivered request after the original result**: MUST return the recorded assistive result with no
  second model call and record the replay (US4).
- **Identical inputs, different idempotency key**: Two distinct requests with identical inputs are
  independent calls; the runtime is not required to deduplicate across different keys, but each individually
  MUST be replay-stable.
- **Oversized prompt / context limit exceeded**: When inputs exceed the model's context budget, the runtime
  MUST fail safely to fallback with a recorded reason rather than silently truncating into a misleading
  result.
- **Cache cold vs. warm**: First call with a new stable context block is a cold prompt; correctness MUST be
  identical whether the context was cache-warm or cold (US7).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide a shared reasoning runtime, callable in-process by any domain agent,
  that accepts an assistive reasoning request (task instructions, grounding inputs, and an expected output
  schema) and returns a structured, schema-valid result for a bounded assistive task — at minimum
  classification, intent/field extraction, customer-facing drafting, and decision summarization.
- **FR-002**: The runtime MUST perform the reasoning step by invoking a large language model through the AWS
  SDK (Bedrock), consistent with the constitution's AI SDK constraint, rather than re-implementing domain
  logic itself.
- **FR-003**: The runtime MUST be assistive only: it MUST NOT determine any binding refund outcome
  (`approve_refund`, `deny_refund`, `offer_partial_credit`, `escalate_to_human`, or any agent's binding
  domain verdict). Those outcomes MUST remain the output of the existing deterministic engines, driven by
  billing results, risk results, policy rules, and timeout rules.
- **FR-004**: Each adopting agent MUST keep its binding decision deterministic and unaffected by LLM output:
  an assistive result — including one that suggests a different outcome — MUST NOT alter the binding verdict
  the deterministic engine produces.
- **FR-005**: The runtime MUST constrain every returned result to the caller-supplied output schema and
  permitted value set: output that is malformed, out-of-enum, out-of-range, or asserts facts not present in
  the grounding inputs MUST NOT be returned.
- **FR-006**: When model output fails validation, the runtime MUST attempt repair/retry within a defined,
  bounded budget, and on exhaustion MUST return either the defined fallback (the agent's pre-LLM behavior)
  or an explicit unable-to-produce outcome with a recorded reason — never invalid or fabricated content.
- **FR-007**: The runtime MUST be idempotent by request identity: an assistive request carrying an
  idempotency key the runtime has already completed MUST return the previously recorded result without
  invoking the model again, yielding identical structured output on replay.
- **FR-008**: The runtime MUST record each completed assistive result against its idempotency key durably
  enough to survive redelivery within the workflow, so replay is served from the recorded result.
- **FR-009**: The runtime MUST bound the time it waits on the model and, on timeout, unreachable model, model
  error, or repeated invalid output, MUST return a safe fallback result (the agent's pre-LLM default
  behavior) with a recorded reason, never blocking the workflow indefinitely.
- **FR-010**: Every returned result MUST record the reasoning path that produced it — model-reasoned,
  served-from-cache (replay), or fallback — so a model-produced result is always distinguishable from a
  fallback or replayed one.
- **FR-011**: The runtime MUST emit a structured audit record for each assistive reasoning step — request
  received, model/parameters invoked, reasoning path, validated result, latency, and any failure or fallback
  — carrying the calling agent's identity, the case/correlation identity, a causation link, a timestamp, and
  the outcome, reusing the project's existing audit subsystem rather than a parallel audit path.
- **FR-012**: The audit record MUST capture enough about the prompt and inputs to reconstruct what the model
  was asked, queryable by the case's correlation identifier in causal order with the rest of the case,
  without requiring a live model session; the audit MUST keep the assistive contribution distinguishable
  from the binding deterministic decision.
- **FR-013**: The runtime MUST enable prompt caching for the large, stable portions of an assistive request
  (task instructions, output schema, examples) so repeated calls reuse cached context, satisfying the
  constitution's prompt-caching requirement; cache reuse MUST be observable in reasoning metadata.
- **FR-014**: The runtime MUST operate fully offline by default using a deterministic stub model requiring no
  cloud credentials, and MUST route to a real Bedrock model only when explicitly configured — with no change
  to calling-agent code between the two modes.
- **FR-015**: The runtime MUST NOT introduce a new agent, a new event contract, a new topic, or any
  supervisor/router/orchestrator behavior; it is a local reasoning capability the existing agents invoke,
  preserving the system's event-only, decentralized coordination.
- **FR-016**: Assistive results produced by the runtime MUST be consumable by each adopting agent without
  changing that agent's published result contract or its downstream consumers.
- **FR-017**: Model selection, region, credentials, time budget, retry budget, and stub-vs-real mode MUST be
  supplied by configuration (environment/config), not hard-coded, so the same runtime serves local and cloud
  modes.
- **FR-018**: All three domain agents — customer resolution, billing entitlement, and risk & fraud — MUST
  adopt the runtime in this feature, each using it for at least one bounded assistive task appropriate to its
  domain (e.g. customer resolution: ticket categorization, intent extraction, response drafting, case
  summarization; billing and risk: extraction/normalization of inputs and/or summarization of their
  deterministic reasoning), while each agent's binding verdict remains deterministic.

### Key Entities *(include if feature involves data)*

- **Assistive Reasoning Request**: The in-process call an agent makes to the runtime — carrying the task
  instructions, the grounding inputs, the expected output schema, an idempotency key, and the
  case/correlation identity. The trigger for a reasoning step. Never a request to decide a binding outcome.
- **Grounding Inputs**: The agent-owned, domain-scoped inputs the model may reason over (e.g. ticket text,
  billing facts, risk signals, a completed decision to summarize). The model reasons only over these; it
  does not fetch inputs itself and may not assert facts beyond them.
- **Output Schema / Permitted Result Set**: The shape and allowed values the assistive result must conform
  to (e.g. the set of valid categories, the intent object shape), supplied by the caller and enforced by the
  runtime.
- **Assistive Reasoning Result**: The validated structured output the runtime returns — a classification
  label, an extracted-intent/field object, a drafted message, or a summary — together with its reasoning
  path (model / cache / fallback). Explicitly NOT a binding refund verdict.
- **Binding Decision**: The agent's authoritative domain outcome (approve / deny / partial credit / escalate
  / each agent's verdict), produced by the deterministic engine from billing/risk/policy/timeout inputs —
  owned by code, never by the runtime.
- **Reasoning Audit Record**: The immutable, correlated record of one assistive reasoning step — calling
  agent, model/parameters, prompt reference, reasoning path, validated result, latency, outcome — observable
  on the existing audit trail and distinguishable from the binding decision.
- **Model Configuration**: The externally supplied settings — model identity, region, credentials, time and
  retry budgets, and stub-vs-real mode — that determine where and how reasoning is performed.
- **Stub Model**: The deterministic, offline local model used by default so the runtime, its tests, and the
  demo run with no cloud access.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of assistive calls return a result that conforms to the caller-supplied schema and whose
  values are within the permitted set, demonstrated by a test suite over varied domains and inputs
  (including adversarial/out-of-schema model responses that are correctly rejected).
- **SC-002**: In 100% of cases, the binding refund outcome is determined by the deterministic engine and is
  provably unchanged when the LLM is forced to emit a contradictory or adversarial "decision", demonstrated
  by a guardrail test per agent.
- **SC-003**: Re-issuing an identical assistive request (same idempotency key) returns identical structured
  output and triggers zero additional model invocations in 100% of test runs.
- **SC-004**: When the model path is forced to fail (unreachable, timeout, or persistently invalid), 100% of
  calls return a safe fallback (the agent's pre-LLM behavior) with a recorded reason, none block beyond the
  configured time budget, and the binding outcome is unaffected.
- **SC-005**: Every assistive call is reconstructable from the audit trail by correlation identifier —
  including which reasoning path (model / cache / fallback) produced the result, and distinguishable from the
  binding decision — in under 30 seconds via a single documented query, with no live model required.
- **SC-006**: The full agent test suite and the local demo run to completion with no AWS credentials present,
  using the stub model, in 100% of runs.
- **SC-007**: All three agents adopt the runtime for at least one assistive task each, with their existing
  result contracts and downstream consumers unchanged, demonstrated by an end-to-end choreography test
  passing against the runtime-backed agents.
- **SC-008**: For assistive calls sharing a large stable context block, prompt-cache reuse is observable in
  reasoning metadata for the warm calls, demonstrating the caching requirement is exercised.
- **SC-009**: A reviewer can confirm the feature introduces no new agent, event contract, topic, or
  orchestrator — the runtime is invoked only in-process by existing agents — by inspecting the system's
  agents, contracts, and topics before and after.

## Assumptions

- **Builds on the existing agent foundation.** The runtime lives in the shared foundation
  (`src/agent_foundation`) alongside the existing runtime/transport/audit/idempotency machinery and reuses
  the established audit subsystem, idempotency mechanism, and correlation/causation conventions rather than
  introducing parallel infrastructure.
- **The deterministic engines remain authoritative and unchanged in authority.** The current decision matrix
  (customer resolution), rules engine (billing), and additive scoring (risk) continue to own every binding
  verdict; this feature wraps assistive LLM enrichment around them and never moves decision authority to the
  model.
- **Each agent's first assistive task is illustrative, finalized in planning.** The exact assistive task(s)
  per agent (e.g. customer resolution: ticket categorization / intent extraction / response drafting /
  summarization; billing & risk: input extraction/normalization and/or reasoning summaries) are chosen in
  planning to best demonstrate the runtime; the spec requires each agent to adopt at least one, with the
  binding verdict staying deterministic.
- **Bedrock is the model provider.** Per the constitution, real reasoning is performed by Bedrock LLMs via
  the AWS SDK with prompt caching enabled; exact model identity and parameters are configuration finalized in
  planning and default to the latest, most capable suitable Claude model on Bedrock.
- **Offline-first.** A deterministic stub model is the default so all tests and the local demo run without
  cloud access; real Bedrock is opt-in via configuration. This keeps the PoC laptop-runnable and CI-safe.
- **Idempotency is reconciled by recording assistive results against their idempotency key**, not by making
  the generative model itself deterministic; deterministic decoding settings may additionally be used, but
  replay-stability is guaranteed by the recorded result, and the binding decision is deterministic
  regardless.
- **"Assistive result" is an in-process return value plus audit record**, not a new published event or topic.
  Adopting agents publish their *own* existing result events as before; the runtime only supplies assistive
  content (classification, extraction, draft, summary) that those agents use internally.
- **No real-world side effects.** Reasoning produces an assistive result and an audit record only; the
  binding decision and any real refund/anti-fraud action remain owned by the deterministic workflow.
- **Single local environment.** The runtime targets local developer workstations and the existing local
  infrastructure; production hardening (auth, scaling, HA, secrets management) is out of scope per the
  constitution's PoC Scope Discipline principle.
- **Prompt-cache demonstration is sufficient, not exhaustive.** Showing cache eligibility and observable
  reuse for shared stable context satisfies the constitutional requirement; tuning cache hit-rate to a
  numeric target is out of scope.

## Dependencies

- **Constitution** (`.specify/memory/constitution.md`): AI SDK / Bedrock + prompt-caching constraint,
  idempotency, observability-first, and PoC scope discipline all directly shape this feature.
- **`001-event-foundation`**: audit subsystem, idempotency tracking, event envelope, correlation/causation.
- **`002-a2a-runtime-contract`**: the shared agent runtime the agents already build on and into which the
  reasoning capability is offered.
- **`003-customer-resolution-agent`, `004-billing-entitlement-agent`, `005-risk-fraud-agent`**: the
  deterministic decision engines this runtime assists (never replaces) and whose result contracts must stay
  unchanged.
