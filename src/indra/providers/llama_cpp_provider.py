"""llama.cpp model provider — the primary target backend.

Wraps ``llama-cpp-python``. The dependency is optional (declared under
the ``llama-cpp`` extra in pyproject.toml) so the rest of Indra can be
installed and tested on machines without a compiled llama.cpp build;
importing this module without the extra installed raises a clear error
only when actually instantiated, not at package-import time.

IMPORTANT: ``pip install llama-cpp-python`` installs a CPU-only wheel
on most platforms. Setting ``gpu_layers`` > 0 does nothing useful
unless llama-cpp-python was built/installed with GPU support (CUDA on
Windows/Linux, Metal on macOS) -- see ``gpu_offload_supported()``
below and ``indra doctor``, which calls it.
"""

from __future__ import annotations

from dataclasses import dataclass

from indra.observability.logging import get_logger
from indra.providers.base import CompletionRequest, CompletionResponse

_logger = get_logger("providers.llama_cpp")


class LlamaCppNotInstalledError(ImportError):
    """Raised when LlamaCppProvider is used without the llama-cpp extra."""


class LlamaCppLoadError(RuntimeError):
    """Raised when llama-cpp-python is installed but its native library
    (llama.dll / libllama.so / libllama.dylib) failed to load.

    This is a different, more urgent problem than "no GPU offload": it
    means *no* inference works, CPU or GPU. The most common cause on
    Windows is a CUDA-enabled wheel whose required NVIDIA CUDA runtime
    DLLs (cudart64_*.dll, cublas64_*.dll) aren't on PATH.
    """


def gpu_offload_supported() -> bool | None:
    """Best-effort check of whether the installed llama-cpp-python build
    actually supports GPU offload, independent of any model being loaded.

    Returns True/False if llama.cpp's own C API answers definitively,
    or None if the installed version doesn't expose a way to ask (in
    which case the caller should say "unknown", not "no").
    """
    try:
        import llama_cpp

        return bool(llama_cpp.llama_supports_gpu_offload())
    except ImportError:
        return None
    except AttributeError:
        return None  # older/newer binding without this function
    except Exception:  # noqa: BLE001 - this is a best-effort diagnostic only
        return None


@dataclass
class LlamaCppProvider:
    model_path: str
    context_size: int = 4096
    gpu_layers: int = -1
    flash_attn: bool = False
    n_threads: int | None = None
    """None lets llama-cpp-python pick its own default (typically CPU
    count). Set explicitly if you suspect it's under-using your CPU."""
    n_batch: int = 512
    """llama.cpp's prompt-processing batch size. The library default
    (512) is usually fine; raising it can speed up prompt ingestion on
    GPU at the cost of more VRAM."""

    def __post_init__(self) -> None:
        self._llm = None  # lazy-loaded on first complete() call

    def _ensure_loaded(self) -> None:
        if self._llm is not None:
            return
        try:
            from llama_cpp import Llama
        except ImportError as exc:
            raise LlamaCppNotInstalledError(
                "llama-cpp-python is not installed. Install with: "
                "pip install 'indra[llama-cpp]'"
            ) from exc

        _logger.info(
            "llama_cpp_loading",
            extra={"indra_extra": {
                "model_path": self.model_path,
                "n_ctx": self.context_size,
                "n_gpu_layers": self.gpu_layers,
                "n_batch": self.n_batch,
                "n_threads": self.n_threads,
                "gpu_offload_supported_by_build": gpu_offload_supported(),
            }},
        )

        base_kwargs: dict = {
            "model_path": self.model_path,
            "n_ctx": self.context_size,
            "n_gpu_layers": self.gpu_layers,
            "n_batch": self.n_batch,
            "verbose": False,
        }
        if self.n_threads is not None:
            base_kwargs["n_threads"] = self.n_threads
        try:
            self._llm = Llama(**base_kwargs, flash_attn=self.flash_attn)
        except TypeError:
            # Installed llama-cpp-python version predates the flash_attn
            # kwarg -- degrade gracefully rather than crash on load.
            if self.flash_attn:
                _logger.warning(
                    "flash_attn_unsupported",
                    extra={"indra_extra": {
                        "note": "installed llama-cpp-python does not accept "
                                "flash_attn=; ignoring and loading without it",
                    }},
                )
            try:
                self._llm = Llama(**base_kwargs)
            except OSError as exc:
                raise self._actionable_load_error(exc) from exc
        except OSError as exc:
            # The Python package imported fine, but its native shared
            # library (llama.dll / libllama.so) failed to load -- a
            # different, more urgent problem than "no GPU offload": it
            # means *no* inference works at all, CPU or GPU.
            raise self._actionable_load_error(exc) from exc

    def _actionable_load_error(self, exc: OSError) -> LlamaCppLoadError:
        return LlamaCppLoadError(
            f"llama-cpp-python's native library failed to load: {exc}\n"
            "This means the Python package is installed but its compiled "
            "backend isn't loadable -- no inference will work, CPU or GPU, "
            "until this is fixed. Common causes on Windows:\n"
            "  1. A CUDA-enabled wheel whose required NVIDIA CUDA runtime "
            "DLLs (cudart64_*.dll, cublas64_*.dll) aren't on PATH -- "
            "install the matching CUDA toolkit version, or use a wheel "
            "that bundles its own runtime.\n"
            "  2. A mismatched/corrupted install -- try: "
            "pip uninstall llama-cpp-python && "
            "pip install llama-cpp-python --no-cache-dir --force-reinstall\n"
            "See https://github.com/abetlen/llama-cpp-python#installation "
            "for platform-specific prebuilt wheels (including CUDA)."
        )

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        self._ensure_loaded()
        kwargs: dict = {
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "stop": list(request.stop) or None,
        }
        if request.json_schema is not None:
            # Grammar-constrained decoding: convert the JSON schema to a
            # GBNF grammar so structured output is enforced at decode
            # time, not just validated after the fact.
            from llama_cpp import LlamaGrammar

            grammar = LlamaGrammar.from_json_schema(_to_json_str(request.json_schema))
            kwargs["grammar"] = grammar

        result = self._llm(request.prompt, **kwargs)  # type: ignore[misc]
        choice = result["choices"][0]
        usage = result.get("usage", {})
        return CompletionResponse(
            text=choice["text"],
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            raw=result,
        )

    def is_available(self) -> bool:
        try:
            self._ensure_loaded()
            return True
        except (LlamaCppNotInstalledError, LlamaCppLoadError):
            return False


def _to_json_str(schema: dict) -> str:
    import json

    return json.dumps(schema)
