"""File tools: read, write, list, delete — sandboxed to a Workspace.

Path handling is deliberately cross-platform:
- Inputs accept both forward slashes and backslashes, normalised
  before resolution via _norm_input().
- Outputs always use forward slashes so the model gets consistent
  paths on Windows and Linux and can use list_files output directly
  in read_file / write_file calls without any translation.
"""
from __future__ import annotations

import time

from indra.tools.base import ToolResult, ToolSchema
from indra.workspaces.workspace_manager import Workspace, WorkspaceError, WorkspaceManager


def _norm_input(path: str) -> str:
    """Accept backslashes and forward slashes interchangeably."""
    return path.strip().replace("\\", "/")


def _to_posix(path_str: str) -> str:
    return path_str.replace("\\", "/")


class ReadFileTool:
    schema = ToolSchema(
        name="read_file",
        description=(
            "Read a UTF-8 text file from the active workspace. "
            "Accepts forward slashes or backslashes. "
            "Use list_files first to find the correct relative path."
        ),
        input_schema={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
        output_schema={"type": "object", "properties": {"content": {"type": "string"}}},
    )

    def __init__(self, workspace: Workspace, manager: WorkspaceManager) -> None:
        self._workspace = workspace
        self._manager = manager

    def run(self, params: dict) -> ToolResult:
        start = time.monotonic()
        try:
            target = self._manager.resolve_path(self._workspace, _norm_input(params["path"]))
            content = target.read_text(encoding="utf-8")
        except (WorkspaceError, OSError) as exc:
            return ToolResult(success=False, error=str(exc), retryable=False)
        return ToolResult(success=True, output={"content": content},
                          duration_ms=int((time.monotonic() - start) * 1000))


class WriteFileTool:
    schema = ToolSchema(
        name="write_file",
        description=(
            "Create or overwrite a UTF-8 text file in the active workspace. "
            "Use forward slashes in the path (e.g. 'src/main.py'). "
            "Parent directories are created automatically."
        ),
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
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
            target = self._manager.resolve_path(self._workspace, _norm_input(params["path"]))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(params["content"], encoding="utf-8")
        except (WorkspaceError, OSError) as exc:
            return ToolResult(success=False, error=str(exc), retryable=False)
        return ToolResult(success=True,
                          output={"bytes_written": len(params["content"].encode("utf-8"))},
                          duration_ms=int((time.monotonic() - start) * 1000))


class ListFilesTool:
    schema = ToolSchema(
        name="list_files",
        description=(
            "Recursively list all files under a directory in the active workspace. "
            "Returns paths relative to the workspace root, always using forward slashes. "
            "Defaults to listing the entire workspace. "
            "Use the returned paths verbatim in read_file / write_file / delete_file."
        ),
        input_schema={"type": "object", "properties": {"path": {"type": "string", "default": "."}}},
        output_schema={"type": "object", "properties": {"files": {"type": "array"}}},
    )

    def __init__(self, workspace: Workspace, manager: WorkspaceManager) -> None:
        self._workspace = workspace
        self._manager = manager

    def run(self, params: dict) -> ToolResult:
        start = time.monotonic()
        try:
            target = self._manager.resolve_path(self._workspace, _norm_input(params.get("path", ".")))
            if not target.exists():
                return ToolResult(success=False, error=f"No such path: {target}", retryable=False)
            root = self._workspace.root_path.resolve()
            files = sorted(
                _to_posix(str(p.relative_to(root)))
                for p in target.rglob("*")
                if p.is_file()
            )
        except (WorkspaceError, OSError) as exc:
            return ToolResult(success=False, error=str(exc), retryable=False)
        return ToolResult(success=True, output={"files": files},
                          duration_ms=int((time.monotonic() - start) * 1000))


class DeleteFileTool:
    schema = ToolSchema(
        name="delete_file",
        description="Delete a file in the active workspace. Accepts forward slashes or backslashes.",
        input_schema={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
        output_schema={"type": "object", "properties": {"deleted": {"type": "boolean"}}},
    )

    def __init__(self, workspace: Workspace, manager: WorkspaceManager) -> None:
        self._workspace = workspace
        self._manager = manager

    def run(self, params: dict) -> ToolResult:
        start = time.monotonic()
        try:
            target = self._manager.resolve_path(self._workspace, _norm_input(params["path"]))
            if not target.exists():
                return ToolResult(success=False, error=f"No such file: {target}", retryable=False)
            target.unlink()
        except (WorkspaceError, OSError) as exc:
            return ToolResult(success=False, error=str(exc), retryable=False)
        return ToolResult(success=True, output={"deleted": True},
                          duration_ms=int((time.monotonic() - start) * 1000))


def register_file_tools(registry, workspace: Workspace, manager: WorkspaceManager) -> None:
    registry.register(ReadFileTool(workspace, manager))
    registry.register(WriteFileTool(workspace, manager))
    registry.register(ListFilesTool(workspace, manager))
    registry.register(DeleteFileTool(workspace, manager))
