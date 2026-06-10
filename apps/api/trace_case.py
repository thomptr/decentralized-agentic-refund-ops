"""CLI: trace a case by correlation_id.

Usage::

    uv run python apps/api/trace_case.py <correlation_id> [--json] [--broker BROKER_URL]

Prints the causal trace of a case by reading all events from the audit topic
that share the given correlation_id, then building and displaying the causal chain.

Examples::

    # Text output (default)
    uv run python apps/api/trace_case.py 123e4567-e89b-12d3-a456-426614174000

    # JSON output
    uv run python apps/api/trace_case.py 123e4567-e89b-12d3-a456-426614174000 --json

    # Custom broker
    uv run python apps/api/trace_case.py 123e4567-... --broker kafka:9092
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from uuid import UUID

from agent_foundation.audit.store import query_by_correlation
from agent_foundation.envelope import EventEnvelope
from apps.agents.customer_resolution.trace import TraceStep, trace_case


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Trace a refund-ops case by correlation_id from the audit topic.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "correlation_id",
        help="The case / correlation UUID to trace.",
    )
    parser.add_argument(
        "--broker",
        default="localhost:9092",
        metavar="BROKER_URL",
        help="Kafka bootstrap server (default: localhost:9092).",
    )
    parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        default=False,
        help="Print trace as JSON instead of human-readable text.",
    )
    return parser.parse_args(argv)


def _step_to_dict(step: TraceStep) -> dict:
    return {
        "seq": step.seq,
        "actor": step.actor,
        "case_id": str(step.correlation_id),
        "event_type": step.event_type,
        "outcome": step.outcome,
        "task_id": str(step.task_id) if step.task_id else None,
        "timestamp": step.timestamp.isoformat(),
        "caused_by": str(step.caused_by) if step.caused_by else None,
    }


def _print_text(steps: list[TraceStep]) -> None:
    if not steps:
        print("No trace steps found for the given correlation_id.")
        return
    for step in steps:
        caused_by_str = str(step.caused_by) if step.caused_by else "root"
        outcome_str = f" [{step.outcome}]" if step.outcome else ""
        task_str = f" task={step.task_id}" if step.task_id else ""
        print(
            f"{step.seq}. [{step.actor}] -> {step.event_type}"
            f"{outcome_str}"
            f"{task_str}"
            f" (causation: {caused_by_str})"
        )


def _print_json(steps: list[TraceStep]) -> None:
    data = [_step_to_dict(s) for s in steps]
    print(json.dumps(data, indent=2))


async def _run(correlation_id: UUID, broker: str, as_json: bool) -> int:
    """Async entry-point: fetch audit records, build trace, print."""
    # query_by_correlation returns AuditPayload list; each wraps the original envelope
    audit_records = await query_by_correlation(broker, correlation_id)

    if not audit_records:
        msg = f"No audit records found for correlation_id={correlation_id}"
        if as_json:
            print(json.dumps({"error": msg, "correlation_id": str(correlation_id)}))
        else:
            print(msg, file=sys.stderr)
        return 1

    # Extract the original EventEnvelopes from the AuditPayload records
    envelopes: list[EventEnvelope] = [r.original_envelope for r in audit_records]

    steps = trace_case(correlation_id, envelopes)

    if as_json:
        _print_json(steps)
    else:
        _print_text(steps)

    return 0


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)

    try:
        correlation_id = UUID(args.correlation_id)
    except ValueError:
        print(
            f"Error: {args.correlation_id!r} is not a valid UUID.",
            file=sys.stderr,
        )
        sys.exit(1)

    exit_code = asyncio.run(_run(correlation_id, args.broker, args.as_json))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
