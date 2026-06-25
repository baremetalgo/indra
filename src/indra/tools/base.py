"""Tool protocol and registry.

Every tool is a small class exposing a frozen ``ToolSchema`` and a
``run(params) -> ToolResult`` method. Tools are registered into a single
process-wide :class:`ToolRegistry` at startup (core tools eagerly,
plugin tools via the plugin registry).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import jsonschema


@dataclass(frozen=True)
class ToolSchema:
    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]


@dataclass(frozen=True)
class ToolResult:
    success: bool
    output: Any = None
    error: str | None = None
    duration_ms: int = 0


class Tool(Protocol):
    schema: ToolSchema

    def run(self, params: dict[str, Any]) -> ToolResult: ...


class ToolValidationError(Exception):
    """Raised when tool input fails schema validation."""


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.schema.name] = tool

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise KeyError(f"Unknown tool: {name}")
        return self._tools[name]

    def has(self, name: str) -> bool:
        return name in self._tools

    def list_schemas(self) -> list[ToolSchema]:
        return [t.schema for t in self._tools.values()]

    def validate_input(self, name: str, params: dict[str, Any]) -> None:
        tool = self.get(name)
        try:
            jsonschema.validate(instance=params, schema=tool.schema.input_schema)
        except jsonschema.ValidationError as exc:
            raise ToolValidationError(
                f"Invalid input for tool '{name}': {exc.message}"
            ) from exc
