"""
Topic clustering: normalized signals -> TopicCandidate clusters.

Similarity is deterministic and dependency-free (no embedding model, no network):
a blend of token Jaccard, character-trigram cosine, and a shared-entity bonus.
That is enough to fold "Fed cuts rates" / "FOMC rate reduction" / "Powell announces
lower interest rates" together while staying fully explainable in a test.

Hard separation rules — two signals NEVER join the same cluster when:
  * their factual states are incompatible (forecast vs confirmed vs rumour), or
  * they describe different event types with different entities.

Syndication: identical stories from many outlets collapse into ONE independent
source. Twenty copies of a press release is one confirmation.
"""
from __future__ import annotations

import hashlib
from collections import Counter
from datetime import datetime, timedelta, timezone

from .models import (
    AssetClass,
    EvidenceItem,
    EventType,
    FactualState,
    NormalizedSignal,
    TopicCandidate,
)
from .normalizer import tokenize
from .settings import ti_settings

# Which factual states may share a cluster. A forecast and its confirmation are
# genuinely different facts about the world and must be ranked separately.
#
# `unknown` means "this text asserts nothing" (a YouTube title, a bare headline),
# so it may join any cluster EXCEPT a rumour — an unlabelled item must never be
# absorbed into, and thereby lend weight to, an unverified claim.
_COMPATIBLE: dict[FactualState, set[FactualState]] = {
    FactualState.confirmed: {FactualState.confirmed, FactualState.unknown},
    FactualState.forecast: {
        FactualState.forecast, FactualState.expectation, FactualState.unknown,
    },
    FactualState.expectation: {
        FactualState.expectation, FactualState.forecast, FactualState.unknown,
    },
    FactualState.opinion: {
        FactualState.opinion, FactualState.unknown, FactualState.historical,
    },
    FactualState.rumour: {FactualState.rumour},
    FactualState.historical: {
        FactualState.historical, FactualState.unknown, FactualState.opinion,
    },
    FactualState.unknown: {
        FactualState.unknown, FactualState.opinion, FactualState.historical,
        FactualState.confirmed, FactualState.forecast, FactualState.expectation,
    },
}


def states_compatible(a: FactualState, b: FactualState) -> bool:
    return b in _COMPATIBLE.get(a, {a}) and a in _COMPATIBLE.get(b, {b})


def _trigrams(text: str) -> Counter:
    t = f"  {text.lower()} "
    return Counter(t[i:i + 3] for i in range(len(t) - 2))


def _cosine(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    dot = sum(a[k] * b[k] for k in common)
    na = sum(v * v for v in a.values()) ** 0.5
    nb = sum(v * v for v in b.values()) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def text_similarity(a: str, b: str) -> float:
    """0-1 blended similarity. Deterministic and symmetric."""
    ta, tb = set(tokenize(a)), set(tokenize(b))
    jac = len(ta & tb) / len(ta | tb) if (ta or tb) else 0.0
    tri = _cosine(_trigrams(a), _trigrams(b))
    return round(0.6 * jac + 0.4 * tri, 4)


def subject_similarity(a: NormalizedSignal, b: NormalizedSignal) -> float:
    """Overlap coefficient over the union of tickers and named entities.

    Containment, not Jaccard, on purpose: one outlet writing "Fed cuts rates" and
    another writing "Fed cuts rates as Powell announces…" are the same story, but
    Jaccard would halve their similarity for the extra name. When NEITHER signal
    names a subject we cannot judge structurally, so we return a neutral 0.5 and
    let the text decide.
    """
    sa = set(a.tickers) | set(a.entities)
    sb = set(b.tickers) | set(b.entities)
    if not sa and not sb:
        return 0.5
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / min(len(sa), len(sb))


def signal_similarity(a: NormalizedSignal, b: NormalizedSignal) -> float:
    """Weighted blend of WHAT is being discussed (subject), WHAT HAPPENED (event
    type) and HOW it is worded (text).

    Structure is weighted heavily on purpose: in finance, "Fed cuts rates" and
    "FOMC rate reduction explained" share almost no vocabulary but are obviously
    the same story, while "Bitcoin rallies" and "Bitcoin crashes" share plenty of
    vocabulary and are not.
    """
    if not states_compatible(a.factual_state, b.factual_state):
        return 0.0
    text = text_similarity(a.canonical_title, b.canonical_title)
    subject = subject_similarity(a, b)
    event = 1.0 if (
        a.event_type is b.event_type and a.event_type is not EventType.other
    ) else 0.0
    sim = 0.45 * text + 0.30 * subject + 0.25 * event
    return round(max(0.0, min(1.0, sim)), 4)


def _topic_id(canonical: str, state: FactualState) -> str:
    basis = f"{state.value}|{' '.join(sorted(set(tokenize(canonical))))}"
    return "tc_" + hashlib.sha1(basis.encode()).hexdigest()[:14]


def _pick_canonical(signals: list[NormalizedSignal]) -> str:
    """The cluster's headline: the most credible, most recent, most specific title."""
    def rank(s: NormalizedSignal) -> tuple:
        return (
            round(s.credibility, 2),
            1 if s.factual_state is FactualState.confirmed else 0,
            -s.age_hours,
            len(s.canonical_title),
        )
    return max(signals, key=rank).canonical_title


def _syndication_groups(signals: list[NormalizedSignal]) -> int:
    """Count INDEPENDENT reports. Near-identical titles from different publishers
    are one story; the same host twice is also one."""
    groups: list[list[NormalizedSignal]] = []
    for s in signals:
        for g in groups:
            if text_similarity(s.canonical_title, g[0].canonical_title) >= 0.80:
                g.append(s)
                break
        else:
            groups.append([s])
    return len(groups)


def _evidence_from(s: NormalizedSignal) -> EvidenceItem:
    return EvidenceItem(
        provider=s.provider,
        title=s.canonical_title,
        url=s.raw.url,
        external_id=s.raw.external_id,
        published_at=s.raw.published_at,
        collected_at=s.raw.collected_at,
        source_tier=s.source_tier,
        source_credibility=s.credibility,
        excerpt=(s.raw.summary or "")[:400] or None,
        metrics=dict(s.normalized_metrics),
        grounded=s.provider == "gemini_grounding",
        grounding_complete=bool(s.raw.url) if s.provider == "gemini_grounding" else True,
    )


def _aggregate_metrics(signals: list[NormalizedSignal]) -> dict[str, float]:
    """Sum rate-like metrics, max level-like ones. Keys absent from every signal
    stay absent — we never publish a zero we did not measure."""
    sums = {
        "views_per_hour", "like_velocity", "comment_velocity", "upvote_velocity",
        "post_velocity", "mention_velocity", "engagement_velocity", "unique_authors",
    }
    maxes = {
        "search_interest", "breakout_ratio", "views_per_subscriber", "importance",
        "controversy", "bot_risk", "channel_subscribers",
    }
    out: dict[str, float] = {}
    for s in signals:
        for k, v in s.normalized_metrics.items():
            if k in sums:
                out[k] = out.get(k, 0.0) + v
            elif k in maxes:
                out[k] = max(out.get(k, 0.0), v)
            else:
                out[k] = max(out.get(k, 0.0), v)
    return {k: round(v, 4) for k, v in out.items()}


def _median(vals: list[float]) -> float:
    if not vals:
        return 0.0
    v = sorted(vals)
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2.0


def _competition_metrics(signals: list[NormalizedSignal]) -> dict[str, float]:
    """YouTube-only competitive picture for this exact topic."""
    yt = [s for s in signals if s.provider == "youtube"]
    if not yt:
        return {}
    views = [float(s.raw.engagement.get("views", 0.0)) for s in yt]
    subs = [
        float(s.raw.raw_metrics["channel_subscribers"])
        for s in yt
        if isinstance(s.raw.raw_metrics.get("channel_subscribers"), (int, float))
    ]
    vps = [s.normalized_metrics["views_per_subscriber"]
           for s in yt if "views_per_subscriber" in s.normalized_metrics]
    ages = [s.age_hours for s in yt if s.age_hours > 0]
    titles = [s.canonical_title for s in yt]
    # How samey is the existing coverage? High = every incumbent used one angle.
    pairs = [
        text_similarity(titles[i], titles[j])
        for i in range(len(titles)) for j in range(i + 1, len(titles))
    ]
    out = {
        "competing_videos": float(len(yt)),
        "median_competitor_views": _median(views),
        "median_competitor_subscribers": _median(subs),
        "median_views_per_subscriber": _median(vps),
        "median_competitor_age_hours": _median(ages),
        "title_similarity": round(_median(pairs), 4) if pairs else 0.0,
        "incumbent_max_subscribers": max(subs) if subs else 0.0,
    }
    return {k: round(v, 4) for k, v in out.items()}


def cluster_signals(
    signals: list[NormalizedSignal],
    *,
    threshold: float | None = None,
    now: datetime | None = None,
) -> list[TopicCandidate]:
    """Greedy single-pass agglomerative clustering, ordered by credibility so the
    most authoritative signal seeds each cluster."""
    s_cfg = ti_settings()
    threshold = s_cfg.topic_cluster_threshold if threshold is None else threshold
    now = now or datetime.now(timezone.utc)

    ordered = sorted(
        signals,
        key=lambda s: (-s.credibility, s.age_hours, s.canonical_title),
    )
    clusters: list[list[NormalizedSignal]] = []
    for sig in ordered:
        best_i, best_sim = -1, 0.0
        for i, members in enumerate(clusters):
            # Compare against the cluster seed AND the best member so a chain of
            # paraphrases doesn't drift the cluster's meaning.
            sim = max(signal_similarity(sig, m) for m in members[:5])
            if sim > best_sim:
                best_i, best_sim = i, sim
        if best_i >= 0 and best_sim >= threshold:
            clusters[best_i].append(sig)
        else:
            clusters.append([sig])

    candidates = [_build_candidate(m, now) for m in clusters]
    candidates.sort(key=lambda c: (-c.source_count, -c.provider_count))
    return candidates[: s_cfg.ti_max_clusters]


def _build_candidate(members: list[NormalizedSignal], now: datetime) -> TopicCandidate:
    canonical = _pick_canonical(members)
    # The cluster's factual state is its STRONGEST claim, in a fixed precedence —
    # a confirmed member means the cluster is about a confirmed event.
    for state in (FactualState.confirmed, FactualState.forecast,
                  FactualState.expectation, FactualState.historical,
                  FactualState.opinion, FactualState.rumour):
        if any(m.factual_state is state for m in members):
            cluster_state = state
            break
    else:
        cluster_state = FactualState.unknown

    event_types = Counter(
        m.event_type for m in members if m.event_type is not EventType.other
    )
    event_type = event_types.most_common(1)[0][0] if event_types else EventType.other

    assets: list[AssetClass] = []
    for m in members:
        for a in m.asset_classes:
            if a is not AssetClass.unknown and a not in assets:
                assets.append(a)

    published = [m.raw.published_at for m in members if m.raw.published_at]
    scheduled = [
        m.raw.published_at for m in members
        if m.provider == "economic_calendar" and m.raw.published_at
    ]
    metrics = _aggregate_metrics(members)
    metrics.update(_competition_metrics(members))
    providers = sorted({m.provider for m in members})
    metrics["provider_count"] = float(len(providers))

    independent = _syndication_groups(members)
    metrics["independent_sources"] = float(independent)

    # A confirmed hard-news event goes stale fast; evergreen education does not.
    ttl = {
        FactualState.confirmed: timedelta(hours=48),
        FactualState.forecast: timedelta(days=7),
        FactualState.expectation: timedelta(days=3),
        FactualState.rumour: timedelta(hours=24),
        FactualState.opinion: timedelta(days=5),
        FactualState.historical: timedelta(days=180),
        FactualState.unknown: timedelta(days=3),
    }[cluster_state]
    base = max(published) if published else now

    return TopicCandidate(
        topic_id=_topic_id(canonical, cluster_state),
        canonical_topic=canonical,
        factual_state=cluster_state,
        event_type=event_type,
        asset_classes=assets or [AssetClass.unknown],
        entities=sorted({e for m in members for e in m.entities}),
        tickers=sorted({t for m in members for t in m.tickers}),
        signals=members,
        evidence=[_evidence_from(m) for m in members[:25]],
        source_names=providers,
        source_count=len(members),
        provider_count=len(providers),
        independent_source_count=independent,
        first_seen=min(published) if published else None,
        last_seen=max(published) if published else None,
        expires_at=base + ttl,
        scheduled_event_at=min(scheduled) if scheduled else None,
        metrics=metrics,
    )
