from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from indra.api.deps import get_app_state, index_and_build_repo_map
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
    index_and_build_repo_map(state, ws)  # initial index, cheap on an empty/small project
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


@router.post("/{name}/index")
def reindex_workspace(name: str) -> dict:
    state = get_app_state()
    try:
        ws = state.workspaces.get(name)
    except WorkspaceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    from indra.coding.file_index import FileIndexer
    from indra.coding.repo_explorer import RepoExplorer

    stats = FileIndexer(state.db).index_workspace(ws.id, ws.root_path)
    summary = RepoExplorer(state.db).build_repo_map(ws.id)
    return {
        "files_scanned": stats.files_scanned,
        "files_changed": stats.files_changed,
        "files_removed": stats.files_removed,
        "symbols_extracted": stats.symbols_extracted,
        "indexed_file_count": summary.indexed_file_count,
        "repo_map_preview": summary.map_text[:500],
    }
