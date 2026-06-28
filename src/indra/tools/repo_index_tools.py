"""Tools that answer repo-structure questions from the index, not grep.

This is the payoff of repository indexing: "where is X defined" is a
SQL lookup, not the model stumbling through files one read_file call
at a time.
"""

from __future__ import annotations

import time

from indra.coding.dependency_graph import DependencyGraph
from indra.coding.symbol_index import SymbolIndex
from indra.tools.base import ToolResult, ToolSchema

SYMBOL_SEARCH_SCHEMA = ToolSchema(
    name="symbol_search",
    description=(
        "Find where a function, class, or method is defined by name "
        "(substring match) using the repository index -- much cheaper "
        "than reading files one at a time to search for something."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer", "default": 20},
        },
        "required": ["query"],
    },
    output_schema={"type": "object", "properties": {"matches": {"type": "array"}}},
)

FIND_IMPORTS_SCHEMA = ToolSchema(
    name="find_imports",
    description=(
        "List what a file imports, or which files import a given module "
        "(substring match), using the repository index."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_path": {"type": "string"},
            "module": {"type": "string"},
        },
    },
    output_schema={"type": "object", "properties": {"imports": {"type": "array"}}},
)


class SymbolSearchTool:
    schema = SYMBOL_SEARCH_SCHEMA

    def __init__(self, workspace_id: str, index: SymbolIndex) -> None:
        self.workspace_id = workspace_id
        self.index = index

    def run(self, params: dict) -> ToolResult:
        start = time.monotonic()
        hits = self.index.search(
            self.workspace_id, params["query"], params.get("max_results", 20)
        )
        matches = [
            {
                "file_path": h.file_path,
                "symbol_name": h.symbol_name,
                "symbol_kind": h.symbol_kind,
                "start_line": h.start_line,
                "signature": h.signature,
            }
            for h in hits
        ]
        return ToolResult(
            success=True, output={"matches": matches},
            duration_ms=int((time.monotonic() - start) * 1000),
        )


class FindImportsTool:
    schema = FIND_IMPORTS_SCHEMA

    def __init__(self, workspace_id: str, graph: DependencyGraph) -> None:
        self.workspace_id = workspace_id
        self.graph = graph

    def run(self, params: dict) -> ToolResult:
        start = time.monotonic()
        if params.get("file_path"):
            imports = self.graph.imports_of(self.workspace_id, params["file_path"])
        elif params.get("module"):
            imports = self.graph.importers_of(self.workspace_id, params["module"])
        else:
            return ToolResult(
                success=False, error="provide either 'file_path' or 'module'", retryable=False
            )
        return ToolResult(
            success=True, output={"imports": imports},
            duration_ms=int((time.monotonic() - start) * 1000),
        )


def register_repo_index_tools(
    registry, workspace_id: str, index: SymbolIndex, graph: DependencyGraph
) -> None:
    registry.register(SymbolSearchTool(workspace_id, index))
    registry.register(FindImportsTool(workspace_id, graph))
