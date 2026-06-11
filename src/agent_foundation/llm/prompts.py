"""PromptTemplate and PromptRegistry — versioned, cache-eligible prompt templates."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from agent_foundation.logging import get_logger

_log = get_logger(__name__)

_DEFAULT_PROMPTS_DIR = "packages/llm-runtime/prompts"


class PromptTemplate(BaseModel):
    model_config = ConfigDict(frozen=True)

    prompt_id: str
    version: int = 1
    task_kind: str = ""
    agent_id: str = ""
    allows_final_recommendation: bool = False
    body: str = ""

    def render(
        self,
        grounding_inputs: dict[str, Any],
        *,
        schema: type[BaseModel] | None = None,
        examples: list[dict[str, Any]] | None = None,
    ) -> tuple[str, str]:
        """Return (rendered_prompt, prompt_ref).

        The stable prefix (body + schema + examples) is cache-eligible;
        the variable suffix (grounding_inputs) changes per call.
        """
        import json

        parts = [self.body]
        if schema is not None:
            parts.append(f"\nOUTPUT_SCHEMA: {json.dumps(schema.model_json_schema())}\nEND_SCHEMA")
        if examples:
            parts.append(f"\nEXAMPLES:\n{json.dumps(examples, indent=2)}")

        prefix = "\n".join(parts)
        suffix = f"\n\nGROUNDING_INPUTS:\n{json.dumps(grounding_inputs, indent=2, default=str)}"
        rendered = prefix + suffix
        prompt_ref = f"{self.prompt_id}@v{self.version}"
        return rendered, prompt_ref

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.body.encode()).hexdigest()[:16]


class PromptRegistry:
    def __init__(self, prompts_dir: str | None = None) -> None:
        self._dir = prompts_dir or _DEFAULT_PROMPTS_DIR
        self._templates: dict[tuple[str, str], PromptTemplate] = {}
        self._loaded = False

    def load(self) -> None:
        prompts_path = Path(self._dir)
        if not prompts_path.is_dir():
            _log.debug("prompt_registry.no_dir", path=self._dir)
            self._loaded = True
            return

        for md_file in sorted(prompts_path.glob("*.md")):
            if md_file.name == "README.md":
                continue
            template = self._parse_template(md_file)
            if template:
                self._register(template)
        self._loaded = True

    def resolve(self, task_kind: str, agent_id: str) -> PromptTemplate:
        if not self._loaded:
            self.load()
        key = (task_kind, agent_id)
        if key not in self._templates:
            raise KeyError(
                f"No prompt template for task_kind={task_kind!r}, agent_id={agent_id!r}. "
                f"Available: {list(self._templates.keys())}"
            )
        return self._templates[key]

    def _register(self, template: PromptTemplate) -> None:
        if template.task_kind == "summarize_reasoning" and template.allows_final_recommendation:
            raise ValueError(
                f"Template {template.prompt_id!r} has task_kind=summarize_reasoning "
                f"but allows_final_recommendation=true — this is forbidden"
            )
        key = (template.task_kind, template.agent_id)
        self._templates[key] = template

    def _parse_template(self, path: Path) -> PromptTemplate | None:
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            return None

        frontmatter, body = self._split_frontmatter(text)
        if not frontmatter:
            return None

        try:
            import yaml  # type: ignore[import-untyped]

            meta = yaml.safe_load(frontmatter) or {}
        except Exception:
            return None

        return PromptTemplate(
            prompt_id=meta.get("prompt_id", path.stem),
            version=int(meta.get("version", 1)),
            task_kind=meta.get("task_kind", ""),
            agent_id=meta.get("agent_id", ""),
            allows_final_recommendation=bool(meta.get("allows_final_recommendation", False)),
            body=body.strip(),
        )

    def _split_frontmatter(self, text: str) -> tuple[str, str]:
        if not text.startswith("---"):
            return "", text
        parts = text.split("---", 2)
        if len(parts) < 3:
            return "", text
        return parts[1], parts[2]

    @property
    def templates(self) -> dict[tuple[str, str], PromptTemplate]:
        if not self._loaded:
            self.load()
        return dict(self._templates)
