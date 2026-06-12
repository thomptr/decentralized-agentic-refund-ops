"""LLMRuntime — the single entry point for assistive reasoning."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from typing import Any

from pydantic import BaseModel

from agent_foundation.llm.audit import build_audit_record, write_reasoning_audit
from agent_foundation.llm.config import RuntimeConfig, resolve_profile
from agent_foundation.llm.errors import FailureReason, LLMRuntimeError
from agent_foundation.llm.providers.base import ModelProvider, ProviderError
from agent_foundation.llm.redaction import Redactor
from agent_foundation.llm.request import AssistiveRequest
from agent_foundation.llm.result import AssistiveResult, ReasoningPath
from agent_foundation.llm.store import AssistiveResultStore
from agent_foundation.logging import get_logger
from agent_foundation.observability.attributes import build_span_attrs
from agent_foundation.observability.client import get_client
from agent_foundation.observability.scores import (
    score_cache_hit,
    score_latency_ms,
    score_schema_valid,
    score_used_fallback,
)
from agent_foundation.observability.tracing import generation as obs_generation

_log = get_logger(__name__)


def _enrich_generation(
    lf_gen: Any,
    result: AssistiveResult,
    redactor: Redactor,
    *,
    redact_pii: bool,
) -> None:
    """Update lf_gen with token usage, output completion, and model_id. Fail-open."""
    if lf_gen is None:
        return
    try:
        if result.model_id:
            lf_gen.update(model=result.model_id)
    except Exception:
        pass

    if result.token_usage is not None:
        try:
            usage: dict[str, int] = {
                "input": result.token_usage.input_tokens,
                "output": result.token_usage.output_tokens,
            }
            if result.token_usage.cache_read_tokens:
                usage["cache_read_tokens"] = result.token_usage.cache_read_tokens
            if result.token_usage.cache_write_tokens:
                usage["cache_write_tokens"] = result.token_usage.cache_write_tokens
            lf_gen.update(usage=usage)
        except Exception:
            pass

    try:
        raw_output: Any = result.value
        if raw_output is not None:
            if isinstance(raw_output, BaseModel):
                raw_output = raw_output.model_dump()
            if redact_pii:
                raw_output = redactor.scrub(raw_output)
            lf_gen.update(output=raw_output)
    except Exception:
        pass


def _emit_scores(
    lf_gen: Any,
    result: AssistiveResult,
) -> None:
    """Write programmatic evaluation scores to LangFuse. Fail-open."""
    if lf_gen is None:
        return
    try:
        trace_id: str | None = getattr(lf_gen, "trace_id", None)
        if trace_id is None:
            return
        client = get_client()
        score_schema_valid(
            client, trace_id, valid=(result.reasoning_path != ReasoningPath.fallback)
        )
        score_used_fallback(
            client, trace_id, used=(result.reasoning_path == ReasoningPath.fallback)
        )
        score_cache_hit(client, trace_id, hit=result.cache_hit)
        score_latency_ms(client, trace_id, latency_ms=float(result.latency_ms))
    except Exception:
        pass


class LLMRuntime:
    def __init__(
        self,
        *,
        provider: ModelProvider,
        store: AssistiveResultStore | None = None,
        config: RuntimeConfig | None = None,
        publisher: Any = None,
        obs_config: Any = None,
    ) -> None:
        self._provider = provider
        self._store = store or AssistiveResultStore()
        self._config = config or RuntimeConfig.from_env()
        self._publisher = publisher
        self._obs_config = obs_config
        self._redactor = Redactor.from_config(self._config)

    async def reason(self, request: AssistiveRequest) -> AssistiveResult:
        with obs_generation(
            "llm.invoke",
            model=request.agent_id,
            attrs=build_span_attrs(
                agent_id=request.agent_id,
                task_id=getattr(request, "task_id", None),
            ),
        ) as lf_gen:
            start = time.perf_counter()
            profile = resolve_profile(request.agent_id, request.task_kind, config=self._config)

            cached = await self._store.get(request.idempotency_key)
            if cached is not None:
                latency_ms = int((time.perf_counter() - start) * 1000)
                result = cached.model_copy(
                    update={"reasoning_path": ReasoningPath.cache, "latency_ms": latency_ms}
                )
                await self._emit_audit(request, result, profile)
                _enrich_generation(
                lf_gen, result, self._redactor, redact_pii=self._config.redact_pii
            )
                _emit_scores(lf_gen, result)
                return result

            prompt = self._render_prompt(request)
            prompt_ref = self._compute_prompt_ref(request, prompt)

            # Set the input prompt on the generation span (redacted if configured)
            if lf_gen is not None:
                try:
                    input_prompt = (
                        self._redactor.scrub(prompt)
                        if self._config.redact_pii
                        else prompt
                    )
                    lf_gen.update(input=input_prompt)
                except Exception:
                    pass

            if not self._config.log_raw_prompts:
                _log.info(
                    "llm.invoke",
                    agent_id=request.agent_id,
                    task_kind=request.task_kind,
                    prompt_ref=prompt_ref,
                )
            else:
                _log.info("llm.invoke", agent_id=request.agent_id, prompt=prompt)

            try:
                raw = await asyncio.wait_for(
                    self._provider.invoke(prompt, profile),
                    timeout=profile.timeout_seconds,
                )
            except TimeoutError:
                result = await self._fallback(
                    request,
                    start,
                    profile,
                    FailureReason.timeout,
                    "Model invocation timed out",
                    prompt_ref=prompt_ref,
                )
                _enrich_generation(
                lf_gen, result, self._redactor, redact_pii=self._config.redact_pii
            )
                _emit_scores(lf_gen, result)
                return result
            except ProviderError as exc:
                result = await self._fallback(
                    request,
                    start,
                    profile,
                    FailureReason.model_unavailable,
                    str(exc),
                    prompt_ref=prompt_ref,
                )
                _enrich_generation(
                lf_gen, result, self._redactor, redact_pii=self._config.redact_pii
            )
                _emit_scores(lf_gen, result)
                return result
            except LLMRuntimeError as exc:
                result = await self._fallback(
                    request,
                    start,
                    profile,
                    exc.failure_reason,
                    str(exc),
                    prompt_ref=prompt_ref,
                )
                _enrich_generation(
                lf_gen, result, self._redactor, redact_pii=self._config.redact_pii
            )
                _emit_scores(lf_gen, result)
                return result
            except Exception as exc:
                result = await self._fallback(
                    request,
                    start,
                    profile,
                    FailureReason.model_unavailable,
                    str(exc),
                    prompt_ref=prompt_ref,
                )
                _enrich_generation(
                lf_gen, result, self._redactor, redact_pii=self._config.redact_pii
            )
                _emit_scores(lf_gen, result)
                return result

            if not self._config.log_raw_outputs:
                _log.info("llm.completed", agent_id=request.agent_id, length=len(raw.text))
            else:
                _log.info("llm.completed", agent_id=request.agent_id, output=raw.text)

            value = self._validate_output(raw.text, request)
            if value is None:
                from agent_foundation.llm.structured import invoke_structured

                outcome = await invoke_structured(
                    prompt,
                    request.output_schema,
                    provider=self._provider,
                    profile=profile,
                    grounding_inputs=request.grounding_inputs,
                    max_repairs=profile.max_repairs,
                )
                if outcome.ok:
                    value = outcome.value
                else:
                    result = await self._fallback(
                        request,
                        start,
                        profile,
                        FailureReason.invalid_output,
                        "Output failed validation after repairs",
                        prompt_ref=prompt_ref,
                    )
                    _enrich_generation(
                lf_gen, result, self._redactor, redact_pii=self._config.redact_pii
            )
                    _emit_scores(lf_gen, result)
                    return result

            latency_ms = int((time.perf_counter() - start) * 1000)
            result = AssistiveResult(
                value=value,
                reasoning_path=ReasoningPath.model,
                token_usage=raw.token_usage,
                cache_hit=raw.cache_hit,
                model_id=raw.model_id,
                latency_ms=latency_ms,
                prompt_ref=prompt_ref,
            )

            await self._store.put(request.idempotency_key, result)
            await self._emit_audit(request, result, profile, prompt_ref=prompt_ref)
            _enrich_generation(
                lf_gen, result, self._redactor, redact_pii=self._config.redact_pii
            )
            _emit_scores(lf_gen, result)
            return result

    async def _fallback(
        self,
        request: AssistiveRequest,
        start: float,
        profile: Any,
        failure_reason: FailureReason,
        message: str,
        *,
        prompt_ref: str = "",
    ) -> AssistiveResult:
        _log.warning(
            "llm.fallback",
            agent_id=request.agent_id,
            reason=failure_reason,
            message=message,
        )
        fallback_value = request.fallback()
        latency_ms = int((time.perf_counter() - start) * 1000)
        result = AssistiveResult(
            value=fallback_value,
            reasoning_path=ReasoningPath.fallback,
            failure_reason=failure_reason,
            latency_ms=latency_ms,
            prompt_ref=prompt_ref,
        )
        await self._emit_audit(request, result, profile, prompt_ref=prompt_ref)
        return result

    def _render_prompt(self, request: AssistiveRequest) -> str:
        try:
            from agent_foundation.llm.prompts import PromptRegistry

            registry = PromptRegistry()
            template = registry.resolve(request.task_kind, request.agent_id)
            rendered, _ = template.render(
                request.grounding_inputs,
                schema=request.output_schema,
                examples=request.examples,
            )
            return rendered
        except (KeyError, Exception):
            parts = [request.instructions]
            schema_json = json.dumps(request.output_schema.model_json_schema(), indent=2)
            parts.append(f"\nOUTPUT_SCHEMA: {schema_json}\nEND_SCHEMA")
            if request.examples:
                parts.append(f"\nEXAMPLES:\n{json.dumps(request.examples, indent=2)}")
            parts.append(
                f"\n\nGROUNDING_INPUTS:\n"
                f"{json.dumps(request.grounding_inputs, indent=2, default=str)}"
            )
            return "\n".join(parts)

    def _compute_prompt_ref(self, request: AssistiveRequest, prompt: str) -> str:
        digest = hashlib.sha256(prompt.encode()).hexdigest()[:16]
        return f"{request.task_kind}:{digest}"

    def _validate_output(self, text: str, request: AssistiveRequest) -> BaseModel | None:
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        try:
            parsed = json.loads(text)
            return request.output_schema.model_validate(parsed)
        except Exception:
            return None

    async def _emit_audit(
        self,
        request: AssistiveRequest,
        result: AssistiveResult,
        profile: Any,
        *,
        prompt_ref: str = "",
    ) -> None:
        try:
            record = build_audit_record(
                request=request,
                result=result,
                profile=profile,
                prompt_ref=prompt_ref or (result.prompt_ref or ""),
                redactor=self._redactor if self._config.redact_pii else None,
            )
            if self._publisher:
                await write_reasoning_audit(self._publisher, record)
        except Exception as exc:
            _log.warning("audit.emit_failed", error=str(exc))


async def assist_or_fallback(
    runtime: LLMRuntime,
    *,
    agent_id: str,
    task_kind: str,
    correlation_id: Any,
    causation_id: Any,
    instructions: str,
    grounding_inputs: dict[str, Any],
    output_schema: type[BaseModel],
    idempotency_key: str = "",
    fallback: Any,
    examples: list[dict[str, Any]] | None = None,
) -> AssistiveResult:
    from agent_foundation.llm.request import TaskKind

    request = AssistiveRequest(
        task_kind=TaskKind(task_kind),
        agent_id=agent_id,
        correlation_id=correlation_id,
        causation_id=causation_id,
        instructions=instructions,
        grounding_inputs=grounding_inputs,
        output_schema=output_schema,
        idempotency_key=idempotency_key,
        fallback=fallback,
        examples=examples,
    )
    return await runtime.reason(request)
