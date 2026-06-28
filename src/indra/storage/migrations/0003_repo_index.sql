-- storage/migrations/0003_repo_index.sql
-- Repository indexing tables: file hashes (for incremental re-index),
-- extracted symbols, and import edges. All scoped by workspace_id so
-- multiple projects share one SQLite file without cross-contamination
-- (the same lesson learned the hard way with memory_items).

CREATE TABLE IF NOT EXISTS repo_files (
    workspace_id  TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    path          TEXT NOT NULL,
    hash          TEXT NOT NULL,
    language      TEXT,
    size_bytes    INTEGER,
    last_indexed  TEXT NOT NULL,
    PRIMARY KEY (workspace_id, path)
);

CREATE TABLE IF NOT EXISTS repo_symbols (
    id            TEXT PRIMARY KEY,
    workspace_id  TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    file_path     TEXT NOT NULL,
    symbol_name   TEXT NOT NULL,
    symbol_kind   TEXT NOT NULL,
    start_line    INTEGER NOT NULL,
    end_line      INTEGER NOT NULL,
    signature     TEXT
);
CREATE INDEX IF NOT EXISTS idx_symbols_name ON repo_symbols(workspace_id, symbol_name);
CREATE INDEX IF NOT EXISTS idx_symbols_file ON repo_symbols(workspace_id, file_path);

CREATE TABLE IF NOT EXISTS repo_imports (
    id              TEXT PRIMARY KEY,
    workspace_id    TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    file_path       TEXT NOT NULL,
    imported_path   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_imports_file ON repo_imports(workspace_id, file_path);
CREATE INDEX IF NOT EXISTS idx_imports_target ON repo_imports(workspace_id, imported_path);
