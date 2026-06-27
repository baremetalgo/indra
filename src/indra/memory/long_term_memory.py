"""Long-term memory: SQLite-backed store of facts/preferences/decisions.

This is the only memory tier that survives across sessions. Working and
session memory (in-process, cleared on completion) live in
``core/memory_manager.py``; this module is purely the persistence layer
for items that have been deemed worth keeping.

Every read and write is scoped by ``workspace_id``. An earlier version
of this store had no workspace scoping at all, which meant memory from
every project leaked into every other project's context -- a real bug
reported by an early user. Treat ``workspace_id`` as mandatory; there
is no "global" query path left, deliberately.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from indra.memory.compression import score_relevance
from indra.schemas.memory import MemoryItem
from indra.storage.db import Database


class LongTermMemoryStore:
    def __init__(self, db: Database) -> None:
        self._db = db

    def add(
        self,
        workspace_id: str,
        scope: str,
        kind: str,
        content: str,
        session_id: str | None = None,
        source_task_id: str | None = None,
    ) -> MemoryItem:
        item = MemoryItem(
            id=uuid.uuid4().hex,
            scope=scope,
            kind=kind,
            content=content,
            source_task_id=source_task_id,
        )
        item = MemoryItem(**{**item.__dict__, "relevance": score_relevance(item)})
        with self._db.connect() as conn:
            conn.execute(
                "INSERT INTO memory_items (id, scope, kind, content, relevance, "
                "session_id, source_task_id, created_at, workspace_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    item.id,
                    item.scope,
                    item.kind,
                    item.content,
                    item.relevance,
                    session_id,
                    source_task_id,
                    item.created_at.isoformat(),
                    workspace_id,
                ),
            )
        return item

    def query(self, workspace_id: str, scope: str | None = None, limit: int = 50) -> list[MemoryItem]:
        sql = "SELECT * FROM memory_items WHERE workspace_id = ?"
        args: tuple = (workspace_id,)
        if scope is not None:
            sql += " AND scope = ?"
            args = args + (scope,)
        sql += " ORDER BY relevance DESC LIMIT ?"
        args = args + (limit,)
        with self._db.connect() as conn:
            rows = conn.execute(sql, args).fetchall()
        return [
            MemoryItem(
                id=row["id"],
                scope=row["scope"],
                kind=row["kind"],
                content=row["content"],
                relevance=row["relevance"],
                created_at=datetime.fromisoformat(row["created_at"]),
                source_task_id=row["source_task_id"],
            )
            for row in rows
        ]
