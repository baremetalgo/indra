"""Shell tool: the highest-risk tool in the system, gated accordingly.

Safety properties, in order of how much they matter:
1. Never uses ``shell=True`` — the command string is tokenized with
   ``shlex`` and executed as an argument list, so there's no shell
   metacharacter injection (``;``, ``|``, ``&&``, backticks, etc. are
   just inert characters to a non-shell ``argv``, not control flow).
2. The executable (argv[0]) must be on the configured allowlist unless
   ``shell.allow_arbitrary`` is explicitly set — off by default.
3. ``cwd`` is resolved through the same workspace path-containment
   check as file tools; a command cannot be pointed outside the
   workspace by its working directory.
4. Bounded timeout and bounded captured output (stdout/stderr truncated
   past a configured byte limit) so a runaway or chatty command can't
   hang the agent loop or blow the context budget.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import time

from indra.config.schema import ShellConfig
from indra.tools.base import ToolResult, ToolSchema
from indra.workspaces.workspace_manager import Workspace, WorkspaceError, WorkspaceManager

RUN_SHELL_SCHEMA = ToolSchema(
    name="run_shell",
    description=(
        "Run a single shell command inside the workspace. The command's "
        "executable must be on the configured allowlist (e.g. git, python, "
        "npm, pytest) unless arbitrary execution has been explicitly enabled."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "command": {"type": "string"},
            "cwd": {"type": "string", "default": "."},
        },
        "required": ["command"],
    },
    output_schema={
        "type": "object",
        "properties": {
            "stdout": {"type": "string"},
            "stderr": {"type": "string"},
            "exit_code": {"type": "integer"},
            "truncated": {"type": "boolean"},
        },
    },
)


def _executable_name(argv0: str) -> str:
    """Normalize an executable for allowlist comparison.

    Strips a path prefix and a Windows-style extension, so
    ``C:\\Python312\\python.exe`` and ``python`` both match ``python``.
    Splits on both separators explicitly (rather than ``os.path``,
    which is platform-specific) since the value being normalized may
    use either style regardless of the host OS running this code.
    """
    base = argv0.replace("\\", "/").rsplit("/", 1)[-1]
    for ext in (".exe", ".bat", ".cmd", ".com"):
        if base.lower().endswith(ext):
            base = base[: -len(ext)]
            break
    return base.lower()


class ShellTool:
    schema = RUN_SHELL_SCHEMA

    def __init__(self, workspace: Workspace, manager: WorkspaceManager, config: ShellConfig) -> None:
        self.workspace = workspace
        self.manager = manager
        self.config = config

    def run(self, params: dict) -> ToolResult:
        command = params["command"]
        try:
            argv = shlex.split(command, posix=(os.name != "nt"))
        except ValueError as exc:
            return ToolResult(success=False, error=f"could not parse command: {exc}", retryable=False)

        if not argv:
            return ToolResult(success=False, error="empty command", retryable=False)

        if not self.config.allow_arbitrary:
            name = _executable_name(argv[0])
            allowed = {a.lower() for a in self.config.allowlist}
            if name not in allowed:
                return ToolResult(
                    success=False,
                    error=(
                        f"command '{argv[0]}' is not in the shell allowlist "
                        f"({sorted(allowed)}). Set shell.allow_arbitrary: true "
                        "in config to bypass this."
                    ),
                    retryable=False,
                )

        try:
            cwd = self.manager.resolve_path(self.workspace, params.get("cwd", "."))
        except WorkspaceError as exc:
            return ToolResult(success=False, error=str(exc), retryable=False)

        start = time.monotonic()
        try:
            completed = subprocess.run(
                argv,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=self.config.timeout_seconds,
                shell=False,
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                error=f"command timed out after {self.config.timeout_seconds}s",
                retryable=False,
            )
        except FileNotFoundError as exc:
            return ToolResult(success=False, error=str(exc), retryable=False)
        except OSError as exc:
            return ToolResult(success=False, error=str(exc), retryable=False)

        stdout, stdout_truncated = _truncate(completed.stdout, self.config.max_output_bytes)
        stderr, stderr_truncated = _truncate(completed.stderr, self.config.max_output_bytes)

        return ToolResult(
            success=completed.returncode == 0,
            output={
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": completed.returncode,
                "truncated": stdout_truncated or stderr_truncated,
            },
            error=None if completed.returncode == 0 else f"exit code {completed.returncode}",
            duration_ms=int((time.monotonic() - start) * 1000),
            retryable=False,  # a non-zero exit code from the same argv won't change on retry
        )


def _truncate(text: str, max_bytes: int) -> tuple[str, bool]:
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= max_bytes:
        return text, False
    return encoded[:max_bytes].decode("utf-8", errors="ignore") + "\n...[truncated]", True


def register_shell_tools(
    registry, workspace: Workspace, manager: WorkspaceManager, config: ShellConfig
) -> None:
    registry.register(ShellTool(workspace, manager, config))
