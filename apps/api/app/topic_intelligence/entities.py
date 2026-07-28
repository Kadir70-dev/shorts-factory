"""
Finance domain vocabulary: ticker/company aliases, event lexicon, asset-class map,
source-tier classification and the factual-state lexicon.

Kept as plain data so it is reviewable and testable without a model. This is the
difference between "NVDA", "Nvidia" and "Jensen Huang's company" landing in the
same cluster.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

from .models import AssetClass, EventType, FactualState, SourceTier

# --------------------------------------------------------------------------- #
# Company / ticker aliases  ->  canonical ticker
# --------------------------------------------------------------------------- #
TICKER_ALIASES: dict[str, str] = {}


def _alias(ticker: str, *names: str) -> None:
    TICKER_ALIASES[ticker.lower()] = ticker
    for n in names:
        TICKER_ALIASES[n.lower()] = ticker


_alias("NVDA", "nvidia", "nvidia corp", "nvidia corporation")
_alias("AAPL", "apple", "apple inc")
_alias("MSFT", "microsoft", "microsoft corp")
_alias("GOOGL", "google", "alphabet", "alphabet inc")
_alias("AMZN", "amazon", "amazon.com")
_alias("META", "meta", "meta platforms", "facebook")
_alias("TSLA", "tesla", "tesla inc")
_alias("AMD", "advanced micro devices")
_alias("INTC", "intel", "intel corp")
_alias("AVGO", "broadcom")
_alias("TSM", "tsmc", "taiwan semiconductor")
_alias("JPM", "jpmorgan", "jp morgan", "jpmorgan chase")
_alias("GS", "goldman sachs", "goldman")
_alias("BRK.B", "berkshire", "berkshire hathaway")
_alias("SPY", "s&p 500", "sp500", "s and p 500", "spx")
_alias("QQQ", "nasdaq 100", "nasdaq100")
_alias("BTC", "bitcoin", "btcusd", "btc-usd")
_alias("ETH", "ethereum", "ether", "ethusd")
_alias("XAU", "gold", "gold price", "bullion")
_alias("WTI", "crude oil", "oil price", "wti crude", "west texas intermediate")
_alias("BRENT", "brent crude", "brent oil")
_alias("DXY", "dollar index", "us dollar index", "greenback")
_alias("EURUSD", "euro dollar", "eur/usd", "euro")
_alias("USDJPY", "dollar yen", "usd/jpy", "yen")

# Bare uppercase tokens that are NOT tickers (avoids "CPI"/"GDP" becoming symbols).
_NOT_TICKERS = {
    "CPI", "PCE", "GDP", "FOMC", "ISM", "PPI", "USA", "US", "AI", "ETF", "IPO",
    "CEO", "CFO", "SEC", "FED", "BLS", "NFP", "QE", "QT", "YOY", "MOM", "EPS",
    "API", "HFT", "NYSE", "IMF", "OPEC", "EU", "UK", "Q1", "Q2", "Q3", "Q4",
}
_TICKER_RE = re.compile(r"\b\$?([A-Z]{2,5})\b")

# --------------------------------------------------------------------------- #
# Named non-ticker entities worth clustering on
# --------------------------------------------------------------------------- #
ENTITY_ALIASES: dict[str, str] = {
    "the fed": "federal reserve",
    "fed": "federal reserve",
    "federal reserve": "federal reserve",
    # The FOMC *is* the Fed's policy committee — same subject. The distinction
    # between a decision and the minutes lives in EVENT_LEXICON, not here.
    "fomc": "federal reserve",
    "jerome powell": "jerome powell",
    "powell": "jerome powell",
    "chair powell": "jerome powell",
    "treasury": "us treasury",
    "us treasury": "us treasury",
    "bls": "bureau of labor statistics",
    "bureau of labor statistics": "bureau of labor statistics",
    "sec": "sec",
    "cftc": "cftc",
    "ecb": "ecb",
    "bank of japan": "bank of japan",
    "boj": "bank of japan",
    "opec": "opec",
    "jensen huang": "NVDA",
    "warren buffett": "warren buffett",
    "elon musk": "elon musk",
}

# --------------------------------------------------------------------------- #
# Event lexicon — ordered: the FIRST match wins, so specific beats generic.
# --------------------------------------------------------------------------- #
EVENT_LEXICON: list[tuple[EventType, tuple[str, ...]]] = [
    (EventType.fomc_minutes, ("fomc minutes", "fed minutes", "meeting minutes")),
    (EventType.fed_decision, (
        "fomc", "fed decision", "rate decision", "interest rate decision",
        "rate cut", "rate hike", "fed cuts", "fed raises", "federal funds rate",
        "powell announces", "fed holds",
    )),
    (EventType.cpi, ("cpi", "consumer price index", "inflation report", "core cpi")),
    (EventType.pce, ("pce", "personal consumption expenditures", "core pce")),
    (EventType.nonfarm_payrolls, (
        "nonfarm payroll", "non-farm payroll", "nfp", "jobs report", "payrolls",
    )),
    (EventType.jobless_claims, ("jobless claims", "initial claims", "continuing claims")),
    (EventType.unemployment, ("unemployment rate", "unemployment data", "labor market report")),
    (EventType.gdp, ("gdp", "gross domestic product")),
    (EventType.retail_sales, ("retail sales",)),
    (EventType.ism, ("ism", "purchasing managers", "pmi")),
    (EventType.treasury, (
        "treasury yield", "10-year", "10 year yield", "bond auction",
        "treasury auction", "yield curve", "debt ceiling",
    )),
    (EventType.earnings, (
        "earnings", "quarterly results", "q1 results", "q2 results", "q3 results",
        "q4 results", "guidance", "revenue beat", "eps",
    )),
    (EventType.regulation, (
        "sec approves", "sec sues", "regulator", "lawsuit", "etf approval",
        "regulation", "ban", "investigation",
    )),
    (EventType.price_move, (
        "surges", "plunges", "rallies", "crashes", "all-time high", "record high",
        "selloff", "sell-off", "tumbles", "jumps", "slides", "soars", "hits $",
    )),
    (EventType.education, (
        "explained", "how does", "what is", "guide to", "beginners", "why does",
        "how it works", "introduction to", "basics of",
    )),
]

# --------------------------------------------------------------------------- #
# Asset classes
# --------------------------------------------------------------------------- #
ASSET_LEXICON: list[tuple[AssetClass, tuple[str, ...]]] = [
    (AssetClass.crypto, (
        "bitcoin", "btc", "ethereum", "crypto", "digital asset", "stablecoin",
        "altcoin", "blockchain", "spot etf",
    )),
    (AssetClass.gold, ("gold", "bullion", "xau", "precious metal")),
    (AssetClass.oil, ("oil", "crude", "wti", "brent", "opec", "barrel")),
    (AssetClass.forex, (
        "forex", "fx", "dollar index", "dxy", "euro", "yen", "currency", "eurusd",
        "usdjpy",
    )),
    (AssetClass.rates, (
        "interest rate", "rate cut", "rate hike", "treasury", "yield", "bond",
        "federal funds", "fomc", "duration",
    )),
    (AssetClass.macro, (
        "cpi", "inflation", "gdp", "payroll", "payrolls", "unemployment",
        "recession", "pce", "retail sales", "ism", "jobless", "economy",
        "economic", "fed", "tariff", "tariffs", "trade war", "stimulus",
        "debt ceiling", "budget deficit", "consumer spending",
    )),
    (AssetClass.ai_tech, (
        "ai", "artificial intelligence", "machine learning", "gpu", "data center",
        "llm", "nvidia", "semiconductor", "chip",
    )),
    (AssetClass.market_structure, (
        "high-frequency", "high frequency", "hft", "market maker", "order flow",
        "payment for order flow", "pfof", "dark pool", "latency arbitrage",
        "market microstructure", "bid-ask", "order book", "colocation",
        "quant", "quantitative trading", "algorithmic trading", "slippage",
        "liquidity provider", "tick size",
    )),
    (AssetClass.equities, (
        "stock", "shares", "s&p", "nasdaq", "dow", "equity", "earnings", "ipo",
        "buyback", "index fund",
    )),
]

# --------------------------------------------------------------------------- #
# Factual state lexicon
# --------------------------------------------------------------------------- #
CONFIRMED_MARKERS = (
    "officially", "announced", "announces", "confirmed", "released", "reported",
    "cut rates", "cuts rates", "raised rates", "raises rates", "has cut",
    "has raised", "came in at", "rose to", "fell to", "posted", "delivered",
    "voted to", "decided to", "actual", "just cut", "just raised", "lowered",
    "reduced", "surges to", "plunges to", "hits a record", "hit a record",
)
FORECAST_MARKERS = (
    "forecast", "consensus", "estimate", "scheduled", "due", "ahead of",
    "preview", "expected to be released", "will report", "set for",
)
EXPECTATION_MARKERS = (
    "expects", "expected", "markets expect", "traders bet", "odds of", "pricing in",
    "anticipate", "likely to", "could", "may ", "might ", "on track to", "bets",
    "speculation",
)
OPINION_MARKERS = (
    "why ", "opinion", "analysis", "here's what", "what it means", "should you",
    "my take", "prediction", "i think", "outlook", "warns", "says",
)
RUMOUR_MARKERS = (
    "rumor", "rumour", "unconfirmed", "allegedly", "sources say", "leaked",
    "insider says", "heard that", "apparently", "supposedly",
)
HISTORICAL_MARKERS = (
    "explained", "how it works", "what is", "history of", "in 2008", "back in",
    "guide", "basics", "the story of", "lessons from",
)

# --------------------------------------------------------------------------- #
# Source credibility tiers by host
# --------------------------------------------------------------------------- #
PRIMARY_HOSTS = {
    "federalreserve.gov", "bls.gov", "treasury.gov", "home.treasury.gov",
    "sec.gov", "bea.gov", "census.gov", "cftc.gov", "whitehouse.gov",
    "ecb.europa.eu", "imf.org", "newyorkfed.org", "eia.gov",
}
WIRE_HOSTS = {
    "reuters.com", "apnews.com", "bloomberg.com", "wsj.com", "ft.com",
    "dowjones.com", "marketwatch.com", "barrons.com", "cnbc.com",
    "feeds.a.dj.com",
}
REPUTABLE_HOSTS = {
    "nytimes.com", "washingtonpost.com", "economist.com", "axios.com",
    "businessinsider.com", "forbes.com", "fortune.com", "investopedia.com",
    "morningstar.com", "seekingalpha.com", "coindesk.com", "theblock.co",
    "yahoo.com", "finance.yahoo.com", "nasdaq.com", "spglobal.com",
}
SOCIAL_HOSTS = {
    "reddit.com", "old.reddit.com", "x.com", "twitter.com", "t.co",
    "youtube.com", "youtu.be",
}
AGGREGATOR_HOSTS = {
    "news.google.com", "msn.com", "flipboard.com", "smartnews.com",
    "prnewswire.com", "businesswire.com", "globenewswire.com", "accesswire.com",
}


def compile_markers(markers: tuple[str, ...]) -> re.Pattern[str]:
    """Whole-token alternation for a marker list.

    Substring matching is a trap here: `"stock" in "dwindling stockpiles"` is True,
    and that one false positive is enough to route a war story into the equities
    bucket. The lookarounds work for markers that end in punctuation too
    (e.g. "hits $"), which a plain \\b cannot do.
    """
    alt = "|".join(re.escape(m) for m in sorted(markers, key=len, reverse=True))
    return re.compile(rf"(?<!\w)(?:{alt})(?!\w)", re.IGNORECASE)


ASSET_PATTERNS: list[tuple[AssetClass, re.Pattern[str]]] = [
    (a, compile_markers(m)) for a, m in ASSET_LEXICON
]
EVENT_PATTERNS: list[tuple[EventType, re.Pattern[str]]] = [
    (e, compile_markers(m)) for e, m in EVENT_LEXICON
]


def _build_alias_patterns() -> list[tuple[re.Pattern[str], str]]:
    """Longest-alias-first phrase patterns mapping every alias to ONE canonical
    slug token ("federal reserve"/"fed"/"fomc" -> "federal_reserve").

    Phrase-level folding is what lets multi-word names survive tokenization: token
    -by-token mapping can never turn "Federal Reserve" and "Fed" into the same
    thing, because one is two tokens and the other is one.
    """
    merged: dict[str, str] = {}
    for alias, canon in ENTITY_ALIASES.items():
        merged[alias] = canon.replace(" ", "_").replace(".", "")
    for alias, ticker in TICKER_ALIASES.items():
        merged.setdefault(alias, ticker.replace(".", "").lower())
    out = []
    for alias in sorted(merged, key=len, reverse=True):
        out.append((re.compile(r"\b" + re.escape(alias) + r"\b"), merged[alias]))
    return out


ALIAS_PATTERNS = _build_alias_patterns()


def fold_aliases(text: str) -> str:
    """Lowercase `text` with every known alias replaced by its canonical slug."""
    out = text.lower()
    for pattern, canon in ALIAS_PATTERNS:
        out = pattern.sub(canon, out)
    return out


def host_of(url: str | None) -> str:
    if not url:
        return ""
    try:
        h = (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""
    return h[4:] if h.startswith("www.") else h


def classify_source(url: str | None, provider: str) -> SourceTier:
    """Host-based tiering. Social providers are pinned to `social` regardless of
    engagement — popularity is never evidence."""
    # YouTube is included on purpose: a competitor's video is an interest signal,
    # never a source that makes a claim true.
    if provider in {"reddit", "x", "youtube"}:
        return SourceTier.social
    h = host_of(url)
    if not h:
        return SourceTier.unknown
    for hosts, tier in (
        (PRIMARY_HOSTS, SourceTier.primary),
        (WIRE_HOSTS, SourceTier.wire),
        (REPUTABLE_HOSTS, SourceTier.reputable),
        (AGGREGATOR_HOSTS, SourceTier.aggregator),
        (SOCIAL_HOSTS, SourceTier.social),
    ):
        if h in hosts or any(h.endswith("." + x) for x in hosts):
            return tier
    return SourceTier.unknown


# --------------------------------------------------------------------------- #
# Extraction helpers
# --------------------------------------------------------------------------- #
def extract_tickers(text: str) -> list[str]:
    """Alias hits first (word-boundary safe), then bare $TICKER / ALLCAPS tokens."""
    lowered = text.lower()
    found: list[str] = []
    for alias, ticker in TICKER_ALIASES.items():
        if len(alias) <= 4 and alias.isalpha():
            pat = r"\b" + re.escape(alias) + r"\b"
            hit = re.search(pat, lowered) is not None
        else:
            hit = alias in lowered
        if hit and ticker not in found:
            found.append(ticker)
    for m in _TICKER_RE.finditer(text):
        tok = m.group(1)
        if tok in _NOT_TICKERS:
            continue
        canon = TICKER_ALIASES.get(tok.lower())
        if canon and canon not in found:
            found.append(canon)
    return found


def extract_entities(text: str) -> list[str]:
    lowered = text.lower()
    out: list[str] = []
    for alias, canon in ENTITY_ALIASES.items():
        if re.search(r"\b" + re.escape(alias) + r"\b", lowered) and canon not in out:
            out.append(canon)
    return out


def detect_event_type(text: str) -> EventType:
    """First match wins — EVENT_LEXICON is ordered specific-before-generic."""
    for etype, pattern in EVENT_PATTERNS:
        if pattern.search(text):
            return etype
    return EventType.other


def detect_asset_classes(text: str) -> list[AssetClass]:
    out = [a for a, pattern in ASSET_PATTERNS if pattern.search(text)]
    return out or [AssetClass.unknown]


_STATE_PATTERNS: tuple[tuple[FactualState, re.Pattern[str]], ...] = (
    # Order matters: the strongest hedge wins, so "markets expect the Fed to cut"
    # is an EXPECTATION even though it contains "cut".
    (FactualState.rumour, compile_markers(RUMOUR_MARKERS)),
    (FactualState.expectation, compile_markers(EXPECTATION_MARKERS)),
    (FactualState.forecast, compile_markers(FORECAST_MARKERS)),
    (FactualState.historical, compile_markers(HISTORICAL_MARKERS)),
    (FactualState.confirmed, compile_markers(CONFIRMED_MARKERS)),
    (FactualState.opinion, compile_markers(OPINION_MARKERS)),
)


def detect_factual_state(text: str, provider: str) -> FactualState:
    # A YouTube title is COMPETING CONTENT, not a claim about the world. Letting
    # "…explained" turn a competitor video into a HISTORICAL claim would split it
    # away from the very story whose competition we are trying to measure.
    if provider == "youtube":
        return FactualState.unknown
    for state, pattern in _STATE_PATTERNS:
        if pattern.search(text):
            return state
    # Unlabelled social chatter is never promoted to fact.
    if provider in {"reddit", "x"}:
        return FactualState.opinion
    return FactualState.unknown
