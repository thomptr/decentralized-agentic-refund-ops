"""LangFuse prompt fetch with local PromptTemplate fallback (non-blocking)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PromptTemplate:
    name: str
    template: str
    version: int = 0

    def render(self, **kwargs: str) -> str:
        result = self.template
        for k, v in kwargs.items():
            result = result.replace("{{" + k + "}}", v)
        return result


def fetch_prompt(
    client: object | None,
    name: str,
    *,
    fallback: PromptTemplate,
    version: int | None = None,
) -> tuple[PromptTemplate, bool]:
    """Fetch a prompt from LangFuse; fall back to local template on any failure.

    Returns (template, is_managed) where is_managed=True means LangFuse provided it.
    """
    if client is None:
        return fallback, False
    try:
        kwargs: dict[str, object] = {"name": name}
        if version is not None:
            kwargs["version"] = version
        lf_prompt = client.get_prompt(**kwargs)  # type: ignore[union-attr]
        if hasattr(lf_prompt, "get_langchain_prompt"):
            template_str = lf_prompt.get_langchain_prompt()
        else:
            template_str = str(lf_prompt)
        version = getattr(lf_prompt, "version", 0)
        return PromptTemplate(name=name, template=template_str, version=version), True
    except Exception:
        return fallback, False
