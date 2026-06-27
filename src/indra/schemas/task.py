from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class TaskStatus(str, Enum):
    CREATED = "created"
    PLANNING = "planning"
    EXECUTING = "executing"
    EVALUATING = "evaluating"
    BLOCKED = "blocked"
    DONE = "done"
    FAILED = "failed"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Task:
    id: str
    session_id: str
    description: str
    status: TaskStatus = TaskStatus.CREATED
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    plan_id: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class TaskResult:
    task_id: str
    status: TaskStatus
    summary: str
    artifacts: list[str] = field(default_factory=list)
    llm_calls_used: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    llm_seconds: float = 0.0
    total_seconds: float = 0.0
