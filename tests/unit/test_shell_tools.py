from __future__ import annotations

import sys

import pytest

from indra.config.schema import ShellConfig
from indra.storage.db import Database
from indra.storage.repositories import WorkspaceRepository
from indra.tools.shell_tools import ShellTool, _executable_name
from indra.workspaces.workspace_manager import WorkspaceManager


@pytest.fixture
def tool(tmp_path) -> ShellTool:
    db = Database(str(tmp_path / "indra.db"))
    db.migrate()
    wm = WorkspaceManager(WorkspaceRepository(db))
    ws = wm.create("demo", str(tmp_path / "proj"))
    config = ShellConfig(allowlist=("python3", "python", "echo"), timeout_seconds=5.0)
    return ShellTool(ws, wm, config)


def test_allowed_command_runs(tool: ShellTool) -> None:
    result = tool.run({"command": f"{sys.executable} -c \"print('hello')\""})
    assert result.success
    assert "hello" in result.output["stdout"]
    assert result.output["exit_code"] == 0


def test_disallowed_command_is_rejected_without_running(tool: ShellTool) -> None:
    result = tool.run({"command": "curl http://example.com"})
    assert not result.success
    assert result.retryable is False
    assert "allowlist" in result.error


def test_allow_arbitrary_bypasses_the_allowlist(tmp_path) -> None:
    db = Database(str(tmp_path / "indra.db"))
    db.migrate()
    wm = WorkspaceManager(WorkspaceRepository(db))
    ws = wm.create("demo", str(tmp_path / "proj"))
    config = ShellConfig(allowlist=(), allow_arbitrary=True, timeout_seconds=5.0)
    tool = ShellTool(ws, wm, config)
    result = tool.run({"command": f"{sys.executable} -c \"print('bypassed')\""})
    assert result.success
    assert "bypassed" in result.output["stdout"]


def test_nonzero_exit_code_is_reported_as_failure(tool: ShellTool) -> None:
    result = tool.run({"command": f"{sys.executable} -c \"import sys; sys.exit(3)\""})
    assert not result.success
    assert result.output["exit_code"] == 3
    assert result.retryable is False


def test_timeout_is_enforced(tmp_path) -> None:
    db = Database(str(tmp_path / "indra.db"))
    db.migrate()
    wm = WorkspaceManager(WorkspaceRepository(db))
    ws = wm.create("demo", str(tmp_path / "proj"))
    config = ShellConfig(allowlist=("python3", "python"), timeout_seconds=0.3)
    tool = ShellTool(ws, wm, config)
    result = tool.run({"command": f"{sys.executable} -c \"import time; time.sleep(5)\""})
    assert not result.success
    assert "timed out" in result.error


def test_cwd_escape_is_rejected(tool: ShellTool) -> None:
    result = tool.run({"command": "echo hi", "cwd": "../../etc"})
    assert not result.success
    assert result.retryable is False


def test_output_is_truncated_past_the_configured_byte_limit(tmp_path) -> None:
    db = Database(str(tmp_path / "indra.db"))
    db.migrate()
    wm = WorkspaceManager(WorkspaceRepository(db))
    ws = wm.create("demo", str(tmp_path / "proj"))
    config = ShellConfig(allowlist=("python3", "python"), timeout_seconds=5.0, max_output_bytes=50)
    tool = ShellTool(ws, wm, config)
    result = tool.run({"command": f"{sys.executable} -c \"print('x' * 1000)\""})
    assert result.success
    assert result.output["truncated"] is True
    assert len(result.output["stdout"]) < 1000


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("python", "python"),
        ("python.exe", "python"),
        ("C:\\Python312\\python.exe", "python"),
        ("/usr/bin/git", "git"),
        ("GIT", "git"),
    ],
)
def test_executable_name_normalization(raw: str, expected: str) -> None:
    assert _executable_name(raw) == expected
