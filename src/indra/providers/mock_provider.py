"""Deterministic mock provider.

Returns canned, schema-valid JSON instead of calling any real model.
Used in unit/integration tests and for `--backend mock` runs so the
whole agent loop can be exercised without a GGUF model loaded — this is
exactly the "mock ModelProvider" integration-testing pattern from the
design doc (§21).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from indra.providers.base import CompletionRequest, CompletionResponse


def _estimate_tokens(text: str) -> int:
    """Cheap, deterministic token estimate (~4 chars/token) — no tokenizer dep."""
    return max(1, len(text) // 4)


@dataclass
class MockProvider:
    """Replays a queue of canned responses, one per ``complete()`` call.

    If the queue is empty, falls back to a tiny default plan/ack so the
    provider never raises on unexpected extra calls during development.
    """

    responses: deque[str] = field(default_factory=deque)

    def queue(self, response_text: str) -> "MockProvider":
        self.responses.append(response_text)
        return self

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        text = self.responses.popleft() if self.responses else self._default_for(request)
        return CompletionResponse(
            text=text,
            prompt_tokens=_estimate_tokens(request.prompt),
            completion_tokens=_estimate_tokens(text),
            raw={"mock": True},
        )

    def is_available(self) -> bool:
        return True

    @staticmethod
    def _default_for(request: CompletionRequest) -> str:
        if request.json_schema is not None:
            return '{"goal": "unspecified", "subtasks": [{"description": "noop"}]}'
        return "ok"
