from __future__ import annotations

import json
from dataclasses import dataclass, field

from indra.util import new_id


@dataclass(frozen=True)
class Subtask:
    id: str
    description: str
    depends_on: tuple[str, ...] = ()
    tool_hint: str | None = None
    done: bool = False


@dataclass(frozen=True)
class Plan:
    id: str
    task_id: str
    goal: str
    constraints: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    subtasks: tuple[Subtask, ...] = ()
    success_criteria: tuple[str, ...] = ()
    version: int = 1

    @staticmethod
    def from_model_json(raw_json: str, task_id: str) -> "Plan":
        """Parse a model's JSON output into a validated Plan.

        Raises ``ValueError`` on malformed input so the caller can decide
        whether to retry or re-plan, per the bounded-retry policy.
        """
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Plan output is not valid JSON: {exc}") from exc

        required = {"goal", "subtasks"}
        missing = required - set(data)
        if missing:
            raise ValueError(f"Plan JSON missing required fields: {missing}")

        subtasks = tuple(
            Subtask(
                id=new_id(),
                description=st["description"],
                depends_on=tuple(st.get("depends_on", [])),
                tool_hint=st.get("tool_hint"),
            )
            for st in data["subtasks"]
        )
        if not subtasks:
            raise ValueError("Plan JSON must contain at least one subtask")

        return Plan(
            id=new_id(),
            task_id=task_id,
            goal=data["goal"],
            constraints=tuple(data.get("constraints", [])),
            assumptions=tuple(data.get("assumptions", [])),
            subtasks=subtasks,
            success_criteria=tuple(data.get("success_criteria", [])),
        )
