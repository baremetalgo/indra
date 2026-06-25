"""Assembles the minimal context for each LLM call.

This is the choke point that enforces "never send entire repos/
conversations/files" (§7): callers ask for a context bundle and get
back short strings, never raw dumps.
"""

from __future__ import annotations

from dataclasses import dataclass

from indra.core.memory_manager import MemoryManager


@dataclass
class ContextManager:
    memory: MemoryManager

    def build_planning_context(self, repo_map: str = "") -> str:
        items = self.memory.retrieve_context()
        memory_text = "; ".join(i.content for i in items) if items else "(none)"
        repo_text = repo_map or "(no repository indexed yet)"
        return f"memory: {memory_text} | repo_map: {repo_text}"

    def build_execution_context(self, subtask_description: str) -> str:
        items = self.memory.retrieve_context()
        memory_text = "; ".join(i.content for i in items) if items else "(none)"
        return f"subtask: {subtask_description} | memory: {memory_text}"
