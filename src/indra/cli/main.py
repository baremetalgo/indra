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
import threading
import time

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

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

# Rich's own Console does its own careful Windows/legacy-terminal
# detection and writes through its own buffered renderer rather than
# Click's per-call writer, which sidesteps the issue above in most
# cases too. force_terminal=None (the default) lets Rich auto-detect;
# we still keep _safe_echo as the last-resort fallback for the rare
# case where even Rich's write fails.
_console = Console(highlight=False, soft_wrap=True)

app = typer.Typer(no_args_is_help=False, add_completion=False)
workspace_app = typer.Typer(no_args_is_help=True)
config_app = typer.Typer(no_args_is_help=True)
tools_app = typer.Typer(no_args_is_help=True)
memory_app = typer.Typer(no_args_is_help=True)
app.add_typer(workspace_app, name="workspace")
app.add_typer(config_app, name="config")
app.add_typer(tools_app, name="tools")
app.add_typer(memory_app, name="memory")

def _safe_echo(text: str = "", fg: str | None = None, bold: bool = False) -> None:
    """Print ``text`` and never crash the process if the console can't.

    Tries Rich's Console first (its own robust Windows handling),
    falls back through Typer/Click's echo, then plain stdout, then a
    raw OS-level write. A failed print should never take down an
    otherwise-successful task result -- see the comment above about
    why Windows console writes can intermittently fail here.
    """
    try:
        style = (fg or "") + (" bold" if bold else "")
        _console.print(text, style=style.strip() or None)
        return
    except Exception:  # noqa: BLE001 - Rich failure falls through to simpler paths
        pass
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


_TITLE_ART = (
    r"#### ##    ## ########  ########     ###    " + "\n"
    r" ##  ###   ## ##     ## ##     ##   ## ##   " + "\n"
    r" ##  ####  ## ##     ## ##     ##  ##   ##  " + "\n"
    r" ##  ## ## ## ##     ## ########  ##     ## " + "\n"
    r" ##  ##  #### ##     ## ##   ##   ######### " + "\n"
    r" ##  ##   ### ##     ## ##    ##  ##     ## " + "\n"
    r"#### ##    ## ########  ##     ## ##     ## "
)
"""Pure-ASCII block-letter 'INDRA' (every char is '#' or space) -- no
Unicode glyphs, no box-drawing characters. This is deliberate: a fancy
multi-line banner is exactly the kind of output most likely to hit the
Windows console issue described above, so it sticks to plain ASCII and
still goes through _safe_echo line by line so a failure on one line
can never take down startup."""

_BANNER_WIDTH = 64


def _print_banner(client, workspace_name: str, thinking_level: str) -> None:
    """Print a startup banner built entirely from live data -- tool
    count, workspace list, and active model config -- rather than
    decorative placeholders.
    """
    try:
        info = client.get("/info").json()
    except Exception:  # noqa: BLE001 - banner must never block startup
        info = {}
    try:
        tool_names = [t["name"] for t in client.get("/tools", params={"workspace": workspace_name}).json()]
    except Exception:  # noqa: BLE001
        tool_names = []
    try:
        workspace_names = [w["name"] for w in client.get("/workspaces").json()]
    except Exception:  # noqa: BLE001
        workspace_names = []

    backend = info.get("backend", "?")
    model_label = backend
    if backend == "llama_cpp" and info.get("model_path"):
        basename = info["model_path"].replace("\\", "/").rsplit("/", 1)[-1]
        model_label = f"llama.cpp: {basename}"
    elif backend == "mock":
        model_label = "mock (no model loaded)"

    try:
        _print_rich_banner(info, tool_names, workspace_names, backend, model_label, workspace_name, thinking_level)
    except Exception:  # noqa: BLE001 - banner must never block startup
        _print_plain_banner(info, tool_names, workspace_names, backend, model_label, workspace_name, thinking_level)


def _print_rich_banner(info, tool_names, workspace_names, backend, model_label, workspace_name, thinking_level) -> None:
    title = Text("\n".join(_TITLE_ART.split("\n")), style="bold yellow", justify="center")
    subtitle = Text("AGENTIC HARNESS FOR LOCAL LLMS", style="bold cyan", justify="center")
    tagline = Text(
        "deliberation, retrieval, and tools over raw model size",
        style="dim", justify="center",
    )

    _console.print(
        Panel(
            Text.assemble(title, "\n", subtitle, "\n", tagline),
            border_style="yellow",
            padding=(1, 2),
            width=min(_console.width, 70),
        )
    )

    body = Table.grid(padding=(0, 1))
    body.add_column(style="dim", justify="right")
    body.add_column()
    body.add_row("model", model_label)
    if backend == "llama_cpp":
        gpu_note = ""
        if info.get("gpu_layers", 0) != 0:
            gpu_note = f"  (gpu_layers={info['gpu_layers']}, flash_attn={info.get('flash_attn', False)})"
        body.add_row("context", f"{info.get('context_size', '?')}{gpu_note}")
    body.add_row("workspace", workspace_name)
    body.add_row("thinking", f"{thinking_level}  (max_steps={info.get('max_steps', '?')})")
    tool_preview = ", ".join(tool_names[:6]) + (" ..." if len(tool_names) > 6 else "")
    body.add_row(f"tools ({len(tool_names)})", tool_preview)
    if workspace_names:
        body.add_row("workspaces", ", ".join(workspace_names))

    _console.print(Panel(body, border_style="grey50", padding=(0, 2)))
    _console.print("type [bold]'exit'[/bold] to quit  |  [dim]indra doctor[/dim] for diagnostics\n")


def _print_plain_banner(info, tool_names, workspace_names, backend, model_label, workspace_name, thinking_level) -> None:
    """ASCII/plain fallback if Rich rendering fails for any reason."""
    line = "+" + "-" * (_BANNER_WIDTH - 2) + "+"
    art_pad = " " * max(0, (_BANNER_WIDTH - 44) // 2)

    _safe_echo(line, fg=typer.colors.YELLOW)
    for art_line in _TITLE_ART.split("\n"):
        _safe_echo(art_pad + art_line, fg=typer.colors.YELLOW, bold=True)
    _safe_echo(_center("AGENTIC HARNESS FOR LOCAL LLMS", _BANNER_WIDTH), fg=typer.colors.CYAN, bold=True)
    _safe_echo(_center("deliberation, retrieval, and tools over raw model size", _BANNER_WIDTH))
    _safe_echo(line, fg=typer.colors.YELLOW)
    _safe_echo(f" model      : {model_label}")
    if backend == "llama_cpp":
        gpu_note = ""
        if info.get("gpu_layers", 0) != 0:
            gpu_note = f"  (gpu_layers={info['gpu_layers']}, flash_attn={info.get('flash_attn', False)})"
        _safe_echo(f" context    : {info.get('context_size', '?')}{gpu_note}")
    _safe_echo(f" workspace  : {workspace_name}")
    _safe_echo(f" thinking   : {thinking_level}  (max_steps={info.get('max_steps', '?')})")
    _safe_echo(f" tools ({len(tool_names)})  : {', '.join(tool_names[:6])}" + (" ..." if len(tool_names) > 6 else ""))
    if workspace_names:
        _safe_echo(f" workspaces : {', '.join(workspace_names)}")
    _safe_echo(line, fg=typer.colors.YELLOW)
    _safe_echo("type 'exit' to quit  |  indra doctor for diagnostics")
    _safe_echo("")


def _center(text: str, width: int) -> str:
    pad = max(0, (width - len(text)) // 2)
    return " " * pad + text


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


class _Spinner:
    """Shows elapsed time while a blocking request is in flight.

    Indra's structured-output architecture (every model response must
    be schema-valid JSON, often grammar-constrained at decode time)
    means there's no clean way to stream raw tokens to the terminal --
    a partially-streamed JSON object isn't useful to read. This spinner
    is the honest alternative: it can't show the answer arriving
    word-by-word, but it proves the process isn't stuck and shows how
    long inference is actually taking, which was the real complaint.

    Uses Rich's Status widget (a mature, purpose-built spinner with its
    own careful terminal handling) when available, falling back to a
    hand-rolled thread-based spinner if Rich's context manager raises
    for any reason -- this should never be the difference between a
    response printing or not.
    """

    def __init__(self, label: str = "thinking") -> None:
        self._label = label
        self._start = 0.0
        self._rich_status = None
        self._fallback: _FallbackSpinner | None = None

    def __enter__(self) -> "_Spinner":
        self._start = time.monotonic()
        try:
            self._rich_status = _console.status(f"[bold cyan]{self._label}...[/bold cyan]")
            self._rich_status.__enter__()
        except Exception:  # noqa: BLE001 - fall back to the plain-text spinner
            self._rich_status = None
            self._fallback = _FallbackSpinner(self._label)
            self._fallback.__enter__()
        return self

    def __exit__(self, *exc: object) -> None:
        elapsed = time.monotonic() - self._start
        if self._rich_status is not None:
            try:
                self._rich_status.__exit__(*exc)
            except Exception:  # noqa: BLE001
                pass
        elif self._fallback is not None:
            self._fallback.__exit__(*exc)
        # Always report total elapsed time once, regardless of which
        # spinner implementation was used -- this is the actual
        # "where did the time go" signal, the animation is secondary.
        _safe_echo(f"({elapsed:0.1f}s)", fg=typer.colors.CYAN)


class _FallbackSpinner:
    """Hand-rolled thread-based spinner, used only if Rich's Status
    widget fails to construct or enter for some reason."""

    def __init__(self, label: str) -> None:
        self._label = label
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._start = 0.0

    def __enter__(self) -> "_FallbackSpinner":
        self._start = time.monotonic()
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()
        return self

    def _spin(self) -> None:
        frames = "|/-\\"
        i = 0
        while not self._stop.is_set():
            elapsed = time.monotonic() - self._start
            try:
                sys.stdout.write(f"\r{self._label}... {frames[i % len(frames)]} {elapsed:0.1f}s ")
                sys.stdout.flush()
            except OSError:
                pass
            i += 1
            time.sleep(0.2)

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        try:
            sys.stdout.write("\r" + " " * 30 + "\r")
            sys.stdout.flush()
        except OSError:
            pass


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
        try:
            _console.print(Panel(answer, border_style="dim", padding=(0, 1)))
        except Exception:  # noqa: BLE001
            _safe_echo(answer)
            _safe_echo("")

    status = data["status"]
    summary = data["summary"]
    from rich.markup import escape as _rich_escape
    color = "green" if status == "done" else "yellow"
    try:
        _console.print(f"[{color}][{status}][/{color}] {_rich_escape(summary)}")
    except Exception:
        _safe_echo(f"[{status}] {summary}",
                   fg=(typer.colors.GREEN if status == "done" else typer.colors.YELLOW))

    completion_tokens = data.get("completion_tokens", 0)
    llm_seconds = data.get("llm_seconds", 0.0)
    total_seconds = data.get("total_seconds", 0.0)
    speed = (completion_tokens / llm_seconds) if llm_seconds > 0 else 0.0
    overhead = max(0.0, total_seconds - llm_seconds)

    try:
        stats = Table.grid(padding=(0, 2))
        for _ in range(6):
            stats.add_column()
        stats.add_row(
            f"calls: {data['llm_calls_used']}",
            f"tokens: {data.get('prompt_tokens', 0)}p/{completion_tokens}c",
            f"llm: {llm_seconds:.1f}s",
            f"overhead: {overhead:.1f}s",
            f"total: {total_seconds:.1f}s",
            f"speed: {speed:.1f} tok/s",
        )
        _console.print(stats, style="dim cyan")
    except Exception:  # noqa: BLE001
        _safe_echo(
            f"  calls: {data['llm_calls_used']}  |  "
            f"tokens: {data.get('prompt_tokens', 0)}p/{completion_tokens}c  |  "
            f"llm: {llm_seconds:.1f}s  |  agent overhead: {overhead:.1f}s  |  "
            f"total: {total_seconds:.1f}s  |  speed: {speed:.1f} tok/s",
            fg=typer.colors.CYAN,
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

        _print_banner(client, ws, thinking_level)

        session_resp = client.post("/sessions", json={"workspace": ws})
        session_resp.raise_for_status()
        session_id = session_resp.json()["session_id"]

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

            # Echo the user's message in cyan before the spinner so the
            # conversation is easy to scan when llama.cpp logs land between turns.
            try:
                from rich.markup import escape as _re2
                _console.print(f"[bold cyan]you:[/bold cyan] {_re2(stripped)}")
            except Exception:
                pass

            try:
                with _Spinner("thinking"):
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

        if as_json:
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
        else:
            with _Spinner("thinking"):
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


@app.command(name="index")
def index_workspace(
    workspace: str = typer.Option(None, "--workspace", "-w", help="Workspace name."),
) -> None:
    """Re-index a workspace's repository (symbols, imports). Incremental:
    unchanged files are skipped via content hash."""
    client = get_client()
    try:
        ws = workspace or _default_workspace(client)
        if ws is None:
            _safe_echo("No workspace found.", fg=typer.colors.YELLOW)
            return
        with _Spinner("indexing"):
            resp = client.post(f"/workspaces/{ws}/index")
        resp.raise_for_status()
        data = resp.json()
        _safe_echo(
            f"scanned: {data['files_scanned']}  changed: {data['files_changed']}  "
            f"removed: {data['files_removed']}  symbols: {data['symbols_extracted']}",
            fg=typer.colors.GREEN,
        )
    finally:
        client.close()


@memory_app.command("list")
def memory_list(
    workspace: str = typer.Option(None, "--workspace", "-w"),
    limit: int = typer.Option(20, "--limit"),
) -> None:
    """List long-term memory items for a workspace."""
    client = get_client()
    try:
        ws = workspace or _default_workspace(client)
        if ws is None:
            _safe_echo("No workspace found.", fg=typer.colors.YELLOW)
            return
        resp = client.get("/memory", params={"workspace": ws, "limit": limit})
        resp.raise_for_status()
        items = resp.json()
        if not items:
            _safe_echo("(no long-term memory items)")
        for item in items:
            _safe_echo(f"[{item['kind']}] {item['content']}  (relevance={item['relevance']:.2f})")
    finally:
        client.close()


@memory_app.command("clear")
def memory_clear(
    workspace: str = typer.Option(None, "--workspace", "-w"),
    yes: bool = typer.Option(False, "--yes", help="Skip the confirmation prompt."),
) -> None:
    """Wipe all long-term memory for a workspace.

    Useful right now if you tested an earlier version of Indra before
    the memory-contamination fix: old "Task completed: ..." rows from
    that version are still sitting in .indra/indra.db and will keep
    getting recalled into unrelated tasks until cleared.
    """
    client = get_client()
    try:
        ws = workspace or _default_workspace(client)
        if ws is None:
            _safe_echo("No workspace found.", fg=typer.colors.YELLOW)
            return
        if not yes:
            confirmed = typer.confirm(f"Clear all long-term memory for workspace '{ws}'?")
            if not confirmed:
                _safe_echo("cancelled")
                return
        resp = client.delete("/memory", params={"workspace": ws})
        resp.raise_for_status()
        data = resp.json()
        _safe_echo(f"cleared {data['deleted']} memory item(s) from '{ws}'", fg=typer.colors.GREEN)
    finally:
        client.close()


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

        try:
            import llama_cpp  # noqa: F401 -- import alone triggers native lib loading

            _safe_echo(
                "[ok] llama-cpp-python native library loaded successfully",
                fg=typer.colors.GREEN,
            )
        except ImportError:
            ok = False
            _safe_echo(
                "[fail] llama-cpp-python is not installed. Install with: "
                "pip install 'indra[llama-cpp]'",
                fg=typer.colors.RED,
            )
        except OSError as exc:
            ok = False
            _safe_echo(
                f"[fail] llama-cpp-python's native library failed to load: {exc}\n"
                "  No inference will work (CPU or GPU) until this is fixed. Try:\n"
                "  pip uninstall llama-cpp-python && pip install llama-cpp-python "
                "--no-cache-dir --force-reinstall",
                fg=typer.colors.RED,
            )

        if config.model.gpu_layers != 0:
            from indra.providers.llama_cpp_provider import gpu_offload_supported

            supports_gpu = gpu_offload_supported()
            if supports_gpu is True:
                _safe_echo(
                    "[ok] installed llama-cpp-python supports GPU offload",
                    fg=typer.colors.GREEN,
                )
                _safe_echo(
                    "[info] if you saw 'suboptimal performance due to a lack of "
                    "tensor cores' when the model loaded, that warning comes from "
                    "llama.cpp itself, not Indra: your installed wheel wasn't built "
                    "for your GPU's specific compute capability. Reinstall with the "
                    "matching arch, e.g. for a Turing card (GTX 16xx/RTX 20xx, "
                    "compute capability 7.5):\n"
                    "  CMAKE_ARGS=\"-DGGML_CUDA=on -DCMAKE_CUDA_ARCHITECTURES=75\" "
                    "pip install llama-cpp-python --force-reinstall --no-cache-dir\n"
                    "(check your card's compute capability at "
                    "https://developer.nvidia.com/cuda-gpus if unsure)",
                    fg=typer.colors.CYAN,
                )
            elif supports_gpu is False:
                _safe_echo(
                    "[warn] installed llama-cpp-python is CPU-only -- gpu_layers "
                    "will be silently ignored. `pip install llama-cpp-python` "
                    "installs a CPU-only wheel on most platforms. Reinstall with "
                    "GPU support, e.g.:\n"
                    "  CMAKE_ARGS=\"-DGGML_CUDA=on\" pip install llama-cpp-python "
                    "--force-reinstall --no-cache-dir\n"
                    "or use one of the prebuilt CUDA wheels at "
                    "https://github.com/abetlen/llama-cpp-python#installation",
                    fg=typer.colors.YELLOW,
                )
            else:
                _safe_echo(
                    "[info] could not determine whether this llama-cpp-python "
                    "build supports GPU offload (older/newer binding without "
                    "llama_supports_gpu_offload()). If inference looks CPU-bound, "
                    "reinstall with CUDA support -- see "
                    "https://github.com/abetlen/llama-cpp-python#installation",
                    fg=typer.colors.CYAN,
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
    else:
        import httpx as _httpx

        discovered = f"http://{config.api.host}:{config.api.port}"
        try:
            reachable = _httpx.get(f"{discovered}/health", timeout=0.5).status_code == 200
        except _httpx.HTTPError:
            reachable = False

        if reachable:
            _safe_echo(
                f"[ok] CLI mode: auto-discovered running server at {discovered} "
                "(no api.base_url needed)",
                fg=typer.colors.GREEN,
            )
        elif config.model.backend == "llama_cpp":
            _safe_echo(
                f"[warn] CLI mode: in-process -- no server found at {discovered}. "
                "Run `indra serve` in another terminal first (the CLI auto-discovers "
                "it there); with backend=llama_cpp, running without a server reloads "
                "the model on every command.",
                fg=typer.colors.YELLOW,
            )
        else:
            _safe_echo(
                "[ok] CLI mode: in-process (fine for the mock backend)", fg=typer.colors.GREEN
            )

    if config.web_search.base_url:
        import httpx

        url = config.web_search.base_url.rstrip("/") + "/search"
        try:
            resp = httpx.get(
                url, params={"q": "test", "format": "json"},
                timeout=config.web_search.fetch_timeout_seconds,
            )
            if resp.status_code == 200:
                try:
                    resp.json()
                    _safe_echo(
                        f"[ok] web_search reachable at {config.web_search.base_url} "
                        "(json format enabled)",
                        fg=typer.colors.GREEN,
                    )
                except ValueError:
                    _safe_echo(
                        f"[warn] web_search at {config.web_search.base_url} responded "
                        "but not with JSON -- if this is SearXNG, enable 'json' under "
                        "search.formats in settings.yml and restart it.",
                        fg=typer.colors.YELLOW,
                    )
            else:
                _safe_echo(
                    f"[warn] web_search at {config.web_search.base_url} returned "
                    f"HTTP {resp.status_code}",
                    fg=typer.colors.YELLOW,
                )
        except httpx.HTTPError as exc:
            _safe_echo(
                f"[warn] web_search unreachable at {config.web_search.base_url}: {exc}\n"
                "  Check that the port in web_search.base_url matches what your "
                "SearXNG container actually publishes (e.g. `docker ps` -- the host "
                "port is the first number in PORTS, like 8888 in '8888:8080').",
                fg=typer.colors.YELLOW,
            )
    else:
        _safe_echo("[info] web_search.base_url not set -- web_search tool will fail", fg=typer.colors.CYAN)

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
