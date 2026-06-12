# Quickstart: Observability (LangFuse)

A runnable validation guide proving the feature end to end. For shapes and field-level detail, see
[data-model.md](./data-model.md) and [contracts/](./contracts/). Implementation belongs in tasks.md.

## Prerequisites

- The existing local stack works (`infra/local/docker-compose.yml` — Redpanda broker) and the three
  demo agents run via `infra/local/run-demo-agents.sh`.
- Docker has headroom for the LangFuse stack (Postgres + ClickHouse + Redis + MinIO + web + worker).
- Install the observability extra: `uv sync --extra observability` (adds `langfuse`).

## 1. Launch the observability stack (US4 / FR-009 / SC-004)

```bash
# from repo root
docker compose -f infra/local/docker-compose.langfuse.yml up -d
```

Open `http://localhost:3000`, create an account + project, and copy the **public** and **secret**
keys. Put them in `infra/local/.env.langfuse` (template: `.env.langfuse.example`):

```dotenv
AGENT_OBSERVABILITY_ENABLED=true
LANGFUSE_HOST=http://localhost:3000
LANGFUSE_PUBLIC_KEY=pk-...
LANGFUSE_SECRET_KEY=sk-...
```

**Expected**: the LangFuse trace viewer and dashboards are reachable in the browser, alongside the
already-running broker and Kafka UI.

## 2. Run agents and submit a refund case (US1 / FR-001–003)

```bash
# brings up LangFuse (if not already), exports LANGFUSE_*, starts the 3 agents
infra/local/run-demo-agents.sh
# then drive one refund case through the normal demo path (intake → CRA → billing/risk → decision)
```

Open LangFuse → Traces, search by the case's correlation ID.

**Expected**:
- One hierarchical trace spanning **all three agents**, built from the eight named spans
  (`event.consume`, `kafka.publish`, `a2a.task.send`, `a2a.task.receive`, `llm.invoke`,
  `ticket.classify`, `policy.evaluate`, `case.decision`), each labeled by agent, operation, and
  duration (AC US1-1 / FR-013).
- Each span carries the applicable FR-014 attributes (`correlation_id`, `case_id`, `ticket_id`,
  `agent_id`, `event_id`, `task_id`, `capability`, `model_id`, `topic`) — IDs only, no PII (FR-011/014).

## 3. Inspect LLM generations (US1-3 / FR-005)

Expand a billing/risk/CRA agent span that performed assistive reasoning.

**Expected**: a child **generation** with `model`, `latency`, token usage (input/output/cache
read/write), and `cache_hit`. With the default stub provider it shows `provider_mode=stub` and zero
tokens (stub edge case still traced).

## 4. View metrics dashboards (US2 / FR-004 / FR-007)

Open LangFuse → Dashboards. Submit several cases.

**Expected**: per-agent request counts, latency distributions, and error rates update in near-real
time; an LLM panel shows per-agent token usage, call counts, latency, and cache-hit rate (AC US2-1/2).
The slowest agent is identifiable from latency without reading logs (AC US2-3 / SC-002).

## 5. Failed-span visibility (US1-2)

Force an error in one agent (e.g., stop a downstream dependency) and submit a case.

**Expected**: the failing span is visually distinct (`status=error`) and shows the exception detail;
the trace is not lost.

## 6. Zero per-agent instrumentation (US3 / SC-003)

```bash
# confirm no agent HANDLER references tracing/metrics APIs
grep -rn "observability" apps/agents/*/event_handlers.py apps/agents/*/agent.py
```

**Expected**: no matches in handler logic. The only agent-package references are (a) one
`configure_observability()` in each `main.py`, and (b) a single `@traced("…")` annotation line on each
pure engine entry point (`ticket_classifier.classify`, `rules_engine.evaluate`,
`scoring.assess_signals`, `decision_engine.decide`) — no observability logic inside any handler.
Traces/metrics still appear (steps 2/3).

## 7. Trace context resilience (FR-010)

Replay or inject an event with no `trace_context`.

**Expected**: the consumer starts a **new trace root** rather than failing or dropping the event.

## 8. Non-blocking / backend-down (FR-008 / SC-006)

```bash
docker compose -f infra/local/docker-compose.langfuse.yml down
# submit a refund case
```

**Expected**: all agents process the case with **no errors** and no added user-visible latency;
when LangFuse is restarted, new cases trace again. Equivalent check with the toggle:
`AGENT_OBSERVABILITY_ENABLED=false` (FR-012) → agents run identically, no telemetry emitted.

## 9. No raw PII by default (FR-017 / SC-007)

Submit a case whose ticket text contains an email/phone/PAN-like string. Open the `llm.invoke`
generation in LangFuse.

**Expected**: the captured prompt/completion has the PII **redacted** (default `REDACT_PII=true`,
`LOG_RAW_*=false`); span attributes contain only IDs/metadata, never the raw text. Setting
`LOG_RAW_LLM_PROMPTS=true` is an explicit local-debug opt-in that disables redaction for prompts.

## 10. Kafka stays the system of record (FR-018)

```bash
# audit events still flow on Kafka regardless of LangFuse
# (inspect via kafka-ui at http://localhost:8080 or the audit query helpers)
```

**Expected**: `audit.agent-task.requested/completed`, `audit.llm.invocation.completed`,
`audit.policy.decision.completed` appear on the existing audit topic, and `system.agent.heartbeat`
appears on its dedicated topic at the configured cadence — **even with LangFuse stopped** (step 8).

## 11. Evaluations (steering input / R7)

**Expected (Layer 1)**: every generation carries programmatic scores `schema_valid`, `used_fallback`,
`cache_hit`, `latency_ms`. **Optional (Layer 2)**: seed a dataset and enable an LLM-as-judge evaluator
in the LangFuse UI; judge scores appear on new traces. No score ever changes a refund outcome (FR-019).

## Automated tests

```bash
# offline unit tests — toggle OFF, no LangFuse/OTel network required
uv run pytest tests/unit/observability -q

# opt-in integration — requires a running LangFuse; auto-skipped otherwise
uv run pytest tests/integration/observability -q
```

**Expected**: unit tests pass with no backend (no-op mode, traceparent round-trip, attribute/score
mapping, prompt fallback, fail-open). Integration test asserts a hierarchical trace appears via the
LangFuse API for a driven case.

## Success-criteria mapping

| Criterion | Step |
|-----------|------|
| SC-001 locate full trace < 30s | 2 |
| SC-002 identify bottleneck < 60s | 4 |
| SC-003 no observability code in handlers | 6 |
| SC-004 zero extra setup steps | 1–2 |
| SC-005 < 5% latency overhead | 8 (toggle) + perf check |
| SC-006 backend down → no errors | 8 |
| SC-007 no raw PII by default | 9 |
| FR-018 Kafka system of record | 10 |
