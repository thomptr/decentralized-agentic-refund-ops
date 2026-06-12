# Feature Specification: Observability

**Feature Branch**: `009-observability`

**Created**: 2026-06-10

**Status**: Draft

**Input**: User description: "Add observability"

## Overview

The decentralized refund operations PoC already satisfies Constitution Principle IV (Observability-First) at the *audit* level: every agent action emits a structured log entry to Kafka with agent name, event ID, timestamp, action type, and outcome, and the demo UI provides a filterable audit stream with causal case replay. What the system lacks is *operational* observability — the ability to answer questions like "how long does a refund case take end to end?", "which agent is the bottleneck?", "are LLM calls getting slower?", and "what does the request flow look like across all three agents for a given case?"

This feature adds end-to-end distributed tracing, quantitative metrics, and a local visualization layer so that operators and developers can monitor system health, diagnose performance issues, and understand agent interaction patterns — all without leaving the local development environment. It builds on the existing structured logging and audit infrastructure rather than replacing it.

This feature introduces no new agent and no change to existing event contracts; it adds a single new lightweight liveness event (`system.agent.heartbeat`). The observability layer instruments the existing agents and foundation in-process, consistent with the decentralized, event-only coordination guarantee, and introduces no supervisor, router, orchestrator, or decision-maker. Kafka remains the replayable business record; LangFuse is the debugging and LLM-observability layer.

## Clarifications

### Session 2026-06-10

- Q: How far should CloudWatch/AgentCore export go in this PoC, given OpenTelemetry-compatible tracing is required? → A: Instrument with OpenTelemetry-compatible semantics and use self-hosted LangFuse as the local default exporter; CloudWatch/AgentCore export is config-only and documented, not wired or tested locally.
- Q: How should the five named Kafka audit events (including `system.agent.heartbeat`, which does not exist today) be treated versus the "no new event/topic/contract" guarantee? → A: Map `audit.agent-task.requested`, `audit.agent-task.completed`, `audit.llm.invocation.completed`, and `audit.policy.decision.completed` onto the existing audit trail (`agent.audit.v1` / `agent.llm.reasoning.v1`) as logical names; add `system.agent.heartbeat` as the single genuinely new lightweight liveness event. The "no new event contract" guarantee is amended to permit this one heartbeat event.
- Q: How are the domain spans (`ticket.classify`, `policy.evaluate`, `case.decision`) created without putting observability code in agent handlers (SC-003)? → A: Instrument the shared deterministic engine entry points (the ticket classifier, `rules_engine.evaluate` / `scoring.assess_signals`, and `decision_engine.decide`) at the foundation/shared layer; agent handlers carry zero observability code.
- Q: How does the observability boundary enforce "do not log raw customer PII by default"? → A: LLM prompts and completions are captured to LangFuse, but a PII-redaction pass runs before export; span attributes carry IDs and non-PII metadata, and any free-text is redacted rather than sent raw.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Trace a Refund Case End to End (Priority: P1)

As a developer debugging a slow or failed refund case, I want to see a visual timeline showing every step the system took — from the initial customer request through each agent's processing, delegation, and response — so I can pinpoint where time was spent or where a failure occurred without reading raw logs.

**Why this priority**: End-to-end tracing is the single most impactful observability capability for a multi-agent system. Without it, correlating behavior across three autonomous agents requires manually searching audit logs by correlation ID. This is the core "can I see what happened?" story.

**Independent Test**: Submit a refund request through the system, then open the trace visualization and locate the case. Confirm the trace shows spans for each agent's processing, with timing, status, and parent-child relationships visible.

**Acceptance Scenarios**:

1. **Given** a completed refund case, **When** a developer opens the trace viewer and searches by case/correlation ID, **Then** they see a hierarchical trace showing every agent interaction, with each span labeled by agent name, operation, and duration.
2. **Given** a refund case where one agent encountered an error, **When** the developer views the trace, **Then** the failed span is visually distinct and includes the error details.
3. **Given** a refund case involving LLM reasoning calls, **When** the developer expands the relevant agent span, **Then** they see child spans for LLM invocations with model, latency, and token usage attributes.

---

### User Story 2 - Monitor Agent Health and Performance Metrics (Priority: P1)

As a developer running the PoC locally, I want to see real-time metrics for each agent — request throughput, processing latency, error rates, and LLM token consumption — so I can understand how the system behaves under load and identify degradation.

**Why this priority**: Metrics answer "is the system healthy right now?" while traces answer "what happened to this specific case?" Both are needed for operational understanding, but metrics provide the at-a-glance health view that makes the system monitorable.

**Independent Test**: Start the agents and submit several refund requests. Open the metrics dashboard and confirm counters and histograms update in near-real-time for each agent.

**Acceptance Scenarios**:

1. **Given** the system is processing refund requests, **When** a developer opens the metrics dashboard, **Then** they see per-agent request counts, latency distributions, and error rates updating in near-real-time.
2. **Given** agents are making LLM reasoning calls, **When** a developer views the LLM metrics panel, **Then** they see per-agent token usage (input/output), call counts, latency, and cache hit rates.
3. **Given** one agent is consistently slower than others, **When** a developer compares agent latency metrics, **Then** the bottleneck agent is identifiable from the dashboard without inspecting logs.

---

### User Story 3 - Instrument Agents with Minimal Code Changes (Priority: P2)

As an agent author, I want the observability layer to integrate into the existing foundation so that my agent gets tracing and metrics automatically when it uses standard foundation primitives (event publishing, event consuming, A2A task delegation, LLM runtime calls), without requiring me to add instrumentation code to every handler.

**Why this priority**: If observability requires per-agent boilerplate, it violates PoC Scope Discipline (Principle V) by adding maintenance burden to every agent. Automatic instrumentation at the foundation level keeps agents focused on domain logic.

**Independent Test**: Review an existing agent's handler code and confirm it has no direct references to tracing or metrics APIs. Run the agent and confirm traces and metrics are still produced for its operations.

**Acceptance Scenarios**:

1. **Given** an agent publishes an event via the foundation's event transport, **When** the event is published, **Then** a trace span is automatically created and the span context is propagated in the event envelope.
2. **Given** an agent receives a delegated A2A task, **When** the agent processes the task, **Then** the resulting trace span is automatically linked to the caller's span via propagated context.
3. **Given** an agent calls the LLM reasoning runtime, **When** the call completes, **Then** a child span is automatically recorded with model, latency, token counts, and cache hit status.

---

### User Story 4 - Launch Observability Stack Locally (Priority: P2)

As a developer setting up the PoC, I want the observability visualization tools to start alongside the existing infrastructure (broker, agents) with a single command, so I don't need to install or configure separate monitoring tools.

**Why this priority**: If the observability stack requires separate setup steps, developers will skip it. Bundling it into the existing docker-compose and startup workflow makes it a natural part of the development experience.

**Independent Test**: Run the standard startup command. Confirm the trace viewer and metrics dashboard are accessible at documented URLs alongside the running agents.

**Acceptance Scenarios**:

1. **Given** a fresh checkout, **When** the developer runs the documented startup command, **Then** the trace viewer and metrics dashboard are accessible alongside the broker and agents.
2. **Given** the observability stack is running, **When** the developer runs the documented stop command, **Then** all observability services shut down cleanly with no orphaned state.

---

### Edge Cases

- What happens when the trace/metrics backend is unavailable? Agents must continue processing refund cases normally — observability is non-blocking.
- What happens when trace context is missing from an incoming event (e.g., events from before this feature was added)? The system starts a new trace root rather than failing.
- What happens under high event volume? Trace sampling or batching should prevent the observability layer from becoming a performance bottleneck.
- What happens when the LLM runtime falls back to the deterministic stub? Traces should still show the stub invocation with appropriate attributes indicating no LLM call was made.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST propagate trace context across agent boundaries through the event transport, enabling end-to-end traces for multi-agent workflows.
- **FR-002**: The system MUST automatically instrument event publishing, event consuming, A2A task delegation, LLM runtime calls, and the shared deterministic engine entry points (ticket classification, policy/rules evaluation, case decision) at the foundation/shared level, without requiring per-agent code changes in agent handlers.
- **FR-003**: The system MUST record trace spans for every agent operation including: agent identity, operation name, duration, status (success/error), and parent-child relationships.
- **FR-004**: The system MUST collect quantitative metrics per agent: request count, processing latency distribution, and error count.
- **FR-005**: The system MUST collect LLM-specific metrics per agent: call count, token usage (input and output), latency, and cache hit rate.
- **FR-006**: The system MUST provide a local trace visualization tool accessible via a web browser that displays hierarchical trace timelines searchable by case/correlation ID.
- **FR-007**: The system MUST provide a local metrics dashboard accessible via a web browser that displays per-agent health and performance metrics in near-real-time.
- **FR-008**: The observability layer MUST be non-blocking — if the trace/metrics backend is unavailable, agents MUST continue processing without error.
- **FR-009**: The observability stack (trace viewer, metrics dashboard) MUST launch alongside existing infrastructure via the standard startup command.
- **FR-010**: When trace context is absent from an incoming event, the system MUST create a new trace root rather than failing or dropping the event.
- **FR-011**: Trace spans MUST include the correlation IDs that link the trace to the audit subsystem — at minimum `correlation_id` and `causation_id` from the event envelope — and, where applicable to the operation, `case_id`, `ticket_id`, `task_id`, and `event_id`.
- **FR-012**: The system MUST support a configuration toggle to enable or disable the observability layer without code changes, defaulting to enabled.
- **FR-013**: The system MUST create trace spans for the following named operations: `event.consume`, `ticket.classify`, `a2a.task.send`, `a2a.task.receive`, `policy.evaluate`, `llm.invoke`, `kafka.publish`, and `case.decision`.
- **FR-014**: Every span MUST carry, where applicable to the operation, the attributes: `correlation_id`, `case_id`, `ticket_id`, `agent_id`, `event_id`, `task_id`, `capability`, `model_id`, and `topic`.
- **FR-015**: Tracing MUST be OpenTelemetry-compatible so spans/metrics can be exported to AgentCore/CloudWatch when deployed to AWS. The local default exporter is the self-hosted LangFuse backend; CloudWatch/AgentCore export is configuration-only and documented — it is not wired or tested in the local PoC.
- **FR-016**: LangFuse MUST capture, for LLM and LangGraph activity: LLM prompts, LLM completions, LangGraph node traces, tool calls, token usage, latency, prompt versions, and evaluation scores.
- **FR-017**: The system MUST NOT export raw customer PII by default. LLM prompts and completions MAY be captured to LangFuse, but a PII-redaction pass MUST run before export; span attributes are limited to IDs and non-PII metadata.
- **FR-018**: The Kafka audit events MUST be retained as the replayable business record even with LangFuse present: `audit.agent-task.requested`, `audit.agent-task.completed`, `audit.llm.invocation.completed`, and `audit.policy.decision.completed` (carried by the existing audit trail), plus a new lightweight `system.agent.heartbeat` liveness event. LangFuse is the debugging/LLM-observability layer, not the system of record.
- **FR-019**: The observability layer MUST NOT introduce a supervisor, router, orchestrator, or decision-maker, and MUST NOT alter any agent's binding decision; it is read-only with respect to agent coordination and outcomes.

### Key Entities

- **Trace**: A complete record of a multi-agent workflow execution, composed of spans linked by parent-child relationships and shared correlation context.
- **Span**: A single timed operation within a trace, attributed with agent identity, operation name, status, and domain-specific metadata (e.g., token counts for LLM spans).
- **Metric**: A quantitative measurement (counter, histogram, or gauge) associated with an agent and operation type, collected over time for dashboard display.
- **Audit Event**: A Kafka-persisted, replayable business record (`audit.agent-task.requested`, `audit.agent-task.completed`, `audit.llm.invocation.completed`, `audit.policy.decision.completed`). Distinct from a Span/Trace: audit events are the system of record (in Kafka); spans/traces are the debugging view (in LangFuse).
- **Heartbeat**: A new lightweight `system.agent.heartbeat` liveness event each agent periodically emits to signal it is alive; carries `agent_id` and timestamp, no domain payload.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A developer can locate and visually inspect the full end-to-end trace of any refund case within 30 seconds of knowing the case ID.
- **SC-002**: A developer can identify which agent is the performance bottleneck from the metrics dashboard within 60 seconds of observing slowness.
- **SC-003**: All three domain agents (customer resolution, billing, risk) produce traces and metrics without any observability-specific code in their handler logic.
- **SC-004**: The observability stack launches with zero additional setup steps beyond the existing startup command.
- **SC-005**: Agent processing latency increases by less than 5% when the observability layer is enabled, compared to when it is disabled.
- **SC-006**: When the trace/metrics backend is stopped, all agents continue processing refund cases with no errors or degraded functionality.
- **SC-007**: By default, no raw customer PII appears in span attributes or in LangFuse-captured prompts/completions — captured free-text passes a redaction pass first, verifiable by inspecting a sample trace.

## Assumptions

- The existing structured logging (structlog to stdout) and audit subsystem (Kafka-based) remain in place and are complemented, not replaced, by this feature.
- The existing event envelope already carries correlation ID and causation ID, which will be leveraged for trace context linkage.
- The local development environment uses Docker Compose, and the observability backend services will be added to the existing compose configuration.
- The demo UI (Streamlit) is not the host for metrics/trace visualization — separate, purpose-built tools are used for these views.
- Performance overhead targets (< 5% latency increase) are validated under typical PoC load (tens of requests), not production-scale traffic.
- Instrumentation is OpenTelemetry-compatible so the same spans can later be exported to AgentCore/CloudWatch; in this PoC the only wired exporter is the local self-hosted LangFuse backend.
- PII redaction reuses the existing LLM-runtime privacy controls (e.g., the 008 `REDACT_PII` / `LOG_RAW_*` toggles) at the observability boundary rather than introducing a separate redaction subsystem.
