from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolCall:
    tool_name: str
    params: dict[str, Any]
    reason: str = ""


@dataclass(frozen=True)
class ToolCallEvaluation:
    success: bool
    matches_intent: bool
    notes: str
    needs_replan: bool = False
