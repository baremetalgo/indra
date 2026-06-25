"""Task lifecycle management.

Wraps :class:`TaskRepository` with the state-machine transition rules
from §8 of the design doc, so invalid transitions (e.g. DONE -> EXECUTING)
raise immediately instead of corrupting persisted state.
"""

from __future__ import annotations

from dataclasses import dataclass

from indra.core.state_machine import StateMachine
from indra.schemas.task import Task, TaskStatus
from indra.storage.repositories import TaskRepository

_TRANSITIONS: dict[tuple[TaskStatus, str], TaskStatus] = {
    (TaskStatus.CREATED, "plan"): TaskStatus.PLANNING,
    (TaskStatus.PLANNING, "execute"): TaskStatus.EXECUTING,
    (TaskStatus.EXECUTING, "evaluate"): TaskStatus.EVALUATING,
    (TaskStatus.EVALUATING, "continue"): TaskStatus.EXECUTING,
    (TaskStatus.EVALUATING, "complete"): TaskStatus.DONE,
    (TaskStatus.EVALUATING, "block"): TaskStatus.BLOCKED,
    (TaskStatus.BLOCKED, "replan"): TaskStatus.PLANNING,
    (TaskStatus.BLOCKED, "abandon"): TaskStatus.FAILED,
}


def new_task_state_machine(initial: TaskStatus = TaskStatus.CREATED) -> StateMachine:
    return StateMachine(initial_state=initial, transitions=_TRANSITIONS)


@dataclass
class TaskManager:
    repo: TaskRepository

    def create(self, session_id: str, description: str) -> Task:
        return self.repo.create(session_id, description)

    def transition(self, task: Task, event: str) -> Task:
        fsm = new_task_state_machine(task.status)
        new_status = fsm.fire(event)
        plan_id = task.plan_id if event != "plan" else task.plan_id
        self.repo.update_status(task.id, new_status, plan_id)
        task.status = new_status
        return task

    def attach_plan(self, task: Task, plan_id: str) -> Task:
        self.repo.update_status(task.id, task.status, plan_id)
        task.plan_id = plan_id
        return task
