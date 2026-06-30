from __future__ import annotations

import httpx
import pytest

from indra.cli.client import get_client


def test_env_var_takes_precedence_over_everything(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "indra.config.yaml").write_text(
        'api:\n  base_url: "http://example.invalid:1"\n'
    )
    monkeypatch.setenv("INDRA_API_URL", "http://127.0.0.1:9999")
    client = get_client()
    assert isinstance(client, httpx.Client)
    assert str(client.base_url) == "http://127.0.0.1:9999"
    client.close()


def test_config_base_url_used_when_no_env_var(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("INDRA_API_URL", raising=False)
    (tmp_path / "indra.config.yaml").write_text(
        'api:\n  base_url: "http://127.0.0.1:8420"\n'
    )
    client = get_client()
    assert str(client.base_url) == "http://127.0.0.1:8420"
    client.close()


def test_falls_back_to_in_process_when_nothing_configured(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("INDRA_API_URL", raising=False)
    # no indra.config.yaml at all in this tmp_path, and nothing
    # listening on the default discovery port for this test
    client = get_client()
    resp = client.get("/health")
    assert resp.status_code == 200
    client.close()


def test_discovers_a_running_server_without_explicit_config(monkeypatch, tmp_path) -> None:
    """Reproduces the requested workflow: `indra serve` in one terminal,
    bare `indra` in another, with no api.base_url set anywhere."""
    import threading

    import uvicorn

    from indra.api.app import app as real_app

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("INDRA_API_URL", raising=False)
    (tmp_path / "indra.config.yaml").write_text(
        "api:\n  host: 127.0.0.1\n  port: 18421\n"
    )

    config = uvicorn.Config(real_app, host="127.0.0.1", port=18421, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        for _ in range(50):
            if server.started:
                break
            import time

            time.sleep(0.05)

        client = get_client()
        assert str(client.base_url) == "http://127.0.0.1:18421"
        client.close()
    finally:
        server.should_exit = True
        thread.join(timeout=2.0)
