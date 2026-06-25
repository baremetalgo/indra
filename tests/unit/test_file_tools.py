from __future__ import annotations

import pytest

from indra.storage.db import Database
from indra.storage.repositories import WorkspaceRepository
from indra.tools.base import ToolRegistry, ToolValidationError
from indra.tools.file_tools import register_file_tools
from indra.workspaces.workspace_manager import WorkspaceManager


@pytest.fixture
def registry_and_workspace(tmp_path):
    db = Database(str(tmp_path / "indra.db"))
    db.migrate()
    wm = WorkspaceManager(WorkspaceRepository(db))
    ws = wm.create("demo", str(tmp_path / "proj"))
    registry = ToolRegistry()
    register_file_tools(registry, ws, wm)
    return registry, ws


def test_write_then_read_round_trip(registry_and_workspace) -> None:
    registry, _ = registry_and_workspace
    write_result = registry.get("write_file").run({"path": "a.txt", "content": "hi"})
    assert write_result.success
    read_result = registry.get("read_file").run({"path": "a.txt"})
    assert read_result.success
    assert read_result.output["content"] == "hi"


def test_read_missing_file_fails_cleanly(registry_and_workspace) -> None:
    registry, _ = registry_and_workspace
    result = registry.get("read_file").run({"path": "missing.txt"})
    assert not result.success
    assert result.error


def test_path_escape_is_rejected(registry_and_workspace) -> None:
    registry, _ = registry_and_workspace
    result = registry.get("write_file").run({"path": "../escape.txt", "content": "x"})
    assert not result.success


def test_list_files_reports_relative_paths(registry_and_workspace) -> None:
    registry, _ = registry_and_workspace
    registry.get("write_file").run({"path": "nested/file.txt", "content": "x"})
    result = registry.get("list_files").run({"path": "."})
    assert result.success
    assert "nested/file.txt" in result.output["files"]


def test_delete_file_removes_it(registry_and_workspace) -> None:
    registry, _ = registry_and_workspace
    registry.get("write_file").run({"path": "to_delete.txt", "content": "x"})
    delete_result = registry.get("delete_file").run({"path": "to_delete.txt"})
    assert delete_result.success
    read_result = registry.get("read_file").run({"path": "to_delete.txt"})
    assert not read_result.success


def test_registry_input_validation_rejects_missing_required_field(registry_and_workspace) -> None:
    registry, _ = registry_and_workspace
    with pytest.raises(ToolValidationError):
        registry.validate_input("write_file", {"path": "a.txt"})  # missing 'content'
