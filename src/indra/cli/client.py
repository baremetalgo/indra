"""Thin HTTP client shared by all CLI commands.

Resolution order for where the CLI talks to:
1. ``INDRA_API_URL`` env var — explicit override, always wins.
2. ``api.base_url`` in indra.config.yaml — the recommended setup for
   llama.cpp: run `indra serve` once in its own process (loads the GGUF
   model a single time) and point every CLI invocation at it here.
3. In-process ASGI app (via FastAPI's TestClient) — zero-setup fallback
   for `mock` backend / quick local trials. Each CLI invocation is its
   own process, so this mode reloads the model on every command if
   `model.backend: llama_cpp` is set; it exists for convenience, not
   for serious local-model use.
"""

from __future__ import annotations

import os
import warnings

import httpx


def get_client() -> httpx.Client:
    api_url = os.environ.get("INDRA_API_URL")
    if not api_url:
        api_url = _config_base_url()
    if api_url:
        return httpx.Client(base_url=api_url, timeout=120.0)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from fastapi.testclient import TestClient

    from indra.api.app import app

    return TestClient(app, base_url="http://indra.local")  # type: ignore[return-value]


def _config_base_url() -> str | None:
    try:
        from indra.config.loader import ConfigError, load_config

        config = load_config("indra.config.yaml")
    except ConfigError:
        return None
    return config.api.base_url or None
