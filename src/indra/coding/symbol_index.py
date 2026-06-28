"""Symbol lookup queries -- the backing store for the symbol_search tool
and for repo_explorer's repo-map generation."""

from __future__ import annotations

from dataclasses import dataclass

from indra.storage.db import Database


@dataclass(frozen=True)
class SymbolHit:
    file_path: str
    symbol_name: str
    symbol_kind: str
    start_line: int
    end_line: int
    signature: str | None


class SymbolIndex:
    def __init__(self, db: Database) -> None:
        self._db = db

    def search(self, workspace_id: str, query: str, limit: int = 20) -> list[SymbolHit]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT file_path, symbol_name, symbol_kind, start_line, end_line, signature "
                "FROM repo_symbols WHERE workspace_id = ? AND symbol_name LIKE ? "
                "ORDER BY symbol_name LIMIT ?",
                (workspace_id, f"%{query}%", limit),
            ).fetchall()
        return [
            SymbolHit(
                file_path=r["file_path"], symbol_name=r["symbol_name"],
                symbol_kind=r["symbol_kind"], start_line=r["start_line"],
                end_line=r["end_line"], signature=r["signature"],
            )
            for r in rows
        ]

    def symbols_in_file(self, workspace_id: str, file_path: str) -> list[SymbolHit]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT file_path, symbol_name, symbol_kind, start_line, end_line, signature "
                "FROM repo_symbols WHERE workspace_id = ? AND file_path = ? "
                "ORDER BY start_line",
                (workspace_id, file_path),
            ).fetchall()
        return [
            SymbolHit(
                file_path=r["file_path"], symbol_name=r["symbol_name"],
                symbol_kind=r["symbol_kind"], start_line=r["start_line"],
                end_line=r["end_line"], signature=r["signature"],
            )
            for r in rows
        ]

    def file_count(self, workspace_id: str) -> int:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM repo_files WHERE workspace_id = ?", (workspace_id,)
            ).fetchone()
        return row["n"]
