"""Shared assistive LLM reasoning runtime.

The LLM is assistive, never authoritative: every binding refund verdict stays the
output of the deterministic engines (decision_engine.decide, rules_engine.evaluate,
scoring.assess_signals). This runtime helps agents understand and communicate; it
does not decide.
"""

from agent_foundation.llm.audit import ReasoningAuditRecord
from agent_foundation.llm.audit_events import (
    LlmAuditEventConfig,
    LlmInvocationCompletedPayload,
    LlmInvocationFailedPayload,
)
from agent_foundation.llm.client import AgentLLM, LLMClientError, LLMResponse, StructuredLLMResponse
from agent_foundation.llm.config import (
    BedrockModelConfig,
    LLMProvider,
    ModelConfigError,
    ModelProfile,
    RuntimeConfig,
    clear_runtime_overrides,
    load_model_config,
    register_runtime_override,
    resolve_profile,
)
from agent_foundation.llm.errors import (
    ContextLimitExceededError,  # noqa: F401
    FailureReason,
    InvalidModelOutputError,  # noqa: F401
    LLMRuntimeError,
    ModelTimeoutError,
    ModelUnavailableError,
)
from agent_foundation.llm.factory import build_runtime
from agent_foundation.llm.langgraph import as_node, create_langgraph_llm_node
from agent_foundation.llm.pricing import LLMUsage, build_llm_usage, estimate_cost
from agent_foundation.llm.prompts import PromptRegistry, PromptTemplate
from agent_foundation.llm.providers import select_provider
from agent_foundation.llm.providers.base import ModelProvider, ProviderError, RawCompletion
from agent_foundation.llm.redaction import Redactor, redact_mapping, redact_text
from agent_foundation.llm.request import AssistiveRequest, TaskKind
from agent_foundation.llm.result import AssistiveResult, ReasoningPath, TextResult, TokenUsage
from agent_foundation.llm.runtime import LLMRuntime, assist_or_fallback
from agent_foundation.llm.store import AssistiveResultStore
from agent_foundation.llm.structured import StructuredError, StructuredOutcome, invoke_structured

__all__ = [
    "AgentLLM",
    "AssistiveRequest",
    "AssistiveResult",
    "AssistiveResultStore",
    "BedrockModelConfig",
    "FailureReason",
    "LLMClientError",
    "LLMProvider",
    "LLMResponse",
    "LLMRuntime",
    "LLMRuntimeError",
    "LLMUsage",
    "LlmAuditEventConfig",
    "LlmInvocationCompletedPayload",
    "LlmInvocationFailedPayload",
    "ModelConfigError",
    "ModelProfile",
    "ModelProvider",
    "ModelTimeoutError",
    "ModelUnavailableError",
    "PromptRegistry",
    "PromptTemplate",
    "ProviderError",
    "RawCompletion",
    "ReasoningAuditRecord",
    "ReasoningPath",
    "Redactor",
    "RuntimeConfig",
    "StructuredError",
    "StructuredLLMResponse",
    "StructuredOutcome",
    "TaskKind",
    "TextResult",
    "TokenUsage",
    "as_node",
    "assist_or_fallback",
    "build_llm_usage",
    "build_runtime",
    "clear_runtime_overrides",
    "create_langgraph_llm_node",
    "estimate_cost",
    "invoke_structured",
    "load_model_config",
    "redact_mapping",
    "redact_text",
    "register_runtime_override",
    "resolve_profile",
    "select_provider",
]
