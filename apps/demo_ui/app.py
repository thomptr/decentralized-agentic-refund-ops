"""Streamlit shell for the RefundOps demo UI (T005, T009, T013, T017, T021).

A read-only observer of the decentralized system: roster + capabilities + liveness,
a causal case timeline (reusing ``trace_case``), a live audit stream, and a single
bounded demo trigger. Runs independently — with no broker or agents up it shows
honest empty states rather than crashing (FR-016).

Run:  streamlit run apps/demo_ui/app.py --server.port 8200
"""

from __future__ import annotations

from uuid import UUID

import streamlit as st

from apps.demo_ui import config
from apps.demo_ui.views import case_view, roster_view, stream_view, trigger_view

_NAV = {
    "Roster": "roster",
    "Case timeline": "case",
    "Audit stream": "stream",
    "Demo trigger": "trigger",
}
_VIEW_TO_LABEL = {v: k for k, v in _NAV.items()}


def _selected_view() -> str:
    """Resolve the active view from the ``?view=`` / ``?case=`` query params."""
    params = st.query_params
    if params.get("case"):
        return "case"
    view = params.get("view")
    return view if view in _VIEW_TO_LABEL else "roster"


def main() -> None:
    st.set_page_config(page_title="RefundOps Demo", page_icon="🧭", layout="wide")
    st.title("🧭 RefundOps — Decentralized Agent Observatory")
    st.caption(
        f"Read-only observer · broker `{config.BROKER_URL}` · refresh ≤{config.REFRESH_SECONDS}s · "
        "no supervisor, no central router"
    )

    current = _selected_view()
    choice = st.sidebar.radio("View", list(_NAV.keys()), index=list(_NAV.values()).index(current))
    target = _NAV[choice]
    # Keep the URL in sync so deep-links and the sidebar agree.
    if target != "case" and st.query_params.get("view") != target:
        st.query_params["view"] = target
        if "case" in st.query_params:
            del st.query_params["case"]

    try:
        if target == "roster":
            roster_view.render(config.BROKER_URL)
        elif target == "case":
            case_param = st.query_params.get("case")
            correlation_id: UUID | None = None
            if case_param:
                try:
                    correlation_id = UUID(case_param)
                except ValueError:
                    st.warning(f"`{case_param}` is not a valid correlation id.")
            case_view.render(config.BROKER_URL, correlation_id)
        elif target == "stream":
            stream_view.render(config.BROKER_URL)
        elif target == "trigger":
            trigger_view.render(config.BROKER_URL)
    except Exception as exc:  # noqa: BLE001 — honest degraded banner, never crash (FR-016)
        st.error(
            "The UI hit a problem reading from the broker. It will keep retrying on the "
            f"next refresh.\n\nDetails: `{exc}`"
        )


if __name__ == "__main__":
    main()
