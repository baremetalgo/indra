"""File tools: read, write, list, delete — all sandboxed to a Workspace.

Every tool here is constructed bound to one :class:`Workspace` and
resolves every path through :meth:`WorkspaceManager.resolve_path` before
touching disk, so a path-escape attempt raises ``WorkspaceError`` instead
of silently succeeding outside the project root.
"""

from __future__ import annotations

import time

from indra.tools.base import ToolResult, ToolSchema
from indra.workspaces.workspace_manager import Workspace, WorkspaceError, WorkspaceManager


class ReadFileTool:
    schema = ToolSchema(
        name="read_file",
        description="Read a UTF-8 text file from the active workspace.",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        output_schema={"type": "object", "properties": {"content": {"type": "string"}}},
    )

    def __init__(self, workspace: Workspace, manager: WorkspaceManager) -> None:
        self._workspace = workspace
        self._manager = manager

    def run(self, params: dict) -> ToolResult:
        start = time.monotonic()
        try:
            target = self._manager.resolve_path(self._workspace, params["path"])
            content = target.read_text(encoding="utf-8")
        except (WorkspaceError, OSError) as exc:
            return ToolResult(success=False, error=str(exc), retryable=False)
        return ToolResult(
            success=True,
            output={"content": content},
            duration_ms=int((time.monotonic() - start) * 1000),
        )


class WriteFileTool:
    schema = ToolSchema(
        name="write_file",
        description="Create or overwrite a UTF-8 text file in the active workspace.",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
        output_schema={"type": "object", "properties": {"bytes_written": {"type": "integer"}}},
    )

    def __init__(self, workspace: Workspace, manager: WorkspaceManager) -> None:
        self._workspace = workspace
        self._manager = manager

    def run(self, params: dict) -> ToolResult:
        start = time.monotonic()
        try:
            target = self._manager.resolve_path(self._workspace, params["path"])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(params["content"], encoding="utf-8")
        except (WorkspaceError, OSError) as exc:
            return ToolResult(success=False, error=str(exc), retryable=False)
        return ToolResult(
            success=True,
            output={"bytes_written": len(params["content"].encode("utf-8"))},
            duration_ms=int((time.monotonic() - start) * 1000),
        )


class ListFilesTool:
    schema = ToolSchema(
        name="list_files",
        description="List files under a directory in the active workspace.",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string", "default": "."}},
        },
        output_schema={"type": "object", "properties": {"files": {"type": "array"}}},
    )

    def __init__(self, workspace: Workspace, manager: WorkspaceManager) -> None:
        self._workspace = workspace
        self._manager = manager

    def run(self, params: dict) -> ToolResult:
        start = time.monotonic()
        try:
            target = self._manager.resolve_path(self._workspace, params.get("path", "."))
            if not target.exists():
                return ToolResult(success=False, error=f"No such path: {target}", retryable=False)
            files = sorted(
                str(p.relative_to(self._workspace.root_path.resolve()))
                for p in target.rglob("*")
                if p.is_file()
            )
        except (WorkspaceError, OSError) as exc:
            return ToolResult(success=False, error=str(exc), retryable=False)
        return ToolResult(
            success=True,
            output={"files": files},
            duration_ms=int((time.monotonic() - start) * 1000),
        )


class DeleteFileTool:
    schema = ToolSchema(
        name="delete_file",
        description="Delete a file in the active workspace.",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        output_schema={"type": "object", "properties": {"deleted": {"type": "boolean"}}},
    )

    def __init__(self, workspace: Workspace, manager: WorkspaceManager) -> None:
        self._workspace = workspace
        self._manager = manager

    def run(self, params: dict) -> ToolResult:
        start = time.monotonic()
        try:
            target = self._manager.resolve_path(self._workspace, params["path"])
            if not target.exists():
                return ToolResult(success=False, error=f"No such file: {target}", retryable=False)
            target.unlink()
        except (WorkspaceError, OSError) as exc:
            return ToolResult(success=False, error=str(exc), retryable=False)
        return ToolResult(
            success=True,
            output={"deleted": True},
            duration_ms=int((time.monotonic() - start) * 1000),
        )


def register_file_tools(registry, workspace: Workspace, manager: WorkspaceManager) -> None:
    """Register all file tools bound to one workspace into ``registry``."""
    registry.register(ReadFileTool(workspace, manager))
    registry.register(WriteFileTool(workspace, manager))
    registry.register(ListFilesTool(workspace, manager))
    registry.register(DeleteFileTool(workspace, manager))
