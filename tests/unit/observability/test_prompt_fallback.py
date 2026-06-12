"""T031: Prompt fetch fallback — unmanaged prompt → local template, non-blocking."""

from __future__ import annotations

from agent_foundation.observability.prompts import PromptTemplate, fetch_prompt


def test_fetch_prompt_no_client_returns_fallback() -> None:
    fallback = PromptTemplate(name="classify", template="Classify: {{input}}")
    tmpl, is_managed = fetch_prompt(None, "classify", fallback=fallback)
    assert tmpl is fallback
    assert not is_managed


def test_fetch_prompt_client_error_returns_fallback() -> None:
    class BadClient:
        def get_prompt(self, **kwargs: object) -> None:
            raise ConnectionError("langfuse down")

    fallback = PromptTemplate(name="classify", template="Classify: {{input}}")
    tmpl, is_managed = fetch_prompt(BadClient(), "classify", fallback=fallback)
    assert tmpl is fallback
    assert not is_managed


def test_prompt_template_render() -> None:
    tmpl = PromptTemplate(name="t", template="Hello {{name}}, your order {{order_id}} is ready.")
    rendered = tmpl.render(name="Alice", order_id="ORD-123")
    assert rendered == "Hello Alice, your order ORD-123 is ready."


def test_fetch_prompt_non_blocking_on_none_client() -> None:
    fallback = PromptTemplate(name="x", template="x")
    tmpl, is_managed = fetch_prompt(None, "nonexistent", fallback=fallback)
    assert not is_managed
    assert tmpl.template == "x"
