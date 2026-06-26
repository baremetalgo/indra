"""Indra CLI entrypoint.

    indra                    # interactive REPL (default — same as `indra chat`)
    indra chat --workspace demo
    indra run "<task>" --workspace demo --thinking-level low
    indra workspace create demo --path ./my-project
    indra workspace list
    indra doctor
    indra config show

ASCII-only output throughout: Windows' legacy console codepages (cp1252
etc.) raise UnicodeEncodeError on emoji/box-drawing characters, so the
banner and all status markers stick to plain ASCII.
"""

from __future__ import annotations

import json
import os
import sys

import typer

from indra.cli.client import get_client

# On Windows, Click uses a special Unicode console writer
# (click._winconsole) whenever stdout's encoding isn't already UTF-8.
# That writer calls the raw Win32 WriteConsoleW API directly, and if a
# native library (llama.cpp's logging, in practice) has touched the
# console state, the cached handle can go stale and WriteConsoleW fails
# with ERROR_INVALID_HANDLE (OSError: Windows error: 6). Reconfiguring
# stdout/stderr to UTF-8 up front makes Click skip that code path
# entirely in most cases; this is a no-op on platforms where it's not
# needed or not supported.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except (AttributeError, ValueError, OSError):
        pass

app = typer.Typer(no_args_is_help=False, add_completion=False)
workspace_app = typer.Typer(no_args_is_help=True)
config_app = typer.Typer(no_args_is_help=True)
tools_app = typer.Typer(no_args_is_help=True)
app.add_typer(workspace_app, name="workspace")
app.add_typer(config_app, name="config")
app.add_typer(tools_app, name="tools")

BANNER = r"""
======================================================
   INDRA -- agentic coding harness for local LLMs
======================================================
"""


def _safe_echo(text: str = "", fg: str | None = None, bold: bool = False) -> None:
    """Print ``text`` and never crash the process if the console can't.

    Falls back through three I/O paths in order: Typer/Click's normal
    echo, plain stdout, then a raw OS-level write. This exists because
    Click's Windows Unicode console writer can hit a stale console
    handle (ERROR_INVALID_HANDLE) after a native library has written to
    the console — see the comment at the top of this module. A failed
    print should never take down an otherwise-successful task result.
    """
    try:
        if fg or bold:
            typer.secho(text, fg=fg, bold=bold)
        else:
            typer.echo(text)
        return
    except OSError:
        pass
    try:
        sys.stdout.write(text + "\n")
        sys.stdout.flush()
        return
    except OSError:
        pass
    try:
        os.write(1, (text + "\n").encode("utf-8", errors="replace"))
    except OSError:
        pass  # genuinely nothing we can do; don't crash the task over a print


def _print_banner() -> None:
    _safe_echo(BANNER)


def _safe_prompt(label: str) -> str:
    """Read one line of input, falling back to plain ``input()`` on OSError.

    ``typer.prompt`` renders its label through the same Click writer
    that can hit a stale Windows console handle (see ``_safe_echo``).
    """
    try:
        return typer.prompt(label, prompt_suffix="")
    except OSError:
        sys.stdout.write(label)
        sys.stdout.flush()
        return input()


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """Running `indra` with no subcommand drops you into the chat REPL."""
    if ctx.invoked_subcommand is None:
        _chat_impl(workspace=None, thinking_level="medium", reasoning_effort=50, max_steps=None)


def _default_workspace(client) -> str | None:
    resp = client.get("/workspaces")
    resp.raise_for_status()
    workspaces = resp.json()
    if not workspaces:
        return None
    for ws in workspaces:
        if ws.get("is_default"):
            return ws["name"]
    return workspaces[0]["name"]


def _print_task_result(data: dict) -> None:
    for answer in data.get("artifacts", []):
        _safe_echo(answer)
        _safe_echo("")
    color = typer.colors.GREEN if data["status"] == "done" else typer.colors.YELLOW
    _safe_echo(
        f"[{data['status']}] {data['summary']}  (llm calls used: {data['llm_calls_used']})",
        fg=color,
    )


@app.command()
def chat(
    workspace: str = typer.Option(None, "--workspace", "-w", help="Workspace name."),
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
    """Interactive REPL — the default when you just run `indra`."""
    _chat_impl(workspace, thinking_level, reasoning_effort, max_steps)


def _chat_impl(
    workspace: str | None,
    thinking_level: str,
    reasoning_effort: int,
    max_steps: int | None,
) -> None:
    _print_banner()
    client = get_client()
    try:
        ws = workspace or _default_workspace(client)
        if ws is None:
            _safe_echo(
                "No workspace found. Create one first:\n"
                "  indra workspace create <name> --path <dir> --default",
                fg=typer.colors.YELLOW,
            )
            return

        session_resp = client.post("/sessions", json={"workspace": ws})
        session_resp.raise_for_status()
        session_id = session_resp.json()["session_id"]

        _safe_echo(f"workspace: {ws}  |  thinking: {thinking_level}  |  type 'exit' to quit")
        _safe_echo("")

        while True:
            try:
                text = _safe_prompt("> ")
            except (EOFError, KeyboardInterrupt):
                _safe_echo("\nbye.")
                break

            stripped = text.strip()
            if stripped.lower() in ("exit", "quit", ":q"):
                _safe_echo("bye.")
                break
            if not stripped:
                continue

            try:
                resp = client.post(
                    "/tasks",
                    json={
                        "session_id": session_id,
                        "description": stripped,
                        "workspace": ws,
                        "thinking_level": thinking_level,
                        "reasoning_effort": reasoning_effort,
                        "max_steps": max_steps,
                    },
                )
                resp.raise_for_status()
                _print_task_result(resp.json())
            except Exception as exc:  # noqa: BLE001 - keep the REPL alive on any error
                _safe_echo(f"error: {exc}", fg=typer.colors.RED)
            _safe_echo("")
    finally:
        client.close()


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
    as_json: bool = typer.Option(False, "--json", help="Print the raw JSON result."),
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
        data = task_resp.json()
        if as_json:
            _safe_echo(json.dumps(data, indent=2))
        else:
            _print_task_result(data)
    finally:
        client.close()


@app.command()
def serve(
    host: str = typer.Option(None, "--host", help="Defaults to api.host in config."),
    port: int = typer.Option(None, "--port", help="Defaults to api.port in config."),
    path: str = typer.Option("indra.config.yaml", "--config"),
) -> None:
    """Run the Indra API as a standalone, long-lived process.

    Recommended for llama.cpp: the GGUF model loads once on the first
    request and stays warm for every task after that, instead of being
    reloaded from disk on every `indra run`/`indra chat` invocation.
    Point the CLI at it by setting `api.base_url` in indra.config.yaml
    (or the INDRA_API_URL env var) to "http://<host>:<port>".
    """
    from indra.config.loader import ConfigError, load_config

    try:
        config = load_config(path)
    except ConfigError as exc:
        _safe_echo(f"[fail] config invalid: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    bind_host = host or config.api.host
    bind_port = port or config.api.port

    try:
        import uvicorn
    except ImportError:
        _safe_echo(
            "uvicorn is not installed. Install with: pip install -e .",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    _safe_echo(
        f"Starting Indra API on http://{bind_host}:{bind_port}\n"
        f"Point the CLI at it via api.base_url in {path} or INDRA_API_URL.",
        fg=typer.colors.GREEN,
    )
    uvicorn.run(
        "indra.api.app:app",
        host=bind_host,
        port=bind_port,
        log_level=config.log_level.lower(),
    )


@tools_app.command("list")
def tools_list(
    workspace: str = typer.Option(None, "--workspace", "-w", help="Workspace name."),
) -> None:
    """List the tools available to the agent in a workspace."""
    client = get_client()
    try:
        ws = workspace or _default_workspace(client)
        if ws is None:
            _safe_echo(
                "No workspace found. Create one first:\n"
                "  indra workspace create <name> --path <dir> --default",
                fg=typer.colors.YELLOW,
            )
            return
        resp = client.get("/tools", params={"workspace": ws})
        resp.raise_for_status()
        for tool in resp.json():
            _safe_echo(f"{tool['name']:<14} {tool['description']}")
    finally:
        client.close()


@tools_app.command("describe")
def tools_describe(
    name: str,
    workspace: str = typer.Option(None, "--workspace", "-w", help="Workspace name."),
) -> None:
    """Show the full description for one tool."""
    client = get_client()
    try:
        ws = workspace or _default_workspace(client)
        if ws is None:
            _safe_echo("No workspace found.", fg=typer.colors.YELLOW)
            return
        resp = client.get("/tools", params={"workspace": ws})
        resp.raise_for_status()
        for tool in resp.json():
            if tool["name"] == name:
                _safe_echo(f"{tool['name']}: {tool['description']}")
                return
        _safe_echo(f"Unknown tool: {name}", fg=typer.colors.YELLOW)
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
        _safe_echo(json.dumps(resp.json(), indent=2))
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
            _safe_echo(f"{marker} {ws['name']:<20} {ws['root_path']}")
    finally:
        client.close()


@workspace_app.command("remove")
def workspace_remove(name: str) -> None:
    client = get_client()
    try:
        resp = client.delete(f"/workspaces/{name}")
        resp.raise_for_status()
        _safe_echo(f"removed: {name}")
    finally:
        client.close()


@config_app.command("show")
def config_show(path: str = typer.Option("indra.config.yaml", "--path")) -> None:
    from indra.config.loader import ConfigError, load_config

    try:
        config = load_config(path)
    except ConfigError as exc:
        _safe_echo(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1)
    _safe_echo(json.dumps(_to_dict(config), indent=2, default=str))


@config_app.command("validate")
def config_validate(path: str = typer.Option("indra.config.yaml", "--path")) -> None:
    from indra.config.loader import ConfigError, load_config

    try:
        load_config(path)
    except ConfigError as exc:
        _safe_echo(f"INVALID: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    _safe_echo("OK", fg=typer.colors.GREEN)


@app.command()
def doctor(path: str = typer.Option("indra.config.yaml", "--path")) -> None:
    """Cold-start sanity check: config, DB, model backend availability."""
    from pathlib import Path

    from indra.config.loader import ConfigError, load_config

    ok = True

    try:
        config = load_config(path)
        _safe_echo("[ok] config valid", fg=typer.colors.GREEN)
    except ConfigError as exc:
        _safe_echo(f"[fail] config invalid: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    try:
        from indra.storage.db import Database

        db = Database(config.db_path)
        applied = db.migrate()
        _safe_echo(
            f"[ok] database ready ({config.db_path}); applied {len(applied)} new migration(s)",
            fg=typer.colors.GREEN,
        )
    except Exception as exc:  # noqa: BLE001 - doctor reports, doesn't crash
        ok = False
        _safe_echo(f"[fail] database: {exc}", fg=typer.colors.RED)

    if config.model.backend == "mock":
        _safe_echo("[ok] backend: mock (no model load required)", fg=typer.colors.GREEN)
    elif config.model.backend == "llama_cpp":
        if not Path(config.model.model_path).exists():
            ok = False
            _safe_echo(
                f"[fail] llama.cpp model_path not found: {config.model.model_path}",
                fg=typer.colors.RED,
            )
        else:
            _safe_echo(
                f"[ok] llama.cpp model file found: {config.model.model_path}",
                fg=typer.colors.GREEN,
            )

    if os.environ.get("INDRA_API_URL"):
        _safe_echo(
            f"[ok] CLI mode: remote server via INDRA_API_URL={os.environ['INDRA_API_URL']}",
            fg=typer.colors.GREEN,
        )
    elif config.api.base_url:
        _safe_echo(
            f"[ok] CLI mode: remote server via api.base_url={config.api.base_url}",
            fg=typer.colors.GREEN,
        )
    elif config.model.backend == "llama_cpp":
        _safe_echo(
            "[warn] CLI mode: in-process (no api.base_url / INDRA_API_URL set) -- "
            "with backend=llama_cpp this reloads the model on every command. "
            "Run `indra serve` and set api.base_url for a much faster workflow.",
            fg=typer.colors.YELLOW,
        )
    else:
        _safe_echo("[ok] CLI mode: in-process (fine for the mock backend)", fg=typer.colors.GREEN)

    if not ok:
        raise typer.Exit(code=1)
    _safe_echo("indra doctor: all checks passed", fg=typer.colors.GREEN, bold=True)


def _to_dict(obj: object) -> object:
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _to_dict(getattr(obj, k)) for k in obj.__dataclass_fields__}
    if isinstance(obj, (list, tuple)):
        return [_to_dict(v) for v in obj]
    return obj


if __name__ == "__main__":
    app()
