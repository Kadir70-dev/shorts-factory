"""
Deterministic scoring — the authority on `overall_score`.

Everything here is a pure function of collected metrics and YAML weights. Gemini
never computes the final number: `recompute_overall()` is called on every ranked
topic regardless of ranker, so a model that returns overall_score=99 for a weak
candidate simply has that field overwritten.

Relative-score discipline: CTR / retention / subscriber / monetization are
explicitly INTERNAL RELATIVE scores (0-100) with a confidence, never a forecast of
a real-world percentage.
"""
from __future__ import annotations

import functools
import math
import re
from datetime import datetime, timezone

import yaml

from .models import AssetClass, EventType, FactualState, TopicCandidate, TopicScores
from .settings import ti_settings

_US_MACRO_EVENTS = {
    EventType.fed_decision, EventType.fomc_minutes, EventType.cpi, EventType.pce,
    EventType.nonfarm_payrolls, EventType.unemployment, EventType.gdp,
    EventType.retail_sales, EventType.ism, EventType.jobless_claims,
    EventType.treasury,
}
_MAJOR_ASSETS = {
    AssetClass.equities, AssetClass.crypto, AssetClass.rates, AssetClass.macro,
    AssetClass.ai_tech,
}
_CHARTABLE = {AssetClass.macro, AssetClass.rates, AssetClass.equities,
              AssetClass.crypto, AssetClass.gold, AssetClass.oil, AssetClass.forex}
_NUMBER_RE = re.compile(r"(\$?\d[\d,.]*\s?(%|bps|billion|trillion|million|k\b)?)")

DEFAULT_CONFIG: dict = {
    "weights": {
        "trend_momentum": 0.20, "audience_relevance": 0.15, "freshness": 0.12,
        "cross_source_confirmation": 0.12, "competition_opportunity": 0.10,
        "ctr_potential": 0.10, "retention_potential": 0.08,
        "monetization_potential": 0.05, "production_feasibility": 0.05,
        "subscriber_potential": 0.03,
    },
    "risk_weight": 0.60,
    "gemini_adjustable": [
        "audience_relevance", "ctr_potential", "retention_potential",
        "subscriber_potential", "monetization_potential", "production_feasibility",
    ],
    "saturation": {
        "views_per_hour": 50000, "upvote_velocity": 400, "comment_velocity": 300,
        "mention_velocity": 800, "engagement_velocity": 5000, "search_interest": 100,
        "competing_videos": 40, "median_competitor_views": 500000,
        "median_competitor_subscribers": 2000000,
    },
    "freshness_half_life_hours": {
        "confirmed": 10, "forecast": 72, "expectation": 36, "opinion": 48,
        "rumour": 8, "historical": 4320, "unknown": 36,
    },
    "audience": {
        "base": 35, "us_region_bonus": 20, "us_macro_event_bonus": 25,
        "major_asset_bonus": 12, "recognizable_ticker_bonus": 10,
    },
    "monetization_by_asset": {
        "equities": 85, "rates": 80, "macro": 78, "crypto": 70, "ai_tech": 88,
        "market_structure": 72, "gold": 65, "oil": 62, "forex": 60, "unknown": 45,
    },
    "feasibility": {
        "base": 70, "has_number_bonus": 12, "chartable_bonus": 10,
        "evergreen_bonus": 8, "many_entities_penalty": 15, "long_topic_penalty": 10,
    },
}

# `cross_source_confirmation` is a weight name, not a TopicScores field — it is
# folded into `credibility`, which carries both source quality AND corroboration.
_WEIGHT_TO_FIELD = {"cross_source_confirmation": "credibility"}


@functools.lru_cache
def load_config(path_str: str = "") -> dict:
    """YAML config with the built-in defaults as a deep fallback. A malformed or
    missing file degrades to defaults with a warning; it never breaks a run."""
    from pathlib import Path

    cfg = {k: (dict(v) if isinstance(v, dict) else list(v) if isinstance(v, list) else v)
           for k, v in DEFAULT_CONFIG.items()}
    path = Path(path_str) if path_str else ti_settings().ti_scoring_config
    try:
        if path.exists():
            loaded = yaml.safe_load(path.read_text()) or {}
            for k, v in loaded.items():
                if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                    cfg[k].update(v)
                else:
                    cfg[k] = v
    except Exception as e:  # noqa: BLE001
        print(f"[ti.scoring] using default weights ({type(e).__name__}: {e})", flush=True)
    return cfg


def is_on_niche(c: TopicCandidate) -> bool:
    """Is this candidate about finance at all?

    General news feeds carry plenty of politics, war and courtroom coverage. A
    story that names no asset class, no ticker and no recognized financial event
    is off-beat for this channel — not unsafe, just not ours. Kept separate from
    `safety.py` on purpose: relevance is an editorial judgement, not a risk.
    """
    return bool(
        c.tickers
        or any(a is not AssetClass.unknown for a in c.asset_classes)
        or c.event_type is not EventType.other
    )


def _clamp(v: float) -> float:
    return max(0.0, min(100.0, v))


def _log_scale(value: float, saturation: float) -> float:
    """Diminishing-returns 0-100. A 10x bigger number is not a 10x better topic."""
    if value <= 0 or saturation <= 0:
        return 0.0
    return _clamp(100.0 * math.log1p(value) / math.log1p(saturation))


# --------------------------------------------------------------------------- #
# Individual dimensions
# --------------------------------------------------------------------------- #
def trend_momentum(c: TopicCandidate, cfg: dict) -> float:
    """Blend of the velocity metrics that were ACTUALLY measured. Providers that
    did not report are excluded from the average rather than counted as zero."""
    sat = cfg["saturation"]
    parts: list[tuple[float, float]] = []   # (score, weight)
    m = c.metrics
    if "views_per_hour" in m:
        parts.append((_log_scale(m["views_per_hour"], sat["views_per_hour"]), 1.0))
    if "search_interest" in m:
        parts.append((_clamp(m["search_interest"]), 1.0))
    if "upvote_velocity" in m:
        parts.append((_log_scale(m["upvote_velocity"], sat["upvote_velocity"]), 0.6))
    if "comment_velocity" in m:
        parts.append((_log_scale(m["comment_velocity"], sat["comment_velocity"]), 0.5))
    if "mention_velocity" in m:
        parts.append((_log_scale(m["mention_velocity"], sat["mention_velocity"]), 0.5))
    if "engagement_velocity" in m:
        parts.append((_log_scale(m["engagement_velocity"], sat["engagement_velocity"]), 0.4))
    if "breakout_ratio" in m:
        parts.append((_clamp(m["breakout_ratio"] * 100.0), 0.8))

    if not parts:
        # Nothing measurable: a scheduled macro event still has real momentum.
        if c.event_type in _US_MACRO_EVENTS:
            return 45.0
        return 20.0
    total_w = sum(w for _, w in parts)
    score = sum(s * w for s, w in parts) / total_w
    # Genuine multi-provider agreement is itself momentum.
    score += min(15.0, 5.0 * max(0, c.provider_count - 1))
    return round(_clamp(score), 2)


def audience_relevance(c: TopicCandidate, cfg: dict) -> float:
    a = cfg["audience"]
    score = float(a["base"])
    regions = {s.raw.region for s in c.signals if s.raw.region}
    if not regions or "US" in regions:
        score += a["us_region_bonus"]
    if c.event_type in _US_MACRO_EVENTS:
        score += a["us_macro_event_bonus"]
    if any(x in _MAJOR_ASSETS for x in c.asset_classes):
        score += a["major_asset_bonus"]
    if c.tickers:
        score += a["recognizable_ticker_bonus"]
    return round(_clamp(score), 2)


def freshness(c: TopicCandidate, cfg: dict, *, now: datetime | None = None) -> float:
    """Exponential decay on a per-factual-state half-life. A scheduled future event
    scores high as it approaches and decays after it passes."""
    now = now or datetime.now(timezone.utc)
    hl = float(cfg["freshness_half_life_hours"].get(c.factual_state.value, 36))

    if c.scheduled_event_at is not None:
        sched = c.scheduled_event_at
        if sched.tzinfo is None:
            sched = sched.replace(tzinfo=timezone.utc)
        delta_h = (sched - now).total_seconds() / 3600.0
        if delta_h >= 0:
            # Peaks in the last ~24h before the release.
            return round(_clamp(100.0 * math.exp(-max(0.0, delta_h - 6.0) / 72.0)), 2)

    if c.last_seen is None:
        return 50.0
    last = c.last_seen if c.last_seen.tzinfo else c.last_seen.replace(tzinfo=timezone.utc)
    age_h = max(0.0, (now - last).total_seconds() / 3600.0)
    return round(_clamp(100.0 * math.pow(0.5, age_h / max(1.0, hl))), 2)


def credibility(c: TopicCandidate, cfg: dict) -> float:
    """Source quality AND cross-source confirmation in one dimension.

    Reddit/X credibility is capped hard: a thousand upvotes never makes a claim
    true, so social-only clusters cannot climb past the low band.
    """
    if not c.evidence:
        return 20.0
    best = max(e.source_credibility for e in c.evidence)
    avg = sum(e.source_credibility for e in c.evidence) / len(c.evidence)
    base = 100.0 * (0.65 * best + 0.35 * avg)
    # Independent corroboration (syndicated copies already collapsed upstream).
    base += min(20.0, 8.0 * max(0, c.independent_source_count - 1))
    base += min(10.0, 5.0 * max(0, c.provider_count - 1))
    if c.factual_state is FactualState.rumour:
        base *= 0.5
    return round(_clamp(base), 2)


def competition_opportunity(c: TopicCandidate, cfg: dict) -> float:
    """Opportunity = demand that existing coverage is not satisfying.

    high demand + weak/stale/samey incumbent coverage -> high score.
    Never a keyword search-volume claim: we only use what YouTube actually returned.
    """
    m, sat = c.metrics, cfg["saturation"]
    if "competing_videos" not in m:
        # No YouTube data — say so with a neutral score instead of guessing.
        return 50.0

    demand = _log_scale(m.get("views_per_hour", 0.0), sat["views_per_hour"])
    n = m["competing_videos"]
    supply = _log_scale(n, sat["competing_videos"])

    # Weak incumbents = opportunity.
    med_views = m.get("median_competitor_views", 0.0)
    med_subs = m.get("median_competitor_subscribers", 0.0)
    incumbent_strength = 0.5 * _log_scale(med_views, sat["median_competitor_views"]) + \
        0.5 * _log_scale(med_subs, sat["median_competitor_subscribers"])

    # Stale coverage = opportunity (nobody has covered TODAY's version).
    age_h = m.get("median_competitor_age_hours", 0.0)
    staleness = _clamp(100.0 * (1.0 - math.exp(-age_h / 96.0)))

    # Everyone using the same angle = room for a differentiated one.
    same_angle = _clamp(m.get("title_similarity", 0.0) * 100.0)

    # Breakout: small channels pulling big views on this topic proves latent demand.
    breakout = _clamp(m.get("median_views_per_subscriber", 0.0) * 100.0)

    score = (
        0.32 * demand
        + 0.20 * (100.0 - supply)
        + 0.18 * (100.0 - incumbent_strength)
        + 0.12 * staleness
        + 0.10 * same_angle
        + 0.08 * breakout
    )
    return round(_clamp(score), 2)


def ctr_potential(c: TopicCandidate, cfg: dict) -> float:
    """INTERNAL RELATIVE score. Not a predicted click-through percentage."""
    title = c.canonical_topic
    score = 40.0
    if _NUMBER_RE.search(title):
        score += 14.0                                   # specificity
    if c.tickers:
        score += 12.0                                   # recognizable asset
    if c.event_type in _US_MACRO_EVENTS or c.event_type is EventType.earnings:
        score += 10.0                                   # timely event
    if c.factual_state is FactualState.confirmed:
        score += 8.0
    words = len(title.split())
    if 6 <= words <= 12:
        score += 8.0                                    # headline-length sweet spot
    elif words > 16:
        score -= 8.0
    if re.search(r"\b(why|how|what)\b", title, re.I):
        score += 6.0                                    # curiosity gap without deceit
    if c.event_type is EventType.price_move:
        score += 6.0                                    # emotional intensity
    if any(a in {AssetClass.crypto, AssetClass.ai_tech} for a in c.asset_classes):
        score += 5.0
    if len(c.entities) > 4:
        score -= 6.0                                    # muddled subject
    return round(_clamp(score), 2)


def retention_potential(c: TopicCandidate, cfg: dict) -> float:
    """INTERNAL RELATIVE score: can this pay off inside 30-45 seconds?"""
    score = 45.0
    if c.event_type is EventType.education:
        score += 14.0                                   # clear concept, clean payoff
    if AssetClass.market_structure in c.asset_classes:
        score += 12.0                                   # HFT/microstructure = surprise
    if _NUMBER_RE.search(c.canonical_topic):
        score += 10.0                                   # a number is a payoff
    if c.factual_state is FactualState.confirmed:
        score += 8.0                                    # resolved tension
    elif c.factual_state in {FactualState.forecast, FactualState.expectation}:
        score += 6.0                                    # open tension
    if any(a in _CHARTABLE for a in c.asset_classes):
        score += 8.0                                    # visual change opportunities
    if len(c.entities) > 4 or len(c.canonical_topic.split()) > 18:
        score -= 12.0                                   # too dense for 40s
    if c.factual_state is FactualState.rumour:
        score -= 10.0                                   # weak payoff
    return round(_clamp(score), 2)


def subscriber_potential(c: TopicCandidate, cfg: dict) -> float:
    """Would this make a viewer subscribe? Recurring, series-able topics win."""
    score = 40.0
    if c.event_type in _US_MACRO_EVENTS:
        score += 18.0                                   # recurring calendar = a series
    if c.event_type is EventType.education:
        score += 14.0                                   # demonstrates expertise
    if AssetClass.market_structure in c.asset_classes:
        score += 10.0                                   # differentiated niche authority
    if c.factual_state is FactualState.rumour:
        score -= 15.0
    return round(_clamp(score), 2)


def monetization_potential(c: TopicCandidate, cfg: dict) -> float:
    """US finance advertiser relevance + evergreen/reuse value.

    NOT a revenue estimate. Real ROI requires YouTube analytics + revenue data,
    which this phase does not have.
    """
    table = cfg["monetization_by_asset"]
    vals = [float(table.get(a.value, table["unknown"])) for a in c.asset_classes]
    score = max(vals) if vals else float(table["unknown"])
    if c.event_type is EventType.education:
        score += 8.0                                    # evergreen, reusable long-form
    if c.factual_state is FactualState.historical:
        score += 5.0
    if c.factual_state is FactualState.rumour:
        score -= 20.0                                   # brand-unsafe for sponsors
    return round(_clamp(score), 2)


def production_feasibility(c: TopicCandidate, cfg: dict) -> float:
    f = cfg["feasibility"]
    score = float(f["base"])
    if _NUMBER_RE.search(c.canonical_topic):
        score += f["has_number_bonus"]
    if any(a in _CHARTABLE for a in c.asset_classes):
        score += f["chartable_bonus"]
    if c.factual_state is FactualState.historical or c.event_type is EventType.education:
        score += f["evergreen_bonus"]
    if len(c.entities) > 4:
        score -= f["many_entities_penalty"]
    if len(c.canonical_topic.split()) > 18:
        score -= f["long_topic_penalty"]
    return round(_clamp(score), 2)


# --------------------------------------------------------------------------- #
# Aggregation
# --------------------------------------------------------------------------- #
def recompute_overall(scores: TopicScores, cfg: dict | None = None) -> float:
    """THE deterministic overall score. Called on every ranked topic, always,
    after Gemini — so the model can never set the final number."""
    cfg = cfg or load_config()
    weights: dict[str, float] = dict(cfg["weights"])
    total_w = sum(weights.values()) or 1.0

    weighted = 0.0
    for name, w in weights.items():
        field = _WEIGHT_TO_FIELD.get(name, name)
        weighted += (w / total_w) * float(getattr(scores, field, 0.0))

    overall = weighted - float(cfg.get("risk_weight", 0.6)) * scores.risk_penalty
    return round(_clamp(overall), 2)


def score_candidate(
    c: TopicCandidate, *, cfg: dict | None = None, now: datetime | None = None
) -> TopicScores:
    """Full deterministic pre-score. `risk_penalty` must already be set by
    `safety.apply()`; it is preserved here."""
    cfg = cfg or load_config()
    scores = TopicScores(
        trend_momentum=trend_momentum(c, cfg),
        audience_relevance=audience_relevance(c, cfg),
        competition_opportunity=competition_opportunity(c, cfg),
        freshness=freshness(c, cfg, now=now),
        credibility=credibility(c, cfg),
        ctr_potential=ctr_potential(c, cfg),
        retention_potential=retention_potential(c, cfg),
        subscriber_potential=subscriber_potential(c, cfg),
        monetization_potential=monetization_potential(c, cfg),
        production_feasibility=production_feasibility(c, cfg),
        risk_penalty=c.deterministic_scores.risk_penalty,
    )
    scores.overall_score = recompute_overall(scores, cfg)
    return scores


def score_all(
    candidates: list[TopicCandidate], *, now: datetime | None = None
) -> list[TopicCandidate]:
    cfg = load_config()
    for c in candidates:
        c.deterministic_scores = score_candidate(c, cfg=cfg, now=now)
    candidates.sort(key=lambda x: -x.deterministic_scores.overall_score)
    return candidates


def blend_gemini_scores(
    deterministic: TopicScores,
    gemini_values: dict[str, float | None],
    *,
    influence: float | None = None,
    cfg: dict | None = None,
) -> TopicScores:
    """Blend Gemini's qualitative judgements into the deterministic scores.

    Only fields listed in `gemini_adjustable` move, and only by `influence`.
    Deterministic-only dimensions (momentum, freshness, credibility, competition,
    risk) are copied through untouched. The overall score is then RECOMPUTED.
    """
    cfg = cfg or load_config()
    influence = ti_settings().gemini_influence if influence is None else influence
    allowed = set(cfg.get("gemini_adjustable", []))

    blended = deterministic.model_copy(deep=True)
    for field, value in gemini_values.items():
        if value is None or field not in allowed:
            continue
        det = float(getattr(blended, field))
        setattr(blended, field, round(
            _clamp(det * (1.0 - influence) + float(value) * influence), 2
        ))
    blended.overall_score = recompute_overall(blended, cfg)
    return blended


def explain(scores: TopicScores, cfg: dict | None = None) -> str:
    """Human-readable weight contribution breakdown — persisted with the decision."""
    cfg = cfg or load_config()
    weights = dict(cfg["weights"])
    total_w = sum(weights.values()) or 1.0
    parts = []
    for name, w in sorted(weights.items(), key=lambda kv: -kv[1]):
        field = _WEIGHT_TO_FIELD.get(name, name)
        val = float(getattr(scores, field, 0.0))
        parts.append(f"{name}={val:.1f}x{w / total_w:.2f}={val * w / total_w:.1f}")
    risk_w = float(cfg.get("risk_weight", 0.6))
    parts.append(f"risk_penalty=-{scores.risk_penalty:.1f}x{risk_w:.2f}"
                 f"={-scores.risk_penalty * risk_w:.1f}")
    return " | ".join(parts) + f" => overall={scores.overall_score:.2f}"
