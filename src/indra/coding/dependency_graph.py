"""Import graph queries: what does file X import, and what imports it."""

from __future__ import annotations

from indra.storage.db import Database


class DependencyGraph:
    def __init__(self, db: Database) -> None:
        self._db = db

    def imports_of(self, workspace_id: str, file_path: str) -> list[str]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT imported_path FROM repo_imports "
                "WHERE workspace_id = ? AND file_path = ? ORDER BY imported_path",
                (workspace_id, file_path),
            ).fetchall()
        return [r["imported_path"] for r in rows]

    def importers_of(self, workspace_id: str, module_substring: str) -> list[str]:
        """Files whose recorded import statement mentions ``module_substring``."""
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT file_path FROM repo_imports "
                "WHERE workspace_id = ? AND imported_path LIKE ? ORDER BY file_path",
                (workspace_id, f"%{module_substring}%"),
            ).fetchall()
        return [r["file_path"] for r in rows]
