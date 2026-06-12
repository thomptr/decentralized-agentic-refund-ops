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
from uuid import UUID

from agent_foundation.envelope import EventEnvelope


@dataclass
class TraceStep:
    seq: int
    actor: str  # agent_id that produced the event
    correlation_id: UUID  # labelled as "case_id" in output
    event_type: str  # event type / action
    outcome: str | None  # outcome/status if available (from AuditPayload)
    task_id: UUID | None  # for A2A task steps (from AuditPayload)
    timestamp: datetime
    caused_by: UUID | None  # raw causation_id of this step (for audit lookup)
    # Resolved causal parent's event_id: caused_by when it names an event in the
    # case, or the triggering TaskRequest's event_id when caused_by is an A2A
    # task_id. None for roots and genuine orphans (parent not in the case).
    parent_event_id: UUID | None = None


def _extract_outcome(envelope: EventEnvelope) -> str | None:
    """Try to extract an outcome string from common payload shapes.

    Handles both AuditPayload (outcome field) and
    CustomerResponseDecisionPayload (outcome field) since both use the same key.
    """
    payload = envelope.payload
    if "outcome" in payload and payload["outcome"] is not None:
        return str(payload["outcome"])
    return None


def _extract_task_id(envelope: EventEnvelope) -> UUID | None:
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
    relevant = [e for e in envelopes if e.correlation_id == correlation_id]
    if not relevant:
        return []

    event_ids = {e.event_id for e in relevant}

    # A peer's domain result (e.g. local.billing.refund-analysis.completed.v1)
    # records its cause as the A2A *task_id*, not the triggering request's
    # event_id — so a naive causation_id→event_id link reports it as an orphan.
    # Map each task_id to the TaskRequest envelope that carries it, so those
    # results attach to the request that caused them.
    request_eid_by_task: dict[UUID, UUID] = {}
    for e in relevant:
        if "task_request" in e.event_type:
            tid = _extract_task_id(e)
            if tid is not None:
                request_eid_by_task.setdefault(tid, e.event_id)

    def _resolve_parent(env: EventEnvelope) -> UUID | None:
        """Resolve an envelope's causal parent event_id (None = root/orphan)."""
        cb: UUID | None = env.causation_id
        if cb is None or cb in event_ids:
            return cb
        parent: UUID | None = request_eid_by_task.get(cb)  # task_id → request; else orphan
        return parent

    # Step 2: find roots (causation_id is None)
    roots = [e for e in relevant if e.causation_id is None]
    if not roots:
        # Fall back: pick the earliest envelope as an implicit root
        roots = [min(relevant, key=lambda e: e.timestamp)]

    # Sort roots by timestamp for determinism
    roots.sort(key=lambda e: e.timestamp)

    # Build children map keyed by the *resolved* parent event_id.
    parent_by_eid: dict[UUID, UUID | None] = {}
    children: dict[UUID, list[EventEnvelope]] = {}
    for e in relevant:
        parent = _resolve_parent(e)
        parent_by_eid[e.event_id] = parent
        if parent is not None:
            children.setdefault(parent, []).append(e)

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
                parent_event_id=parent_by_eid.get(env.event_id),
            )
        )

    return steps
