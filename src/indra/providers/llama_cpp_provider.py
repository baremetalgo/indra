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
    gpu_layers: int = 20
    flash_attn: bool = False

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

        base_kwargs: dict = {
            "model_path": self.model_path,
            "n_ctx": self.context_size,
            "n_gpu_layers": self.gpu_layers,
            "verbose": False,
        }
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
            self._llm = Llama(**base_kwargs)

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
        except LlamaCppNotInstalledError:
            return False


def _to_json_str(schema: dict) -> str:
    import json

    return json.dumps(schema)
