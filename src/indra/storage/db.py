"""SQLite connection management and migration runner.

Migrations are plain ``.sql`` files in ``storage/migrations/``, applied
in filename order exactly once each (tracked in ``schema_migrations``).
This keeps schema evolution simple and dependency-free.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path
from typing import Iterator

from indra.observability.logging import get_logger

_logger = get_logger("storage.db")


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    """Thin wrapper around a single SQLite file with migration support."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def migrate(self, migrations_dir: str | Path | None = None) -> list[str]:
        """Apply any not-yet-applied migrations. Returns applied filenames."""
        if migrations_dir is None:
            migrations_dir = resources.files("indra.storage") / "migrations"
        migrations_dir = Path(str(migrations_dir))

        applied: list[str] = []
        with self.connect() as conn:
            conn.executescript(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "  filename TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            already = {
                row["filename"]
                for row in conn.execute("SELECT filename FROM schema_migrations")
            }
            for sql_file in sorted(migrations_dir.glob("*.sql")):
                if sql_file.name in already:
                    continue
                conn.executescript(sql_file.read_text(encoding="utf-8"))
                conn.execute(
                    "INSERT INTO schema_migrations (filename, applied_at) "
                    "VALUES (?, ?)",
                    (sql_file.name, _utcnow()),
                )
                applied.append(sql_file.name)
                _logger.info(
                    "migration_applied", extra={"indra_extra": {"file": sql_file.name}}
                )
        return applied
