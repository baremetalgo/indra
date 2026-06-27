from __future__ import annotations

from unittest import mock

from indra.providers.llama_cpp_provider import LlamaCppProvider, gpu_offload_supported


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
