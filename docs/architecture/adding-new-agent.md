# Adding a New Agent

Follow these steps to add a new agent that participates in the event foundation. Each step names the exact file to edit.

**Step 1 — Define AgentIdentity**

Instantiate `AgentIdentity` in your agent's entry point:

```python
from agent_foundation.envelope import AgentIdentity

identity = AgentIdentity(
    agent_id="billing.refund-analyzer",   # must match ^[a-z][a-z0-9_.-]{1,62}$
    display_name="Billing Refund Analyzer",
    tenant_id="poc",
)
```

Pass `identity` to `Publisher` and `Consumer` constructors. Call `configure_logging()` at startup.

**Step 2 — Add a payload model**

Create `src/agent_foundation/payloads/<your_payload>.py` with a Pydantic v2 `BaseModel` subclass. All fields must be JSON-serializable. Use `frozen=True, extra="forbid"`.

Example:

```python
from pydantic import BaseModel, ConfigDict, Field
from typing import Annotated

class BillingDecisionPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_id: str
    approved: bool
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    reason: str
```

**Step 3 — Add event-type constants**

Add string constants to `packages/contracts/events/payloads.py` (or a new `packages/contracts/events/types.py` file). If the event initiates a new workflow, add it to `ROOT_EVENT_TYPES` in `src/agent_foundation/envelope.py`. Most agent events are NOT root events — they are caused by a prior event in the workflow.

**Step 4 — Register in the payload registry**

Edit `src/agent_foundation/payloads/__init__.py`:

```python
from agent_foundation.payloads.billing_decision import BillingDecisionPayload
from packages.contracts.topics import topic_for

_BILLING_DECISION_ET = topic_for("billing", "refund-analysis", "completed")
PAYLOAD_REGISTRY[_BILLING_DECISION_ET] = BillingDecisionPayload
```

**Step 5 — Add topic mapping**

If the event needs its own topic, edit `src/agent_foundation/transport/topics.py`:

```python
from packages.contracts.topics import topic_for

_BILLING_DECISION = topic_for("billing", "refund-analysis", "completed")

TOPIC_NAMES[_BILLING_DECISION_ET] = _BILLING_DECISION
```

Add a `NewTopic` entry to `_CANONICAL_TOPICS` with the correct retention config. Follow the `{env}.{domain}.{entity}.{action}.v{major}` naming rule (see [topic-naming.md](./topic-naming.md)).

**Step 6 — Subscribe and handle events**

```python
from agent_foundation.transport.consumer import Consumer
from agent_foundation.envelope import EventEnvelope
from agent_foundation.payloads import PAYLOAD_REGISTRY

consumer = Consumer(
    broker_url="localhost:9092",
    group_id="billing.refund-analyzer",
    agent_identity=identity,
    idempotent=True,  # always True for business agents
)
consumer.subscribe([_BILLING_DECISION])

async def handler(envelope: EventEnvelope) -> None:
    payload_cls = PAYLOAD_REGISTRY[envelope.event_type]
    payload = payload_cls.model_validate(envelope.payload)
    # ... process payload

await consumer.run(handler)
```

**Step 7 — Add tests**

- **Unit** (`tests/unit/test_<your_payload>.py`): validate the payload model with valid and invalid inputs.
- **Contract** (`tests/contract/test_<your_event>.py`): round-trip serialize/deserialize; validate against the JSON schema in `specs/001-event-foundation/contracts/`.
- **Integration** (`tests/integration/test_<your_agent>.py`, `@pytest.mark.integration`): use `KafkaContainer`; publish a well-formed event, consume and assert envelope round-trip + audit record written; publish an invalid event and assert `AuditPayload(outcome="rejected")`; replay same stream to same consumer group and assert zero handler invocations.

---

## Constitution compliance reminder

Before shipping, verify compliance with all five principles:

| Principle | Check |
|-----------|-------|
| I. Agent Autonomy | Single, clearly scoped responsibility. No direct agent-to-agent calls. |
| II. Event-Driven Coordination | All communication goes through Kafka topics. Never call another agent's HTTP endpoint. |
| III. Idempotency & Safety | Handler is idempotent. `Consumer(idempotent=True)`. Re-processing the same event produces the same outcome. |
| IV. Observability-First | `configure_logging()` at startup. Every significant action emits a structured log entry via `structlog`. |
| V. PoC Scope Discipline | Justify every new dependency in `plan.md`'s Complexity Tracking table. Choose the simpler approach when in doubt. |
