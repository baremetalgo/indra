"""Repository indexing: file discovery, hashing, and symbol/import extraction.

Indexing is deterministic and non-LLM, per the design's "repository
understanding should rely primarily on indexing rather than LLM
reasoning" rule. The only thing that makes this *incremental* is the
hash comparison against the previously stored row: unchanged files are
never re-parsed.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pathspec

from indra.coding.ast_inspect import language_for, node_text, parse
from indra.storage.db import Database

_DEFAULT_IGNORES = (
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    "dist", "build", ".indra", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "*.egg-info",
)


@dataclass(frozen=True)
class IndexStats:
    files_scanned: int
    files_changed: int
    files_removed: int
    symbols_extracted: int


def _hash_file(path: Path) -> str:
    h = hashlib.blake2b(digest_size=16)
    h.update(path.read_bytes())
    return h.hexdigest()


def _load_ignore_spec(root: Path) -> pathspec.PathSpec:
    patterns = list(_DEFAULT_IGNORES)
    gitignore = root / ".gitignore"
    if gitignore.exists():
        patterns.extend(gitignore.read_text(encoding="utf-8", errors="replace").splitlines())
    return pathspec.PathSpec.from_lines("gitignore", patterns)


class FileIndexer:
    def __init__(self, db: Database) -> None:
        self._db = db

    def index_workspace(self, workspace_id: str, root: Path) -> IndexStats:
        ignore_spec = _load_ignore_spec(root)
        seen_paths: set[str] = set()
        files_changed = 0
        symbols_extracted = 0

        with self._db.connect() as conn:
            existing = {
                row["path"]: row["hash"]
                for row in conn.execute(
                    "SELECT path, hash FROM repo_files WHERE workspace_id = ?", (workspace_id,)
                )
            }

            for file_path in sorted(root.rglob("*")):
                if not file_path.is_file():
                    continue
                rel_path = str(file_path.relative_to(root))
                if ignore_spec.match_file(rel_path):
                    continue

                seen_paths.add(rel_path)
                try:
                    file_hash = _hash_file(file_path)
                except OSError:
                    continue  # unreadable file (broken symlink, permissions); skip silently

                if existing.get(rel_path) == file_hash:
                    continue  # unchanged since last index

                files_changed += 1
                spec = language_for(rel_path)
                language_name = spec.name if spec else None

                conn.execute(
                    "INSERT INTO repo_files (workspace_id, path, hash, language, "
                    "size_bytes, last_indexed) VALUES (?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(workspace_id, path) DO UPDATE SET "
                    "hash=excluded.hash, language=excluded.language, "
                    "size_bytes=excluded.size_bytes, last_indexed=excluded.last_indexed",
                    (
                        workspace_id, rel_path, file_hash, language_name,
                        file_path.stat().st_size, _utcnow(),
                    ),
                )
                conn.execute(
                    "DELETE FROM repo_symbols WHERE workspace_id = ? AND file_path = ?",
                    (workspace_id, rel_path),
                )
                conn.execute(
                    "DELETE FROM repo_imports WHERE workspace_id = ? AND file_path = ?",
                    (workspace_id, rel_path),
                )

                if spec is not None:
                    symbols_extracted += self._index_symbols(
                        conn, workspace_id, rel_path, file_path, spec
                    )

            removed_paths = set(existing) - seen_paths
            for rel_path in removed_paths:
                conn.execute(
                    "DELETE FROM repo_files WHERE workspace_id = ? AND path = ?",
                    (workspace_id, rel_path),
                )
                conn.execute(
                    "DELETE FROM repo_symbols WHERE workspace_id = ? AND file_path = ?",
                    (workspace_id, rel_path),
                )
                conn.execute(
                    "DELETE FROM repo_imports WHERE workspace_id = ? AND file_path = ?",
                    (workspace_id, rel_path),
                )

        return IndexStats(
            files_scanned=len(seen_paths),
            files_changed=files_changed,
            files_removed=len(removed_paths),
            symbols_extracted=symbols_extracted,
        )

    def _index_symbols(self, conn, workspace_id: str, rel_path: str, file_path: Path, spec) -> int:
        import uuid

        try:
            source = file_path.read_bytes()
        except OSError:
            return 0
        tree = parse(source, spec)
        count = 0

        def walk(node, inside_class: bool = False) -> None:
            nonlocal count
            kind = spec.symbol_node_types.get(node.type)
            if kind is not None:
                if kind == "function" and inside_class:
                    kind = "method"
                name_node = node.child_by_field_name("name")
                name = node_text(name_node, source) if name_node is not None else "?"
                signature = _first_line(node_text(node, source))
                conn.execute(
                    "INSERT INTO repo_symbols (id, workspace_id, file_path, symbol_name, "
                    "symbol_kind, start_line, end_line, signature) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        uuid.uuid4().hex, workspace_id, rel_path, name, kind,
                        node.start_point[0] + 1, node.end_point[0] + 1, signature,
                    ),
                )
                count += 1
            elif node.type in spec.import_node_types:
                imported = _first_line(node_text(node, source))
                conn.execute(
                    "INSERT INTO repo_imports (id, workspace_id, file_path, imported_path) "
                    "VALUES (?, ?, ?, ?)",
                    (uuid.uuid4().hex, workspace_id, rel_path, imported),
                )
            next_inside_class = inside_class or node.type == "class_definition"
            for child in node.children:
                walk(child, next_inside_class)

        walk(tree.root_node)
        return count


def _first_line(text: str) -> str:
    return text.split("\n", 1)[0].strip()[:200]


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()
