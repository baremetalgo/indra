from __future__ import annotations

from indra.tools.answer_tool import AnswerTool
from indra.tools.base import ToolRegistry, ToolValidationError
import pytest


def test_answer_tool_returns_text_verbatim() -> None:
    tool = AnswerTool()
    result = tool.run({"answer": "use Get-ChildItem Env: on PowerShell"})
    assert result.success
    assert result.output["answer"] == "use Get-ChildItem Env: on PowerShell"


def test_answer_tool_registers_and_validates() -> None:
    registry = ToolRegistry()
    registry.register(AnswerTool())
    registry.validate_input("answer", {"answer": "hi"})
    with pytest.raises(ToolValidationError):
        registry.validate_input("answer", {})  # missing required field
