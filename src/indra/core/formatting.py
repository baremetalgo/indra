"""Formats a tool's structured output into a short, human-readable string."""

from __future__ import annotations

import json
from typing import Any

_MAX_CONTENT_CHARS = 4000


def format_tool_output(tool_name: str, output: Any) -> str | None:
    if output is None:
        return None
    if not isinstance(output, dict):
        return str(output)
    if "answer" in output:
        return str(output["answer"])
    if "files" in output:
        return _format_file_list(output["files"])
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
    if "matches" in output:
        return _format_symbol_matches(output["matches"])
    if "imports" in output:
        imports = output["imports"]
        return "\n".join(imports) if imports else "(none found)"
    if "bytes_written" in output:
        return f"wrote {output['bytes_written']} bytes"
    if "deleted" in output:
        return "deleted" if output["deleted"] else None
    return json.dumps(output)


def _format_file_list(files: list[str]) -> str:
    if not files:
        return "(no files found)"
    by_dir: dict[str, list[str]] = {}
    for f in sorted(files):
        normalized = f.replace("\\", "/")
        parts = normalized.rsplit("/", 1)
        directory = parts[0] if len(parts) > 1 else "."
        basename = parts[-1]
        by_dir.setdefault(directory, []).append(basename)
    lines = []
    for directory in sorted(by_dir):
        if directory == ".":
            for name in sorted(by_dir[directory]):
                lines.append(f"  {name}")
        else:
            lines.append(f"  {directory}/")
            for name in sorted(by_dir[directory]):
                lines.append(f"    {name}")
    return "\n".join(lines)


def _format_search_results(results: list[dict]) -> str:
    """Render web-search results as a Markdown table instead of raw links."""
    if not results:
        return "(no results found)"
    header = "| # | Title | Source | Snippet |"
    sep    = "|---|-------|--------|---------|"
    rows = [header, sep]
    for i, r in enumerate(results, 1):
        title   = _md_cell(r.get("title", ""))
        url     = r.get("url", "")
        try:
            from urllib.parse import urlparse
            source = urlparse(url).netloc or url
        except Exception:  # noqa: BLE001
            source = url
        snippet = _md_cell((r.get("snippet") or "")[:120])
        rows.append(f"| {i} | [{title}]({url}) | {source} | {snippet} |")
    return "\n".join(rows)


def _format_symbol_matches(matches: list[dict]) -> str:
    if not matches:
        return "(no matches found)"
    lines = []
    for m in matches:
        lines.append(
            f"{m.get('file_path', '?')}:{m.get('start_line', '?')} "
            f"{m.get('symbol_kind', '')} {m.get('symbol_name', '')}"
        )
    return "\n".join(lines)


def _md_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _truncate(text: str) -> str:
    if len(text) <= _MAX_CONTENT_CHARS:
        return text
    return text[:_MAX_CONTENT_CHARS] + f"\n...[truncated, {len(text)} chars total]"
