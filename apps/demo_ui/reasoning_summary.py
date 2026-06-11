"""Reasoning-step display helpers for the demo UI.

Formats ``ReasoningAuditRecord``-shaped dicts into safe, redacted display rows
for the case audit timeline.  The UI shows only compact summaries -- never raw
prompts, full model output, or PII.
"""

from __future__ import annotations

from typing import Any


def format_reasoning_step(record: dict[str, Any]) -> dict[str, Any]:
    """Return a display-safe row for one reasoning audit record.

    ``record`` is the ``payload`` dict from an ``agent.llm.reasoning.v1``
    inner envelope.  Only safe, pre-redacted fields are surfaced.
    """
    task_kind = record.get("task_kind", "unknown")
    agent_id = record.get("agent_id", "unknown")
    reasoning_path = record.get("reasoning_path", "--")
    outcome = record.get("outcome", "--")
    latency_ms = record.get("latency_ms", 0)
    model_id = record.get("model_id") or "stub"
    cache_hit = record.get("cache_hit", False)
    failure_reason = record.get("failure_reason")

    result_summary = record.get("result_summary", {})
    summary_text = _compact_summary(result_summary)
    summary_text = redact_text(summary_text)

    usage = record.get("token_usage")
    usage_display = format_usage(usage)

    row: dict[str, Any] = {
        "agent": agent_id,
        "task": task_kind,
        "path": reasoning_path,
        "outcome": outcome,
        "model": model_id,
        "latency_ms": latency_ms,
        "cache": "yes" if cache_hit else "no",
        "tokens": usage_display,
        "summary": summary_text,
    }

    if failure_reason:
        row["failure"] = str(failure_reason)

    return row


def format_usage(usage: dict[str, Any] | None) -> str:
    """Format token usage into a compact display string.

    Returns em-dash for None or empty usage.
    """
    if not usage:
        return "—"

    parts: list[str] = []
    input_t = usage.get("input_tokens")
    output_t = usage.get("output_tokens")
    cache_read = usage.get("cache_read_tokens")

    if input_t is not None:
        parts.append(f"in:{input_t}")
    if output_t is not None:
        parts.append(f"out:{output_t}")
    if cache_read:
        parts.append(f"cache:{cache_read}")

    return " ".join(parts) if parts else "—"


def redact_text(text: str) -> str:
    """Defensive PII redaction guard before display.

    Re-applies the foundation redaction patterns so that even if the audit
    record was written without redaction enabled, the UI never displays PII.
    """
    try:
        from agent_foundation.llm.redaction import redact_text as _redact

        return _redact(text)
    except ImportError:
        return text


def _compact_summary(summary: dict[str, Any] | Any) -> str:
    """Produce a short text representation of the result summary."""
    if isinstance(summary, str):
        return summary[:200]

    if not isinstance(summary, dict):
        return str(summary)[:200]

    if "text" in summary:
        return str(summary["text"])[:200]

    parts = []
    for key, value in list(summary.items())[:4]:
        sv = str(value)
        if len(sv) > 60:
            sv = sv[:57] + "..."
        parts.append(f"{key}={sv}")

    return ", ".join(parts) if parts else "—"
