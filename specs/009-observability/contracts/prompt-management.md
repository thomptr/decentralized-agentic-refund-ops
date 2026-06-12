# Contract: Prompt Management

Covers the "prompts" half of the steering input (R6). LangFuse prompt management is an **overlay**:
the in-code `PromptTemplate` (`src/agent_foundation/llm/prompts.py`) stays the runtime source of truth
and fallback so offline/test paths and prompt-cache `cache_control` breakpoints are unaffected.

## Module: `observability/prompts.py`

### `get_prompt(name: str, *, fallback: PromptTemplate) -> ResolvedPrompt`

1. If observability is off ⇒ return `ResolvedPrompt(text=fallback.render(...), version=None)` —
   no network.
2. Else attempt `langfuse.get_prompt(name)` (client-side cached by the SDK).
   - Success ⇒ return its text + version, and the caller links the generation to `(name, version)`.
   - Any failure/timeout ⇒ log debug, return the **local fallback** (FR-008 non-blocking).

### Registration

A one-time helper / documented script seeds LangFuse with the 008 prompt names so versions exist to
fetch and diff. Registration is **idempotent** and optional; the system runs correctly with an empty
LangFuse prompt store (fallback path).

## Invariants

- LangFuse is **never authoritative** for prompt content the deterministic path depends on.
- The stable cache-eligible prefix from 008 is preserved regardless of prompt source, so prompt
  caching (constitution AI-SDK constraint) keeps working.
- Prompt fetch is off the hot path when disabled and best-effort when enabled.

## Linkage

When a managed prompt is used, the LLM generation (see llm-generation-attributes.md) records the
prompt `name`+`version`, enabling prompt → generation → score analytics in the LangFuse UI.
