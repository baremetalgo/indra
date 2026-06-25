-- storage/migrations/0001_init.sql
-- Initial Indra schema. Applied in order by filename; see storage/db.py.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS workspaces (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL UNIQUE,
    root_path     TEXT NOT NULL UNIQUE,
    created_at    TEXT NOT NULL,
    is_default    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sessions (
    id            TEXT PRIMARY KEY,
    workspace_id  TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'active'
);
CREATE INDEX IF NOT EXISTS idx_sessions_workspace ON sessions(workspace_id);

CREATE TABLE IF NOT EXISTS tasks (
    id            TEXT PRIMARY KEY,
    session_id    TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    description   TEXT NOT NULL,
    status        TEXT NOT NULL,
    plan_id       TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_tasks_session ON tasks(session_id);

CREATE TABLE IF NOT EXISTS plans (
    id                TEXT PRIMARY KEY,
    task_id           TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    version           INTEGER NOT NULL DEFAULT 1,
    goal              TEXT NOT NULL,
    constraints_json  TEXT NOT NULL DEFAULT '[]',
    assumptions_json  TEXT NOT NULL DEFAULT '[]',
    success_json      TEXT NOT NULL DEFAULT '[]',
    created_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS subtasks (
    id            TEXT PRIMARY KEY,
    plan_id       TEXT NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    description   TEXT NOT NULL,
    depends_on    TEXT NOT NULL DEFAULT '[]',
    tool_hint     TEXT,
    done          INTEGER NOT NULL DEFAULT 0,
    seq           INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_subtasks_plan ON subtasks(plan_id);

CREATE TABLE IF NOT EXISTS tool_calls (
    id            TEXT PRIMARY KEY,
    task_id       TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    subtask_id    TEXT REFERENCES subtasks(id),
    tool_name     TEXT NOT NULL,
    params_json   TEXT NOT NULL,
    result_json   TEXT,
    success       INTEGER,
    duration_ms   INTEGER,
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_toolcalls_task ON tool_calls(task_id);

CREATE TABLE IF NOT EXISTS memory_items (
    id             TEXT PRIMARY KEY,
    scope          TEXT NOT NULL,
    kind           TEXT NOT NULL,
    content        TEXT NOT NULL,
    relevance      REAL NOT NULL DEFAULT 0.5,
    session_id     TEXT REFERENCES sessions(id),
    source_task_id TEXT REFERENCES tasks(id),
    created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memory_scope ON memory_items(scope, relevance DESC);

CREATE TABLE IF NOT EXISTS token_usage (
    id                 TEXT PRIMARY KEY,
    task_id            TEXT REFERENCES tasks(id),
    prompt_tokens      INTEGER NOT NULL,
    completion_tokens  INTEGER NOT NULL,
    purpose            TEXT NOT NULL,
    created_at         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS search_cache (
    query_hash    TEXT PRIMARY KEY,
    query_text    TEXT NOT NULL,
    provider      TEXT NOT NULL,
    results_json  TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    expires_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_search_cache_expiry ON search_cache(expires_at);

CREATE TABLE IF NOT EXISTS capability_profile (
    id              TEXT PRIMARY KEY DEFAULT 'current',
    detected_json   TEXT NOT NULL,
    derived_json    TEXT NOT NULL,
    model_hash      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS config_state (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS schema_migrations (
    filename     TEXT PRIMARY KEY,
    applied_at   TEXT NOT NULL
);
