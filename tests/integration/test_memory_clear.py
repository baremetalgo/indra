from __future__ import annotations

from indra.memory.long_term_memory import LongTermMemoryStore
from indra.storage.db import Database
from indra.storage.repositories import WorkspaceRepository
from indra.workspaces.workspace_manager import WorkspaceManager


def test_clear_removes_all_items_for_a_workspace_only(tmp_path) -> None:
    db = Database(str(tmp_path / "indra.db"))
    db.migrate()
    wm = WorkspaceManager(WorkspaceRepository(db))
    ws_a = wm.create("a", str(tmp_path / "a"))
    ws_b = wm.create("b", str(tmp_path / "b"))

    store = LongTermMemoryStore(db)
    store.add(workspace_id=ws_a.id, scope="long_term", kind="fact", content="old contaminated entry")
    store.add(workspace_id=ws_a.id, scope="long_term", kind="fact", content="another old entry")
    store.add(workspace_id=ws_b.id, scope="long_term", kind="fact", content="unrelated, must survive")

    with db.connect() as conn:
        deleted = conn.execute(
            "DELETE FROM memory_items WHERE workspace_id = ?", (ws_a.id,)
        ).rowcount

    assert deleted == 2
    assert store.query(workspace_id=ws_a.id) == []
    remaining = store.query(workspace_id=ws_b.id)
    assert len(remaining) == 1
    assert remaining[0].content == "unrelated, must survive"
