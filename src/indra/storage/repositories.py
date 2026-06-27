"""Data-access objects (DAOs) over the SQLite schema.

Each repository owns exactly one table's read/write logic so callers in
``core/`` never write raw SQL — this is the seam that keeps storage
swappable and unit-testable with an in-memory SQLite file.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from indra.schemas.plan import Plan, Subtask
from indra.schemas.task import Task, TaskStatus
from indra.storage.db import Database
from indra.util import new_id


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorkspaceRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def create(self, name: str, root_path: str, is_default: bool = False) -> str:
        workspace_id = new_id()
        with self._db.connect() as conn:
            conn.execute(
                "INSERT INTO workspaces (id, name, root_path, created_at, is_default) "
                "VALUES (?, ?, ?, ?, ?)",
                (workspace_id, name, root_path, _utcnow(), int(is_default)),
            )
        return workspace_id

    def get_by_name(self, name: str) -> sqlite3.Row | None:
        with self._db.connect() as conn:
            return conn.execute(
                "SELECT * FROM workspaces WHERE name = ?", (name,)
            ).fetchone()

    def list_all(self) -> list[sqlite3.Row]:
        with self._db.connect() as conn:
            return conn.execute(
                "SELECT * FROM workspaces ORDER BY created_at"
            ).fetchall()

    def delete(self, name: str) -> None:
        with self._db.connect() as conn:
            conn.execute("DELETE FROM workspaces WHERE name = ?", (name,))


class SessionRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def create(self, workspace_id: str) -> str:
        session_id = new_id()
        now = _utcnow()
        with self._db.connect() as conn:
            conn.execute(
                "INSERT INTO sessions (id, workspace_id, created_at, updated_at, status) "
                "VALUES (?, ?, ?, ?, 'active')",
                (session_id, workspace_id, now, now),
            )
        return session_id


class TaskRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def create(self, session_id: str, description: str) -> Task:
        task = Task(id=new_id(), session_id=session_id, description=description)
        with self._db.connect() as conn:
            conn.execute(
                "INSERT INTO tasks (id, session_id, description, status, plan_id, "
                "created_at, updated_at, metadata_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    task.id,
                    task.session_id,
                    task.description,
                    task.status.value,
                    task.plan_id,
                    task.created_at.isoformat(),
                    task.updated_at.isoformat(),
                    json.dumps(task.metadata),
                ),
            )
        return task

    def update_status(self, task_id: str, status: TaskStatus, plan_id: str | None = None) -> None:
        with self._db.connect() as conn:
            if plan_id is not None:
                conn.execute(
                    "UPDATE tasks SET status = ?, plan_id = ?, updated_at = ? WHERE id = ?",
                    (status.value, plan_id, _utcnow(), task_id),
                )
            else:
                conn.execute(
                    "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
                    (status.value, _utcnow(), task_id),
                )

    def get(self, task_id: str) -> sqlite3.Row | None:
        with self._db.connect() as conn:
            return conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()


class PlanRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def save(self, plan: Plan) -> None:
        with self._db.connect() as conn:
            conn.execute(
                "INSERT INTO plans (id, task_id, version, goal, constraints_json, "
                "assumptions_json, success_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    plan.id,
                    plan.task_id,
                    plan.version,
                    plan.goal,
                    json.dumps(list(plan.constraints)),
                    json.dumps(list(plan.assumptions)),
                    json.dumps(list(plan.success_criteria)),
                    _utcnow(),
                ),
            )
            for seq, subtask in enumerate(plan.subtasks):
                conn.execute(
                    "INSERT INTO subtasks (id, plan_id, description, depends_on, "
                    "tool_hint, done, seq) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        subtask.id,
                        plan.id,
                        subtask.description,
                        json.dumps(list(subtask.depends_on)),
                        subtask.tool_hint,
                        int(subtask.done),
                        seq,
                    ),
                )

    def mark_subtask_done(self, subtask_id: str) -> None:
        with self._db.connect() as conn:
            conn.execute("UPDATE subtasks SET done = 1 WHERE id = ?", (subtask_id,))


class ToolCallRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def record(
        self,
        task_id: str,
        tool_name: str,
        params: dict[str, Any],
        result_json: str | None,
        success: bool,
        duration_ms: int,
        subtask_id: str | None = None,
    ) -> None:
        with self._db.connect() as conn:
            conn.execute(
                "INSERT INTO tool_calls (id, task_id, subtask_id, tool_name, "
                "params_json, result_json, success, duration_ms, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    new_id(),
                    task_id,
                    subtask_id,
                    tool_name,
                    json.dumps(params),
                    result_json,
                    int(success),
                    duration_ms,
                    _utcnow(),
                ),
            )


class SearchCacheRepository:
    """TTL cache for the web_search tool, backed by the search_cache table.

    Keeps repeated/near-duplicate queries within a task (or across
    tasks, within the TTL) from costing another network round-trip.
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    def get(self, query_hash: str) -> list[dict[str, Any]] | None:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT results_json, expires_at FROM search_cache WHERE query_hash = ?",
                (query_hash,),
            ).fetchone()
        if row is None:
            return None
        if row["expires_at"] < _utcnow():
            return None  # expired; caller will overwrite via set()
        return json.loads(row["results_json"])

    def set(
        self, query_hash: str, query_text: str, results: list[dict[str, Any]],
        provider: str, ttl_seconds: int,
    ) -> None:
        expires_at = (
            datetime.fromisoformat(_utcnow()) + timedelta(seconds=ttl_seconds)
        ).isoformat()
        with self._db.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO search_cache "
                "(query_hash, query_text, provider, results_json, created_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (query_hash, query_text, provider, json.dumps(results), _utcnow(), expires_at),
            )


class TokenUsageRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def record(
        self, task_id: str, purpose: str, prompt_tokens: int, completion_tokens: int
    ) -> None:
        with self._db.connect() as conn:
            conn.execute(
                "INSERT INTO token_usage (id, task_id, prompt_tokens, "
                "completion_tokens, purpose, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (new_id(), task_id, prompt_tokens, completion_tokens, purpose, _utcnow()),
            )
