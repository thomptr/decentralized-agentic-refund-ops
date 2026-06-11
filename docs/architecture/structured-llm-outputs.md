# Structured LLM Outputs — Schema Enforcement

Authoritative sources: `specs/008-agent-llm-runtime/plan.md`,
`specs/008-agent-llm-runtime/data-model.md`,
`src/agent_foundation/llm/structured.py`.

## Overview

Every assistive call declares an `output_schema` (a Pydantic `BaseModel` subclass). The runtime
enforces that the model output conforms to this schema before returning an `AssistiveResult`. When
the initial output is invalid, a validate-and-repair loop retries with error feedback. If all
retries fail, the caller-supplied fallback is used and the binding verdict is unaffected.

## Validate-and-repair loop

`invoke_structured()` in `structured.py` drives the repair loop:

```
attempt 0:  parse JSON from raw text -> validate against output_schema -> grounding check
            |-- valid: return StructuredOutcome(ok=True, value=...)
            |-- invalid: record error, continue

attempt 1..max_repairs:
            append error feedback to prompt:
              "Previous output was invalid: {error}. Fix the JSON to match this schema: {schema}"
            re-invoke provider -> parse -> validate -> grounding check
            |-- valid: return
            |-- invalid: record, continue

all attempts exhausted:
            return StructuredOutcome(ok=False, error=StructuredError(...))
```

The `max_repairs` budget is set per-profile (default 2). The runtime falls back to the caller's
`fallback()` value when the outcome is not ok.

### JSON extraction

The parser strips markdown code fences before `json.loads`. This handles models that wrap JSON in
fences without requiring special instructions.

### Schema validation

`output_schema.model_validate(parsed)` runs full Pydantic validation including type coercion, enum
checking, and field constraints. Any `ValidationError` is captured and fed back to the model in the
next attempt.

## TextResult default

When a caller does not need structured output (free-text summarization), `TextResult` is the default
schema:

```python
class TextResult(BaseModel):
    text: str
```

This ensures every assistive result is schema-validated, even for unstructured calls.

## Grounding bounds check

After schema validation, `_grounding_check(value, grounding_inputs)` rejects results that assert
facts absent from the grounding inputs. The check targets numeric claims:

1. For each string field longer than 20 characters in the validated output, extract tokens containing
   digits (length > 3).
2. Check each numeric claim against the JSON-serialized grounding inputs.
3. If a claim appears in neither its original form nor a stripped form (no `$`, `,`), the output is
   rejected.

This prevents the model from hallucinating dollar amounts, order numbers, or quantities not present
in the original case data. Non-numeric hallucinations are not caught by this layer -- the assistive
boundary ensures they are never binding.

## StructuredOutcome

```python
class StructuredOutcome(BaseModel):
    ok: bool                          # True if validation succeeded
    value: Any = None                 # The validated Pydantic model instance
    error: StructuredError | None     # Failure details when ok=False

class StructuredError(BaseModel):
    failure_reason: FailureReason     # always invalid_output
    attempts: int                     # total attempts made
    error_messages: list[str]         # per-attempt error descriptions
```

## Integration with LLMRuntime

In `LLMRuntime.reason()`, the first validation attempt uses `_validate_output()` (a fast path that
skips re-invocation). Only on failure does the full `invoke_structured` repair loop run. This avoids
wasting a repair attempt when the initial output is already valid.

## Related docs

- [agent-llm-runtime.md](./agent-llm-runtime.md) -- overall runtime flow
- [llm-audit-events.md](./llm-audit-events.md) -- how validation failures are recorded
