"""FastAPI app factory.

The CLI talks to this app over HTTP rather than importing ``core``
directly — keeping the CLI a thin client per the design's
"CLI communicates through the API" rule.
"""

from __future__ import annotations

from fastapi import FastAPI

from indra.api.routes import logs, memory, sessions, tasks, tools, workspaces


def create_app() -> FastAPI:
    app = FastAPI(title="Indra API", version="0.1.0")
    app.include_router(workspaces.router)
    app.include_router(sessions.router)
    app.include_router(tasks.router)
    app.include_router(memory.router)
    app.include_router(logs.router)
    app.include_router(tools.router)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
