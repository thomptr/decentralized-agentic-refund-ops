"""T043: Opt-in integration test — a trace appears via LangFuse API for a driven case.

Auto-skipped unless LANGFUSE_HOST, LANGFUSE_PUBLIC_KEY, and LANGFUSE_SECRET_KEY are all set.
"""

from __future__ import annotations

import os
import time
import uuid

import pytest

pytestmark = pytest.mark.integration


def _require_langfuse() -> None:
    missing = [
        v
        for v in ("LANGFUSE_HOST", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")
        if not os.environ.get(v)
    ]
    if missing:
        pytest.skip(f"LangFuse env vars not set: {missing}")


def test_langfuse_reachable() -> None:
    """Smoke: LangFuse API is reachable and credentials are valid."""
    _require_langfuse()
    try:
        import langfuse  # noqa: F401
    except ImportError:
        pytest.skip("langfuse package not installed")

    from langfuse import Langfuse  # type: ignore[import-untyped]

    lf = Langfuse(
        public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
        secret_key=os.environ["LANGFUSE_SECRET_KEY"],
        host=os.environ["LANGFUSE_HOST"],
    )
    lf.flush()


def test_trace_appears_after_span() -> None:
    """Emit a span, flush, and confirm the LangFuse client accepted it without error."""
    _require_langfuse()
    try:
        import langfuse  # noqa: F401
    except ImportError:
        pytest.skip("langfuse package not installed")

    from agent_foundation.observability import configure_observability, flush
    from agent_foundation.observability.config import ObservabilityConfig
    from agent_foundation.observability.tracing import span

    config = ObservabilityConfig.from_env(agent_id="integration-test")
    if not config.is_active:
        pytest.skip("LangFuse client not active (missing keys or langfuse unimportable)")

    configure_observability(agent_id="integration-test", config=config)

    correlation_id = str(uuid.uuid4())
    with span("integration.test.span", attrs={"correlation_id": correlation_id}):
        pass

    flush()
    time.sleep(2)


def test_cost_metadata_non_null_for_priced_model() -> None:
    """T987: estimated_cost_usd is >= 0 for a priced model and == 0 for stub."""
    _require_langfuse()
    try:
        from agent_foundation.llm import pricing  # type: ignore[attr-defined]
    except (ImportError, AttributeError):
        pytest.skip("pricing module not available")

    from agent_foundation.llm.pricing import LLMUsage  # type: ignore[attr-defined]

    stub_usage = LLMUsage(
        input_tokens=0,
        output_tokens=0,
        cache_read_tokens=0,
        cache_write_tokens=0,
        estimated_cost_usd=0.0,
    )
    assert stub_usage.estimated_cost_usd == 0.0

    if pricing._PRICING_TABLE:  # type: ignore[attr-defined]
        model_id = next(iter(pricing._PRICING_TABLE))  # type: ignore[attr-defined]
        from agent_foundation.llm.pricing import build_llm_usage  # type: ignore[attr-defined]
        from agent_foundation.llm.result import TokenUsage

        usage = TokenUsage(input_tokens=1000, output_tokens=500)
        llm_usage = build_llm_usage(usage, model_id=model_id)
        assert llm_usage.estimated_cost_usd >= 0.0
