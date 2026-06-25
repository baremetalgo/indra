from __future__ import annotations

import pytest

from indra.storage.db import Database
from indra.storage.repositories import WorkspaceRepository
from indra.workspaces.workspace_manager import WorkspaceError, WorkspaceManager


@pytest.fixture
def manager(tmp_path) -> WorkspaceManager:
    db = Database(str(tmp_path / "indra.db"))
    db.migrate()
    return WorkspaceManager(WorkspaceRepository(db))


def test_create_and_get_workspace(manager: WorkspaceManager, tmp_path) -> None:
    ws = manager.create("demo", str(tmp_path / "proj"))
    fetched = manager.get("demo")
    assert fetched.name == "demo"
    assert fetched.root_path == ws.root_path


def test_unknown_workspace_raises(manager: WorkspaceManager) -> None:
    with pytest.raises(WorkspaceError):
        manager.get("nope")


def test_duplicate_workspace_name_rejected(manager: WorkspaceManager, tmp_path) -> None:
    manager.create("demo", str(tmp_path / "proj1"))
    with pytest.raises(WorkspaceError):
        manager.create("demo", str(tmp_path / "proj2"))


def test_resolve_path_allows_paths_inside_root(manager: WorkspaceManager, tmp_path) -> None:
    ws = manager.create("demo", str(tmp_path / "proj"))
    resolved = manager.resolve_path(ws, "subdir/file.txt")
    assert str(resolved).startswith(str(ws.root_path))


@pytest.mark.parametrize("escape", ["../outside.txt", "../../etc/passwd", "../../../x"])
def test_resolve_path_blocks_escapes(manager: WorkspaceManager, tmp_path, escape: str) -> None:
    ws = manager.create("demo", str(tmp_path / "proj"))
    with pytest.raises(WorkspaceError):
        manager.resolve_path(ws, escape)


def test_resolve_path_blocks_symlink_escape(manager: WorkspaceManager, tmp_path) -> None:
    ws = manager.create("demo", str(tmp_path / "proj"))
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("nope")
    symlink = ws.root_path / "escape_link"
    symlink.symlink_to(outside)
    with pytest.raises(WorkspaceError):
        manager.resolve_path(ws, "escape_link/secret.txt")
