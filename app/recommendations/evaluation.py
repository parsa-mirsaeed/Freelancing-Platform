from __future__ import annotations

import math
from collections.abc import Sequence


def precision_at_k(ranked_ids: Sequence[str], relevant_ids: set[str], k: int) -> float:
    if k <= 0:
        raise ValueError("k must be positive")
    selected = ranked_ids[:k]
    if not selected:
        return 0.0
    return sum(item in relevant_ids for item in selected) / len(selected)


def recall_at_k(ranked_ids: Sequence[str], relevant_ids: set[str], k: int) -> float:
    if k <= 0:
        raise ValueError("k must be positive")
    if not relevant_ids:
        return 0.0
    selected = ranked_ids[:k]
    return sum(item in relevant_ids for item in selected) / len(relevant_ids)


def ndcg_at_k(ranked_ids: Sequence[str], relevance: dict[str, float], k: int) -> float:
    if k <= 0:
        raise ValueError("k must be positive")
    gains = [max(0.0, float(relevance.get(item, 0.0))) for item in ranked_ids[:k]]
    dcg = _dcg(gains)
    ideal = _dcg(sorted((max(0.0, float(value)) for value in relevance.values()), reverse=True)[:k])
    if ideal == 0:
        return 0.0
    return dcg / ideal


def conversion_at_k(ranked_ids: Sequence[str], converted_ids: set[str], k: int) -> float:
    return precision_at_k(ranked_ids, converted_ids, k)


def _dcg(gains: Sequence[float]) -> float:
    return sum(gain / math.log2(index + 2) for index, gain in enumerate(gains))
