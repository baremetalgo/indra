from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from indra.api.deps import get_app_state
from indra.workspaces.workspace_manager import WorkspaceError

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


class CreateWorkspaceRequest(BaseModel):
    name: str
    root_path: str
    is_default: bool = False


@router.post("")
def create_workspace(req: CreateWorkspaceRequest) -> dict:
    state = get_app_state()
    try:
        ws = state.workspaces.create(req.name, req.root_path, req.is_default)
    except WorkspaceError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"id": ws.id, "name": ws.name, "root_path": str(ws.root_path)}


@router.get("")
def list_workspaces() -> list[dict]:
    state = get_app_state()
    return [
        {"id": w.id, "name": w.name, "root_path": str(w.root_path), "is_default": w.is_default}
        for w in state.workspaces.list_all()
    ]


@router.delete("/{name}")
def delete_workspace(name: str) -> dict:
    state = get_app_state()
    state.workspaces.remove(name)
    return {"deleted": name}
