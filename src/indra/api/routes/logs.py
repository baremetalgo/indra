from __future__ import annotations

from fastapi import APIRouter

from indra.api.deps import get_app_state

router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("/{task_id}")
def get_task_logs(task_id: str) -> list[dict]:
    state = get_app_state()
    with state.db.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM tool_calls WHERE task_id = ? ORDER BY created_at", (task_id,)
        ).fetchall()
    return [dict(row) for row in rows]
