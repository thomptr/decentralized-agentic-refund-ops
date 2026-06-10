"""Bounded demo trigger view (T020, T021).

A form to start a case from the screen. On submit it publishes exactly one root
``support.ticket.created`` event and offers a deep-link to the new case's timeline.
This is the UI's only write.
"""

from __future__ import annotations

import streamlit as st

from apps.demo_ui import config
from apps.demo_ui.ticket_form import DemoTriggerRequest, publish_demo_ticket


def render(broker_url: str = config.BROKER_URL) -> None:
    st.header("Start a demo case")
    st.caption(
        "Publishes a single root `support.ticket.created` event (the only write). "
        "It never requests A2A tasks or routes work — the agents react on their own."
    )

    with st.form("demo-trigger"):
        amount = st.number_input("Refund amount", min_value=0.01, value=29.99, step=1.0)
        currency = st.text_input("Currency", value="USD", max_chars=3)
        reason = st.text_area("Reason", value="Charged twice for monthly subscription")
        c1, c2 = st.columns(2)
        ticket_id = c1.text_input("Ticket id (optional)", value="")
        customer_id = c2.text_input("Customer id (optional)", value="")
        submitted = st.form_submit_button("Publish ticket")

    if not submitted:
        return

    try:
        req = DemoTriggerRequest(
            amount=float(amount),
            currency=currency.strip().upper(),
            reason=reason.strip(),
            ticket_id=ticket_id.strip() or None,
            customer_id=customer_id.strip() or None,
        )
    except ValueError as exc:
        st.error(f"Invalid input: {exc}")
        return

    try:
        result = publish_demo_ticket(req, broker_url)
    except Exception as exc:  # noqa: BLE001 — surface, never crash
        st.error(f"Could not publish to the broker: {exc}")
        return

    st.success("Published one root ticket event.")
    st.code(
        f"correlation_id = {result.correlation_id}\n"
        f"event_id       = {result.event_id}\n"
        f"event_type     = {result.event_type}",
        language="text",
    )
    if st.button("Open this case's timeline"):
        st.query_params["case"] = str(result.correlation_id)
        st.query_params["view"] = "case"
        st.rerun()
