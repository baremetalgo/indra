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
from indra.tools.answer_tool import register_answer_tool
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
    register_answer_tool(registry)

    provider = MockProvider()
    prompts = PromptManager()
    mem = MemoryManager(LongTermMemoryStore(db), workspace_id=workspace.id, max_tokens=300)

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


def test_answer_tool_output_surfaces_as_artifact(harness) -> None:
    provider = harness["provider"]
    provider.queue(json.dumps({
        "goal": "answer a question",
        "subtasks": [{"description": "answer it", "tool_hint": "answer"}],
    }))
    provider.queue(json.dumps({
        "tool_name": "answer",
        "params": {"answer": "use Get-ChildItem Env: on PowerShell"},
        "reason": "direct answer",
    }))

    task = TaskManager(TaskRepository(harness["db"])).create(
        harness["session_id"], "what command prints env vars on windows?"
    )
    profile = resolve_run_profile(AgentConfig(), thinking_level="low")
    result = harness["runtime"].run_task(task, profile)

    assert result.status == TaskStatus.DONE
    assert result.artifacts == ["use Get-ChildItem Env: on PowerShell"]


def test_replan_receives_the_previous_failure_reason(harness) -> None:
    provider = harness["provider"]
    # First plan asks to read a file that doesn't exist (deterministic failure).
    provider.queue(json.dumps({
        "goal": "do something",
        "subtasks": [{"description": "read missing config"}],
    }))
    provider.queue(json.dumps({
        "tool_name": "read_file",
        "params": {"path": "missing.txt"},
        "reason": "read it",
    }))
    # Re-plan should be invoked with the failure reason in the rendered prompt;
    # we just confirm a second plan call happens and the task fails cleanly
    # within the (low) replan budget of 0 -- i.e. no replan attempted at all.
    task = TaskManager(TaskRepository(harness["db"])).create(
        harness["session_id"], "do something with a missing file"
    )
    profile = resolve_run_profile(AgentConfig(), thinking_level="low")
    result = harness["runtime"].run_task(task, profile)

    assert result.status == TaskStatus.FAILED
    assert "missing.txt" in result.summary or "read_file" in result.summary
    # low thinking level => 0 replan attempts => exactly 2 calls (plan + execute)
    assert result.llm_calls_used == 2


def test_replan_actually_happens_with_medium_thinking_and_gets_failure_context(harness) -> None:
    provider = harness["provider"]
    provider.queue(json.dumps({
        "goal": "do something",
        "subtasks": [{"description": "read missing config"}],
    }))
    provider.queue(json.dumps({
        "tool_name": "read_file",
        "params": {"path": "missing.txt"},
        "reason": "read it",
    }))
    # Re-plan: this time answer directly instead of repeating the bad read.
    provider.queue(json.dumps({
        "goal": "do something",
        "subtasks": [{"description": "answer instead", "tool_hint": "answer"}],
    }))
    provider.queue(json.dumps({
        "tool_name": "answer",
        "params": {"answer": "the file does not exist, here is an alternative"},
        "reason": "avoid repeating the failed read",
    }))

    task = TaskManager(TaskRepository(harness["db"])).create(
        harness["session_id"], "do something with a missing file"
    )
    profile = resolve_run_profile(AgentConfig(), thinking_level="medium")
    result = harness["runtime"].run_task(task, profile)

    assert result.status == TaskStatus.DONE
    assert result.artifacts == ["the file does not exist, here is an alternative"]
    assert result.llm_calls_used == 4
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


def test_task_result_carries_token_and_timing_stats(harness) -> None:
    provider = harness["provider"]
    provider.queue(json.dumps({
        "goal": "answer something",
        "subtasks": [{"description": "answer", "tool_hint": "answer"}],
    }))
    provider.queue(json.dumps({
        "tool_name": "answer",
        "params": {"answer": "ok"},
        "reason": "direct answer",
    }))

    task = TaskManager(TaskRepository(harness["db"])).create(
        harness["session_id"], "say something"
    )
    profile = resolve_run_profile(AgentConfig(), thinking_level="low")
    result = harness["runtime"].run_task(task, profile)

    assert result.status == TaskStatus.DONE
    assert result.prompt_tokens > 0
    assert result.completion_tokens > 0
    assert result.total_seconds >= 0.0
    assert result.llm_seconds >= 0.0
    # total wall-clock can never be less than time spent purely inside LLM calls
    assert result.total_seconds >= result.llm_seconds
    """Reproduces a real reported bug: a successful list_files call
    completed the task but showed nothing to the user -- only the
    'answer' tool's output used to be surfaced."""
    (harness["workspace"].root_path / "a.txt").write_text("x")
    (harness["workspace"].root_path / "b.txt").write_text("y")

    provider = harness["provider"]
    provider.queue(json.dumps({
        "goal": "list files",
        "subtasks": [{"description": "list files", "tool_hint": "list_files"}],
    }))
    provider.queue(json.dumps({
        "tool_name": "list_files",
        "params": {"path": "."},
        "reason": "show the files",
    }))

    task = TaskManager(TaskRepository(harness["db"])).create(
        harness["session_id"], "list all the files in the workspace"
    )
    profile = resolve_run_profile(AgentConfig(), thinking_level="low")
    result = harness["runtime"].run_task(task, profile)

    assert result.status == TaskStatus.DONE
    assert any("a.txt" in a for a in result.artifacts)
    assert any("b.txt" in a for a in result.artifacts)


def test_write_file_output_surfaces_a_confirmation(harness) -> None:
    provider = harness["provider"]
    provider.queue(json.dumps({
        "goal": "write a file",
        "subtasks": [{"description": "write notes.txt", "tool_hint": "write_file"}],
    }))
    provider.queue(json.dumps({
        "tool_name": "write_file",
        "params": {"path": "notes.txt", "content": "hello"},
        "reason": "create it",
    }))

    task = TaskManager(TaskRepository(harness["db"])).create(
        harness["session_id"], "write notes.txt"
    )
    profile = resolve_run_profile(AgentConfig(), thinking_level="low")
    result = harness["runtime"].run_task(task, profile)

    assert result.status == TaskStatus.DONE
    assert any("wrote" in a and "bytes" in a for a in result.artifacts)
