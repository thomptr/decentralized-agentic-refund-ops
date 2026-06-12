"""FR-014 span attribute assembly — IDs and non-PII metadata only."""
from __future__ import annotations

from typing import Any


def build_span_attrs(**kwargs: Any) -> dict[str, str]:
    """Assemble FR-014 span attributes, dropping None values.

    Accepts: correlation_id, causation_id, event_id, case_id, ticket_id,
             task_id, capability, agent_id, model_id, topic.
    All values are stringified; None values are omitted.
    """
    allowed = {
        "correlation_id",
        "causation_id",
        "event_id",
        "case_id",
        "ticket_id",
        "task_id",
        "capability",
        "agent_id",
        "model_id",
        "topic",
    }
    return {
        k: str(v)
        for k, v in kwargs.items()
        if k in allowed and v is not None
    }


def attrs_from_envelope(envelope: Any) -> dict[str, str]:
    """Extract FR-014 attrs from an EventEnvelope (or envelope-like object)."""
    return build_span_attrs(
        correlation_id=getattr(envelope, "correlation_id", None),
        causation_id=getattr(envelope, "causation_id", None),
        event_id=getattr(envelope, "event_id", None),
        agent_id=getattr(envelope, "agent_id", None),
        topic=getattr(envelope, "event_type", None),
    )
