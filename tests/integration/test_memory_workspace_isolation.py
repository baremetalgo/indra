from __future__ import annotations

from indra.core.memory_manager import MemoryManager
from indra.memory.long_term_memory import LongTermMemoryStore
from indra.storage.db import Database
from indra.storage.repositories import WorkspaceRepository
from indra.workspaces.workspace_manager import WorkspaceManager


def test_long_term_memory_does_not_leak_across_workspaces(tmp_path) -> None:
    """Reproduces a real reported bug: memory from one project showing up
    in another. memory_items must be scoped by workspace_id end to end."""
    db = Database(str(tmp_path / "indra.db"))
    db.migrate()
    wm = WorkspaceManager(WorkspaceRepository(db))
    ws_a = wm.create("project-a", str(tmp_path / "a"))
    ws_b = wm.create("project-b", str(tmp_path / "b"))

    store = LongTermMemoryStore(db)
    mem_a = MemoryManager(store, workspace_id=ws_a.id, max_tokens=1000)
    mem_b = MemoryManager(store, workspace_id=ws_b.id, max_tokens=1000)

    mem_a.promote_to_long_term(content="secret detail about project A", kind="fact")
    mem_b.promote_to_long_term(content="unrelated detail about project B", kind="fact")

    a_context = [i.content for i in mem_a.retrieve_context()]
    b_context = [i.content for i in mem_b.retrieve_context()]

    assert "secret detail about project A" in a_context
    assert "secret detail about project A" not in b_context
    assert "unrelated detail about project B" in b_context
    assert "unrelated detail about project B" not in a_context


def test_query_requires_workspace_id_and_filters_by_it(tmp_path) -> None:
    db = Database(str(tmp_path / "indra.db"))
    db.migrate()
    wm = WorkspaceManager(WorkspaceRepository(db))
    ws_a = wm.create("project-a", str(tmp_path / "a"))
    ws_b = wm.create("project-b", str(tmp_path / "b"))

    store = LongTermMemoryStore(db)
    store.add(workspace_id=ws_a.id, scope="long_term", kind="fact", content="A only")
    store.add(workspace_id=ws_b.id, scope="long_term", kind="fact", content="B only")

    results_a = store.query(workspace_id=ws_a.id)
    assert [r.content for r in results_a] == ["A only"]

    results_b = store.query(workspace_id=ws_b.id)
    assert [r.content for r in results_b] == ["B only"]
