"""Workspace (project) management and path-containment enforcement.

A Workspace is the sandbox boundary for everything Indra touches: one
root directory, one set of sessions/tasks/memory scoped to it. Every
tool that accepts a path goes through :meth:`WorkspaceManager.resolve_path`
exactly once, centrally, so individual tools never have to reimplement
path-escape checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from indra.observability.logging import get_logger
from indra.storage.repositories import WorkspaceRepository

_logger = get_logger("workspaces.manager")


class WorkspaceError(Exception):
    """Raised on path-containment violations or unknown workspaces."""


@dataclass(frozen=True)
class Workspace:
    id: str
    name: str
    root_path: Path
    is_default: bool = False


class WorkspaceManager:
    def __init__(self, repo: WorkspaceRepository) -> None:
        self._repo = repo

    def create(self, name: str, root_path: str, is_default: bool = False) -> Workspace:
        root = Path(root_path).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        if self._repo.get_by_name(name) is not None:
            raise WorkspaceError(f"Workspace already exists: {name}")
        workspace_id = self._repo.create(name, str(root), is_default)
        _logger.info(
            "workspace_created",
            extra={"indra_extra": {"name": name, "root_path": str(root)}},
        )
        return Workspace(id=workspace_id, name=name, root_path=root, is_default=is_default)

    def get(self, name: str) -> Workspace:
        row = self._repo.get_by_name(name)
        if row is None:
            raise WorkspaceError(f"Unknown workspace: {name}")
        return Workspace(
            id=row["id"],
            name=row["name"],
            root_path=Path(row["root_path"]),
            is_default=bool(row["is_default"]),
        )

    def list_all(self) -> list[Workspace]:
        return [
            Workspace(
                id=row["id"],
                name=row["name"],
                root_path=Path(row["root_path"]),
                is_default=bool(row["is_default"]),
            )
            for row in self._repo.list_all()
        ]

    def remove(self, name: str) -> None:
        self._repo.delete(name)

    def resolve_path(self, workspace: Workspace, relative: str) -> Path:
        """Resolve ``relative`` against the workspace root; reject escapes.

        Symlinks are resolved (``Path.resolve()``) before the containment
        check, so a symlink inside the workspace cannot be used to point
        outside of it.
        """
        root = workspace.root_path.resolve()
        candidate = (root / relative).resolve()
        if candidate != root and root not in candidate.parents:
            raise WorkspaceError(
                f"Path escapes workspace '{workspace.name}': {relative!r}"
            )
        return candidate
