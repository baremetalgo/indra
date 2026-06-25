"""Deterministic memory compression and relevance scoring.

Relevance is recency x a small kind-weight, computed without an LLM
call — keeping memory retrieval itself off the token budget. Token
budgeting is a crude char-based estimate (~4 chars/token), good enough
to keep prompts within the target ceiling without a tokenizer
dependency.
"""

from __future__ import annotations

from datetime import datetime, timezone

from indra.schemas.memory import MemoryItem

_KIND_WEIGHT = {
    "decision": 1.0,
    "preference": 0.9,
    "fact": 0.7,
    "tool_usage": 0.5,
    "summary": 0.6,
}


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def score_relevance(item: MemoryItem, now: datetime | None = None) -> float:
    now = now or datetime.now(timezone.utc)
    age_hours = max(0.0, (now - item.created_at).total_seconds() / 3600)
    recency = 1.0 / (1.0 + age_hours / 24)  # halves roughly every day
    weight = _KIND_WEIGHT.get(item.kind, 0.5)
    return round(recency * weight, 4)


def rank_and_truncate(items: list[MemoryItem], max_tokens: int) -> list[MemoryItem]:
    """Rank by relevance descending, then take items until the budget fills."""
    ranked = sorted(items, key=lambda i: i.relevance, reverse=True)
    selected: list[MemoryItem] = []
    used = 0
    for item in ranked:
        cost = estimate_tokens(item.content)
        if used + cost > max_tokens:
            continue
        selected.append(item)
        used += cost
    return selected


def deduplicate(items: list[MemoryItem]) -> list[MemoryItem]:
    """Drop items whose content exactly repeats an earlier (higher-relevance) one."""
    seen: set[str] = set()
    result: list[MemoryItem] = []
    for item in sorted(items, key=lambda i: i.relevance, reverse=True):
        key = item.content.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result
