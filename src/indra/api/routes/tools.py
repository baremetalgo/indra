from __future__ import annotations

from fastapi import APIRouter, HTTPException

from indra.api.deps import build_tool_registry, get_app_state
from indra.workspaces.workspace_manager import WorkspaceError

router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("")
def list_tools(workspace: str) -> list[dict]:
    state = get_app_state()
    try:
        ws = state.workspaces.get(workspace)
    except WorkspaceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    registry = build_tool_registry(ws, state.workspaces, state.config.shell)
    return [
        {"name": s.name, "description": s.description}
        for s in registry.list_schemas()
    ]
