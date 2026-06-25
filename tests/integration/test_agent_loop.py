from __future__ import annotations

import json

import pytest

from indra.config.schema import AgentConfig
from indra.core.agent import AgentRuntime
from indra.core.context_manager import ContextManager
from indra.core.executor import Executor
from indra.core.memory_manager import MemoryManager
from indra.core.planner import Planner
from indra.core.run_profile import resolve_run_profile
from indra.core.task_manager import TaskManager
from indra.memory.long_term_memory import LongTermMemoryStore
from indra.prompts.loader import PromptManager
from indra.providers.mock_provider import MockProvider
from indra.schemas.task import TaskStatus
from indra.storage.db import Database
from indra.storage.repositories import (
    PlanRepository,
    SessionRepository,
    TaskRepository,
    ToolCallRepository,
    WorkspaceRepository,
)
from indra.tools.base import ToolRegistry
from indra.tools.file_tools import register_file_tools
from indra.workspaces.workspace_manager import WorkspaceManager


@pytest.fixture
def harness(tmp_path):
    db = Database(str(tmp_path / "indra.db"))
    db.migrate()
    wm = WorkspaceManager(WorkspaceRepository(db))
    workspace = wm.create("demo", str(tmp_path / "project"))
    session_id = SessionRepository(db).create(workspace.id)

    registry = ToolRegistry()
    register_file_tools(registry, workspace, wm)

    provider = MockProvider()
    prompts = PromptManager()
    mem = MemoryManager(LongTermMemoryStore(db), max_tokens=300)

    runtime = AgentRuntime(
        task_manager=TaskManager(TaskRepository(db)),
        planner=Planner(provider, prompts),
        executor=Executor(provider, prompts, registry),
        memory=mem,
        context=ContextManager(mem),
        plan_repo=PlanRepository(db),
        tool_call_repo=ToolCallRepository(db),
    )
    return {
        "db": db,
        "workspace": workspace,
        "session_id": session_id,
        "provider": provider,
        "runtime": runtime,
    }


def test_successful_task_writes_file_and_completes(harness, tmp_path) -> None:
    provider = harness["provider"]
    provider.queue(json.dumps({
        "goal": "create hello.txt",
        "subtasks": [{"description": "write hello.txt", "tool_hint": "write_file"}],
        "success_criteria": ["file exists"],
    }))
    provider.queue(json.dumps({
        "tool_name": "write_file",
        "params": {"path": "hello.txt", "content": "hello from indra\n"},
        "reason": "create the requested file",
    }))

    task = TaskManager(TaskRepository(harness["db"])).create(
        harness["session_id"], "create hello.txt with greeting"
    )
    profile = resolve_run_profile(AgentConfig(), thinking_level="low")
    result = harness["runtime"].run_task(task, profile)

    assert result.status == TaskStatus.DONE
    assert result.llm_calls_used == 2
    written = harness["workspace"].root_path / "hello.txt"
    assert written.read_text() == "hello from indra\n"


def test_call_budget_is_never_exceeded(harness) -> None:
    provider = harness["provider"]
    # Plan with 5 subtasks but a budget of only 3 total calls (low thinking level).
    provider.queue(json.dumps({
        "goal": "do a lot",
        "subtasks": [{"description": f"step {i}"} for i in range(5)],
    }))
    # Every executor call returns an unknown tool -> ToolSelectionError -> failure path.
    for _ in range(10):
        provider.queue(json.dumps({"tool_name": "nonexistent_tool", "params": {}}))

    task = TaskManager(TaskRepository(harness["db"])).create(
        harness["session_id"], "do a lot of things"
    )
    profile = resolve_run_profile(AgentConfig(), thinking_level="low")
    result = harness["runtime"].run_task(task, profile)

    assert result.llm_calls_used <= profile.max_llm_calls
    assert result.status == TaskStatus.FAILED


def test_unparseable_plan_fails_cleanly_without_crashing(harness) -> None:
    provider = harness["provider"]
    provider.queue("this is not json")
    provider.queue("still not json")

    task = TaskManager(TaskRepository(harness["db"])).create(
        harness["session_id"], "an impossible task"
    )
    profile = resolve_run_profile(AgentConfig(), thinking_level="low")
    result = harness["runtime"].run_task(task, profile)

    assert result.status == TaskStatus.FAILED
    assert "planning failed" in result.summary
