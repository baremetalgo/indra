"""Thin HTTP client shared by all CLI commands.

Defaults to talking to the FastAPI app in-process via an ASGI transport
(no server process required for `indra run`/`indra chat` etc.). Set
``INDRA_API_URL`` to point the CLI at a real running ``indra serve``
instance instead (e.g. for the Telegram bridge or remote use).
"""

from __future__ import annotations

import os
import warnings

import httpx


def get_client() -> httpx.Client:
    api_url = os.environ.get("INDRA_API_URL")
    if api_url:
        return httpx.Client(base_url=api_url, timeout=120.0)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from fastapi.testclient import TestClient

    from indra.api.app import app

    return TestClient(app, base_url="http://indra.local")  # type: ignore[return-value]
