"""Facade over working/session/long-term memory.

Hard rule (per design §11): this manager never returns more than
``max_tokens`` worth of content to a caller. Working memory is just a
plain in-process list scoped to the active task; it is never persisted
beyond the task unless explicitly promoted to long-term memory.

Every instance is bound to one ``workspace_id`` and never reads or
writes outside it -- see ``memory/long_term_memory.py`` for why that
matters (it didn't used to be true, and memory leaked across projects
as a result).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from indra.memory.compression import deduplicate, estimate_tokens, rank_and_truncate
from indra.memory.long_term_memory import LongTermMemoryStore
from indra.schemas.memory import MemoryItem


@dataclass
class MemoryManager:
    long_term: LongTermMemoryStore
    workspace_id: str
    max_tokens: int = 300
    _working: list[MemoryItem] = field(default_factory=list)

    def remember_working(self, item: MemoryItem) -> None:
        """Add a fact to the active task's working memory (in-process only)."""
        self._working.append(item)

    def clear_working(self) -> None:
        self._working.clear()

    def promote_to_long_term(
        self, content: str, kind: str, source_task_id: str | None = None
    ) -> MemoryItem:
        """Persist a working-memory fact (or summary) to long-term storage."""
        return self.long_term.add(
            workspace_id=self.workspace_id,
            scope="long_term",
            kind=kind,
            content=content,
            source_task_id=source_task_id,
        )

    def retrieve_context(self, scope: str = "long_term") -> list[MemoryItem]:
        """Return a token-budgeted, deduplicated, relevance-ranked slice,
        scoped to this manager's workspace only.

        Working-memory items are always included first (they're free —
        already in process memory) before any budget is spent on
        long-term retrieval.
        """
        working_cost = sum(estimate_tokens(i.content) for i in self._working)
        remaining_budget = max(0, self.max_tokens - working_cost)

        long_term_items = deduplicate(
            self.long_term.query(workspace_id=self.workspace_id, scope=scope)
        )
        budgeted = rank_and_truncate(long_term_items, remaining_budget)
        return list(self._working) + budgeted
