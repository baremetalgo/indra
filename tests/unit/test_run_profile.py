from __future__ import annotations

import pytest

from indra.config.schema import AgentConfig
from indra.core.run_profile import resolve_run_profile


def test_default_profile_is_medium() -> None:
    profile = resolve_run_profile(AgentConfig())
    assert profile.thinking_level == "medium"


def test_low_thinking_level_disables_replanning() -> None:
    profile = resolve_run_profile(AgentConfig(), thinking_level="low")
    assert profile.max_replan_attempts == 0


def test_high_effort_increases_call_budget_over_low_effort() -> None:
    low_effort = resolve_run_profile(AgentConfig(), thinking_level="medium", reasoning_effort=0)
    high_effort = resolve_run_profile(AgentConfig(), thinking_level="medium", reasoning_effort=100)
    assert high_effort.max_llm_calls > low_effort.max_llm_calls
    assert high_effort.memory_top_k > low_effort.memory_top_k


def test_call_budget_never_exceeds_complex_cap() -> None:
    base = AgentConfig(max_llm_calls_complex=5)
    profile = resolve_run_profile(base, thinking_level="high", reasoning_effort=100)
    assert profile.max_llm_calls <= base.max_llm_calls_complex


def test_max_steps_override_takes_precedence_over_config_default() -> None:
    profile = resolve_run_profile(AgentConfig(max_steps=40), max_steps=5)
    assert profile.max_steps == 5


def test_unknown_thinking_level_rejected() -> None:
    with pytest.raises(ValueError):
        resolve_run_profile(AgentConfig(), thinking_level="extreme")
