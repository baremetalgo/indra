from __future__ import annotations

from unittest import mock

from indra.cli.main import _TITLE_ART, _print_banner


def test_title_art_is_pure_ascii() -> None:
    """The whole point of hand-picking this font: no Unicode glyphs that
    could trip the Windows console issue described elsewhere in this
    module. Every character must be plain ASCII."""
    _TITLE_ART.encode("ascii")  # raises UnicodeEncodeError if not


def test_print_banner_does_not_raise_when_endpoints_are_unreachable() -> None:
    """The banner must degrade gracefully -- a remote server being slow
    or down should never prevent the REPL from starting."""
    client = mock.Mock()
    client.get.side_effect = Exception("connection refused")
    _print_banner(client, "demo", "medium")  # must not raise


def test_print_banner_uses_live_data(capsys) -> None:
    client = mock.Mock()

    def fake_get(path, **kwargs):
        resp = mock.Mock()
        if path == "/info":
            resp.json.return_value = {
                "backend": "llama_cpp",
                "model_path": "D:\\models\\gemma.gguf",
                "context_size": 8192,
                "gpu_layers": 40,
                "flash_attn": True,
                "max_steps": 40,
            }
        elif path == "/tools":
            resp.json.return_value = [{"name": "git_status"}, {"name": "answer"}]
        elif path == "/workspaces":
            resp.json.return_value = [{"name": "demo"}, {"name": "other"}]
        return resp

    client.get.side_effect = fake_get
    _print_banner(client, "demo", "high")
    out = capsys.readouterr().out
    assert "gemma.gguf" in out
    assert "8192" in out
    assert "git_status" in out
    assert "other" in out
