"""
Signal normalization: RawTrendSignal -> NormalizedSignal.

Two jobs, kept strictly apart:

1. TEXT normalization — casing, punctuation, publisher suffixes, ticker/alias
   folding, entity/event/asset extraction, factual-state detection.
2. METRIC normalization — turn each provider's native counters into a small,
   explicitly-named vocabulary. A key is only emitted when the provider actually
   supplies the underlying number. Absent != zero.

Normalized metric vocabulary (all per-hour rates unless noted):
    views_per_hour, like_velocity, comment_velocity, upvote_velocity,
    post_velocity, mention_velocity, engagement_velocity, unique_authors,
    channel_subscribers, views_per_subscriber, search_interest, breakout_ratio,
    bot_risk, controversy, importance
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime, timezone

from . import entities as ent
from .models import (
    TIER_CREDIBILITY,
    FactualState,
    NormalizedSignal,
    RawTrendSignal,
    SourceTier,
)

_PUBLISHER_SUFFIX = re.compile(
    r"\s*[\|\-–—:]\s*(reuters|bloomberg|cnbc|wsj|the wall street journal|ap|"
    r"associated press|marketwatch|barron'?s|yahoo finance|business insider|"
    r"ft|financial times|forbes|fortune|coindesk|investing\.com)\s*$",
    re.IGNORECASE,
)
_SOCIAL_PREFIX = re.compile(
    r"^\s*(\[?(dd|discussion|news|meme|gain|loss|question|help|daily|serious)\]?|"
    r"breaking|just in|update|watch|opinion)\s*[:\-–—]\s*",
    re.IGNORECASE,
)
_PUNCT = re.compile(r"[^\w\s$%.]")
_WS = re.compile(r"\s+")
_STOPWORDS = {
    "the", "a", "an", "of", "to", "in", "on", "for", "and", "is", "are", "was",
    "were", "be", "as", "at", "by", "it", "its", "this", "that", "with", "from",
    "after", "before", "amid", "over", "into", "will", "has", "have", "but",
    "not", "you", "your", "we", "our", "how", "what", "why", "s", "t",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def clean_title(title: str) -> str:
    """Human-readable canonical title: strip emoji/publisher/clickbait scaffolding
    but KEEP capitalisation and numbers (they carry meaning: "$4T", "3.2%")."""
    t = unicodedata.normalize("NFKC", title or "").strip()
    t = "".join(c for c in t if unicodedata.category(c)[0] != "C")
    t = _SOCIAL_PREFIX.sub("", t)
    t = _PUBLISHER_SUFFIX.sub("", t)
    t = _WS.sub(" ", t).strip(" -–—|:")
    return t[:300]


def tokenize(text: str) -> list[str]:
    """Lowercased, de-punctuated, stopword-free tokens with aliases folded to a
    canonical slug, so "Fed", "FOMC" and "Federal Reserve" all tokenize to
    `federal_reserve` and "Nvidia"/"NVDA" both to `nvda`."""
    t = unicodedata.normalize("NFKC", text or "").lower()
    t = t.replace("&", " and ")
    t = ent.fold_aliases(t)
    t = _PUNCT.sub(" ", t)
    return [w for w in _WS.split(t) if w and w not in _STOPWORDS and len(w) > 1]


def canonical_key(canonical_title: str, factual_state: FactualState) -> str:
    """Deterministic exact-dedup key. Includes the factual state so a forecast and
    its confirmation can never collide on the exact-match path."""
    toks = sorted(set(tokenize(canonical_title)))
    basis = f"{factual_state.value}|{' '.join(toks)}"
    return hashlib.sha1(basis.encode()).hexdigest()[:20]


# --------------------------------------------------------------------------- #
# Per-provider metric normalization
# --------------------------------------------------------------------------- #
def _age_hours(published: datetime | None, now: datetime) -> float:
    if published is None:
        return 0.0
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    return max(0.0, (now - published).total_seconds() / 3600.0)


def _rate(total: float | None, hours: float) -> float | None:
    """Counter -> per-hour rate. The 1h floor stops a 5-minute-old post with 3
    upvotes from reporting an absurd 36/hour velocity."""
    if total is None:
        return None
    return float(total) / max(1.0, hours)


def normalize_metrics(sig: RawTrendSignal, age_h: float) -> dict[str, float]:
    """Provider-specific -> shared vocabulary. NEVER invents a value."""
    e, r = sig.engagement, sig.raw_metrics
    out: dict[str, float] = {}

    def put(key: str, val: float | None) -> None:
        if val is not None:
            out[key] = round(float(val), 4)

    p = sig.provider
    if p == "youtube":
        put("views_per_hour", _rate(e.get("views"), age_h))
        put("like_velocity", _rate(e.get("likes"), age_h))
        put("comment_velocity", _rate(e.get("comments"), age_h))
        subs = r.get("channel_subscribers")
        if isinstance(subs, (int, float)) and subs > 0:
            put("channel_subscribers", float(subs))
            views = e.get("views")
            if views is not None:
                # Breakout: a video outrunning its own channel size is real demand,
                # not just an audience already primed to click.
                put("views_per_subscriber", float(views) / float(subs))
    elif p == "reddit":
        put("upvote_velocity", _rate(e.get("score"), age_h))
        put("comment_velocity", _rate(e.get("comments"), age_h))
        ur = r.get("upvote_ratio")
        if isinstance(ur, (int, float)):
            # 0.5 ratio = maximally contested; 1.0 = consensus.
            put("controversy", max(0.0, 1.0 - abs(float(ur) - 0.5) * 2.0))
    elif p == "x":
        put("mention_velocity", _rate(e.get("mentions"), age_h))
        put("engagement_velocity", _rate(
            (e.get("likes") or 0) + (e.get("retweets") or 0) + (e.get("replies") or 0)
            if e else None, age_h))
        ua = r.get("unique_authors")
        if isinstance(ua, (int, float)):
            put("unique_authors", float(ua))
            mentions = e.get("mentions") or 0
            if mentions > 0:
                # Many posts from few accounts = amplification, not interest.
                ratio = float(ua) / float(mentions)
                put("bot_risk", max(0.0, min(1.0, 1.0 - ratio)))
    elif p == "google_trends":
        put("search_interest", e.get("interest"))
        put("breakout_ratio", r.get("breakout_ratio") if isinstance(
            r.get("breakout_ratio"), (int, float)) else None)
    elif p == "economic_calendar":
        imp = str(r.get("importance", "medium")).lower()
        put("importance", {"high": 100.0, "medium": 60.0, "low": 25.0}.get(imp, 60.0))
    elif p == "finance_news":
        put("post_velocity", _rate(r.get("syndication_count"), age_h))
    elif p == "gemini_grounding":
        pass  # grounding contributes evidence, never metrics

    return out


def normalize_signal(sig: RawTrendSignal, *, now: datetime | None = None) -> NormalizedSignal:
    now = now or _utcnow()
    title = clean_title(sig.title)
    text = f"{title}. {sig.summary or ''}"

    tier = ent.classify_source(sig.url, sig.provider)
    # A provider may supply a better-informed credibility (e.g. an official
    # calendar feed); we take the max but a social tier can never exceed its cap.
    cred = TIER_CREDIBILITY[tier]
    if sig.source_credibility is not None and tier is not SourceTier.social:
        cred = max(cred, min(1.0, float(sig.source_credibility)))

    state = ent.detect_factual_state(text, sig.provider)
    age_h = _age_hours(sig.published_at, now)

    return NormalizedSignal(
        raw=sig,
        canonical_title=title,
        canonical_key=canonical_key(title, state),
        entities=ent.extract_entities(text),
        tickers=ent.extract_tickers(text),
        asset_classes=ent.detect_asset_classes(text),
        event_type=ent.detect_event_type(text),
        factual_state=state,
        source_tier=tier,
        credibility=cred,
        normalized_metrics=normalize_metrics(sig, age_h),
        age_hours=age_h,
    )


def normalize_all(
    signals: list[RawTrendSignal], *, now: datetime | None = None
) -> list[NormalizedSignal]:
    now = now or _utcnow()
    out: list[NormalizedSignal] = []
    for s in signals:
        try:
            out.append(normalize_signal(s, now=now))
        except Exception as e:  # noqa: BLE001 — one bad signal must not kill a run
            print(f"[ti.normalizer] dropped signal from {s.provider}: "
                  f"{type(e).__name__}: {e}", flush=True)
    return out
