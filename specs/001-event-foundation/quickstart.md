# Quickstart: Decentralized Agent Event Foundation

**Feature**: 001-event-foundation
**Audience**: Developers and reviewers validating the foundation works end-to-end.

This guide is a runnable validation script. Following it should take ~5 minutes on a fresh clone
and proves all five user stories from the spec.

---

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.12+ | Runtime |
| Docker | Engine 24+ with Compose v2 | Local Kafka broker |
| `uv` or `pip` | latest | Package install |

> No AWS credentials, no Anthropic API key, and no external services are required for this
> feature. Bedrock integration is a future feature.

---

## 1. Install the package

From the repo root:

```bash
uv sync --extra dev   # or: pip install -e ".[dev]"
```

This installs `agent_foundation` plus the dev extras (`pytest`, `pytest-asyncio`,
`testcontainers[kafka]`).

---

## 2. Start the local event backbone

From the repo root:

```bash
docker compose -f infra/local/docker-compose.yml up -d
```

Expected services after ~30 seconds:
- `redpanda` — single-broker Kafka-compatible broker (Redpanda), listening on `localhost:9092`.
- `kafka-ui` — browser-accessible inspector (Kafkbat) at <http://localhost:8080>.

Verify health (validates **User Story 1** acceptance scenarios):

```bash
python -m agent_foundation health
```

Expected output (JSON-per-line, structured logging):

```json
{"event": "health.broker", "broker": "localhost:9092", "status": "ok"}
{"event": "health.topics", "expected": 3, "found": 3, "status": "ok"}
{"event": "health.overall", "status": "ok"}
```

Exit code `0` means all components healthy.

---

## 3. Publish and consume a sample event

In **terminal A**, start the sample consumer:

```bash
python -m agent_foundation consume-sample --consumer-group demo
```

In **terminal B**, publish a sample event:

```bash
python -m agent_foundation publish-sample --message "hello from terminal B"
```

Terminal A should print a JSON line within ~1 second showing the received envelope. This validates
**User Story 2** (publish + consume + envelope round-trip).

> See [contracts/event-envelope.schema.json](./contracts/event-envelope.schema.json) for the wire
> contract.

---

## 4. Verify schema and envelope validation

Publish a deliberately malformed payload:

```bash
python -m agent_foundation publish-sample --message ""
```

Expected: the CLI exits non-zero with a Pydantic validation error before sending. Now simulate a
missing-causation rejection:

```bash
python -m agent_foundation publish-sample --message "ghost" --omit-causation --non-root
```

Expected: CLI exits non-zero with "Rejected: missing_causation" and writes a rejection audit
record to `local.audit.envelope.recorded.v1`. The audit record is visible in the Kafkbat UI
(step 7) with `outcome: "rejected"`, `reason: "missing_causation"`.

This validates **edge cases** from the spec and **FR-007 / FR-008**.

---

## 5. Trace a workflow by correlation ID

Publish a 3-event chain (each event marks the previous as cause):

```bash
python -m agent_foundation publish-chain --length 3
```

The CLI prints the `correlation_id` it generated. Use it:

```bash
python -m agent_foundation query-audit --correlation <correlation_id>
```

Expected: three audit records returned in causal order, each with a `causation_id` pointing to
the previous event. This validates **User Story 3**.

---

## 6. Replay a stream from a chosen offset

```bash
python -m agent_foundation replay \
  --topic local.system.sample.published.v1 \
  --from-offset earliest \
  --consumer-group demo-replay
```

Expected: every previously published event is re-delivered in original order. Re-run with the same
`--consumer-group` and observe — because the consumer's `IdempotencyTracker` already has those
event IDs — that nothing reaches the user handler the second time.

This validates **User Story 4** and **SC-005 / SC-006**.

---

## 7. Inspect the audit record

Open <http://localhost:8080> in a browser, navigate to
`Topics → local.audit.envelope.recorded.v1 → Messages`. Each audited event appears with its full
envelope, outcome, and reason (if any). This validates **User Story 5** and **FR-009 / FR-010**.

---

## 8. Tear down

```bash
docker compose -f infra/local/docker-compose.yml down -v
```

The `-v` flag removes named volumes so a subsequent `up` starts clean.

---

## Running the test suite

```bash
# Fast: unit + contract (no Kafka required)
pytest

# Slow: integration tests against testcontainers-managed Kafka
pytest -m integration
```

---

## Where things live

| Path | Purpose |
|------|---------|
| `src/agent_foundation/envelope.py` | `EventEnvelope`, `AgentIdentity` |
| `src/agent_foundation/a2a.py` | `A2APart`, `A2AMessage`, `A2ATask` |
| `src/agent_foundation/payloads/` | Registered payload models per `event_type` |
| `src/agent_foundation/transport/` | Async publisher and consumer helpers |
| `src/agent_foundation/audit/store.py` | Audit write + correlation query helpers |
| `src/agent_foundation/idempotency.py` | `IdempotencyTracker` |
| `src/agent_foundation/cli.py` | Typer CLI (`health`, `publish-sample`, `consume-sample`, `publish-chain`, `query-audit`, `replay`, `query-rejections`) |
| `infra/local/docker-compose.yml` | Single-broker Redpanda (Kafka-compatible) + Kafkbat UI |

For schemas, see [contracts/](./contracts/). For the architectural rationale, see
[research.md](./research.md). For the model rules, see [data-model.md](./data-model.md).
