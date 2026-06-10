"""Causal trace builder for refund-ops cases (T029).

Given a list of EventEnvelopes all sharing the same correlation_id, produces a
topologically-ordered list of TraceStep objects that can be rendered as a causal
chain or serialised to JSON for analysis.

Usage::

    from apps.agents.customer_resolution.trace import trace_case

    steps = trace_case(correlation_id, envelopes)
    for step in steps:
        print(f"{step.seq}. [{step.actor}] -> {step.event_type}")
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID

from agent_foundation.envelope import EventEnvelope


@dataclass
class TraceStep:
    seq: int
    actor: str            # agent_id that produced the event
    correlation_id: UUID  # labelled as "case_id" in output
    event_type: str       # event type / action
    outcome: Optional[str]  # outcome/status if available (from AuditPayload)
    task_id: Optional[UUID]  # for A2A task steps (from AuditPayload)
    timestamp: datetime
    caused_by: Optional[UUID]  # causation_id of this step


def _extract_outcome(envelope: EventEnvelope) -> Optional[str]:
    """Try to extract an outcome string from common payload shapes.

    Handles both AuditPayload (outcome field) and
    CustomerResponseDecisionPayload (outcome field) since both use the same key.
    """
    payload = envelope.payload
    if "outcome" in payload and payload["outcome"] is not None:
        return str(payload["outcome"])
    return None


def _extract_task_id(envelope: EventEnvelope) -> Optional[UUID]:
    """Try to extract task_id from common payload shapes.

    Handles AuditPayload (task_id field), TaskRequest, and TaskResult shapes
    which all use the "task_id" key at the top level of the payload dict.
    """
    payload = envelope.payload
    val = payload.get("task_id")
    if val is not None:
        try:
            return UUID(str(val))
        except (ValueError, AttributeError):
            pass
    return None


def trace_case(correlation_id: UUID, envelopes: list[EventEnvelope]) -> list[TraceStep]:
    """Build the causal trace from a list of EventEnvelopes for one correlation_id.

    Algorithm:
    1. Build event_id -> envelope map (filtering to the given correlation_id).
    2. Find root: causation_id is None (e.g. support.ticket.created.v1).
       If multiple roots exist, pick the one with the earliest timestamp.
    3. Topologically order by causation chain using BFS from root.
       Ties (multiple children with the same causation_id) are broken by timestamp.
    4. Append any unreachable envelopes (orphans) sorted by timestamp.
    5. Assign seq numbers starting at 1.
    6. Return list of TraceStep.

    Args:
        correlation_id: The case / correlation identifier to trace.
        envelopes: All EventEnvelopes to consider.  Envelopes whose
            correlation_id does not match are silently ignored.

    Returns:
        Ordered list of TraceStep, one entry per envelope.
    """
    # Step 1: filter to this correlation_id and build event_id map
    relevant = [
        e for e in envelopes
        if e.correlation_id == correlation_id
    ]
    if not relevant:
        return []

    # Step 2: find roots (causation_id is None)
    roots = [e for e in relevant if e.causation_id is None]
    if not roots:
        # Fall back: pick the earliest envelope as an implicit root
        roots = [min(relevant, key=lambda e: e.timestamp)]

    # Sort roots by timestamp for determinism
    roots.sort(key=lambda e: e.timestamp)

    # Build children map: causation_id -> list of children envelopes
    children: dict[UUID, list[EventEnvelope]] = {}
    for e in relevant:
        if e.causation_id is not None:
            children.setdefault(e.causation_id, []).append(e)

    # Sort each child list by timestamp (tie-breaking)
    for child_list in children.values():
        child_list.sort(key=lambda e: e.timestamp)

    # Step 3: BFS topological ordering
    visited: set[UUID] = set()
    ordered: list[EventEnvelope] = []
    queue: deque[EventEnvelope] = deque(roots)

    while queue:
        env = queue.popleft()
        if env.event_id in visited:
            continue
        visited.add(env.event_id)
        ordered.append(env)
        for child in children.get(env.event_id, []):
            if child.event_id not in visited:
                queue.append(child)

    # Step 4: append any orphaned envelopes (not reachable from root)
    orphans = [e for e in relevant if e.event_id not in visited]
    orphans.sort(key=lambda e: e.timestamp)
    ordered.extend(orphans)

    # Step 5 & 6: build TraceStep list
    steps: list[TraceStep] = []
    for seq, env in enumerate(ordered, start=1):
        steps.append(
            TraceStep(
                seq=seq,
                actor=env.agent_id,
                correlation_id=env.correlation_id,
                event_type=env.event_type,
                outcome=_extract_outcome(env),
                task_id=_extract_task_id(env),
                timestamp=env.timestamp,
                caused_by=env.causation_id,
            )
        )

    return steps
