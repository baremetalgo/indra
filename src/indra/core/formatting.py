"""Formats a tool's structured output into a short, human-readable line.

Without this, a successful ``list_files`` or ``git_status`` call would
complete the task with no visible result at all -- the user would see
"[done] ok" and have no idea what actually happened. This was reported
as "it fails to list files" when in fact the tool succeeded; the
output just wasn't shown anywhere.
"""

from __future__ import annotations

import json
from typing import Any

_MAX_CONTENT_CHARS = 4000


def format_tool_output(tool_name: str, output: Any) -> str | None:
    """Return a short string to show the user, or None if there's nothing
    worth showing (e.g. a bare boolean confirmation)."""
    if output is None:
        return None
    if not isinstance(output, dict):
        return str(output)

    if "answer" in output:
        return str(output["answer"])
    if "files" in output:
        files = output["files"]
        return "\n".join(files) if files else "(no files found)"
    if "content" in output:
        return _truncate(str(output["content"]))
    if "status" in output:
        return str(output["status"]) or "(clean working tree)"
    if "diff" in output:
        return str(output["diff"]) or "(no changes)"
    if "log" in output:
        return str(output["log"])
    if "stdout" in output:
        parts = [output["stdout"]] if output["stdout"] else []
        if output.get("stderr"):
            parts.append(f"[stderr]\n{output['stderr']}")
        return _truncate("\n".join(parts)) if parts else "(no output)"
    if "output" in output:
        return str(output["output"]) or "(ok)"
    if "results" in output:
        return _format_search_results(output["results"])
    if "bytes_written" in output:
        return f"wrote {output['bytes_written']} bytes"
    if "deleted" in output:
        return "deleted" if output["deleted"] else None
    return json.dumps(output)


def _format_search_results(results: list[dict]) -> str:
    if not results:
        return "(no results)"
    lines = []
    for r in results:
        lines.append(f"- {r.get('title', '')} ({r.get('url', '')})")
        if r.get("snippet"):
            lines.append(f"  {r['snippet']}")
    return "\n".join(lines)


def _truncate(text: str) -> str:
    if len(text) <= _MAX_CONTENT_CHARS:
        return text
    return text[:_MAX_CONTENT_CHARS] + f"\n...[truncated, {len(text)} chars total]"
