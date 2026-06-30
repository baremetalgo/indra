from __future__ import annotations

from unittest import mock

import pytest

from indra.providers.llama_cpp_provider import (
    LlamaCppLoadError,
    LlamaCppProvider,
    gpu_offload_supported,
)


def test_gpu_offload_supported_returns_none_when_llama_cpp_not_installed() -> None:
    with mock.patch.dict("sys.modules", {"llama_cpp": None}):
        assert gpu_offload_supported() is None


def test_gpu_offload_supported_returns_true_when_backend_reports_true() -> None:
    fake_module = mock.Mock()
    fake_module.llama_supports_gpu_offload.return_value = True
    with mock.patch.dict("sys.modules", {"llama_cpp": fake_module}):
        assert gpu_offload_supported() is True


def test_gpu_offload_supported_returns_false_when_backend_reports_false() -> None:
    fake_module = mock.Mock()
    fake_module.llama_supports_gpu_offload.return_value = False
    with mock.patch.dict("sys.modules", {"llama_cpp": fake_module}):
        assert gpu_offload_supported() is False


def test_gpu_offload_supported_returns_none_on_missing_attribute() -> None:
    fake_module = mock.Mock(spec=[])  # no llama_supports_gpu_offload attribute at all
    with mock.patch.dict("sys.modules", {"llama_cpp": fake_module}):
        assert gpu_offload_supported() is None


def test_flash_attn_kwarg_falls_back_gracefully_on_older_bindings() -> None:
    """Simulates an installed llama-cpp-python that predates flash_attn=."""
    call_log: list[dict] = []

    def fake_llama(**kwargs):
        call_log.append(kwargs)
        if "flash_attn" in kwargs:
            raise TypeError("Llama.__init__() got an unexpected keyword argument 'flash_attn'")
        return mock.Mock()

    fake_module = mock.Mock()
    fake_module.Llama = fake_llama

    provider = LlamaCppProvider(model_path="fake.gguf", flash_attn=True)
    with mock.patch.dict("sys.modules", {"llama_cpp": fake_module}):
        provider._ensure_loaded()

    assert len(call_log) == 2  # first attempt with flash_attn, then without
    assert "flash_attn" in call_log[0]
    assert "flash_attn" not in call_log[1]
    assert provider._llm is not None


def test_native_library_load_failure_raises_an_actionable_error() -> None:
    """Reproduces a real reported failure: llama-cpp-python is installed
    (the Python package imports) but its native shared library fails to
    load (OSError: Could not find module 'llama.dll' ...). This must
    surface as a clear, actionable LlamaCppLoadError, not a raw OSError
    with no guidance.
    """
    fake_module = mock.Mock()
    fake_module.Llama = mock.Mock(
        side_effect=OSError(
            "Failed to load shared library 'llama.dll': Could not find module"
        )
    )

    provider = LlamaCppProvider(model_path="fake.gguf")
    with mock.patch.dict("sys.modules", {"llama_cpp": fake_module}):
        with pytest.raises(LlamaCppLoadError) as exc_info:
            provider._ensure_loaded()

    message = str(exc_info.value)
    assert "native library failed to load" in message
    assert "force-reinstall" in message


def test_native_library_load_failure_after_flash_attn_typeerror_also_actionable() -> None:
    """Same failure mode, but only surfacing on the fallback call after a
    flash_attn TypeError -- both code paths must produce the same
    actionable error, not let the OSError escape raw.
    """
    fake_module = mock.Mock()

    def fake_llama(**kwargs):
        if "flash_attn" in kwargs:
            raise TypeError("unexpected keyword argument 'flash_attn'")
        raise OSError("Could not find module 'llama.dll'")

    fake_module.Llama = fake_llama

    provider = LlamaCppProvider(model_path="fake.gguf", flash_attn=True)
    with mock.patch.dict("sys.modules", {"llama_cpp": fake_module}):
        with pytest.raises(LlamaCppLoadError):
            provider._ensure_loaded()


def test_is_available_returns_false_on_load_error_without_raising() -> None:
    fake_module = mock.Mock()
    fake_module.Llama = mock.Mock(side_effect=OSError("Could not find module 'llama.dll'"))

    provider = LlamaCppProvider(model_path="fake.gguf")
    with mock.patch.dict("sys.modules", {"llama_cpp": fake_module}):
        assert provider.is_available() is False
