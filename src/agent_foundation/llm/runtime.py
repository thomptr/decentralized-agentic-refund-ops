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

_log = get_logger(__name__)


class LLMRuntime:
    def __init__(
        self,
        *,
        provider: ModelProvider,
        store: AssistiveResultStore | None = None,
        config: RuntimeConfig | None = None,
        publisher: Any = None,
    ) -> None:
        self._provider = provider
        self._store = store or AssistiveResultStore()
        self._config = config or RuntimeConfig.from_env()
        self._publisher = publisher
        self._redactor = Redactor.from_config(self._config)

    async def reason(self, request: AssistiveRequest) -> AssistiveResult:
        start = time.perf_counter()
        profile = resolve_profile(request.agent_id, request.task_kind, config=self._config)

        cached = await self._store.get(request.idempotency_key)
        if cached is not None:
            latency_ms = int((time.perf_counter() - start) * 1000)
            result = cached.model_copy(
                update={"reasoning_path": ReasoningPath.cache, "latency_ms": latency_ms}
            )
            await self._emit_audit(request, result, profile)
            return result

        prompt = self._render_prompt(request)
        prompt_ref = self._compute_prompt_ref(request, prompt)

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
            return await self._fallback(
                request,
                start,
                profile,
                FailureReason.timeout,
                "Model invocation timed out",
                prompt_ref=prompt_ref,
            )
        except ProviderError as exc:
            return await self._fallback(
                request,
                start,
                profile,
                FailureReason.model_unavailable,
                str(exc),
                prompt_ref=prompt_ref,
            )
        except LLMRuntimeError as exc:
            return await self._fallback(
                request,
                start,
                profile,
                exc.failure_reason,
                str(exc),
                prompt_ref=prompt_ref,
            )
        except Exception as exc:
            return await self._fallback(
                request,
                start,
                profile,
                FailureReason.model_unavailable,
                str(exc),
                prompt_ref=prompt_ref,
            )

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
                return await self._fallback(
                    request,
                    start,
                    profile,
                    FailureReason.invalid_output,
                    "Output failed validation after repairs",
                    prompt_ref=prompt_ref,
                )

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
