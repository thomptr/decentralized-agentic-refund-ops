# Prompt Templates

Versioned Markdown prompt templates for the assistive LLM runtime.

## Format

Each `.md` file uses YAML frontmatter with these keys:

| Key | Type | Description |
|-----|------|-------------|
| `prompt_id` | str | Stable identifier for the prompt |
| `version` | int | Prompt version (increment on content changes) |
| `task_kind` | str | classify, extract_intent, draft_response, summarize_reasoning |
| `agent_id` | str | Target agent identity |
| `allows_final_recommendation` | bool | Must be false for summarize_reasoning templates |

The body after the frontmatter is the stable instruction prefix (cache-eligible).
Grounding inputs are appended at render time as a variable suffix.

## Convention

- Billing/Risk summary templates MUST set `allows_final_recommendation: false`
- The registry rejects any `summarize_reasoning` template that claims final-recommendation authority
- Instructions must explicitly forbid proposing, changing, or implying binding verdicts
