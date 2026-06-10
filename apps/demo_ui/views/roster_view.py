"""Agent roster view — User Story 1 (T008).

Pure presentation of ``build_roster()``: one card per expected agent with identity,
version, accepting endpoint, capabilities, a liveness badge, and the last-announced
time. Auto-refreshes every ``REFRESH_SECONDS``.
"""

from __future__ import annotations

import streamlit as st

from apps.demo_ui import config
from apps.demo_ui.agent_cards import RosterEntry, build_roster

_LIVENESS_BADGE = {
    "live": "🟢 live",
    "unknown": "⚪ unknown",
    "not_announced": "⚫ not announced",
}


def _render_entry(entry: RosterEntry) -> None:
    with st.container(border=True):
        header = entry.name or entry.agent_id
        st.subheader(header)
        cols = st.columns([2, 1, 1])
        cols[0].markdown(f"`{entry.agent_id}`")
        cols[1].markdown(f"**version** {entry.version or '—'}")
        cols[2].markdown(_LIVENESS_BADGE.get(entry.liveness, entry.liveness))

        if not entry.announced:
            st.info("Not announced yet — no Agent Card on the discovery topic.")
            return

        if entry.description:
            st.write(entry.description)
        if entry.endpoint_topic:
            st.markdown(f"**Accepts work on** `{entry.endpoint_topic}`")
        if entry.last_announced:
            st.caption(f"Last announced: {entry.last_announced.isoformat()}")

        if entry.capabilities:
            st.markdown("**Capabilities**")
            for cap in entry.capabilities:
                tags = " ".join(f"`{t}`" for t in cap.tags)
                st.markdown(f"- **{cap.name}** (`{cap.id}`) — {cap.description} {tags}")


@st.fragment(run_every=config.REFRESH_SECONDS)
def _live_roster(broker_url: str) -> None:
    entries = config.cached_call(f"roster:{broker_url}", lambda: build_roster(broker_url))
    if not any(e.announced for e in entries):
        st.warning("Waiting for agents to announce their cards…")
    for entry in entries:
        _render_entry(entry)


def render(broker_url: str = config.BROKER_URL) -> None:
    st.header("Agent roster & capabilities")
    st.caption("The three peer agents as they advertise themselves over the discovery topic.")
    _live_roster(broker_url)
