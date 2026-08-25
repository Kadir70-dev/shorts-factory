"""Tests for the semantic asset-ranking module (OpenMontage-audit gap #1).

`clip_rank.py`'s network/model-touching functions (`embed_text`,
`embed_image_path`, `rank_async`) need torch/transformers and, for the image
path, a real model download — not something to depend on for a fast unit
suite. What IS unit-testable without any of that is the actual ranking
MATH: `score_candidates` takes pre-computed vectors and does pure numpy, so
these tests build synthetic embeddings and check the scoring/ordering
contract directly. `available()`/`rank_async()` degrade-to-empty behavior is
also covered without requiring the real deps to be installed.
"""
from __future__ import annotations

import numpy as np
import pytest

from app.pipeline import clip_rank


def _unit(vec: list[float]) -> np.ndarray:
    arr = np.asarray(vec, dtype=np.float32)
    return arr / np.linalg.norm(arr)


class _Cand:
    """Minimal stand-in for providers.RankCandidate in these tests."""
    def __init__(self, name: str):
        self.name = name

    def __repr__(self):
        return f"Cand({self.name})"


def test_cosine_of_identical_vectors_is_one():
    v = _unit([1.0, 2.0, 3.0])
    assert clip_rank.cosine(v, v) == pytest.approx(1.0, abs=1e-5)


def test_cosine_none_is_zero_not_a_crash():
    assert clip_rank.cosine(None, _unit([1.0, 0.0])) == 0.0
    assert clip_rank.cosine(_unit([1.0, 0.0]), None) == 0.0


def test_higher_relevance_ranks_first():
    text_vec = _unit([1.0, 0.0, 0.0])
    close = _unit([0.9, 0.1, 0.0])       # near the query
    far = _unit([0.0, 1.0, 0.0])         # orthogonal to the query
    a, b = _Cand("close"), _Cand("far")
    triples = [(b, far, "image"), (a, close, "image")]  # deliberately out of order

    ranked = clip_rank.score_candidates(triples, text_vec)

    assert [rc.candidate.name for rc in ranked] == ["close", "far"]
    assert ranked[0].relevance > ranked[1].relevance


def test_unranked_candidate_scores_zero_relevance_not_excluded():
    text_vec = _unit([1.0, 0.0])
    triples = [(_Cand("no-thumb"), None, "unranked"),
              (_Cand("has-thumb"), _unit([0.1, 0.99]), "image")]

    ranked = clip_rank.score_candidates(triples, text_vec)

    # Still present (never silently dropped) with relevance 0, not crashed.
    names = {rc.candidate.name: rc.relevance for rc in ranked}
    assert names["no-thumb"] == 0.0
    assert len(ranked) == 2


def test_diversity_penalty_demotes_a_near_duplicate_of_something_selected():
    text_vec = _unit([1.0, 0.0, 0.0])
    # Both candidates are EQUALLY relevant to the query...
    twin_a = _unit([0.8, 0.6, 0.0])
    twin_b = _unit([0.8, 0.6, 0.01])     # ...and near-identical to twin_a
    distinct = _unit([0.75, 0.0, 0.66])  # similarly relevant, visually different

    already_selected = [twin_a]
    triples = [(_Cand("twin_b"), twin_b, "image"),
              (_Cand("distinct"), distinct, "image")]

    ranked = clip_rank.score_candidates(triples, text_vec, selected=already_selected,
                                        diversity_weight=0.5)

    # twin_b has higher raw relevance to the query than `distinct`, but its
    # similarity to something already selected must cost it the top spot.
    assert ranked[0].relevance < ranked[1].relevance  # sanity: distinct is NOT more relevant
    assert ranked[0].candidate.name == "distinct"


def test_zero_diversity_weight_ignores_selected_entirely():
    text_vec = _unit([1.0, 0.0])
    same_as_selected = _unit([1.0, 0.0])
    triples = [(_Cand("dup"), same_as_selected, "image")]

    ranked = clip_rank.score_candidates(
        triples, text_vec, selected=[same_as_selected], diversity_weight=0.0)

    assert ranked[0].score == pytest.approx(ranked[0].relevance, abs=1e-6)


def test_is_near_duplicate_threshold():
    a = _unit([1.0, 0.0])
    almost_same = _unit([0.99, 0.05])
    different = _unit([0.0, 1.0])
    assert clip_rank.is_near_duplicate(a, almost_same) is True
    assert clip_rank.is_near_duplicate(a, different) is False
    assert clip_rank.is_near_duplicate(a, None) is False


def test_available_is_cached_and_boolean():
    result = clip_rank.available()
    assert isinstance(result, bool)
    # Second call must not re-import — just re-read the cached flag.
    assert clip_rank.available() == result


@pytest.mark.asyncio
async def test_rank_async_returns_empty_list_for_no_candidates():
    assert await clip_rank.rank_async([], "a query") == []


@pytest.mark.asyncio
async def test_rank_async_empty_when_unavailable(monkeypatch):
    monkeypatch.setattr(clip_rank, "available", lambda: False)
    result = await clip_rank.rank_async([_Cand("x")], "a query")
    assert result == []
