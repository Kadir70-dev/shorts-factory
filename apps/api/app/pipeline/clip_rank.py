"""Semantic (CLIP-style) candidate ranking — clean-room implementation.

Ranks stock-footage/photo candidates against a scene's narration + visual
intent using image/text embeddings from a small pretrained CLIP model
(`openai/clip-vit-base-patch32`, a public HuggingFace checkpoint — using the
same off-the-shelf model as any other CLIP-based tool is not the same thing
as reusing anyone's code; every line below is original), plus a lightweight
MMR-style diversity penalty against assets already picked elsewhere in the
same job so two beats don't end up wearing the same stock footage.

This module is a RANKING layer only. It never sources candidates (that is
`pipeline/providers.py`'s job) and it never decides what to do when ranking
isn't possible — every entry point returns `None` on any failure (missing
torch/transformers, a model that won't load, a thumbnail that won't
download, zero usable candidates) and the caller in `broll.py` falls back
to today's keyword-first-hit path unchanged. Ranking a beat wrong would be
a regression; declining to rank it is just today's behavior.

Design notes
------------
- Lazy-loaded, cached on first use — importing this module costs nothing
  until `available()` or `embed_text`/`embed_image_path` is actually called.
- Every embedding (text and image) is cached to disk keyed by a content
  hash, so re-running the same job (or a different job that happens to draw
  the same stock candidate) never re-embeds the same content twice.
- Candidates whose thumbnail can't be embeddded (no thumb_url — Pixabay
  video, see `providers.RankCandidate`) fall back to a weaker text-vs-tags
  comparison rather than being silently dropped from ranking.
- Cross-scene diversity is intentionally NOT computed during the concurrent
  per-scene resolution pass (scenes resolve via `asyncio.gather`, so an
  "already selected" list mutated mid-flight would be order-dependent and
  unreliable — the exact reason `broll._dedupe_real_assets` already runs as
  a separate deterministic post-pass instead of inline). `rank_async` accepts
  an optional `selected` list of embeddings for callers that DO have a stable
  sequential view (the post-pass diversify step); the concurrent per-scene
  callers simply pass `selected=None` and rank on relevance alone.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Optional

import numpy as np

from ..config import settings

_MODEL_ID = "openai/clip-vit-base-patch32"
_EMBED_DIM = 512

# Below this cosine similarity a "match" is not trustworthy enough to prefer
# over keyword retrieval — roughly the same conservative floor independent
# CLIP ViT-B/32 evaluations use for "plausibly related, not coincidence".
DEFAULT_MIN_RELEVANCE = 0.20
# How strongly a near-duplicate-to-something-already-picked candidate is
# penalized relative to raw relevance. 0 = ignore diversity entirely.
DEFAULT_DIVERSITY_WEIGHT = 0.35
# Two candidates whose embeddings cosine above this are treated as "the same
# shot" for diversify purposes (a blinking-server-room clip and a slightly
# different blinking-server-room clip both clear this).
NEAR_DUPLICATE_THRESHOLD = 0.90

_STATE = {"model": None, "processor": None, "checked": False, "ok": False}


def _feature_tensor(features):
    """`CLIPModel.get_text_features`/`get_image_features` return a raw tensor
    on some transformers versions and a `BaseModelOutputWithPooling` (with a
    `pooler_output` attribute holding the same projected embedding) on
    others — confirmed directly against the installed version rather than
    assumed, since this is exactly the kind of thing that silently breaks a
    `.norm()` call into a caught-and-ignored exception. Do not project
    `pooler_output` again: it is already in CLIP's shared embedding space."""
    pooled = getattr(features, "pooler_output", None)
    return features if pooled is None else pooled


def available() -> bool:
    """Cheap (after the first call), cached check: can we actually embed?"""
    if _STATE["checked"]:
        return _STATE["ok"]
    _STATE["checked"] = True
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
    except ImportError:
        _STATE["ok"] = False
        return False
    _STATE["ok"] = True
    return True


def _load() -> bool:
    """Load the model exactly once per process. Returns False on any failure
    (corrupt cache, no network on first-ever run, out of memory, ...) — the
    caller treats that identically to `available() is False`."""
    if _STATE["model"] is not None:
        return True
    if not available():
        return False
    try:
        import torch
        from transformers import CLIPModel, CLIPProcessor
        device = "cuda" if torch.cuda.is_available() else "cpu"
        processor = CLIPProcessor.from_pretrained(_MODEL_ID)
        model = CLIPModel.from_pretrained(_MODEL_ID).to(device)
        model.eval()
        _STATE.update(model=model, processor=processor, device=device)
        return True
    except Exception:
        # A half-initialised model must never be reused — force every future
        # call back through this function (which will fail fast and cheap).
        _STATE["model"] = None
        _STATE["ok"] = False
        return False


def _cache_dir() -> Path:
    d = settings().data_dir / "cache" / "clip_embed"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cache_path(key: str) -> Path:
    return _cache_dir() / f"{hashlib.sha1(key.encode()).hexdigest()}.json"


def _load_cached_vec(key: str) -> Optional[np.ndarray]:
    p = _cache_path(key)
    try:
        vec = json.loads(p.read_text())
        arr = np.asarray(vec, dtype=np.float32)
        return arr if arr.shape == (_EMBED_DIM,) else None
    except (OSError, ValueError, TypeError):
        return None


def _store_cached_vec(key: str, vec: np.ndarray) -> None:
    p = _cache_path(key)
    tmp = p.with_suffix(".json.tmp")
    try:
        tmp.write_text(json.dumps(vec.astype(np.float32).tolist()))
        tmp.replace(p)
    except OSError:
        tmp.unlink(missing_ok=True)


def embed_text(text: str) -> Optional[np.ndarray]:
    """Embed one text string into a normalised 512-d vector, or None."""
    text = (text or "").strip()
    if not text or not _load():
        return None
    key = f"text:{text}"
    cached = _load_cached_vec(key)
    if cached is not None:
        return cached
    try:
        import torch
        proc, model, device = _STATE["processor"], _STATE["model"], _STATE["device"]
        inputs = proc(text=[text], return_tensors="pt", padding=True,
                      truncation=True, max_length=77).to(device)
        with torch.no_grad():
            feat = _feature_tensor(model.get_text_features(**inputs))
        feat = feat / feat.norm(dim=-1, keepdim=True).clamp_min(1e-8)
        vec = feat.cpu().numpy().astype(np.float32, copy=False)[0]
    except Exception:
        return None
    _store_cached_vec(key, vec)
    return vec


def embed_image_path(path: str) -> Optional[np.ndarray]:
    """Embed one local image file into a normalised 512-d vector, or None."""
    if not path or not Path(path).is_file() or not _load():
        return None
    try:
        digest = hashlib.sha1(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None
    key = f"image:{digest}"
    cached = _load_cached_vec(key)
    if cached is not None:
        return cached
    try:
        import torch
        from PIL import Image
        proc, model, device = _STATE["processor"], _STATE["model"], _STATE["device"]
        img = Image.open(path).convert("RGB")
        try:
            inputs = proc(images=[img], return_tensors="pt").to(device)
            with torch.no_grad():
                feat = _feature_tensor(model.get_image_features(**inputs))
        finally:
            img.close()
        feat = feat / feat.norm(dim=-1, keepdim=True).clamp_min(1e-8)
        vec = feat.cpu().numpy().astype(np.float32, copy=False)[0]
    except Exception:
        return None
    _store_cached_vec(key, vec)
    return vec


def cosine(a: Optional[np.ndarray], b: Optional[np.ndarray]) -> float:
    if a is None or b is None:
        return 0.0
    return float(np.clip(np.dot(a, b), -1.0, 1.0))


class RankedCandidate:
    """One scored candidate, carrying its embedding so a later diversify
    pass can reuse it without re-embedding."""

    __slots__ = ("candidate", "vec", "relevance", "score", "ranked_by")

    def __init__(self, candidate, vec, relevance: float, score: float, ranked_by: str):
        self.candidate = candidate
        self.vec = vec
        self.relevance = relevance
        self.score = score
        self.ranked_by = ranked_by  # "image" | "tags" | "unranked"


def score_candidates(triples: list[tuple], text_vec: np.ndarray, *,
                     selected: Optional[list[np.ndarray]] = None,
                     diversity_weight: float = DEFAULT_DIVERSITY_WEIGHT
                     ) -> list[RankedCandidate]:
    """Pure scoring step: given `[(candidate, vec_or_None, ranked_by), ...]`
    and an already-embedded query vector, return candidates sorted best-first.

    Separated from `rank_async` (which does the network/embedding I/O to
    produce `triples`) so the scoring math — relevance minus an MMR-style
    penalty for similarity to `selected` — is unit-testable with synthetic
    vectors and no model/network involved. `ranked_by` is caller-supplied
    (`"image"` / `"tags"` / `"unranked"`) rather than inferred here, since by
    this point that distinction is just bookkeeping, not a scoring input.
    """
    selected = selected or []
    scored: list[RankedCandidate] = []
    for cand, vec, ranked_by in triples:
        relevance = cosine(text_vec, vec) if vec is not None else 0.0
        penalty = max((cosine(vec, s) for s in selected), default=0.0) if vec is not None else 0.0
        rc = RankedCandidate(cand, vec, relevance, relevance - diversity_weight * penalty, ranked_by)
        scored.append(rc)
    scored.sort(key=lambda rc: rc.score, reverse=True)
    return scored


async def rank_async(candidates: list, query_text: str, *,
                     selected: Optional[list[np.ndarray]] = None,
                     diversity_weight: float = DEFAULT_DIVERSITY_WEIGHT) -> list[RankedCandidate]:
    """Production entry point: downloads each candidate's thumbnail (or embeds
    its tag text when there is no thumbnail), embeds it, and scores it against
    `query_text` with an optional MMR-style penalty against `selected`
    (embeddings of assets already picked elsewhere in this job).

    Returns [] the moment ranking isn't usable — no partial/best-effort
    ranking is returned, because a caller that can't tell "no good match" from
    "some candidates errored" would silently ship a worse pick than keyword
    search would have found.
    """
    if not candidates or not available():
        return []
    text_vec = embed_text(query_text)
    if text_vec is None:
        return []

    from .providers import _download

    triples: list[tuple] = []
    for cand in candidates:
        vec: Optional[np.ndarray] = None
        ranked_by = "unranked"
        if cand.thumb_url:
            try:
                local = await _download(cand.thumb_url, "jpg")
                vec = embed_image_path(local)
                if vec is not None:
                    ranked_by = "image"
            except Exception:
                vec = None
        if vec is None and cand.tags:
            vec = embed_text(cand.tags)
            if vec is not None:
                ranked_by = "tags"
        triples.append((cand, vec, ranked_by))

    return score_candidates(triples, text_vec, selected=selected, diversity_weight=diversity_weight)


def is_near_duplicate(a: Optional[np.ndarray], b: Optional[np.ndarray],
                      threshold: float = NEAR_DUPLICATE_THRESHOLD) -> bool:
    if a is None or b is None:
        return False
    return cosine(a, b) >= threshold
