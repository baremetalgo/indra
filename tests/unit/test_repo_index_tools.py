from __future__ import annotations

from indra.coding.dependency_graph import DependencyGraph
from indra.coding.file_index import FileIndexer
from indra.coding.symbol_index import SymbolIndex
from indra.storage.db import Database
from indra.storage.repositories import WorkspaceRepository
from indra.tools.repo_index_tools import FindImportsTool, SymbolSearchTool
from indra.workspaces.workspace_manager import WorkspaceManager


def _setup(tmp_path):
    db = Database(str(tmp_path / "indra.db"))
    db.migrate()
    wm = WorkspaceManager(WorkspaceRepository(db))
    root = tmp_path / "proj"
    root.mkdir()
    ws = wm.create("demo", str(root))
    (root / "module.py").write_text(
        "import os\n\ndef calculate_total(items):\n    return sum(items)\n"
    )
    FileIndexer(db).index_workspace(ws.id, root)
    return db, ws.id


def test_symbol_search_tool_returns_matches(tmp_path) -> None:
    db, workspace_id = _setup(tmp_path)
    tool = SymbolSearchTool(workspace_id, SymbolIndex(db))
    result = tool.run({"query": "calculate"})
    assert result.success
    assert result.output["matches"][0]["symbol_name"] == "calculate_total"


def test_symbol_search_tool_no_match(tmp_path) -> None:
    db, workspace_id = _setup(tmp_path)
    tool = SymbolSearchTool(workspace_id, SymbolIndex(db))
    result = tool.run({"query": "does_not_exist"})
    assert result.success
    assert result.output["matches"] == []


def test_find_imports_tool_by_file(tmp_path) -> None:
    db, workspace_id = _setup(tmp_path)
    tool = FindImportsTool(workspace_id, DependencyGraph(db))
    result = tool.run({"file_path": "module.py"})
    assert result.success
    assert "import os" in result.output["imports"]


def test_find_imports_tool_by_module(tmp_path) -> None:
    db, workspace_id = _setup(tmp_path)
    tool = FindImportsTool(workspace_id, DependencyGraph(db))
    result = tool.run({"module": "os"})
    assert result.success
    assert "module.py" in result.output["imports"]


def test_find_imports_tool_requires_a_param(tmp_path) -> None:
    db, workspace_id = _setup(tmp_path)
    tool = FindImportsTool(workspace_id, DependencyGraph(db))
    result = tool.run({})
    assert not result.success
    assert result.retryable is False
