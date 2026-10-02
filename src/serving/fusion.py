# fusion.py — weighted Reciprocal Rank Fusion + deterministic tie-break (pure).
# Spec: specs/recommendation-api/spec.md "Rank-based fusion and deterministic ordering".
# Design: design.md D-8. No I/O: callers pass already-fetched, per-source ranked lists.
from __future__ import annotations

from typing import Iterable, Mapping

from .models import Candidate


def rank_candidates(
    items: Iterable[tuple[int, float, int]],
) -> list[Candidate]:
    """Turn (movie_id, raw_score, support) tuples into a ranked Candidate list.

    Sort key: raw_score desc, then support desc, then movie_id asc — this is the
    tie-break rule design.md D-8 specifies for content-similarity ties (e.g. many
    movies sharing cosine score 1.0, MODEL_DESIGN.md §4). Rank is assigned 1..n
    after sorting, so it is always consistent with the tie-break order.
    """
    ordered = sorted(items, key=lambda t: (-t[1], -t[2], t[0]))
    return [
        Candidate(movie_id=movie_id, rank=i + 1, support=support, score=raw_score)
        for i, (movie_id, raw_score, support) in enumerate(ordered)
    ]


def weighted_rrf(
    sources: Mapping[str, list[Candidate]],
    weights: Mapping[str, float],
    rrf_k: int,
    support_lookup: Mapping[int, int] | None = None,
) -> list[Candidate]:
    """Weighted Reciprocal Rank Fusion (design.md D-8):

        score(m) = sum_s  weight_s / (rrf_k + rank_s(m))

    A candidate present in multiple sources gets the sum of each source's
    contribution. Final ordering: fused score desc, then support desc
    (from `support_lookup`, defaulting to 0), then movie_id asc — deterministic
    for identical inputs (spec: "Determinism" scenario).
    """
    support_lookup = support_lookup or {}
    fused_scores: dict[int, float] = {}
    for source_name, ranked in sources.items():
        weight = weights.get(source_name, 0.0)
        if weight <= 0:
            continue
        for candidate in ranked:
            contribution = weight / (rrf_k + candidate.rank)
            fused_scores[candidate.movie_id] = fused_scores.get(candidate.movie_id, 0.0) + contribution

    ordered_ids = sorted(
        fused_scores.keys(),
        key=lambda mid: (-fused_scores[mid], -support_lookup.get(mid, 0), mid),
    )
    return [
        Candidate(
            movie_id=mid,
            rank=i + 1,
            support=support_lookup.get(mid, 0),
            score=fused_scores[mid],
        )
        for i, mid in enumerate(ordered_ids)
    ]


def fill_from_popularity(
    fused: list[Candidate],
    popularity_ranked: list[Candidate],
    k: int,
    exclude_ids: frozenset[int] = frozenset(),
) -> tuple[list[Candidate], bool]:
    """Pad `fused` up to `k` items using the popularity list (spec: "Not enough
    candidates"), skipping ids already present in `fused` or in `exclude_ids`
    (already-rated). Returns (final_list_truncated_to_k, was_filled).
    """
    if len(fused) >= k:
        return fused[:k], False

    have = {c.movie_id for c in fused} | exclude_ids
    result = list(fused)
    next_rank = len(result) + 1
    filled_any = False
    for candidate in popularity_ranked:
        if len(result) >= k:
            break
        if candidate.movie_id in have:
            continue
        result.append(
            Candidate(
                movie_id=candidate.movie_id,
                rank=next_rank,
                support=candidate.support,
                score=candidate.score,
            )
        )
        have.add(candidate.movie_id)
        next_rank += 1
        filled_any = True

    return result[:k], filled_any
