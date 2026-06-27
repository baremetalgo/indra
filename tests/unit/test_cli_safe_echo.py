from __future__ import annotations

import time
from unittest import mock

import typer

from indra.cli.main import _safe_echo, _safe_prompt


def test_safe_echo_falls_back_when_click_echo_raises_oserror(capsys) -> None:
    """Reproduces the real-world Windows bug: Click's console writer can
    raise OSError('Windows error: 6') after a native library (llama.cpp)
    has touched the console. _safe_echo must still get the text out
    instead of crashing the whole CLI command.
    """
    with mock.patch("typer.echo", side_effect=OSError("Windows error: 6")):
        _safe_echo("hello from a broken console")
    captured = capsys.readouterr()
    assert "hello from a broken console" in captured.out


def test_safe_echo_falls_back_for_colored_output(capsys) -> None:
    with mock.patch("typer.secho", side_effect=OSError("Windows error: 6")):
        _safe_echo("colored line", fg=typer.colors.GREEN)
    captured = capsys.readouterr()
    assert "colored line" in captured.out


def test_safe_echo_does_not_raise_even_if_stdout_write_also_fails(capsys) -> None:
    with mock.patch("typer.echo", side_effect=OSError("boom")):
        with mock.patch("sys.stdout.write", side_effect=OSError("boom too")):
            with mock.patch("os.write") as os_write:
                _safe_echo("last resort path")
    os_write.assert_called_once()


def test_safe_prompt_falls_back_to_plain_input(monkeypatch) -> None:
    monkeypatch.setattr(typer, "prompt", mock.Mock(side_effect=OSError("Windows error: 6")))
    monkeypatch.setattr("builtins.input", lambda: "typed text")
    result = _safe_prompt("> ")
    assert result == "typed text"


def test_spinner_enter_exit_does_not_raise(capsys) -> None:
    from indra.cli.main import _Spinner

    with _Spinner("thinking"):
        time.sleep(0.05)
    # no exception means the background thread started and stopped cleanly


def test_spinner_survives_a_broken_stdout(monkeypatch) -> None:
    from indra.cli.main import _Spinner

    monkeypatch.setattr(
        "sys.stdout.write", mock.Mock(side_effect=OSError("Windows error: 6"))
    )
    with _Spinner("thinking"):
        time.sleep(0.05)
    # must not raise even though every write attempt fails
