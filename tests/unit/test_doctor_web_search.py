from __future__ import annotations

from unittest import mock

import httpx

from indra.cli.main import doctor


def _run_doctor(path: str) -> str:
    import io
    import contextlib

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            doctor(path=path)
        except SystemExit:
            pass
    return buf.getvalue()


def test_doctor_reports_unreachable_web_search(tmp_path) -> None:
    config_path = tmp_path / "indra.config.yaml"
    config_path.write_text(
        'web_search:\n  base_url: "http://127.0.0.1:1"\n  fetch_timeout_seconds: 0.5\n'
    )
    output = _run_doctor(str(config_path))
    assert "web_search unreachable" in output
    assert "docker ps" in output


def test_doctor_reports_healthy_web_search_with_json_format(tmp_path) -> None:
    config_path = tmp_path / "indra.config.yaml"
    config_path.write_text('web_search:\n  base_url: "http://localhost:8088"\n')

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": []})

    with mock.patch("httpx.get", lambda url, **kw: httpx.Client(
        transport=httpx.MockTransport(handler)
    ).get(url, **{k: v for k, v in kw.items() if k != "timeout"})):
        output = _run_doctor(str(config_path))
    assert "web_search reachable" in output
    assert "json format enabled" in output


def test_doctor_warns_on_non_json_response(tmp_path) -> None:
    config_path = tmp_path / "indra.config.yaml"
    config_path.write_text('web_search:\n  base_url: "http://localhost:8088"\n')

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>not json</html>")

    with mock.patch("httpx.get", lambda url, **kw: httpx.Client(
        transport=httpx.MockTransport(handler)
    ).get(url, **{k: v for k, v in kw.items() if k != "timeout"})):
        output = _run_doctor(str(config_path))
    assert "not with JSON" in output
    assert "settings.yml" in output


def test_doctor_notes_unset_web_search_base_url(tmp_path) -> None:
    config_path = tmp_path / "indra.config.yaml"
    config_path.write_text('web_search:\n  base_url: ""\n')
    output = _run_doctor(str(config_path))
    assert "web_search.base_url not set" in output
