from __future__ import annotations

from indra.coding.dependency_graph import DependencyGraph
from indra.coding.file_index import FileIndexer
from indra.coding.repo_explorer import RepoExplorer
from indra.coding.symbol_index import SymbolIndex
from indra.storage.db import Database
from indra.storage.repositories import WorkspaceRepository
from indra.workspaces.workspace_manager import WorkspaceManager


def _setup(tmp_path):
    db = Database(str(tmp_path / "indra.db"))
    db.migrate()
    wm = WorkspaceManager(WorkspaceRepository(db))
    root = tmp_path / "proj"
    root.mkdir()
    ws = wm.create("demo", str(root))
    return db, ws.id, root


def test_symbol_search_finds_by_substring(tmp_path) -> None:
    db, workspace_id, root = _setup(tmp_path)
    (root / "module.py").write_text("def calculate_total():\n    pass\n")
    FileIndexer(db).index_workspace(workspace_id, root)

    index = SymbolIndex(db)
    hits = index.search(workspace_id, "calc")
    assert len(hits) == 1
    assert hits[0].symbol_name == "calculate_total"


def test_symbol_search_is_scoped_to_workspace(tmp_path) -> None:
    db = Database(str(tmp_path / "indra.db"))
    db.migrate()
    wm = WorkspaceManager(WorkspaceRepository(db))
    root_a = tmp_path / "a"
    root_a.mkdir()
    root_b = tmp_path / "b"
    root_b.mkdir()
    ws_a = wm.create("a", str(root_a))
    ws_b = wm.create("b", str(root_b))

    (root_a / "module.py").write_text("def only_in_a():\n    pass\n")
    (root_b / "module.py").write_text("def only_in_b():\n    pass\n")
    FileIndexer(db).index_workspace(ws_a.id, root_a)
    FileIndexer(db).index_workspace(ws_b.id, root_b)

    index = SymbolIndex(db)
    assert [h.symbol_name for h in index.search(ws_a.id, "only_in")] == ["only_in_a"]
    assert [h.symbol_name for h in index.search(ws_b.id, "only_in")] == ["only_in_b"]


def test_dependency_graph_imports_of(tmp_path) -> None:
    db, workspace_id, root = _setup(tmp_path)
    (root / "module.py").write_text("import json\nimport os\n")
    FileIndexer(db).index_workspace(workspace_id, root)

    graph = DependencyGraph(db)
    imports = graph.imports_of(workspace_id, "module.py")
    assert "import json" in imports
    assert "import os" in imports


def test_dependency_graph_importers_of(tmp_path) -> None:
    db, workspace_id, root = _setup(tmp_path)
    (root / "a.py").write_text("import json\n")
    (root / "b.py").write_text("x = 1\n")
    FileIndexer(db).index_workspace(workspace_id, root)

    graph = DependencyGraph(db)
    importers = graph.importers_of(workspace_id, "json")
    assert importers == ["a.py"]


def test_repo_explorer_builds_a_compact_map(tmp_path) -> None:
    db, workspace_id, root = _setup(tmp_path)
    (root / "module.py").write_text("def foo():\n    pass\n\nclass Bar:\n    pass\n")
    FileIndexer(db).index_workspace(workspace_id, root)

    summary = RepoExplorer(db).build_repo_map(workspace_id)
    assert "module.py" in summary.map_text
    assert "function foo" in summary.map_text
    assert "class Bar" in summary.map_text
    assert summary.indexed_file_count == 1


def test_repo_explorer_handles_empty_workspace(tmp_path) -> None:
    db, workspace_id, root = _setup(tmp_path)
    summary = RepoExplorer(db).build_repo_map(workspace_id)
    assert "no indexed files" in summary.map_text
