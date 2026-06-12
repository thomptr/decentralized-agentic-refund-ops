from __future__ import annotations

import logging
import sys
from collections.abc import MutableMapping
from typing import Any

import structlog

EVENT_PUBLISHED = "event.published"
EVENT_RECEIVED = "event.received"
EVENT_REJECTED = "event.rejected"
EVENT_DUPLICATE_SKIPPED = "event.duplicate_skipped"
EVENT_PUBLISH_FAILED = "event.publish_failed"
CONSUMER_ERROR = "consumer.error"

TASK_CARD_PUBLISHED = "agent-card.published"
TASK_ENDPOINT_SERVING = "endpoint.serving"
TASK_ACCEPTED = "task.accepted"
TASK_REJECTED = "task.rejected"
TASK_COMPLETED = "task.completed"
TASK_FAILED = "task.failed"
TASK_DUPLICATE_SKIPPED = "task.duplicate-skipped"


def inject_trace_context(
    logger: Any, method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Structlog processor that injects OTel trace_id/span_id into log lines.

    When observability is off or no active span exists, this is a no-op.
    Fail-open: any exception returns event_dict unchanged.
    """
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        ctx = span.get_span_context()
        if ctx is not None and ctx.is_valid:
            event_dict["trace_id"] = format(ctx.trace_id, "032x")
            event_dict["span_id"] = format(ctx.span_id, "016x")
    except Exception:
        pass
    return event_dict


def configure_logging(level: int = logging.INFO) -> None:
    """Configure structlog for JSON output to stdout."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            inject_trace_context,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)  # type: ignore[no-any-return]
