# Contract References (existing — reused unchanged)

This feature defines exactly one new HTTP contract ([ui-http-api.md](./ui-http-api.md)) and reuses the
following existing contracts and helpers without modification. They remain authoritative in their
owning features.

## Discovery / Agent Card
- **`AgentCard`, `Capability`** — `src/agent_foundation/runtime/agent_card.py`
  (fields: `agent_id, name, description, version, endpoint_topic, capabilities[], security`;
  capability: `id, name, description, tags[]`).
- **`discover_agents(broker_url)`** — `src/agent_foundation/runtime/discovery.py`. Reads compacted
  topic `local.agent.agent-card.published.v1`, returns latest card per `agent_id`.
- **HTTP health** — `GET /ping` and `GET /.well-known/agent.json` on `apps/agents/billing_entitlement/http_app.py`
  (`:8101`) and `apps/agents/risk_fraud/http_app.py` (`:8103`). Used best-effort for liveness.
- Owning feature: `specs/002-a2a-runtime-contract/`.

## Audit trail
- **`AuditPayload`** — `src/agent_foundation/payloads/sample.py`
  (`original_envelope, outcome ∈ {accepted, rejected, duplicate_skipped, completed, failed}, reason, recorded_at, task_id`).
- **`EventEnvelope`** — `src/agent_foundation/envelope.py`
  (`event_id, correlation_id, causation_id, agent_id, tenant_id, timestamp, event_type, schema_version, payload`).
- **`query_by_correlation(broker, correlation_id)`**, **`consume_all_audit_records(broker)`** —
  `src/agent_foundation/audit/store.py`. Read topic `local.audit.envelope.recorded.v1`.
- Owning feature: `specs/001-event-foundation/`.

## Causal ordering
- **`trace_case(correlation_id, envelopes) -> list[TraceStep]`** —
  `apps/agents/customer_resolution/trace.py`. Causation-then-time ordering; earliest-root fallback;
  sibling tie-break by timestamp; orphan append. The UI MUST reuse this so UI == CLI
  (`apps/api/trace_case.py`).
- Owning feature: `specs/006-workflow-choreography/`.

## Demo trigger (bounded write)
- **`SupportTicketCreatedPayload`** — `src/agent_foundation/payloads/support_ticket.py`
  (`ticket_id, customer_id, amount, currency, reason, created_at`).
- **`Publisher.publish(payload, event_type, correlation_id, causation_id=None)`** —
  `src/agent_foundation/transport/publisher.py`.
- **`topic_for("support","ticket","created")`** → `local.support.ticket.created.v1` —
  `packages/contracts/topics.py`.
- Existing reference implementation reused: `apps/api/dev_publish_ticket.py`.

The UI adds **no new Kafka topic, no new event type, and no new agent**.
