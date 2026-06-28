from __future__ import annotations

from pathlib import Path

from indra.coding.file_index import FileIndexer
from indra.storage.db import Database
from indra.storage.repositories import WorkspaceRepository
from indra.workspaces.workspace_manager import WorkspaceManager


def _make_indexer(tmp_path) -> tuple[FileIndexer, str, Path]:
    db = Database(str(tmp_path / "indra.db"))
    db.migrate()
    wm = WorkspaceManager(WorkspaceRepository(db))
    root = tmp_path / "proj"
    root.mkdir()
    ws = wm.create("demo", str(root))
    return FileIndexer(db), ws.id, root


def test_indexing_a_python_file_extracts_functions_and_classes(tmp_path) -> None:
    indexer, workspace_id, root = _make_indexer(tmp_path)
    (root / "module.py").write_text(
        "def top_level():\n    pass\n\n"
        "class Thing:\n    def method(self):\n        pass\n"
    )
    stats = indexer.index_workspace(workspace_id, root)

    assert stats.files_changed == 1
    assert stats.symbols_extracted == 3  # top_level, Thing, method

    with indexer._db.connect() as conn:
        rows = conn.execute(
            "SELECT symbol_name, symbol_kind FROM repo_symbols WHERE workspace_id = ? "
            "ORDER BY start_line",
            (workspace_id,),
        ).fetchall()
    kinds = {(r["symbol_name"], r["symbol_kind"]) for r in rows}
    assert ("top_level", "function") in kinds
    assert ("Thing", "class") in kinds
    assert ("method", "method") in kinds  # nested in a class -> method, not function


def test_unchanged_file_is_skipped_on_second_index(tmp_path) -> None:
    indexer, workspace_id, root = _make_indexer(tmp_path)
    (root / "module.py").write_text("def f():\n    pass\n")
    indexer.index_workspace(workspace_id, root)

    second = indexer.index_workspace(workspace_id, root)
    assert second.files_changed == 0
    assert second.files_scanned == 1


def test_modified_file_is_reindexed(tmp_path) -> None:
    indexer, workspace_id, root = _make_indexer(tmp_path)
    target = root / "module.py"
    target.write_text("def f():\n    pass\n")
    indexer.index_workspace(workspace_id, root)

    target.write_text("def f():\n    pass\n\ndef g():\n    pass\n")
    second = indexer.index_workspace(workspace_id, root)
    assert second.files_changed == 1
    assert second.symbols_extracted == 2


def test_deleted_file_is_removed_from_the_index(tmp_path) -> None:
    indexer, workspace_id, root = _make_indexer(tmp_path)
    target = root / "module.py"
    target.write_text("def f():\n    pass\n")
    indexer.index_workspace(workspace_id, root)

    target.unlink()
    second = indexer.index_workspace(workspace_id, root)
    assert second.files_removed == 1

    with indexer._db.connect() as conn:
        remaining = conn.execute(
            "SELECT COUNT(*) AS n FROM repo_symbols WHERE workspace_id = ?", (workspace_id,)
        ).fetchone()["n"]
    assert remaining == 0


def test_imports_are_extracted(tmp_path) -> None:
    indexer, workspace_id, root = _make_indexer(tmp_path)
    (root / "module.py").write_text("import os\nfrom pathlib import Path\n")
    indexer.index_workspace(workspace_id, root)

    with indexer._db.connect() as conn:
        rows = conn.execute(
            "SELECT imported_path FROM repo_imports WHERE workspace_id = ?", (workspace_id,)
        ).fetchall()
    imported = {r["imported_path"] for r in rows}
    assert "import os" in imported
    assert "from pathlib import Path" in imported


def test_gitignored_files_are_skipped(tmp_path) -> None:
    indexer, workspace_id, root = _make_indexer(tmp_path)
    (root / ".gitignore").write_text("ignored_dir/\n")
    (root / "ignored_dir").mkdir()
    (root / "ignored_dir" / "module.py").write_text("def f():\n    pass\n")
    (root / "kept.py").write_text("def g():\n    pass\n")

    stats = indexer.index_workspace(workspace_id, root)
    # .gitignore itself and kept.py are legitimately scanned; only the
    # gitignored directory's content must be excluded.
    assert stats.files_scanned == 2
    assert stats.symbols_extracted == 1  # only kept.py's `g`, not ignored_dir's `f`


def test_default_ignores_skip_common_noise_directories(tmp_path) -> None:
    indexer, workspace_id, root = _make_indexer(tmp_path)
    (root / "__pycache__").mkdir()
    (root / "__pycache__" / "module.cpython-312.pyc").write_text("junk")
    (root / "kept.py").write_text("def g():\n    pass\n")

    stats = indexer.index_workspace(workspace_id, root)
    assert stats.files_scanned == 1


def test_non_code_files_are_tracked_but_not_parsed_for_symbols(tmp_path) -> None:
    indexer, workspace_id, root = _make_indexer(tmp_path)
    (root / "README.md").write_text("# hello\n")

    stats = indexer.index_workspace(workspace_id, root)
    assert stats.files_scanned == 1
    assert stats.symbols_extracted == 0
