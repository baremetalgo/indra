from __future__ import annotations

from fastapi import APIRouter

from indra.api.deps import get_app_state
from indra.memory.long_term_memory import LongTermMemoryStore

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("")
def query_memory(scope: str | None = None, limit: int = 50) -> list[dict]:
    state = get_app_state()
    store = LongTermMemoryStore(state.db)
    items = store.query(scope=scope, limit=limit)
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
