-- storage/migrations/0002_memory_workspace_scope.sql
-- Fixes a real bug: memory_items had no workspace_id, so long-term
-- memory from every project bled into every other project's context.

ALTER TABLE memory_items ADD COLUMN workspace_id TEXT REFERENCES workspaces(id);

CREATE INDEX IF NOT EXISTS idx_memory_workspace
    ON memory_items(workspace_id, scope, relevance DESC);
