"""Tracks LLM call counts and token usage per task, enforcing budgets.

This is the mechanism that makes the "every LLM call is expensive"
principle real rather than aspirational: callers must ask
:class:`TokenTracker` for permission before each call, and it raises
once the configured budget for that task is exhausted.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from indra.observability.logging import get_logger

_logger = get_logger("observability.token_tracker")


class BudgetExceededError(Exception):
    """Raised when a task tries to exceed its LLM call budget."""


@dataclass
class CallRecord:
    purpose: str
    prompt_tokens: int
    completion_tokens: int


@dataclass
class TokenTracker:
    """Per-task call budget enforcement and usage accounting."""

    task_id: str
    max_calls: int
    _records: list[CallRecord] = field(default_factory=list)

    @property
    def calls_used(self) -> int:
        return len(self._records)

    @property
    def calls_remaining(self) -> int:
        return max(0, self.max_calls - self.calls_used)

    def check_budget(self) -> None:
        """Raise :class:`BudgetExceededError` if no calls remain."""
        if self.calls_used >= self.max_calls:
            raise BudgetExceededError(
                f"Task {self.task_id} exceeded LLM call budget "
                f"({self.max_calls} calls)"
            )

    def record(self, purpose: str, prompt_tokens: int, completion_tokens: int) -> None:
        self.check_budget()
        self._records.append(CallRecord(purpose, prompt_tokens, completion_tokens))
        _logger.info(
            "llm_call_recorded",
            extra={
                "indra_extra": {
                    "task_id": self.task_id,
                    "purpose": purpose,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "calls_used": self.calls_used,
                    "calls_remaining": self.calls_remaining,
                }
            },
        )

    def total_tokens(self) -> int:
        return sum(r.prompt_tokens + r.completion_tokens for r in self._records)
