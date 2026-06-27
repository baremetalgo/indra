"""Dependency wiring for the FastAPI app.

Builds the process-wide :class:`AppState` (config, DB, workspace
manager) once, and per-call helpers to assemble an
:class:`~indra.core.agent.AgentRuntime` bound to a specific workspace —
this is the only place that wires providers/tools/core modules together
for the API layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from indra.config.loader import load_config
from indra.config.schema import IndraConfig, ShellConfig, WebSearchConfig
from indra.core.agent import AgentRuntime
from indra.core.context_manager import ContextManager
from indra.core.executor import Executor
from indra.core.memory_manager import MemoryManager
from indra.core.planner import Planner
from indra.core.task_manager import TaskManager
from indra.memory.long_term_memory import LongTermMemoryStore
from indra.prompts.loader import PromptManager
from indra.providers.base import ModelProvider
from indra.providers.mock_provider import MockProvider
from indra.storage.db import Database
from indra.storage.repositories import (
    PlanRepository,
    SearchCacheRepository,
    SessionRepository,
    TaskRepository,
    ToolCallRepository,
    WorkspaceRepository,
)
from indra.tools.answer_tool import register_answer_tool
from indra.tools.base import ToolRegistry
from indra.tools.file_tools import register_file_tools
from indra.tools.git_tools import register_git_tools
from indra.tools.shell_tools import register_shell_tools
from indra.tools.web_search_tools import register_web_search_tool
from indra.workspaces.workspace_manager import Workspace, WorkspaceManager


@dataclass
class AppState:
    config: IndraConfig
    db: Database
    workspaces: WorkspaceManager
    prompts: PromptManager


@lru_cache
def get_app_state(config_path: str = "indra.config.yaml") -> AppState:
    config = load_config(config_path)
    db = Database(config.db_path)
    db.migrate()
    workspaces = WorkspaceManager(WorkspaceRepository(db))
    return AppState(config=config, db=db, workspaces=workspaces, prompts=PromptManager())


@lru_cache
def _build_provider_singleton(config: IndraConfig) -> ModelProvider:
    """Build the model provider exactly once per process per config.

    This is the difference between `indra serve` loading a GGUF model
    once and reusing it for every task, versus reloading it from disk
    on every single request. IndraConfig is a frozen dataclass of
    hashable fields, so it's safe to use directly as an lru_cache key.
    """
    return build_provider(config)


def build_provider(config: IndraConfig) -> ModelProvider:
    if config.model.backend == "mock":
        return MockProvider()
    if config.model.backend == "llama_cpp":
        from indra.providers.llama_cpp_provider import LlamaCppProvider

        return LlamaCppProvider(
            model_path=config.model.model_path,
            context_size=config.model.context_size,
            gpu_layers=config.model.gpu_layers,
            flash_attn=config.model.flash_attn,
        )
    raise ValueError(f"Unsupported backend for this build: {config.model.backend}")


def build_tool_registry(
    workspace: Workspace,
    workspaces: WorkspaceManager,
    shell_config: ShellConfig,
    web_search_config: WebSearchConfig,
    db: Database,
) -> ToolRegistry:
    registry = ToolRegistry()
    register_file_tools(registry, workspace, workspaces)
    register_answer_tool(registry)
    register_git_tools(registry, workspace, workspaces, timeout=shell_config.timeout_seconds)
    register_shell_tools(registry, workspace, workspaces, shell_config)
    register_web_search_tool(registry, web_search_config, SearchCacheRepository(db))
    return registry


def build_agent_runtime(state: AppState, workspace: Workspace) -> AgentRuntime:
    provider = _build_provider_singleton(state.config)
    registry = build_tool_registry(
        workspace, state.workspaces, state.config.shell, state.config.web_search, state.db
    )
    mem = MemoryManager(
        LongTermMemoryStore(state.db),
        workspace_id=workspace.id,
        max_tokens=state.config.memory.max_tokens,
    )
    cap = state.config.model.max_tokens_per_call
    return AgentRuntime(
        task_manager=TaskManager(TaskRepository(state.db)),
        planner=Planner(provider, state.prompts, max_tokens_cap=cap),
        executor=Executor(provider, state.prompts, registry, max_tokens_cap=cap),
        memory=mem,
        context=ContextManager(mem),
        plan_repo=PlanRepository(state.db),
        tool_call_repo=ToolCallRepository(state.db),
    )
