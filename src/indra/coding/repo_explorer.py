"""High-level repository queries, built on the indexes below.

``build_repo_map`` is the one function that matters most: it produces
the compact, token-cheap summary handed to the planner as repo context
(per §10 -- "prefer repository maps over raw source code"). It lists
files and their top-level symbols only, never bodies.
"""

from __future__ import annotations

from dataclasses import dataclass

from indra.storage.db import Database

_MAX_FILES_IN_MAP = 40
_MAX_SYMBOLS_PER_FILE = 8


@dataclass(frozen=True)
class RepoSummary:
    file_count: int
    indexed_file_count: int
    map_text: str


class RepoExplorer:
    def __init__(self, db: Database) -> None:
        self._db = db

    def build_repo_map(self, workspace_id: str) -> RepoSummary:
        with self._db.connect() as conn:
            total_files = conn.execute(
                "SELECT COUNT(*) AS n FROM repo_files WHERE workspace_id = ?", (workspace_id,)
            ).fetchone()["n"]

            indexed_files = conn.execute(
                "SELECT DISTINCT file_path FROM repo_symbols WHERE workspace_id = ? "
                "ORDER BY file_path LIMIT ?",
                (workspace_id, _MAX_FILES_IN_MAP),
            ).fetchall()

            lines: list[str] = []
            for row in indexed_files:
                file_path = row["file_path"]
                symbols = conn.execute(
                    "SELECT symbol_name, symbol_kind FROM repo_symbols "
                    "WHERE workspace_id = ? AND file_path = ? ORDER BY start_line LIMIT ?",
                    (workspace_id, file_path, _MAX_SYMBOLS_PER_FILE),
                ).fetchall()
                names = ", ".join(f"{s['symbol_kind']} {s['symbol_name']}" for s in symbols)
                lines.append(f"{file_path}: {names}" if names else file_path)

        if not lines:
            map_text = "(no indexed files yet)"
        else:
            map_text = "\n".join(lines)
            if total_files > len(indexed_files):
                map_text += f"\n... and {total_files - len(indexed_files)} more files"

        return RepoSummary(
            file_count=total_files,
            indexed_file_count=len(indexed_files),
            map_text=map_text,
        )
