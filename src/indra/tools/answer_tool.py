"""The ``answer`` tool: respond directly to the user, no side effects.

Forcing every subtask through a file/shell tool breaks down for
question-answering tasks ("write me a command to do X", "what does
this function do"). This tool gives the model a legitimate way to
finish a subtask by producing text instead of hallucinating a
file/shell action that doesn't fit the request.
"""

from __future__ import annotations

import time

from indra.tools.base import ToolResult, ToolSchema

ANSWER_SCHEMA = ToolSchema(
    name="answer",
    description=(
        "Directly answer or respond to the user in text — use this when the "
        "subtask asks a question, wants an explanation, or wants a command/"
        "snippet shown rather than a file created or a program run."
    ),
    input_schema={
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
    },
    output_schema={"type": "object", "properties": {"answer": {"type": "string"}}},
)


class AnswerTool:
    schema = ANSWER_SCHEMA

    def run(self, params: dict) -> ToolResult:
        start = time.monotonic()
        return ToolResult(
            success=True,
            output={"answer": params["answer"]},
            duration_ms=int((time.monotonic() - start) * 1000),
        )


def register_answer_tool(registry) -> None:
    registry.register(AnswerTool())
