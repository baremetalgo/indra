"""Executor: turns one :class:`Subtask` into a tool call and runs it.

Tool *selection* costs one bounded LLM call (via the ``executor``
prompt). Tool *execution* and *evaluation* are fully deterministic — no
LLM involved — matching the "tool-first, evaluate without re-asking the
model" rule from §6/§11 of the design doc.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from indra.observability.logging import get_logger
from indra.observability.token_tracker import TokenTracker
from indra.prompts.loader import PromptManager
from indra.providers.base import CompletionRequest, ModelProvider
from indra.schemas.plan import Subtask
from indra.schemas.tool_call import ToolCall, ToolCallEvaluation
from indra.tools.base import ToolRegistry, ToolResult, ToolValidationError

_logger = get_logger("core.executor")

_TOOL_CALL_SCHEMA = {
    "type": "object",
    "properties": {
        "tool_name": {"type": "string"},
        "params": {"type": "object"},
        "reason": {"type": "string"},
    },
    "required": ["tool_name", "params"],
}


class ToolSelectionError(Exception):
    """Raised when the model picks an unknown tool or invalid JSON."""


@dataclass
class Executor:
    provider: ModelProvider
    prompts: PromptManager
    tools: ToolRegistry
    max_tool_retries: int = 2
    max_tokens_cap: int | None = None

    def decide_tool_call(
        self, subtask: Subtask, context: str, tracker: TokenTracker, temperature: float = 0.0
    ) -> ToolCall:
        available = "; ".join(
            f"{s.name} ({s.description})" for s in self.tools.list_schemas()
        )
        rendered = self.prompts.render(
            "executor",
            subtask=subtask.description,
            available_tools=available,
            context=context,
        )
        max_tokens = rendered.max_output_tokens
        if self.max_tokens_cap is not None:
            max_tokens = min(max_tokens, self.max_tokens_cap)
        tracker.check_budget()
        response = self.provider.complete(
            CompletionRequest(
                prompt=rendered.text,
                max_tokens=max_tokens,
                temperature=temperature,
                json_schema=_TOOL_CALL_SCHEMA,
            )
        )
        tracker.record("execute", response.prompt_tokens, response.completion_tokens)

        try:
            data = json.loads(response.text)
        except json.JSONDecodeError as exc:
            raise ToolSelectionError(f"Executor output is not valid JSON: {exc}") from exc

        tool_name = data.get("tool_name")
        if not self.tools.has(tool_name):
            raise ToolSelectionError(f"Model selected unknown tool: {tool_name!r}")

        return ToolCall(
            tool_name=tool_name,
            params=data.get("params", {}),
            reason=data.get("reason", ""),
        )

    def execute_subtask(self, call: ToolCall) -> ToolResult:
        attempts = 0
        last_result: ToolResult | None = None
        while attempts <= self.max_tool_retries:
            try:
                self.tools.validate_input(call.tool_name, call.params)
            except ToolValidationError as exc:
                return ToolResult(success=False, error=str(exc), retryable=False)

            tool = self.tools.get(call.tool_name)
            last_result = tool.run(call.params)
            if last_result.success or not last_result.retryable:
                return last_result
            attempts += 1
            _logger.info(
                "tool_call_retry",
                extra={
                    "indra_extra": {
                        "tool": call.tool_name,
                        "attempt": attempts,
                        "error": last_result.error,
                    }
                },
            )
        assert last_result is not None
        return last_result

    def evaluate(self, result: ToolResult) -> ToolCallEvaluation:
        return ToolCallEvaluation(
            success=result.success,
            matches_intent=result.success,
            notes=result.error or "ok",
            needs_replan=not result.success,
        )
