# Contract: Span Catalog & Attributes

Satisfies FR-013 (named spans) and FR-014 (span attributes). The catalog is closed: exactly these
eight span names are produced.

## The eight spans

| Span name | Emitted by | Mechanism |
|-----------|-----------|-----------|
| `event.consume` | `transport/consumer.py` handler dispatch | foundation seam wrapper |
| `kafka.publish` | `transport/publisher.py` `publish()` / `publish_raw()` | foundation seam wrapper |
| `a2a.task.send` | `runtime/client.py` `A2AClient.submit()` | foundation seam wrapper |
| `a2a.task.receive` | `runtime/runtime.py` handler dispatch | foundation seam wrapper |
| `llm.invoke` | `llm/runtime.py` `LLMRuntime.reason()` | foundation seam wrapper (generation) |
| `ticket.classify` | `customer_resolution/ticket_classifier.py::classify` | `@traced("ticket.classify")` |
| `policy.evaluate` | `billing_entitlement/rules_engine.py::evaluate` and `risk_fraud/scoring.py::assess_signals` | `@traced("policy.evaluate")` |
| `case.decision` | `customer_resolution/decision_engine.py::decide` | `@traced("case.decision")` |

`policy.evaluate` is emitted by both billing and risk engines, disambiguated by the `agent_id`
attribute.

## `@traced` decorator (domain spans)

`observability/decorators.py`:

```python
@traced("case.decision")
def decide(triage, billing, risk, *, ... , case_id=None, ticket_id="", ...) -> CustomerResponseDecisionPayload:
    ...
```

Contract:
- Wraps a **pure** engine function: opens a span, runs the function, returns its value **unchanged**
  (Principle III — no behavior change). On exception, marks `status=error`, records it, re-raises.
- No-op mode (observability off) ⇒ calls the function directly with zero overhead.
- Attributes are pulled from the function's own arguments/return (e.g., `case_id`, `ticket_id`) via the
  attribute extractor; nothing PII is added (R15/FR-017).
- The decorator is the **only** per-engine footprint — handlers/service orchestration are untouched
  (SC-003).

## FR-014 attributes — "where applicable"

Assembled by `observability/attributes.py`. An attribute is set only when the operation has it;
missing attributes are **omitted** (not empty strings).

| Attribute | Present on |
|-----------|-----------|
| `correlation_id` | all spans |
| `causation_id` | `event.consume` |
| `event_id` | transport spans |
| `case_id` | `ticket.classify`, `policy.evaluate`, `case.decision` |
| `ticket_id` | `ticket.classify`, `case.decision` |
| `task_id` | `a2a.task.*`, `llm.invoke` (when task-scoped) |
| `capability` | `a2a.task.*`, `policy.evaluate` |
| `agent_id` | all spans |
| `model_id` | `llm.invoke` |
| `topic` | transport spans |

## Invariants

- No span outside this catalog is created by the observability layer.
- No attribute carries customer PII (only IDs + non-PII metadata).
- Span names are stable identifiers (dashboards/alerts depend on them).
