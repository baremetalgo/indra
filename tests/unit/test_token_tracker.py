from __future__ import annotations

import time

from indra.observability.token_tracker import TokenTracker


def test_total_tokens_breakdown() -> None:
    tracker = TokenTracker(task_id="t1", max_calls=5)
    tracker.record("plan", prompt_tokens=100, completion_tokens=20, duration_seconds=1.0)
    tracker.record("execute", prompt_tokens=50, completion_tokens=10, duration_seconds=0.5)

    assert tracker.total_prompt_tokens() == 150
    assert tracker.total_completion_tokens() == 30
    assert tracker.total_tokens() == 180
    assert tracker.total_llm_seconds() == 1.5


def test_elapsed_seconds_tracks_wall_clock_since_creation() -> None:
    tracker = TokenTracker(task_id="t1", max_calls=5)
    time.sleep(0.05)
    assert tracker.elapsed_seconds() >= 0.05


def test_elapsed_seconds_can_exceed_llm_seconds_revealing_agent_overhead() -> None:
    tracker = TokenTracker(task_id="t1", max_calls=5)
    tracker.record("plan", prompt_tokens=10, completion_tokens=5, duration_seconds=0.01)
    time.sleep(0.05)  # simulates agent-loop overhead between calls
    assert tracker.elapsed_seconds() > tracker.total_llm_seconds()
