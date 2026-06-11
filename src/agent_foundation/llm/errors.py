"""Base exception hierarchy for the assistive LLM runtime."""

from __future__ import annotations

from enum import StrEnum


class FailureReason(StrEnum):
    model_unavailable = "model_unavailable"
    timeout = "timeout"
    invalid_output = "invalid_output"
    missing_inputs = "missing_inputs"
    context_limit_exceeded = "context_limit_exceeded"
    unable_to_produce = "unable_to_produce"


class LLMRuntimeError(Exception):
    def __init__(self, message: str, failure_reason: FailureReason) -> None:
        super().__init__(message)
        self.failure_reason = failure_reason


class ModelUnavailableError(LLMRuntimeError):
    def __init__(self, message: str = "Model provider is unavailable") -> None:
        super().__init__(message, FailureReason.model_unavailable)


class ModelTimeoutError(LLMRuntimeError):
    def __init__(self, message: str = "Model invocation timed out") -> None:
        super().__init__(message, FailureReason.timeout)


class ContextLimitExceededError(LLMRuntimeError):
    def __init__(self, message: str = "Context limit exceeded") -> None:
        super().__init__(message, FailureReason.context_limit_exceeded)


class InvalidModelOutputError(LLMRuntimeError):
    def __init__(self, message: str = "Model output failed validation") -> None:
        super().__init__(message, FailureReason.invalid_output)
