"""Planner: one bounded LLM call -> a structured :class:`Plan`.

Re-planning (after a failed/blocked task) is just calling
:meth:`Planner.create_plan` again with updated context — the same
single call shape, not a separate code path.
"""

from __future__ import annotations

from dataclasses import dataclass

from indra.observability.logging import get_logger
from indra.observability.token_tracker import TokenTracker
from indra.prompts.loader import PromptManager
from indra.providers.base import CompletionRequest, ModelProvider
from indra.schemas.plan import Plan
from indra.schemas.task import Task

_logger = get_logger("core.planner")

_PLAN_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "goal": {"type": "string"},
        "constraints": {"type": "array", "items": {"type": "string"}},
        "assumptions": {"type": "array", "items": {"type": "string"}},
        "subtasks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "tool_hint": {"type": ["string", "null"]},
                },
                "required": ["description"],
            },
        },
        "success_criteria": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["goal", "subtasks"],
}


class PlanningError(Exception):
    """Raised when the model fails to produce a usable plan after retries."""


@dataclass
class Planner:
    provider: ModelProvider
    prompts: PromptManager
    max_parse_retries: int = 1

    def create_plan(
        self,
        task: Task,
        repo_map: str,
        tracker: TokenTracker,
        temperature: float = 0.0,
    ) -> Plan:
        rendered = self.prompts.render(
            "planner", goal=task.description, repo_map=repo_map, constraints="none"
        )

        last_error: Exception | None = None
        for attempt in range(self.max_parse_retries + 1):
            tracker.check_budget()
            response = self.provider.complete(
                CompletionRequest(
                    prompt=rendered.text,
                    max_tokens=rendered.max_output_tokens,
                    temperature=temperature,
                    json_schema=_PLAN_JSON_SCHEMA,
                )
            )
            tracker.record(
                "plan", response.prompt_tokens, response.completion_tokens
            )
            try:
                return Plan.from_model_json(response.text, task_id=task.id)
            except ValueError as exc:
                last_error = exc
                _logger.warning(
                    "plan_parse_failed",
                    extra={"indra_extra": {"attempt": attempt, "error": str(exc)}},
                )

        raise PlanningError(f"Planner failed to produce a valid plan: {last_error}")
