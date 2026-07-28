"""
Topic-intelligence configuration.

Deliberately a SEPARATE BaseSettings from `app.config.Settings` so Phase 2A can be
added, flagged off, or removed without touching the frozen pipeline's config. Same
`.env` file, `extra="ignore"`, so both classes coexist happily.

Every external provider is independently switchable. Nothing here is required for
the existing video pipeline to run.
"""
from __future__ import annotations

import functools
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from ..config import CONFIG_DIR, DATA_DIR

DEFAULT_SUBREDDITS = (
    "stocks,investing,wallstreetbets,options,SecurityAnalysis,economics,"
    "finance,algotrading,quant,Bitcoin,CryptoCurrency"
)

# Free, public finance RSS endpoints, all verified live and parseable. Primary
# sources (Fed, BLS) first, then wire/market coverage. Deliberately conservative:
# no aggregator spam. Override the whole list with TI_NEWS_RSS_FEEDS.
#
# NOTE: primary-source feeds publish infrequently by nature — the Fed press feed
# can be quiet for a week. That is why the staleness check is per-provider and
# advisory, not a failure.
DEFAULT_NEWS_RSS = (
    "https://www.federalreserve.gov/feeds/press_all.xml,"
    "https://www.federalreserve.gov/feeds/press_monetary.xml,"
    "https://www.bls.gov/feed/bls_latest.rss,"
    "https://www.cnbc.com/id/10000664/device/rss/rss.html,"      # CNBC markets
    "https://www.cnbc.com/id/10000113/device/rss/rss.html,"      # CNBC economy
    "https://www.cnbc.com/id/20910258/device/rss/rss.html,"      # CNBC investing
    "https://www.marketwatch.com/rss/topstories"
)


class TopicIntelligenceSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ---------------- master switches ----------------
    ti_enabled: bool = True
    ti_region: str = "US"
    ti_default_channel: str = "usa_trading"

    # ---------------- Gemini (the ranking/reasoning brain) ----------------
    gemini_api_key: str = ""
    # Stable, production Flash-class model. NEVER hardcode a preview model — this is
    # the only place the model name lives and it is env-overridable.
    gemini_model: str = "gemini-2.5-flash"
    gemini_ranker_enabled: bool = True
    gemini_grounding_enabled: bool = True
    gemini_max_candidates: int = 30
    gemini_max_retries: int = 3
    gemini_daily_budget_usd: float = 1.0
    gemini_timeout_s: float = 60.0
    # Public list-price per million tokens (USD) for cost accounting only. Update
    # from the pricing page; wrong values affect budget math, never correctness.
    gemini_input_cost_per_mtok: float = 0.30
    gemini_output_cost_per_mtok: float = 2.50
    # How much Gemini may move a QUALITATIVE sub-score away from the deterministic
    # value (0 = Gemini ignored, 1 = Gemini fully trusted). Deterministic-only
    # dimensions are never blended at all. See scoring.py.
    gemini_influence: float = 0.5

    # ---------------- Google Trends ----------------
    # OFF by default: there is no free, officially supported public Trends API.
    # Enabling it requires you to supply an approved connector (see docs).
    google_trends_enabled: bool = False
    google_trends_region: str = "US"
    google_trends_base_url: str = ""       # your approved connector endpoint
    google_trends_api_key: str = ""

    # ---------------- YouTube Data API ----------------
    youtube_data_api_key: str = ""
    youtube_trends_enabled: bool = True
    youtube_region: str = "US"
    youtube_relevance_language: str = "en"
    youtube_max_queries: int = 8
    youtube_results_per_query: int = 25

    # ---------------- Reddit ----------------
    reddit_enabled: bool = False
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = ""
    ti_subreddits: str = DEFAULT_SUBREDDITS
    reddit_posts_per_sub: int = 25

    # ---------------- X / Twitter ----------------
    # Requires a paid plan for meaningful recent-search access. Auto-disabled when
    # the bearer token is missing — never a hard dependency.
    x_trends_enabled: bool = False
    x_bearer_token: str = ""
    x_max_results: int = 50

    # ---------------- Economic calendar ----------------
    economic_calendar_enabled: bool = False
    economic_calendar_provider: str = ""   # "tradingeconomics" | "finnhub" | "generic_json"
    economic_calendar_api_key: str = ""
    economic_calendar_base_url: str = ""

    # ---------------- Finance news ----------------
    finance_news_enabled: bool = True
    news_api_key: str = ""                 # optional; RSS works with no key
    ti_news_rss_feeds: str = DEFAULT_NEWS_RSS
    news_articles_per_feed: int = 25

    # ---------------- funnel sizing (cost control) ----------------
    ti_lookback_hours: int = 48
    ti_max_raw_signals: int = 500
    ti_max_clusters: int = 40
    ti_max_finalists: int = 15
    ti_min_eligible_candidates: int = 1
    ti_min_source_count: int = 1
    # Reject candidates with no asset class, ticker or financial event. General
    # news feeds carry politics/war/court stories that are safe but off-beat.
    ti_require_finance_relevance: bool = True

    # ---------------- dedup windows ----------------
    topic_exact_dedup_days: int = 365
    topic_semantic_dedup_days: int = 90
    topic_similarity_threshold: float = 0.86
    angle_similarity_threshold: float = 0.90
    # Cluster merge threshold. Deliberately LOWER than the dedup thresholds: here
    # we are merging different wordings of ONE story, not deciding whether two
    # stories are the same. See clustering.signal_similarity for the blend.
    topic_cluster_threshold: float = 0.55

    # ---------------- resilience ----------------
    ti_provider_timeout_s: float = 20.0
    ti_http_retries: int = 3
    ti_http_backoff_base_s: float = 0.5
    ti_http_backoff_max_s: float = 8.0
    ti_cache_ttl_s: float = 900.0
    ti_circuit_failure_threshold: int = 3
    ti_circuit_reset_s: float = 300.0
    ti_stale_after_hours: float = 12.0

    # ---------------- integration ----------------
    # When true, `select`/`run` enqueue the winning topic into the EXISTING Director
    # pipeline. Default OFF: Phase 2A ships as a decision engine, not a producer.
    ti_auto_enqueue: bool = False
    ti_scoring_config: Path = CONFIG_DIR / "topic_intelligence" / "scoring.yaml"
    ti_state_dir: Path = DATA_DIR / "topic_intelligence"
    ranking_version: str = "2a.1"
    prompt_version: str = "ti-rank-v1"

    # ---------------- derived helpers ----------------
    @field_validator("gemini_influence")
    @classmethod
    def _clamp_influence(cls, v: float) -> float:
        return max(0.0, min(1.0, v))

    @property
    def subreddits(self) -> list[str]:
        return [s.strip() for s in self.ti_subreddits.split(",") if s.strip()]

    @property
    def news_feeds(self) -> list[str]:
        return [s.strip() for s in self.ti_news_rss_feeds.split(",") if s.strip()]

    # A provider is *usable* only when it is both enabled AND credentialed. These
    # properties are the single source of truth — providers never re-derive them.
    @property
    def youtube_usable(self) -> bool:
        return bool(self.youtube_trends_enabled and self.youtube_data_api_key.strip())

    @property
    def reddit_usable(self) -> bool:
        return bool(
            self.reddit_enabled
            and self.reddit_client_id.strip()
            and self.reddit_client_secret.strip()
        )

    @property
    def x_usable(self) -> bool:
        return bool(self.x_trends_enabled and self.x_bearer_token.strip())

    @property
    def google_trends_usable(self) -> bool:
        return bool(self.google_trends_enabled and self.google_trends_base_url.strip())

    @property
    def economic_calendar_usable(self) -> bool:
        return bool(
            self.economic_calendar_enabled and self.economic_calendar_provider.strip()
        )

    @property
    def finance_news_usable(self) -> bool:
        return bool(self.finance_news_enabled and (self.news_feeds or self.news_api_key))

    @property
    def gemini_usable(self) -> bool:
        return bool(self.gemini_api_key.strip())

    @property
    def grounding_usable(self) -> bool:
        return bool(self.gemini_grounding_enabled and self.gemini_usable)


@functools.lru_cache
def ti_settings() -> TopicIntelligenceSettings:
    return TopicIntelligenceSettings()
