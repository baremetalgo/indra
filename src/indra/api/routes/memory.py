from __future__ import annotations

from fastapi import APIRouter, HTTPException

from indra.api.deps import get_app_state
from indra.memory.long_term_memory import LongTermMemoryStore
from indra.workspaces.workspace_manager import WorkspaceError

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("")
def query_memory(workspace: str, scope: str | None = None, limit: int = 50) -> list[dict]:
    state = get_app_state()
    try:
        ws = state.workspaces.get(workspace)
    except WorkspaceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    store = LongTermMemoryStore(state.db)
    items = store.query(workspace_id=ws.id, scope=scope, limit=limit)
    return [
        {
            "id": i.id,
            "scope": i.scope,
            "kind": i.kind,
            "content": i.content,
            "relevance": i.relevance,
            "created_at": i.created_at.isoformat(),
        }
        for i in items
    ]
