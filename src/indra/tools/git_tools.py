"""Git tools: structured, deterministic wrappers over common git operations.

Unlike the shell tool, these never take a raw command string from the
model — each tool has its own narrow schema (a commit message, a
branch name, an optional path filter), so there's no allowlist/parsing
question at all. Every git invocation is pinned to the workspace root
via ``git -C <root>``, so it can't act on a repository outside the
sandbox even if one exists on the host machine.
"""

from __future__ import annotations

import subprocess
import time

from indra.tools.base import ToolResult, ToolSchema
from indra.workspaces.workspace_manager import Workspace, WorkspaceError, WorkspaceManager

_DEFAULT_TIMEOUT = 30.0


def _run_git(workspace: Workspace, args: list[str], timeout: float) -> tuple[bool, str, str, int]:
    try:
        completed = subprocess.run(
            ["git", "-C", str(workspace.root_path), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        return False, "", f"git command timed out after {timeout}s", -1
    except FileNotFoundError:
        return False, "", "git executable not found on PATH", -1
    return completed.returncode == 0, completed.stdout, completed.stderr, completed.returncode


class GitStatusTool:
    schema = ToolSchema(
        name="git_status",
        description="Show the working tree status (branch, staged/unstaged/untracked files).",
        input_schema={"type": "object", "properties": {}},
        output_schema={"type": "object", "properties": {"status": {"type": "string"}}},
    )

    def __init__(self, workspace: Workspace, timeout: float = _DEFAULT_TIMEOUT) -> None:
        self.workspace = workspace
        self.timeout = timeout

    def run(self, params: dict) -> ToolResult:
        start = time.monotonic()
        ok, out, err, code = _run_git(self.workspace, ["status", "--porcelain=v1", "-b"], self.timeout)
        if not ok:
            return ToolResult(success=False, error=err or f"git status failed (exit {code})", retryable=False)
        return ToolResult(
            success=True, output={"status": out},
            duration_ms=int((time.monotonic() - start) * 1000),
        )


class GitDiffTool:
    schema = ToolSchema(
        name="git_diff",
        description="Show the diff of unstaged (or, if path given, a specific file's) changes.",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
        },
        output_schema={"type": "object", "properties": {"diff": {"type": "string"}}},
    )

    def __init__(self, workspace: Workspace, manager: WorkspaceManager, timeout: float = _DEFAULT_TIMEOUT) -> None:
        self.workspace = workspace
        self.manager = manager
        self.timeout = timeout

    def run(self, params: dict) -> ToolResult:
        start = time.monotonic()
        args = ["diff"]
        path = params.get("path")
        if path:
            try:
                self.manager.resolve_path(self.workspace, path)  # containment check only
            except WorkspaceError as exc:
                return ToolResult(success=False, error=str(exc), retryable=False)
            args += ["--", path]
        ok, out, err, code = _run_git(self.workspace, args, self.timeout)
        if not ok:
            return ToolResult(success=False, error=err or f"git diff failed (exit {code})", retryable=False)
        return ToolResult(
            success=True, output={"diff": out},
            duration_ms=int((time.monotonic() - start) * 1000),
        )


class GitLogTool:
    schema = ToolSchema(
        name="git_log",
        description="Show recent commit history (one line per commit).",
        input_schema={
            "type": "object",
            "properties": {"limit": {"type": "integer", "default": 10}},
        },
        output_schema={"type": "object", "properties": {"log": {"type": "string"}}},
    )

    def __init__(self, workspace: Workspace, timeout: float = _DEFAULT_TIMEOUT) -> None:
        self.workspace = workspace
        self.timeout = timeout

    def run(self, params: dict) -> ToolResult:
        start = time.monotonic()
        limit = max(1, min(int(params.get("limit", 10)), 200))
        ok, out, err, code = _run_git(
            self.workspace, ["log", f"-n{limit}", "--oneline"], self.timeout
        )
        if not ok:
            return ToolResult(success=False, error=err or f"git log failed (exit {code})", retryable=False)
        return ToolResult(
            success=True, output={"log": out},
            duration_ms=int((time.monotonic() - start) * 1000),
        )


class GitCommitTool:
    schema = ToolSchema(
        name="git_commit",
        description="Stage and commit changes with a message.",
        input_schema={
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "add_all": {"type": "boolean", "default": True},
            },
            "required": ["message"],
        },
        output_schema={"type": "object", "properties": {"output": {"type": "string"}}},
    )

    def __init__(self, workspace: Workspace, timeout: float = _DEFAULT_TIMEOUT) -> None:
        self.workspace = workspace
        self.timeout = timeout

    def run(self, params: dict) -> ToolResult:
        start = time.monotonic()
        if params.get("add_all", True):
            ok, _, err, code = _run_git(self.workspace, ["add", "-A"], self.timeout)
            if not ok:
                return ToolResult(success=False, error=err or f"git add failed (exit {code})", retryable=False)

        ok, out, err, code = _run_git(
            self.workspace, ["commit", "-m", params["message"]], self.timeout
        )
        if not ok:
            # "nothing to commit" is a deterministic, expected outcome, not a crash.
            return ToolResult(success=False, error=err or out or f"git commit failed (exit {code})", retryable=False)
        return ToolResult(
            success=True, output={"output": out},
            duration_ms=int((time.monotonic() - start) * 1000),
        )


class GitBranchTool:
    schema = ToolSchema(
        name="git_branch",
        description="List, create, or switch branches.",
        input_schema={
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["list", "create", "switch"]},
                "name": {"type": "string"},
            },
            "required": ["action"],
        },
        output_schema={"type": "object", "properties": {"output": {"type": "string"}}},
    )

    def __init__(self, workspace: Workspace, timeout: float = _DEFAULT_TIMEOUT) -> None:
        self.workspace = workspace
        self.timeout = timeout

    def run(self, params: dict) -> ToolResult:
        start = time.monotonic()
        action = params["action"]
        if action == "list":
            args = ["branch", "--list"]
        elif action == "create":
            if not params.get("name"):
                return ToolResult(success=False, error="'name' is required to create a branch", retryable=False)
            args = ["branch", params["name"]]
        elif action == "switch":
            if not params.get("name"):
                return ToolResult(success=False, error="'name' is required to switch branches", retryable=False)
            args = ["checkout", params["name"]]
        else:
            return ToolResult(success=False, error=f"unknown action: {action!r}", retryable=False)

        ok, out, err, code = _run_git(self.workspace, args, self.timeout)
        if not ok:
            return ToolResult(success=False, error=err or f"git {action} failed (exit {code})", retryable=False)
        return ToolResult(
            success=True, output={"output": out},
            duration_ms=int((time.monotonic() - start) * 1000),
        )


class GitStashTool:
    schema = ToolSchema(
        name="git_stash",
        description="Stash or pop uncommitted changes.",
        input_schema={
            "type": "object",
            "properties": {"action": {"type": "string", "enum": ["push", "pop", "list"]}},
            "required": ["action"],
        },
        output_schema={"type": "object", "properties": {"output": {"type": "string"}}},
    )

    def __init__(self, workspace: Workspace, timeout: float = _DEFAULT_TIMEOUT) -> None:
        self.workspace = workspace
        self.timeout = timeout

    def run(self, params: dict) -> ToolResult:
        start = time.monotonic()
        action = params["action"]
        if action not in ("push", "pop", "list"):
            return ToolResult(success=False, error=f"unknown action: {action!r}", retryable=False)
        ok, out, err, code = _run_git(self.workspace, ["stash", action], self.timeout)
        if not ok:
            return ToolResult(success=False, error=err or f"git stash {action} failed (exit {code})", retryable=False)
        return ToolResult(
            success=True, output={"output": out},
            duration_ms=int((time.monotonic() - start) * 1000),
        )


def register_git_tools(
    registry, workspace: Workspace, manager: WorkspaceManager, timeout: float = _DEFAULT_TIMEOUT
) -> None:
    registry.register(GitStatusTool(workspace, timeout))
    registry.register(GitDiffTool(workspace, manager, timeout))
    registry.register(GitLogTool(workspace, timeout))
    registry.register(GitCommitTool(workspace, timeout))
    registry.register(GitBranchTool(workspace, timeout))
    registry.register(GitStashTool(workspace, timeout))
