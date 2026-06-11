"""Case timeline view — User Story 2 (T012, T013).

For a ``correlation_id``, renders the full causal timeline (reusing ``trace_case``
so the UI matches the CLI), each row attributed with actor / event type / outcome /
timestamp / caused-by, failures showing their reason, orphans flagged, with an
explicit "no events found" state. Honors the ``?case=<uuid>`` deep-link.

LLM reasoning steps (``agent.llm.reasoning.v1``) are surfaced in a separate
"Reasoning steps" expander below the causal timeline, showing only safe,
redacted summaries -- never raw prompts or PII.
"""

from __future__ import annotations

from uuid import UUID

import streamlit as st

from apps.demo_ui import config
from apps.demo_ui.reasoning_summary import format_reasoning_step
from apps.demo_ui.timeline import TimelineView, build_timeline

_FAILURE_OUTCOMES = {"failed", "rejected"}
_REASONING_EVENT_TYPE = "agent.llm.reasoning.v1"


def _extract_reasoning_records(view: TimelineView) -> list[dict]:
    """Pull reasoning-step payloads from the timeline entries."""
    records = []
    if not view.found or not view.entries:
        return records
    for e in view.entries:
        if e.event_type == _REASONING_EVENT_TYPE:
            # The payload is embedded in the audit envelope; we surface
            # what trace_case already extracted as the entry's attributes.
            records.append(
                {
                    "agent_id": e.actor,
                    "task_kind": e.outcome or "unknown",
                    "reasoning_path": "—",
                    "outcome": e.outcome or "—",
                    "latency_ms": 0,
                    "model_id": "—",
                    "cache_hit": False,
                    "token_usage": None,
                    "result_summary": {},
                }
            )
    return records


def _render_timeline(view: TimelineView) -> None:
    if not view.found or not view.entries:
        st.info("No events found for this case yet.")
        return

    rows = []
    for e in view.entries:
        label = e.event_type
        if e.is_orphan:
            label += "  orphan (parent not found)"

        rows.append(
            {
                "#": e.seq,
                "actor": e.actor,
                "event": label,
                "outcome": e.outcome or "—",
                "reason": e.reason if e.outcome in _FAILURE_OUTCOMES else "",
                "timestamp": e.timestamp.isoformat(),
                "caused_by": str(e.caused_by) if e.caused_by else "—",
            }
        )
    st.dataframe(rows, width="stretch", hide_index=True)

    failures = [e for e in view.entries if e.outcome in _FAILURE_OUTCOMES]
    for e in failures:
        st.error(f"Step {e.seq} `{e.event_type}` {e.outcome}: {e.reason or '(no reason given)'}")

    # Reasoning-step summary section.
    reasoning_records = _extract_reasoning_records(view)
    if reasoning_records:
        with st.expander(f"LLM reasoning steps ({len(reasoning_records)})", expanded=False):
            st.caption(
                "Assistive LLM summaries only -- binding decisions come from "
                "deterministic engines. PII is redacted before display."
            )
            reasoning_rows = [format_reasoning_step(rec) for rec in reasoning_records]
            st.dataframe(reasoning_rows, width="stretch", hide_index=True)


@st.fragment(run_every=config.REFRESH_SECONDS)
def _live_timeline(broker_url: str, correlation_id: UUID) -> None:
    view = config.cached_call(
        f"timeline:{broker_url}:{correlation_id}",
        lambda: build_timeline(broker_url, correlation_id),
    )
    _render_timeline(view)


def render(broker_url: str = config.BROKER_URL, correlation_id: UUID | None = None) -> None:
    st.header("Case timeline")
    default = str(correlation_id) if correlation_id else ""
    raw = st.text_input("Correlation id", value=default, placeholder="paste a case correlation_id")

    resolved: UUID | None = None
    if raw.strip():
        try:
            resolved = UUID(raw.strip())
        except ValueError:
            st.warning("That is not a valid UUID.")

    if resolved is None:
        st.info("Enter a correlation id (or open a case from the audit stream) to trace it.")
        return

    # Keep the URL deep-linkable.
    if st.query_params.get("case") != str(resolved):
        st.query_params["case"] = str(resolved)
    st.caption(f"Causal order (matches `trace_case` CLI) for `{resolved}`")
    _live_timeline(broker_url, resolved)
