from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from indra.api.deps import get_app_state
from indra.storage.repositories import SessionRepository
from indra.workspaces.workspace_manager import WorkspaceError

router = APIRouter(prefix="/sessions", tags=["sessions"])


class CreateSessionRequest(BaseModel):
    workspace: str


@router.post("")
def create_session(req: CreateSessionRequest) -> dict:
    state = get_app_state()
    try:
        workspace = state.workspaces.get(req.workspace)
    except WorkspaceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    session_id = SessionRepository(state.db).create(workspace.id)
    return {"session_id": session_id, "workspace": workspace.name}
