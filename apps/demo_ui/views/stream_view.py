"""Live audit stream view — User Story 3 (T016, T017).

Newest-first cross-case feed, deduped by ``event_id``, with AND-combined agent /
event-type / case filters, auto-refresh, and a per-row "open case" deep-link into
the case timeline.
"""

from __future__ import annotations

import streamlit as st

from apps.demo_ui import config
from apps.demo_ui.event_stream import StreamView, build_stream


def _open_case(correlation_id: str) -> None:
    st.query_params["case"] = correlation_id
    st.query_params["view"] = "case"
    st.rerun()


def _render_stream(view: StreamView) -> None:
    if not view.events:
        st.info("No audit events match the current filters.")
        return

    for e in view.events:
        cols = st.columns([2, 3, 2, 3, 1])
        cols[0].markdown(f"`{e.agent_id}`")
        cols[1].markdown(f"`{e.event_type}`")
        cols[2].markdown(e.outcome or "—")
        cols[3].caption(f"{e.timestamp.isoformat()} · case `{str(e.correlation_id)[:8]}…`")
        cols[4].button(
            "open",
            key=f"open-{e.event_id}",
            on_click=_open_case,
            args=(str(e.correlation_id),),
        )


@st.fragment(run_every=config.REFRESH_SECONDS)
def _live_stream(
    broker_url: str,
    filter_agent: str | None,
    filter_event_type: str | None,
    filter_case: str | None,
) -> None:
    from uuid import UUID

    cid: UUID | None = None
    if filter_case:
        try:
            cid = UUID(filter_case)
        except ValueError:
            st.warning("Case filter is not a valid UUID — ignoring it.")
    view = config.cached_call(
        f"stream:{broker_url}",
        lambda: build_stream(broker_url),
    )
    # Apply filters in-memory over the cached full stream so widget changes are instant.
    filtered = StreamView(
        events=[
            e
            for e in view.events
            if (not filter_agent or e.agent_id == filter_agent)
            and (not filter_event_type or e.event_type == filter_event_type)
            and (cid is None or e.correlation_id == cid)
        ],
        filter_agent=filter_agent,
        filter_event_type=filter_event_type,
        filter_correlation_id=cid,
    )
    _render_stream(filtered)


def render(broker_url: str = config.BROKER_URL) -> None:
    st.header("Live audit stream")
    st.caption("Every audited event across all cases, newest first, deduped by event id.")

    # Build filter option lists from the current (cached) stream.
    snapshot = config.cached_call(f"stream:{broker_url}", lambda: build_stream(broker_url))
    agents = sorted({e.agent_id for e in snapshot.events})
    types = sorted({e.event_type for e in snapshot.events})

    c1, c2, c3 = st.columns(3)
    filter_agent = c1.selectbox("Agent", ["(all)", *agents]) or "(all)"
    filter_type = c2.selectbox("Event type", ["(all)", *types]) or "(all)"
    filter_case = c3.text_input("Case (correlation id)", value="")

    _live_stream(
        broker_url,
        None if filter_agent == "(all)" else filter_agent,
        None if filter_type == "(all)" else filter_type,
        filter_case.strip() or None,
    )
