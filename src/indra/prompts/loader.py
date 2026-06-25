"""Loads and renders versioned prompt templates from ``*.prompt.yaml``.

Each template declares its own ``max_output_tokens`` and the variables
it expects. :meth:`PromptManager.render` fails fast if a required
variable is missing, and stamps the result with ``name@version`` for
tracing — this is what lets §14's "keep prompts concise" be enforced in
CI rather than relying on convention.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from pathlib import Path

import yaml
from jinja2 import Environment, StrictUndefined


class PromptError(Exception):
    """Raised on missing templates or missing required variables."""


@dataclass(frozen=True)
class RenderedPrompt:
    name: str
    version: int
    text: str
    max_output_tokens: int


class PromptManager:
    def __init__(self, prompts_dir: str | Path | None = None) -> None:
        if prompts_dir is None:
            prompts_dir = resources.files("indra.prompts")
        self._dir = Path(str(prompts_dir))
        self._env = Environment(undefined=StrictUndefined, autoescape=False)
        self._cache: dict[str, dict] = {}

    def _load(self, name: str) -> dict:
        if name in self._cache:
            return self._cache[name]
        path = self._dir / f"{name}.prompt.yaml"
        if not path.exists():
            raise PromptError(f"Unknown prompt template: {name}")
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        self._cache[name] = data
        return data

    def render(self, name: str, **variables: str) -> RenderedPrompt:
        spec = self._load(name)
        required = set(spec.get("variables", []))
        missing = required - set(variables)
        if missing:
            raise PromptError(f"Prompt '{name}' missing variables: {missing}")

        template = self._env.from_string(spec["template"])
        try:
            text = template.render(**variables)
        except Exception as exc:  # jinja raises various subclasses
            raise PromptError(f"Failed to render prompt '{name}': {exc}") from exc

        return RenderedPrompt(
            name=name,
            version=spec.get("version", 1),
            text=text,
            max_output_tokens=spec.get("max_output_tokens", 256),
        )
