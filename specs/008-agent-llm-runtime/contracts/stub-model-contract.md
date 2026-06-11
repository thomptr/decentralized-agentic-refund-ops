# Contract: Stub Model (Deterministic, Offline)

The default provider. Makes the runtime, its tests, and the local demo run with **no** cloud access
and **no** credentials (FR-014, US8, SC-006). It is the linchpin of offline-first.

## Guarantees

- **No I/O**: no network, no AWS, no filesystem beyond reading config. Pure function of the rendered
  prompt + profile.
- **Deterministic**: identical input ⇒ identical output, byte for byte. This underpins replay
  determinism alongside the result store (R5) and makes every test reproducible.
- **Schema-shaped**: produces output that the runtime's validate-and-repair loop accepts for the
  given `output_schema` in the normal case — so US1's happy path is reachable offline.

## Behavior by `task_kind`

| `task_kind` | Stub output (deterministic) |
|-------------|-----------------------------|
| `classify` | Derives a label from the permitted set by a stable rule over `grounding_inputs` (e.g. keyword presence), mirroring the agent's pre-LLM `classify()` so offline behavior is sensible. |
| `extract_intent` | Emits the schema's intent object populated from grounding fields present. |
| `draft_response` | Renders a deterministic message from the `AllowedFacts` grounding only — never invents facts. |
| `summarize_reasoning` | Emits a fixed-form summary of the supplied deterministic reasoning. |

## Test affordances (drive the guardrail/negative paths offline)

The stub MUST support being forced into adversarial modes via the request/grounding (so US2/US3/US5
are testable with no cloud):

- **Force out-of-schema / out-of-enum output** → exercises validate-and-repair and rejection (US3,
  SC-001).
- **Force a contradictory "decision" field** → proves the binding outcome is unchanged (US2, SC-002).
- **Force unreachable / timeout / persistently-invalid** → proves bounded fallback with recorded
  reason (US5, SC-004).
- **Token usage**: returns plausible deterministic `TokenUsage` and a `cache_hit` flag so caching and
  usage-tracking assertions run offline (US7, SC-008).

## Non-goals

The stub does not attempt language quality; it exists to make every runtime behavior — validation,
idempotency, fallback, audit, caching metadata — verifiable without a model. Real language
understanding comes from the Bedrock provider when explicitly enabled.
