from __future__ import annotations

import logging
import sys

import structlog

EVENT_PUBLISHED = "event.published"
EVENT_RECEIVED = "event.received"
EVENT_REJECTED = "event.rejected"
EVENT_DUPLICATE_SKIPPED = "event.duplicate_skipped"
EVENT_PUBLISH_FAILED = "event.publish_failed"
CONSUMER_ERROR = "consumer.error"


def configure_logging(level: int = logging.INFO) -> None:
    """Configure structlog for JSON output to stdout."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
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
    return structlog.get_logger(name)  # type: ignore[return-value]
