"""AgentRuntime: the single-agent loop.

Implements the loop from §6 of the design doc: plan once, then for each
subtask retrieve context -> pick a tool -> run it -> evaluate
deterministically -> update memory -> move to the next subtask, bounded
by ``max_steps`` and the per-task LLM call budget. On failure it
re-plans at most ``max_replan_attempts`` times before giving up.
"""

from __future__ import annotations

from dataclasses import dataclass

from indra.core.context_manager import ContextManager
from indra.core.executor import Executor, ToolSelectionError
from indra.core.memory_manager import MemoryManager
from indra.core.planner import Planner, PlanningError
from indra.core.run_profile import RunProfile
from indra.core.task_manager import TaskManager
from indra.observability.logging import get_logger
from indra.observability.token_tracker import BudgetExceededError, TokenTracker
from indra.schemas.memory import MemoryItem
from indra.schemas.plan import Plan
from indra.schemas.task import Task, TaskResult, TaskStatus
from indra.storage.repositories import PlanRepository, ToolCallRepository
from indra.util import new_id

_logger = get_logger("core.agent")


@dataclass
class AgentRuntime:
    task_manager: TaskManager
    planner: Planner
    executor: Executor
    memory: MemoryManager
    context: ContextManager
    plan_repo: PlanRepository
    tool_call_repo: ToolCallRepository

    def run_task(self, task: Task, profile: RunProfile, repo_map: str = "") -> TaskResult:
        tracker = TokenTracker(task_id=task.id, max_calls=profile.max_llm_calls)
        replans_used = 0
        steps_used = 0

        self.task_manager.transition(task, "plan")
        try:
            plan = self._plan(task, repo_map, tracker, profile)
        except PlanningError as exc:
            self.task_manager.transition(task, "execute")
            self.task_manager.transition(task, "evaluate")
            self.task_manager.transition(task, "block")
            self.task_manager.transition(task, "abandon")
            return self._finish(task, tracker, success=False, reason=f"planning failed: {exc}")
        self.task_manager.attach_plan(task, plan.id)
        self.task_manager.transition(task, "execute")

        while True:
            pending = [s for s in plan.subtasks if not s.done]
            if not pending:
                self.task_manager.transition(task, "evaluate")
                self.task_manager.transition(task, "complete")
                return self._finish(task, tracker, success=True)

            for subtask in pending:
                steps_used += 1
                if steps_used > profile.max_steps:
                    self.task_manager.transition(task, "evaluate")
                    self.task_manager.transition(task, "block")
                    self.task_manager.transition(task, "abandon")
                    return self._finish(
                        task, tracker, success=False,
                        reason=f"max_steps exceeded ({profile.max_steps})",
                    )

                ctx = self.context.build_execution_context(subtask.description)
                call = None
                result = None
                try:
                    call = self.executor.decide_tool_call(
                        subtask, ctx, tracker, profile.temperature
                    )
                    result = self.executor.execute_subtask(call)
                except (ToolSelectionError, BudgetExceededError) as exc:
                    _logger.warning(
                        "subtask_failed",
                        extra={"indra_extra": {"subtask": subtask.id, "error": str(exc)}},
                    )

                success = result is not None and result.success
                self.tool_call_repo.record(
                    task_id=task.id,
                    tool_name=call.tool_name if call is not None else "none",
                    params=call.params if call is not None else {},
                    result_json=str(result.output) if result else None,
                    success=success,
                    duration_ms=result.duration_ms if result else 0,
                    subtask_id=subtask.id,
                )

                if success:
                    self.plan_repo.mark_subtask_done(subtask.id)
                    plan = _mark_done(plan, subtask.id)
                    self.memory.remember_working(
                        MemoryItem(
                            id=new_id(),
                            scope="working",
                            kind="tool_usage",
                            content=f"completed: {subtask.description}",
                            source_task_id=task.id,
                        )
                    )
                else:
                    self.task_manager.transition(task, "evaluate")
                    if replans_used >= profile.max_replan_attempts:
                        self.task_manager.transition(task, "block")
                        self.task_manager.transition(task, "abandon")
                        return self._finish(
                            task, tracker, success=False,
                            reason="subtask failed, replan budget exhausted",
                        )
                    self.task_manager.transition(task, "block")
                    self.task_manager.transition(task, "replan")
                    replans_used += 1
                    try:
                        plan = self._plan(task, repo_map, tracker, profile)
                    except PlanningError as exc:
                        self.task_manager.transition(task, "execute")
                        self.task_manager.transition(task, "evaluate")
                        self.task_manager.transition(task, "block")
                        self.task_manager.transition(task, "abandon")
                        return self._finish(
                            task, tracker, success=False, reason=f"replanning failed: {exc}"
                        )
                    self.task_manager.attach_plan(task, plan.id)
                    self.task_manager.transition(task, "execute")
                    break  # restart the pending-subtasks loop with the new plan

    def _plan(self, task: Task, repo_map: str, tracker, profile: RunProfile) -> Plan:
        plan = self.planner.create_plan(task, repo_map, tracker, profile.temperature)
        self.plan_repo.save(plan)
        return plan

    def _finish(
        self, task: Task, tracker: TokenTracker, success: bool, reason: str = "ok"
    ) -> TaskResult:
        if success:
            self.memory.promote_to_long_term(
                content=f"Task completed: {task.description}",
                kind="fact",
                source_task_id=task.id,
            )
        status = TaskStatus.DONE if success else TaskStatus.FAILED
        self.memory.clear_working()
        return TaskResult(
            task_id=task.id,
            status=status,
            summary=reason,
            llm_calls_used=tracker.calls_used,
        )


def _mark_done(plan: Plan, subtask_id: str) -> Plan:
    new_subtasks = tuple(
        s if s.id != subtask_id else type(s)(**{**s.__dict__, "done": True})
        for s in plan.subtasks
    )
    return type(plan)(**{**plan.__dict__, "subtasks": new_subtasks})
