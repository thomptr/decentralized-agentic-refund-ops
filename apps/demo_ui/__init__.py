"""Read-only Streamlit demo UI for the decentralized RefundOps system.

Aggregates the three peer agents' self-published Agent Cards (roster + liveness),
renders a causal case timeline by reusing ``trace_case``, and shows a live audit
stream with filters. Its only write is a single bounded demo trigger that publishes
one root ``support.ticket.created`` event — it never routes work or supervises.
"""
