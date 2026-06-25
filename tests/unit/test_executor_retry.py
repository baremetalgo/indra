from __future__ import annotations

from indra.prompts.loader import PromptManager
from indra.providers.mock_provider import MockProvider
from indra.schemas.tool_call import ToolCall
from indra.storage.db import Database
from indra.storage.repositories import WorkspaceRepository
from indra.tools.base import ToolRegistry
from indra.tools.file_tools import register_file_tools
from indra.workspaces.workspace_manager import WorkspaceManager
from indra.core.executor import Executor


def _executor(tmp_path) -> tuple[Executor, object]:
    db = Database(str(tmp_path / "indra.db"))
    db.migrate()
    wm = WorkspaceManager(WorkspaceRepository(db))
    ws = wm.create("demo", str(tmp_path / "proj"))
    registry = ToolRegistry()
    register_file_tools(registry, ws, wm)
    return Executor(MockProvider(), PromptManager(), registry, max_tool_retries=3), ws


def test_non_retryable_failure_is_not_retried(tmp_path) -> None:
    executor, _ = _executor(tmp_path)
    call = ToolCall(tool_name="read_file", params={"path": "nope.txt"})
    result = executor.execute_subtask(call)
    assert not result.success
    assert result.retryable is False


def test_invalid_input_fails_fast_without_running_the_tool(tmp_path) -> None:
    executor, _ = _executor(tmp_path)
    call = ToolCall(tool_name="write_file", params={"path": "a.txt"})  # missing content
    result = executor.execute_subtask(call)
    assert not result.success
    assert result.retryable is False
