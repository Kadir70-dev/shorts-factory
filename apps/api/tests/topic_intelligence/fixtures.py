"""
Realistic fixture signals covering the seven scenarios the phase must handle:

  1. an FOMC decision                 (confirmed, primary source)
  2. a CPI release                    (scheduled forecast + confirmed release)
  3. an Nvidia earnings story         (equities/AI, wire + YouTube competition)
  4. a Bitcoin price event            (crypto price move)
  5. an HFT educational evergreen     (market microstructure, no news)
  6. an unsupported viral Reddit rumour
  7. a duplicate syndicated news story (same wire copy from many outlets)

All timestamps are relative to a fixed NOW so tests are deterministic.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.topic_intelligence.models import RawTrendSignal

NOW = datetime(2026, 7, 28, 18, 0, 0, tzinfo=timezone.utc)


def _ago(hours: float) -> datetime:
    return NOW - timedelta(hours=hours)


def _ahead(hours: float) -> datetime:
    return NOW + timedelta(hours=hours)


# --------------------------------------------------------------------------- #
# 1. FOMC decision — confirmed, primary source + wire + YouTube competition
# --------------------------------------------------------------------------- #
FOMC_SIGNALS = [
    RawTrendSignal(
        provider="finance_news",
        external_id="fed-press-2026-07-28",
        title="Federal Reserve officially cuts the federal funds rate by 25 basis points",
        summary=(
            "The FOMC voted to lower the target range for the federal funds rate to "
            "4.00-4.25 percent, citing continued disinflation."
        ),
        url="https://www.federalreserve.gov/newsevents/pressreleases/monetary20260728a.htm",
        published_at=_ago(2),
        collected_at=NOW,
        region="US",
        raw_metrics={"syndication_group": "fomc1", "syndication_count": 1,
                     "publishers": ["federalreserve.gov"], "publisher_count": 1},
        author_or_channel="federalreserve.gov",
    ),
    RawTrendSignal(
        provider="finance_news",
        external_id="reuters-fomc-cut",
        title="Fed cuts rates as Powell announces lower interest rates for the first time this year",
        summary="Reuters reports the Federal Reserve reduced rates by a quarter point.",
        url="https://www.reuters.com/markets/us/fed-cuts-rates-2026-07-28/",
        published_at=_ago(1.5),
        collected_at=NOW,
        region="US",
        raw_metrics={"syndication_group": "fomc2", "syndication_count": 3,
                     "publishers": ["reuters.com", "msn.com", "yahoo.com"],
                     "publisher_count": 3},
        author_or_channel="reuters.com",
    ),
    RawTrendSignal(
        provider="youtube",
        external_id="yt_fomc_1",
        title="FOMC rate reduction explained in 60 seconds",
        summary="What the Fed just did and what it means for your mortgage.",
        url="https://www.youtube.com/watch?v=yt_fomc_1",
        published_at=_ago(1),
        collected_at=NOW,
        region="US",
        engagement={"views": 48000.0, "likes": 2100.0, "comments": 310.0},
        raw_metrics={"channel_subscribers": 120000.0, "video_id": "yt_fomc_1",
                     "channel_id": "ch_a", "query": "federal reserve interest rates"},
        author_or_channel="Macro Daily",
    ),
    RawTrendSignal(
        provider="youtube",
        external_id="yt_fomc_2",
        title="Fed cuts rates — what happens next",
        summary="Breaking down the FOMC decision.",
        url="https://www.youtube.com/watch?v=yt_fomc_2",
        published_at=_ago(3),
        collected_at=NOW,
        region="US",
        engagement={"views": 15000.0, "likes": 700.0, "comments": 90.0},
        raw_metrics={"channel_subscribers": 900000.0, "video_id": "yt_fomc_2",
                     "channel_id": "ch_b", "query": "federal reserve interest rates"},
        author_or_channel="Big Finance TV",
    ),
]

# --------------------------------------------------------------------------- #
# 2. CPI — a scheduled release (forecast) AND, separately, the confirmed print.
#    These must NEVER be merged into one cluster.
# --------------------------------------------------------------------------- #
CPI_FORECAST_SIGNALS = [
    RawTrendSignal(
        provider="economic_calendar",
        external_id="te:CPI:2026-08-12",
        title="Inflation Rate CPI scheduled — forecast 2.9%",
        summary=(
            "US economic event. Importance: high. Previous: 3.1%. Forecast: 2.9%. "
            "Actual: not released."
        ),
        url="https://www.bls.gov/cpi/",
        published_at=_ahead(36),
        collected_at=NOW,
        region="US",
        raw_metrics={
            "event_name": "Inflation Rate CPI", "importance": "high",
            "status": "scheduled", "previous_value": "3.1%",
            "forecast_value": "2.9%", "actual_value": None,
            "affected_assets": ["macro", "rates", "equities"],
            "scheduled_at": _ahead(36).isoformat(), "source": "tradingeconomics",
        },
        author_or_channel="tradingeconomics",
        source_credibility=0.95,
    ),
]

CPI_CONFIRMED_SIGNALS = [
    RawTrendSignal(
        provider="finance_news",
        external_id="bls-cpi-release",
        title="CPI report released: consumer price index came in at 2.8 percent",
        summary="The Bureau of Labor Statistics reported annual CPI of 2.8%.",
        url="https://www.bls.gov/news.release/cpi.nr0.htm",
        published_at=_ago(5),
        collected_at=NOW,
        region="US",
        raw_metrics={"syndication_group": "cpi1", "syndication_count": 1,
                     "publishers": ["bls.gov"], "publisher_count": 1},
        author_or_channel="bls.gov",
    ),
]

# --------------------------------------------------------------------------- #
# 3. Nvidia earnings
# --------------------------------------------------------------------------- #
NVDA_SIGNALS = [
    RawTrendSignal(
        provider="finance_news",
        external_id="nvda-earnings-wire",
        title="Nvidia reported record data center revenue in quarterly results",
        summary=(
            "Nvidia posted quarterly revenue above consensus, driven by AI data "
            "center demand."
        ),
        url="https://www.reuters.com/technology/nvidia-results-2026-07-27/",
        published_at=_ago(8),
        collected_at=NOW,
        region="US",
        raw_metrics={"syndication_group": "nvda1", "syndication_count": 4,
                     "publishers": ["reuters.com", "cnbc.com", "yahoo.com", "msn.com"],
                     "publisher_count": 4},
        author_or_channel="reuters.com",
    ),
    RawTrendSignal(
        provider="youtube",
        external_id="yt_nvda_1",
        title="Nvidia earnings: the AI number nobody noticed",
        summary="Breaking down NVDA quarterly results.",
        url="https://www.youtube.com/watch?v=yt_nvda_1",
        published_at=_ago(6),
        collected_at=NOW,
        region="US",
        engagement={"views": 92000.0, "likes": 5400.0, "comments": 820.0},
        raw_metrics={"channel_subscribers": 45000.0, "video_id": "yt_nvda_1",
                     "channel_id": "ch_c", "query": "nvidia earnings AI"},
        author_or_channel="Chip Watch",
    ),
]

# --------------------------------------------------------------------------- #
# 4. Bitcoin price event
# --------------------------------------------------------------------------- #
BITCOIN_SIGNALS = [
    RawTrendSignal(
        provider="finance_news",
        external_id="btc-ath",
        title="Bitcoin surges to a record high above $148,000",
        summary="Bitcoin reported a new all-time high amid spot ETF inflows.",
        url="https://www.coindesk.com/markets/2026/07/28/bitcoin-record-high/",
        published_at=_ago(4),
        collected_at=NOW,
        region="US",
        raw_metrics={"syndication_group": "btc1", "syndication_count": 2,
                     "publishers": ["coindesk.com", "cnbc.com"], "publisher_count": 2},
        author_or_channel="coindesk.com",
    ),
    RawTrendSignal(
        provider="youtube",
        external_id="yt_btc_1",
        title="Bitcoin all-time high — what actually drove it",
        summary="ETF flows and the BTC record.",
        url="https://www.youtube.com/watch?v=yt_btc_1",
        published_at=_ago(3),
        collected_at=NOW,
        region="US",
        engagement={"views": 210000.0, "likes": 12000.0, "comments": 1900.0},
        raw_metrics={"channel_subscribers": 88000.0, "video_id": "yt_btc_1",
                     "channel_id": "ch_d", "query": "bitcoin price"},
        author_or_channel="Crypto Desk",
    ),
]

# --------------------------------------------------------------------------- #
# 5. HFT educational evergreen
# --------------------------------------------------------------------------- #
HFT_SIGNALS = [
    RawTrendSignal(
        provider="youtube",
        external_id="yt_hft_1",
        title="How high frequency trading actually works, explained simply",
        summary=(
            "A guide to latency arbitrage, colocation and the order book for "
            "retail traders."
        ),
        url="https://www.youtube.com/watch?v=yt_hft_1",
        published_at=_ago(30),
        collected_at=NOW,
        region="US",
        engagement={"views": 64000.0, "likes": 4100.0, "comments": 430.0},
        raw_metrics={"channel_subscribers": 22000.0, "video_id": "yt_hft_1",
                     "channel_id": "ch_e", "query": "high frequency trading explained"},
        author_or_channel="Market Plumbing",
    ),
]

# --------------------------------------------------------------------------- #
# 6. Unsupported viral Reddit rumour — high engagement, zero verification
# --------------------------------------------------------------------------- #
REDDIT_RUMOUR_SIGNALS = [
    RawTrendSignal(
        provider="reddit",
        external_id="rd_rumour_1",
        title="Rumor: sources say a major bank is about to collapse next week",
        summary="Unconfirmed, allegedly from someone on the trading desk.",
        url="https://www.reddit.com/r/wallstreetbets/comments/rd_rumour_1/",
        published_at=_ago(6),
        collected_at=NOW,
        engagement={"score": 24000.0, "comments": 3100.0, "awards": 40.0},
        raw_metrics={"subreddit": "wallstreetbets", "upvote_ratio": 0.93,
                     "cross_subreddit_spread": 3, "is_self": True},
        author_or_channel="r/wallstreetbets",
    ),
    RawTrendSignal(
        provider="reddit",
        external_id="rd_rumour_2",
        title="Rumour about the bank collapse — leaked screenshots inside",
        summary="Supposedly leaked, unconfirmed.",
        url="https://www.reddit.com/r/stocks/comments/rd_rumour_2/",
        published_at=_ago(5),
        collected_at=NOW,
        engagement={"score": 9000.0, "comments": 1400.0, "awards": 5.0},
        raw_metrics={"subreddit": "stocks", "upvote_ratio": 0.71,
                     "cross_subreddit_spread": 3, "is_self": True},
        author_or_channel="r/stocks",
    ),
]

# --------------------------------------------------------------------------- #
# 7. Duplicate syndicated news — ONE story, six outlets
# --------------------------------------------------------------------------- #
SYNDICATED_SIGNALS = [
    RawTrendSignal(
        provider="finance_news",
        external_id=f"synd-{i}",
        title="Treasury announced a new debt buyback program, officials reported",
        summary="The US Treasury announced a debt buyback operation schedule.",
        url=url,
        published_at=_ago(7),
        collected_at=NOW,
        region="US",
        raw_metrics={"syndication_group": "synd1", "syndication_count": 6,
                     "publishers": ["home.treasury.gov"], "publisher_count": 1},
        author_or_channel=url.split("/")[2],
    )
    for i, url in enumerate([
        "https://home.treasury.gov/news/press-releases/jy2026",
        "https://www.reuters.com/markets/us/treasury-buyback-2026/",
        "https://www.cnbc.com/2026/07/28/treasury-buyback.html",
        "https://www.msn.com/en-us/money/treasury-buyback",
        "https://finance.yahoo.com/news/treasury-buyback-2026",
        "https://www.marketwatch.com/story/treasury-buyback-2026",
    ])
]

# --------------------------------------------------------------------------- #
# An unsafe-advice topic that the finance safety gate must block outright.
# --------------------------------------------------------------------------- #
UNSAFE_SIGNALS = [
    RawTrendSignal(
        provider="reddit",
        external_id="rd_unsafe_1",
        title="Buy now: this guaranteed risk-free trade will double your money",
        summary="Load up on this ticker before it explodes. To the moon.",
        url="https://www.reddit.com/r/wallstreetbets/comments/rd_unsafe_1/",
        published_at=_ago(2),
        collected_at=NOW,
        engagement={"score": 40000.0, "comments": 5000.0},
        raw_metrics={"subreddit": "wallstreetbets", "upvote_ratio": 0.97,
                     "cross_subreddit_spread": 1},
        author_or_channel="r/wallstreetbets",
    ),
]


ALL_SIGNALS = (
    FOMC_SIGNALS + CPI_FORECAST_SIGNALS + CPI_CONFIRMED_SIGNALS + NVDA_SIGNALS
    + BITCOIN_SIGNALS + HFT_SIGNALS + REDDIT_RUMOUR_SIGNALS + SYNDICATED_SIGNALS
)
