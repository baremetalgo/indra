from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from indra.api.deps import build_agent_runtime, get_app_state
from indra.core.run_profile import resolve_run_profile
from indra.storage.repositories import SessionRepository, TaskRepository

router = APIRouter(prefix="/tasks", tags=["tasks"])


class CreateTaskRequest(BaseModel):
    session_id: str
    description: str
    workspace: str
    thinking_level: str | None = None
    reasoning_effort: int | None = None
    max_steps: int | None = None


@router.post("")
def create_and_run_task(req: CreateTaskRequest) -> dict:
    state = get_app_state()
    workspace = state.workspaces.get(req.workspace)
    task = TaskRepository(state.db).create(req.session_id, req.description)

    profile = resolve_run_profile(
        state.config.agent,
        thinking_level=req.thinking_level,
        reasoning_effort=req.reasoning_effort,
        max_steps=req.max_steps,
    )
    runtime = build_agent_runtime(state, workspace)
    result = runtime.run_task(task, profile)
    return {
        "task_id": result.task_id,
        "status": result.status.value,
        "summary": result.summary,
        "artifacts": result.artifacts,
        "llm_calls_used": result.llm_calls_used,
        "prompt_tokens": result.prompt_tokens,
        "completion_tokens": result.completion_tokens,
        "llm_seconds": result.llm_seconds,
        "total_seconds": result.total_seconds,
        "run_profile": {
            "thinking_level": profile.thinking_level,
            "max_llm_calls": profile.max_llm_calls,
            "max_steps": profile.max_steps,
        },
    }


@router.get("/{task_id}")
def get_task(task_id: str) -> dict:
    state = get_app_state()
    row = TaskRepository(state.db).get(task_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Unknown task")
    return dict(row)
