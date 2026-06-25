"""Indra CLI entrypoint.

    indra run "<task>" --workspace demo --thinking-level low
    indra workspace create demo --path ./my-project
    indra workspace list
    indra doctor
    indra config show
"""

from __future__ import annotations

import json
from pathlib import Path

import typer

from indra.cli.client import get_client
from indra.config.loader import ConfigError, load_config

app = typer.Typer(no_args_is_help=True, add_completion=False)
workspace_app = typer.Typer(no_args_is_help=True)
config_app = typer.Typer(no_args_is_help=True)
app.add_typer(workspace_app, name="workspace")
app.add_typer(config_app, name="config")


@app.command()
def run(
    description: str = typer.Argument(..., help="Task description for the agent."),
    workspace: str = typer.Option(..., "--workspace", "-w", help="Workspace name."),
    thinking_level: str = typer.Option(
        "medium", "--thinking-level", help="low|medium|high"
    ),
    reasoning_effort: int = typer.Option(
        50, "--reasoning-effort", help="0-100, fine-tunes within the thinking level."
    ),
    max_steps: int = typer.Option(
        None, "--max-steps", help="Hard cap on agent-loop iterations."
    ),
) -> None:
    """Run a one-shot task in the given workspace."""
    client = get_client()
    try:
        session_resp = client.post("/sessions", json={"workspace": workspace})
        session_resp.raise_for_status()
        session_id = session_resp.json()["session_id"]

        task_resp = client.post(
            "/tasks",
            json={
                "session_id": session_id,
                "description": description,
                "workspace": workspace,
                "thinking_level": thinking_level,
                "reasoning_effort": reasoning_effort,
                "max_steps": max_steps,
            },
        )
        task_resp.raise_for_status()
        typer.echo(json.dumps(task_resp.json(), indent=2))
    finally:
        client.close()


@workspace_app.command("create")
def workspace_create(
    name: str,
    path: str = typer.Option(..., "--path", help="Root directory for this workspace."),
    default: bool = typer.Option(False, "--default"),
) -> None:
    client = get_client()
    try:
        resp = client.post(
            "/workspaces", json={"name": name, "root_path": path, "is_default": default}
        )
        resp.raise_for_status()
        typer.echo(json.dumps(resp.json(), indent=2))
    finally:
        client.close()


@workspace_app.command("list")
def workspace_list() -> None:
    client = get_client()
    try:
        resp = client.get("/workspaces")
        resp.raise_for_status()
        for ws in resp.json():
            marker = "*" if ws.get("is_default") else " "
            typer.echo(f"{marker} {ws['name']:<20} {ws['root_path']}")
    finally:
        client.close()


@workspace_app.command("remove")
def workspace_remove(name: str) -> None:
    client = get_client()
    try:
        resp = client.delete(f"/workspaces/{name}")
        resp.raise_for_status()
        typer.echo(f"removed: {name}")
    finally:
        client.close()


@config_app.command("show")
def config_show(path: str = typer.Option("indra.config.yaml", "--path")) -> None:
    try:
        config = load_config(path)
    except ConfigError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1)
    typer.echo(json.dumps(_to_dict(config), indent=2, default=str))


@config_app.command("validate")
def config_validate(path: str = typer.Option("indra.config.yaml", "--path")) -> None:
    try:
        load_config(path)
    except ConfigError as exc:
        typer.secho(f"INVALID: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    typer.secho("OK", fg=typer.colors.GREEN)


@app.command()
def doctor(path: str = typer.Option("indra.config.yaml", "--path")) -> None:
    """Cold-start sanity check: config, DB, model backend availability."""
    ok = True

    try:
        config = load_config(path)
        typer.secho("[ok] config valid", fg=typer.colors.GREEN)
    except ConfigError as exc:
        typer.secho(f"[fail] config invalid: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    try:
        from indra.storage.db import Database

        db = Database(config.db_path)
        applied = db.migrate()
        typer.secho(
            f"[ok] database ready ({config.db_path}); applied {len(applied)} new migration(s)",
            fg=typer.colors.GREEN,
        )
    except Exception as exc:  # noqa: BLE001 - doctor reports, doesn't crash
        ok = False
        typer.secho(f"[fail] database: {exc}", fg=typer.colors.RED)

    if config.model.backend == "mock":
        typer.secho("[ok] backend: mock (no model load required)", fg=typer.colors.GREEN)
    elif config.model.backend == "llama_cpp":
        if not Path(config.model.model_path).exists():
            ok = False
            typer.secho(
                f"[fail] llama.cpp model_path not found: {config.model.model_path}",
                fg=typer.colors.RED,
            )
        else:
            typer.secho(
                f"[ok] llama.cpp model file found: {config.model.model_path}",
                fg=typer.colors.GREEN,
            )

    if not ok:
        raise typer.Exit(code=1)
    typer.secho("indra doctor: all checks passed", fg=typer.colors.GREEN, bold=True)


def _to_dict(obj: object) -> object:
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _to_dict(getattr(obj, k)) for k in obj.__dataclass_fields__}
    if isinstance(obj, (list, tuple)):
        return [_to_dict(v) for v in obj]
    return obj


if __name__ == "__main__":
    app()
