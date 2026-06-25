from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class MemoryItem:
    id: str
    scope: str  # "working" | "session" | "long_term"
    kind: str   # "fact" | "preference" | "decision" | "tool_usage" | "summary"
    content: str
    relevance: float = 0.5
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source_task_id: str | None = None
