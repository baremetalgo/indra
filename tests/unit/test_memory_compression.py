from __future__ import annotations

from datetime import datetime, timedelta, timezone

from indra.memory.compression import (
    deduplicate,
    estimate_tokens,
    rank_and_truncate,
    score_relevance,
)
from indra.schemas.memory import MemoryItem


def _item(content: str, kind: str = "fact", age_hours: float = 0.0) -> MemoryItem:
    created = datetime.now(timezone.utc) - timedelta(hours=age_hours)
    item = MemoryItem(id=content, scope="long_term", kind=kind, content=content, created_at=created)
    return MemoryItem(**{**item.__dict__, "relevance": score_relevance(item)})


def test_recent_items_score_higher_than_old() -> None:
    recent = _item("recent fact", age_hours=0)
    old = _item("old fact", age_hours=240)
    assert recent.relevance > old.relevance


def test_decision_kind_weighted_above_tool_usage() -> None:
    decision = _item("made a decision", kind="decision")
    tool_usage = _item("used a tool", kind="tool_usage")
    assert decision.relevance > tool_usage.relevance


def test_rank_and_truncate_respects_token_budget() -> None:
    items = [_item(f"fact number {i} padding padding padding") for i in range(20)]
    budget = 40
    selected = rank_and_truncate(items, max_tokens=budget)
    total = sum(estimate_tokens(i.content) for i in selected)
    assert total <= budget
    assert len(selected) < len(items)


def test_deduplicate_drops_exact_repeats_keeping_higher_relevance() -> None:
    high = _item("same content", age_hours=0)
    low = _item("same content", age_hours=100)
    result = deduplicate([low, high])
    assert len(result) == 1
    assert result[0].relevance == high.relevance
