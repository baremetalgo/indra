"""Resolves CLI knobs (thinking level / reasoning effort / max steps)
into a concrete, bounded :class:`RunProfile`.

These never change prompt wording — only the deterministic budgets the
agent loop runs under — so behavior stays explainable and reproducible
from the stored profile alone.
"""

from __future__ import annotations

from dataclasses import dataclass

from indra.config.schema import AgentConfig

THINKING_LEVEL_PRESETS: dict[str, dict[str, float]] = {
    "low": {"max_llm_calls": 3, "max_replan_attempts": 0, "temperature": 0.0},
    "medium": {"max_llm_calls": 8, "max_replan_attempts": 1, "temperature": 0.1},
    "high": {"max_llm_calls": 15, "max_replan_attempts": 2, "temperature": 0.2},
}


@dataclass(frozen=True)
class RunProfile:
    thinking_level: str
    max_llm_calls: int
    max_replan_attempts: int
    temperature: float
    max_steps: int
    memory_top_k: int


def resolve_run_profile(
    base: AgentConfig,
    thinking_level: str | None = None,
    reasoning_effort: int | None = None,
    max_steps: int | None = None,
) -> RunProfile:
    level = thinking_level or "medium"
    if level not in THINKING_LEVEL_PRESETS:
        raise ValueError(
            f"Unknown thinking_level {level!r}; choose from "
            f"{sorted(THINKING_LEVEL_PRESETS)}"
        )
    preset = THINKING_LEVEL_PRESETS[level]

    effort = (reasoning_effort if reasoning_effort is not None else 50) / 100
    calls = min(
        base.max_llm_calls_complex,
        max(1, round(preset["max_llm_calls"] * (0.5 + effort))),
    )

    return RunProfile(
        thinking_level=level,
        max_llm_calls=calls,
        max_replan_attempts=int(preset["max_replan_attempts"]),
        temperature=preset["temperature"],
        max_steps=max_steps or base.max_steps,
        memory_top_k=max(2, round(5 * (0.5 + effort))),
    )
