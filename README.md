<h1 align="center"> Indra</h1>
<h3 align="center"> Agentic Harness</h3>
<p align="center">
  <img src="indra_logo.png" width="50%">
</p>
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
- Structured JSON logging + per-task LLM call budget tracking
- Workspace sandboxing (path-containment enforced centrally, symlink-safe)
- Tool registry + file tools (read/write/list/delete) + an `answer` tool
  for question/explanation subtasks that don't need a file/shell action,
  all schema-validated
- Model provider abstraction: `mock` (default, no model needed) and
  `llama_cpp` (grammar-constrained JSON decoding)
- Planner → Executor → Agent loop with bounded re-planning (the planner
  is told *why* the previous attempt failed, so re-planning picks a
  different approach instead of repeating it) and a hard `max_steps`
  safety valve — never crashes on bad/unparseable model output
- Tool retries distinguish transient vs. deterministic failures
  (`ToolResult.retryable`) — a `FileNotFoundError` is not retried 3x
  with the same doomed params
- Working/long-term memory with deterministic (non-LLM) relevance
  scoring, deduplication, and token-budgeted retrieval
- `RunProfile` resolution from `--thinking-level` / `--reasoning-effort`
  / `--max-steps`, plus `model.max_tokens_per_call` as a hard per-call cap
- FastAPI app (workspaces/sessions/tasks/memory/logs) + a CLI that talks
  to it — running `indra` with no arguments drops straight into an
  interactive chat REPL (Claude-Code style); `indra run` remains for
  one-shot/scripted use
- 51 passing unit/integration tests

**Not yet implemented** (see `PLAN.md` §19 for the full roadmap):
repository indexing (tree-sitter symbol/import graphs), git/shell/test/
build tools, web search tooling, Telegram bridge, hardware/model
auto-tuning, plugin discovery wiring, patch/diff-based editing. These
are scaffolded as empty packages where the design doc places them
(`coding/`, `integrations/telegram/`, `plugins/`) and are the next
slice of work.

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
