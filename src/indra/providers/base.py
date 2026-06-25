"""Model provider protocol.

Every backend (llama.cpp, Ollama, OpenAI-compatible, vLLM, LM Studio,
or the deterministic mock used in tests) implements this same
interface, so the rest of Indra never talks to a backend-specific
client directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class CompletionRequest:
    prompt: str
    max_tokens: int
    temperature: float = 0.0
    json_schema: dict[str, Any] | None = None
    stop: tuple[str, ...] = ()


@dataclass(frozen=True)
class CompletionResponse:
    text: str
    prompt_tokens: int
    completion_tokens: int
    raw: dict[str, Any] = None  # type: ignore[assignment]


class ModelProvider(Protocol):
    def complete(self, request: CompletionRequest) -> CompletionResponse: ...

    def is_available(self) -> bool: ...
