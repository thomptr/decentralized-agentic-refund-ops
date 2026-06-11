"""LangGraph-compatible adapter — as_node() and create_langgraph_llm_node()."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel

from agent_foundation.llm.request import AssistiveRequest, TaskKind
from agent_foundation.llm.result import TextResult
from agent_foundation.llm.runtime import LLMRuntime


def as_node(
    runtime: LLMRuntime,
    *,
    agent_id: str,
    task_kind: str = "summarize_reasoning",
    output_schema: type[BaseModel] | None = None,
    instructions: str = "Summarize the reasoning.",
    fallback: Callable[[], BaseModel] | None = None,
    state_key: str = "llm_result",
) -> Callable[[dict[str, Any]], Coroutine[Any, Any, dict[str, Any]]]:
    """Return a graph-shaped async callable wrapping LLMRuntime.reason()."""
    schema = output_schema or TextResult
    fb = fallback or (lambda: schema(text="fallback") if schema is TextResult else schema())

    async def _node(state: dict[str, Any]) -> dict[str, Any]:
        correlation_id = state.get("correlation_id", uuid4())
        causation_id = state.get("causation_id", uuid4())
        if isinstance(correlation_id, str):
            correlation_id = UUID(correlation_id)
        if isinstance(causation_id, str):
            causation_id = UUID(causation_id)

        grounding = {k: v for k, v in state.items() if k not in ("correlation_id", "causation_id")}

        request = AssistiveRequest(
            task_kind=TaskKind(task_kind),
            agent_id=agent_id,
            correlation_id=correlation_id,
            causation_id=causation_id,
            instructions=instructions,
            grounding_inputs=grounding,
            output_schema=schema,
            fallback=fb,
        )

        result = await runtime.reason(request)
        return {
            **state,
            state_key: result.value.model_dump(mode="json")
            if hasattr(result.value, "model_dump")
            else result.value,
            f"{state_key}_reasoning_path": result.reasoning_path,
            f"{state_key}_token_usage": result.token_usage.model_dump()
            if result.token_usage
            else None,
            f"{state_key}_model_id": result.model_id,
            f"{state_key}_cache_hit": result.cache_hit,
            f"{state_key}_latency_ms": result.latency_ms,
        }

    return _node


def create_langgraph_llm_node(
    agent_id: str,
    prompt_template: str,
    output_schema: type[BaseModel] | None = None,
    *,
    runtime: LLMRuntime | None = None,
    task_kind: str = "summarize_reasoning",
    fallback: Callable[[], BaseModel] | None = None,
    state_key: str = "llm_result",
) -> Callable[[dict[str, Any]], Coroutine[Any, Any, dict[str, Any]]]:
    """Factory returning a graph-shaped node callable wrapping LLMRuntime.reason().

    The factory MUST return only a single node callable — it must not build graphs,
    edges, routing, or instantiate LLMRuntime internally (accept via closure/arg).
    LangGraph is imported lazily and only if actually present.
    """
    schema = output_schema or TextResult
    fb = fallback or (lambda: schema(text="fallback") if schema is TextResult else schema())

    async def _node(state: dict[str, Any]) -> dict[str, Any]:
        rt = runtime
        if rt is None:
            from agent_foundation.llm.factory import build_runtime

            rt = build_runtime()

        correlation_id = state.get("correlation_id", uuid4())
        causation_id = state.get("causation_id", uuid4())
        if isinstance(correlation_id, str):
            correlation_id = UUID(correlation_id)
        if isinstance(causation_id, str):
            causation_id = UUID(causation_id)

        grounding = {k: v for k, v in state.items() if k not in ("correlation_id", "causation_id")}

        rendered_instructions = prompt_template
        for key, value in grounding.items():
            rendered_instructions = rendered_instructions.replace(f"{{{key}}}", str(value))

        request = AssistiveRequest(
            task_kind=TaskKind(task_kind),
            agent_id=agent_id,
            correlation_id=correlation_id,
            causation_id=causation_id,
            instructions=rendered_instructions,
            grounding_inputs=grounding,
            output_schema=schema,
            fallback=fb,
        )

        result = await runtime.reason(request) if runtime else await rt.reason(request)
        out = dict(state)
        out[state_key] = (
            result.value.model_dump(mode="json")
            if hasattr(result.value, "model_dump")
            else result.value
        )
        out[f"{state_key}_reasoning_path"] = str(result.reasoning_path)
        out[f"{state_key}_token_usage"] = (
            result.token_usage.model_dump() if result.token_usage else None
        )
        out[f"{state_key}_model_id"] = result.model_id
        out[f"{state_key}_cache_hit"] = result.cache_hit
        out[f"{state_key}_latency_ms"] = result.latency_ms
        return out

    return _node
