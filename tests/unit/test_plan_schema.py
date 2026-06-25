from __future__ import annotations

import json

import pytest

from indra.schemas.plan import Plan


def test_parses_valid_plan_json() -> None:
    raw = json.dumps(
        {
            "goal": "do the thing",
            "subtasks": [{"description": "step one", "tool_hint": "write_file"}],
            "success_criteria": ["file exists"],
        }
    )
    plan = Plan.from_model_json(raw, task_id="t1")
    assert plan.goal == "do the thing"
    assert len(plan.subtasks) == 1
    assert plan.subtasks[0].tool_hint == "write_file"


def test_rejects_invalid_json() -> None:
    with pytest.raises(ValueError):
        Plan.from_model_json("not json", task_id="t1")


def test_rejects_missing_required_fields() -> None:
    with pytest.raises(ValueError):
        Plan.from_model_json(json.dumps({"goal": "x"}), task_id="t1")  # no subtasks key


def test_rejects_empty_subtasks_list() -> None:
    with pytest.raises(ValueError):
        Plan.from_model_json(json.dumps({"goal": "x", "subtasks": []}), task_id="t1")
