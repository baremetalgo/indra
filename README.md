<h1 align="center"> Indra</h1>
<p align="center">Intelligent Network for Deliberation, Reasoning & Action</p>
<p align="center">
  <img src="indra_logo.png" width="50%">
</p>
<h3 align="center"> Agentic Harness</h3>

Indra is an AI coding and automation harness designed for lightweight local LLMs, inspired by modern agentic development tools and optimized for consumer hardware.

See [`PLAN.md`](PLAN.md) for the full architecture and design rationale.

## Status

This branch currently implements **Phase 0–2 of the roadmap**: a
working, tested, end-to-end agent loop (plan → execute → evaluate →
persist) running against either a deterministic mock model or a real
llama.cpp GGUF model, with workspace sandboxing, SQLite persistence,
structured logging, and a CLI/API split.

**Implemented:**
- Config system (YAML + env overrides, fail-fast validation)
- SQLite schema + migrations
- Structured JSON logging + per-task LLM call budget **and timing**
  tracking (`llm_seconds` vs. total wall-clock, so you can see how much
  time is the model vs. the agent loop itself)
- Workspace sandboxing (path-containment enforced centrally, symlink-safe),
  and **long-term memory is correctly scoped per workspace** — it used
  to leak across projects; fixed and covered by a regression test
- Tool registry with 13 schema-validated tools: file (read/write/list/
  delete), `answer` (respond in text without a file/shell action), git
  (status/diff/log/commit/branch/stash, structured not raw-command),
  `run_shell` (allowlist-gated, no `shell=True`, sandboxed `cwd`,
  bounded timeout/output), and `web_search` (SearXNG, cached, capped
  snippets)
- Every successful tool's output is shown to the user, not just
  `answer`'s — a silent `list_files`/`git_status` success used to look
  like nothing happened
- Model provider abstraction: `mock` (default, no model needed) and
  `llama_cpp` (grammar-constrained JSON decoding, optional `flash_attn`
  with graceful fallback on older bindings)
- `indra doctor` checks whether the installed llama-cpp-python build
  actually supports GPU offload and tells you how to fix it if not —
  `pip install llama-cpp-python` alone is CPU-only on most platforms
- Planner → Executor → Agent loop with bounded re-planning (the planner
  is told *why* the previous attempt failed, so re-planning picks a
  different approach instead of repeating it) and a hard `max_steps`
  safety valve — never crashes on bad/unparseable model output
- Tool retries distinguish transient vs. deterministic failures
  (`ToolResult.retryable`) — a `FileNotFoundError` is not retried 3x
  with the same doomed params
- `RunProfile` resolution from `--thinking-level` / `--reasoning-effort`
  / `--max-steps`, plus `model.max_tokens_per_call` as a hard per-call cap
- `indra serve`: standalone long-lived API process so llama.cpp loads
  the model once, not on every CLI invocation; `api.base_url` in config
  (or `INDRA_API_URL`) points the CLI at it
- FastAPI app (workspaces/sessions/tasks/memory/logs/tools/info) + a CLI
  that talks to it — running `indra` with no arguments drops straight
  into an interactive chat REPL with a live startup banner (real tool
  count, workspace list, and model config, not placeholders), a
  "thinking..." spinner with elapsed time while waiting on the model
  (see note on streaming below), and a stats footer per response
  (calls / tokens / llm time / agent overhead / total time / tok-per-sec)
- 118 passing unit/integration tests

**On token streaming:** every model response in Indra must be valid,
often grammar-constrained JSON (a tool call or a plan) — that's the
core reliability mechanism for small models. Streaming raw tokens would
mean showing a user a partially-formed JSON object, not readable
prose, so it isn't implemented as naive token streaming. The spinner +
per-call timing above is the practical alternative; a dedicated
freeform-chat mode that bypasses the JSON schema for plain Q&A (trading
some structure for true streaming) is a possible future addition, not
yet built.

**Not yet implemented** (see `PLAN.md` §19 for the full roadmap):
repository indexing (tree-sitter symbol/import graphs), test/build
tools, Telegram bridge, hardware/model auto-tuning, plugin discovery
wiring, patch/diff-based editing. These are scaffolded as empty
packages where the design doc places them (`coding/`,
`integrations/telegram/`, `plugins/`) and are the next slice of work.

## Quickstart

```bash
pip install -e .
indra            # interactive REPL (mock backend, no model needed)
```

Or step by step:

```bash
indra doctor                                  # sanity check
indra workspace create demo --path ./my-project --default
indra run "create a file named notes.txt with some text" --workspace demo --thinking-level low
```

By default `model.backend: mock` in `indra.config.yaml`, so the whole
loop (planning, tool selection, file writes, persistence) runs with
zero model downloads — useful for development and for the test suite.

To use a real local model:

```yaml
# indra.config.yaml
model:
  backend: llama_cpp
  model_path: "/path/to/your-model.Q4_K_M.gguf"
  context_size: 4096
  max_tokens_per_call: 1024
  gpu_layers: 40
  temperature: 0.0
```

```bash
pip install -e ".[llama-cpp]"
indra doctor
indra            # or: indra run "your task" --workspace demo
```

### Recommended for llama.cpp: run the server separately

Each CLI invocation is its own process — without a standalone server,
`model.backend: llama_cpp` reloads the entire GGUF model from disk on
*every single command*, which is most of the latency you'll see.
Instead, run the API once and point the CLI at it:

```bash
# terminal 1 -- starts once, loads the model once, stays warm
indra serve

# indra.config.yaml
api:
  base_url: "http://127.0.0.1:8420"
```

```bash
# terminal 2 (or any other machine on your network)
indra run "your task" --workspace demo
```

`indra doctor` reports which mode you're in (`api.base_url`/
`INDRA_API_URL` set → remote server; unset → in-process, fine for the
`mock` backend but not recommended for `llama_cpp`).

## Development

```bash
pip install -e ".[dev]"
pytest -q
```

## License

This project is free for personal, educational, and research use.

Commercial use is prohibited without prior written permission.

See the LICENSE file for details.
