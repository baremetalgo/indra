from __future__ import annotations

from indra.core.formatting import format_tool_output


def test_answer_output() -> None:
    assert format_tool_output("answer", {"answer": "use Get-ChildItem Env:"}) == "use Get-ChildItem Env:"


def test_list_files_output() -> None:
    assert format_tool_output("list_files", {"files": ["a.txt", "b.txt"]}) == "a.txt\nb.txt"


def test_list_files_empty() -> None:
    assert format_tool_output("list_files", {"files": []}) == "(no files found)"


def test_git_status_clean() -> None:
    assert format_tool_output("git_status", {"status": ""}) == "(clean working tree)"


def test_git_diff_no_changes() -> None:
    assert format_tool_output("git_diff", {"diff": ""}) == "(no changes)"


def test_run_shell_stdout_and_stderr() -> None:
    text = format_tool_output("run_shell", {"stdout": "ok", "stderr": "warn", "exit_code": 0})
    assert "ok" in text
    assert "warn" in text


def test_write_file_confirmation() -> None:
    assert format_tool_output("write_file", {"bytes_written": 42}) == "wrote 42 bytes"


def test_delete_file_true_shows_confirmation() -> None:
    assert format_tool_output("delete_file", {"deleted": True}) == "deleted"


def test_search_results_formatting() -> None:
    text = format_tool_output(
        "web_search",
        {"results": [{"title": "Example", "url": "http://example.com", "snippet": "a snippet"}]},
    )
    assert "Example" in text
    assert "http://example.com" in text
    assert "a snippet" in text


def test_none_output_returns_none() -> None:
    assert format_tool_output("delete_file", None) is None


def test_unknown_shape_falls_back_to_json() -> None:
    result = format_tool_output("mystery_tool", {"weird_field": 123})
    assert "weird_field" in result
