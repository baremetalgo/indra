from __future__ import annotations

from indra.core.executor import Executor
from indra.observability.token_tracker import TokenTracker
from indra.prompts.loader import PromptManager
from indra.providers.base import CompletionRequest, CompletionResponse
from indra.schemas.plan import Subtask
from indra.storage.db import Database
from indra.storage.repositories import WorkspaceRepository
from indra.tools.base import ToolRegistry
from indra.tools.file_tools import register_file_tools
from indra.workspaces.workspace_manager import WorkspaceManager


class _CapturingProvider:
    """Records the rendered prompt text instead of calling a real model."""

    def __init__(self) -> None:
        self.last_prompt: str | None = None

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        self.last_prompt = request.prompt
        return CompletionResponse(
            text='{"tool_name": "write_file", "params": {"path": "a.txt", "content": "x"}}',
            prompt_tokens=1,
            completion_tokens=1,
        )

    def is_available(self) -> bool:
        return True


def _setup(tmp_path):
    db = Database(str(tmp_path / "indra.db"))
    db.migrate()
    wm = WorkspaceManager(WorkspaceRepository(db))
    ws = wm.create("demo", str(tmp_path / "proj"))
    registry = ToolRegistry()
    register_file_tools(registry, ws, wm)
    return registry


def test_planner_tool_hint_is_surfaced_in_the_executor_prompt(tmp_path) -> None:
    """Reproduces a real gap: the planner's tool_hint was computed but
    silently discarded -- the executor had to re-guess the tool from
    scratch on every subtask with no benefit from the planner's choice.
    """
    registry = _setup(tmp_path)
    provider = _CapturingProvider()
    executor = Executor(provider, PromptManager(), registry)
    subtask = Subtask(id="s1", description="create a file", tool_hint="write_file")
    tracker = TokenTracker(task_id="t1", max_calls=5)

    executor.decide_tool_call(subtask, context="", tracker=tracker)

    assert provider.last_prompt is not None
    assert "write_file" in provider.last_prompt


def test_unknown_tool_hint_does_not_leak_into_the_prompt_as_a_suggestion(tmp_path) -> None:
    """If the planner suggests a tool that doesn't actually exist in this
    workspace's registry, the executor must not pass that bogus name
    through as if it were a valid suggestion."""
    registry = _setup(tmp_path)
    provider = _CapturingProvider()
    executor = Executor(provider, PromptManager(), registry)
    subtask = Subtask(id="s1", description="do something", tool_hint="totally_made_up_tool")
    tracker = TokenTracker(task_id="t1", max_calls=5)

    executor.decide_tool_call(subtask, context="", tracker=tracker)

    assert provider.last_prompt is not None
    assert "totally_made_up_tool" not in provider.last_prompt
    assert "(none)" in provider.last_prompt


def test_no_tool_hint_renders_as_none(tmp_path) -> None:
    registry = _setup(tmp_path)
    provider = _CapturingProvider()
    executor = Executor(provider, PromptManager(), registry)
    subtask = Subtask(id="s1", description="do something", tool_hint=None)
    tracker = TokenTracker(task_id="t1", max_calls=5)

    executor.decide_tool_call(subtask, context="", tracker=tracker)

    assert provider.last_prompt is not None
    assert "(none)" in provider.last_prompt
