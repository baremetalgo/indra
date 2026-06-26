from __future__ import annotations

import subprocess

import pytest

from indra.storage.db import Database
from indra.storage.repositories import WorkspaceRepository
from indra.tools.git_tools import (
    GitBranchTool,
    GitCommitTool,
    GitDiffTool,
    GitLogTool,
    GitStashTool,
    GitStatusTool,
)
from indra.workspaces.workspace_manager import Workspace, WorkspaceManager


def _init_repo(workspace: Workspace) -> None:
    root = str(workspace.root_path)
    subprocess.run(["git", "init", "-q", root], check=True)
    subprocess.run(["git", "-C", root, "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", root, "config", "user.name", "Test"], check=True)


@pytest.fixture
def workspace_and_manager(tmp_path) -> tuple[Workspace, WorkspaceManager]:
    db = Database(str(tmp_path / "indra.db"))
    db.migrate()
    wm = WorkspaceManager(WorkspaceRepository(db))
    ws = wm.create("demo", str(tmp_path / "proj"))
    _init_repo(ws)
    return ws, wm


@pytest.fixture
def workspace(workspace_and_manager) -> Workspace:
    return workspace_and_manager[0]


def test_status_on_clean_repo_reports_nothing_to_commit(workspace: Workspace) -> None:
    result = GitStatusTool(workspace).run({})
    assert result.success
    assert "##" in result.output["status"] or result.output["status"] == ""


def test_commit_then_log_shows_the_commit(workspace: Workspace) -> None:
    (workspace.root_path / "file.txt").write_text("hello")
    commit_result = GitCommitTool(workspace).run({"message": "add file"})
    assert commit_result.success

    log_result = GitLogTool(workspace).run({"limit": 5})
    assert log_result.success
    assert "add file" in log_result.output["log"]


def test_commit_with_nothing_to_commit_fails_cleanly(workspace: Workspace) -> None:
    result = GitCommitTool(workspace).run({"message": "empty commit attempt"})
    assert not result.success
    assert result.retryable is False


def test_diff_reflects_unstaged_changes(workspace: Workspace) -> None:
    (workspace.root_path / "file.txt").write_text("v1")
    GitCommitTool(workspace).run({"message": "v1"})
    (workspace.root_path / "file.txt").write_text("v2")

    result = GitDiffTool(workspace, manager=None).run({})
    assert result.success
    assert "v2" in result.output["diff"] or "+v2" in result.output["diff"]


def test_diff_with_path_filter_uses_workspace_containment(workspace_and_manager) -> None:
    workspace, manager = workspace_and_manager
    (workspace.root_path / "file.txt").write_text("v1")
    GitCommitTool(workspace).run({"message": "v1"})
    (workspace.root_path / "file.txt").write_text("v2")

    result = GitDiffTool(workspace, manager).run({"path": "file.txt"})
    assert result.success
    assert "file.txt" in result.output["diff"]

    escape_result = GitDiffTool(workspace, manager).run({"path": "../../etc/passwd"})
    assert not escape_result.success
    assert escape_result.retryable is False


def test_branch_create_then_list(workspace: Workspace) -> None:
    (workspace.root_path / "f.txt").write_text("x")
    GitCommitTool(workspace).run({"message": "init"})

    create_result = GitBranchTool(workspace).run({"action": "create", "name": "feature-x"})
    assert create_result.success

    list_result = GitBranchTool(workspace).run({"action": "list"})
    assert list_result.success
    assert "feature-x" in list_result.output["output"]


def test_branch_create_without_name_fails_cleanly(workspace: Workspace) -> None:
    result = GitBranchTool(workspace).run({"action": "create"})
    assert not result.success
    assert result.retryable is False


def test_stash_push_then_list(workspace: Workspace) -> None:
    (workspace.root_path / "f.txt").write_text("x")
    GitCommitTool(workspace).run({"message": "init"})
    (workspace.root_path / "f.txt").write_text("y")

    push_result = GitStashTool(workspace).run({"action": "push"})
    assert push_result.success

    list_result = GitStashTool(workspace).run({"action": "list"})
    assert list_result.success
