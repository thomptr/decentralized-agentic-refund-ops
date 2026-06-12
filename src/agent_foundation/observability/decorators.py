"""@traced(span_name) decorator for pure engine entry points."""

from __future__ import annotations

import asyncio
import functools
from collections.abc import Callable
from typing import Any, TypeVar

from agent_foundation.observability.tracing import span as _span

F = TypeVar("F", bound=Callable[..., Any])


def traced(span_name: str) -> Callable[[F], F]:
    """Decorator that wraps a pure engine function with a named span.

    - Returns the wrapped value unchanged.
    - Emits status=error and re-raises on exception.
    - No-op (body still runs) when observability is off.
    """

    def decorator(fn: F) -> F:
        if asyncio.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                with _span(span_name):
                    return await fn(*args, **kwargs)

            return async_wrapper  # type: ignore[return-value]
        else:

            @functools.wraps(fn)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                with _span(span_name):
                    return fn(*args, **kwargs)

            return sync_wrapper  # type: ignore[return-value]

    return decorator
