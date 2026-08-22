#!/usr/bin/env python3
"""
FOREX EXPLAINED · Episode 1 — "How The $9.6 Trillion-A-Day Currency Market
Actually Works"

Single-source-of-truth authoring script for one long-form (16:9, ~5 minute)
K70 Finance explainer. Same pattern as `build_bitcoin_ep01.py`: the narration,
per-beat visual plan, chart data and source citations are authored ONCE in
`BEATS` below and emitted as a validated SceneGraph plus supporting docs.

`threejs_provenance`, `motion_graphics_provenance`, `ai_broll_provenance` and
`asset_provenance` stay EMPTY in the graph — those are written by the pipeline
stages that actually render/fetch something. The intent lives in
`visual.strategy` / `visual.query` / `visual.visual_intent` here.

No `ai` (ai_image) beats are used in this episode by design: the brief calls
for real footage, real charts and motion graphics over synthetic imagery, and
the documentary_finance preset ships with AI generation off by default.

    .venv-win/Scripts/python.exe scripts/build_forex_ep01.py
    .venv-win/Scripts/python.exe scripts/produce.py --preset documentary_finance \
        --from-json data/series/forex_explainer/ep01/scene_graph.json --keep
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

OUT_DIR = ROOT / "data" / "series" / "forex_explainer" / "ep01"

# --------------------------------------------------------------------------- #
# Visual channel vocabulary — same shape as build_bitcoin_ep01.py's CHANNELS,
# minus the "ai" channel (unused in this episode; documentary_finance keeps
# AI_BROLL_ENGINE_ENABLED off, so an "ai" beat would render as a generic local
# plate anyway — better to just not reach for it).
# --------------------------------------------------------------------------- #
CHANNELS: dict[str, dict] = {
    "mgfx":    {"type": "motion_gfx", "strategy": "motion_gfx", "channel": "motion_gfx",
                "svt": "dramatic",     "motion": "none",
                "sb": "motion_gfx", "prio": ["local_graphics", "branded_fallback"]},
    "threejs": {"type": "threejs",    "strategy": "threejs",    "channel": "threejs",
                "svt": "data_viz",     "motion": "none",
                "sb": "threejs",   "prio": ["local_graphics", "branded_fallback"]},
    "chart":   {"type": "dataviz",    "strategy": "dataviz",    "channel": "charts",
                "svt": "data_viz",     "motion": "none",
                "sb": "dataviz",   "prio": ["local_graphics", "branded_fallback"]},
    "archival": {"type": "image",     "strategy": "real",       "channel": "official",
                "svt": "real_footage", "motion": "ken_burns",
                "sb": "real",      "prio": ["licensed_image", "exact_footage",
                                            "local_graphics", "branded_fallback"]},
    "stock":   {"type": "broll",      "strategy": "real",       "channel": "stock",
                "svt": "real_footage", "motion": "ken_burns",
                "sb": "real",      "prio": ["exact_footage", "licensed_image",
                                            "local_graphics", "branded_fallback"]},
}

EMOTION = {
    "hook": "urgent", "tension": "tense", "stakes": "tense", "context": "neutral",
    "evidence": "confident", "turn": "surprising", "reveal": "surprising",
    "contrast": "curious", "mechanism": "curious", "consequence": "cautionary",
    "payoff": "confident", "cta": "urgent", "question": "curious",
}

# --------------------------------------------------------------------------- #
# Source register — every figure spoken in this episode traces to one of these,
# checked directly against the primary source during authoring (Aug 2026).
# --------------------------------------------------------------------------- #
SOURCES: dict[str, dict] = {
    "bis25": {"label": "Bank for International Settlements, 2025 Triennial Survey",
              "url": "https://www.bis.org/press/p250930.htm",
              "license": "public data / editorial use"},
    "bis25stats": {"label": "BIS, OTC foreign exchange turnover, April 2025",
              "url": "https://www.bis.org/statistics/rpfx25_fx.htm",
              "license": "public data / editorial use"},
    "cftc59": {"label": "CFTC, 17 CFR § 5.9 — Security deposits for retail forex",
              "url": "https://www.ecfr.gov/current/title-17/chapter-I/part-5/section-5.9",
              "license": "US government work (public domain)"},
}

CHAPTERS = [
    ("00", "Cold Open — The Market Nobody Sees"),
    ("01", "What Forex Actually Is"),
    ("02", "Why Currencies Need To Be Exchanged"),
    ("03", "Currency Pairs — EUR/USD"),
    ("04", "Bid, Ask, and the Spread"),
    ("05", "Why Exchange Rates Move"),
    ("06", "Central Banks and Interest Rates"),
    ("07", "Economic Data and Market Expectations"),
    ("08", "Leverage"),
    ("09", "Institutional vs. Retail Forex"),
    ("10", "Why Beginners Misunderstand Forex"),
    ("11", "Closing — A Market, Not a Machine"),
]


def beat(text: str, role: str, vis: str, *, ch: str, intent: str, q: str = "",
         kw: tuple[str, ...] = (), ov: tuple[dict, ...] = (), data: dict | None = None,
         conf: str = "confirmed", tr: str = "", src: str = "", ent: str = "",
         loc: str = "", year: int | None = None, nums: tuple[str, ...] = (),
         emo: str = "", dur: float | None = None) -> dict:
    return {"n": text, "role": role, "vis": vis, "ch": ch, "intent": intent,
            "q": q, "kw": list(kw), "ov": [dict(o) for o in ov], "data": data,
            "conf": conf, "tr": tr, "src": src, "ent": ent, "loc": loc,
            "year": year, "nums": list(nums), "emo": emo, "dur": dur}


# =========================================================================== #
#  THE EPISODE
# =========================================================================== #
BEATS: list[dict] = [

    # ── 00 · COLD OPEN ────────────────────────────────────────────────────── #
    beat("While you watch this video, tens of billions of dollars will change hands "
         "in a market almost nobody outside a bank has ever actually seen work.",
         "hook", "stock", ch="00", dur=6.4,
         intent="Cinematic dawn shot of a financial district skyline, glass towers, real city — the market hiding in plain sight",
         q="financial district skyline sunrise glass skyscrapers wide cinematic",
         kw=("financial district skyline sunrise", "stock exchange building exterior wide"),
         emo="urgent"),

    beat("It's called the foreign exchange market — forex — and according to the "
         "Bank for International Settlements, it now moves more than nine and a half "
         "trillion dollars, every single day.",
         "hook", "chart", ch="00", dur=7.5,
         intent="A hero counter rolling up to $9.6T, branded, sourced on screen",
         q="Global daily FX turnover",
         data={"kind": "counter", "title": "Global daily FX turnover", "points": [
                {"label": "Per day", "value": 9.6, "emphasis": "primary"}],
               "prefix": "$", "suffix": "T", "decimals": 1,
               "source": "BIS, 2025 Triennial Survey"},
         src="bis25", nums=("$9.6 trillion",)),

    beat("And it's growing fast — up twenty-eight percent from seven and a half "
         "trillion a day, just three years earlier.",
         "evidence", "chart", ch="00", dur=5.2,
         intent="A simple two-point growth chart, 2022 to 2025, branded and sourced",
         q="FX turnover growth 2022 to 2025",
         data={"kind": "delta", "title": "Global daily FX turnover", "points": [
                {"label": "2022", "value": 7.5, "emphasis": "normal"},
                {"label": "2025", "value": 9.6, "emphasis": "positive"}],
               "prefix": "$", "suffix": "T", "decimals": 1,
               "source": "BIS Triennial Surveys, 2022 & 2025"},
         src="bis25", nums=("$7.5 trillion", "28%")),

    beat("So what actually is this market — and why does it move more money in one "
         "day than most countries produce in an entire year?",
         "question", "mgfx", ch="00", dur=5.4, tr="dip_to_black",
         intent="The question that structures the rest of the video, held on black",
         q="WHAT IS THIS MARKET, ACTUALLY?", emo="curious"),

    # ── 01 · WHAT FOREX ACTUALLY IS ──────────────────────────────────────── #
    beat("Forex is simply the market where one country's currency gets traded for "
         "another's.",
         "context", "stock", ch="01", dur=4.6, tr="fade",
         intent="Real currency notes from multiple countries, clean overhead shot",
         q="different world currencies banknotes overhead flat lay",
         kw=("world currencies banknotes flat lay", "foreign currency notes different countries")),

    beat("No single building. No opening bell. No central exchange anywhere on "
         "Earth.",
         "tension", "mgfx", ch="01", dur=4.2,
         intent="Three quick negations in type — what forex is NOT",
         q="NO EXCHANGE. NO OPENING BELL. NO SINGLE BUILDING."),

    beat("It's a network of banks, governments, funds and brokers trading directly "
         "with each other, twenty-four hours a day, five days a week.",
         "context", "stock", ch="01", dur=5.8,
         intent="Real bank dealing-room / trading terminal footage, multiple screens, professional",
         q="bank trading floor multiple monitors professional dealing room",
         kw=("trading floor multiple screens", "financial dealing room professional")),

    beat("It opens in Sydney. Hands off to Tokyo. Then London. Then New York. And "
         "by the time New York closes, Sydney is already opening again.",
         "evidence", "threejs", ch="01", dur=7.2,
         intent="Globe flight following the 24-hour session handoff: Sydney → Tokyo → London → New York",
         q="forex trading session handoff",
         ov=({"type": "lower_third", "text": "OPEN 24 HOURS", "sub": "Sydney → Tokyo → London → New York", "y": 0.24},)),

    # ── 02 · WHY CURRENCIES NEED TO BE EXCHANGED ─────────────────────────── #
    beat("Here's why this market exists. Say a US company wants to buy machine "
         "parts from a supplier in Japan.",
         "context", "stock", ch="02", dur=5.6, tr="fade",
         intent="Real cargo port / shipping containers, international trade in motion",
         q="cargo shipping port containers international trade",
         kw=("shipping containers port crane", "cargo ship international trade")),

    beat("That supplier doesn't want dollars. They want yen — because that's what "
         "pays their workers and their bills.",
         "mechanism", "stock", ch="02", dur=5.2,
         intent="Real factory floor / manufacturing footage, workers, everyday and concrete",
         q="factory workers manufacturing floor",
         kw=("factory production line workers", "manufacturing plant floor")),

    beat("Somewhere in that transaction, dollars get converted into yen. That "
         "conversion IS the forex market.",
         "reveal", "mgfx", ch="02", dur=5.0,
         intent="Dollars converting to yen, rendered as clean kinetic type",
         q="$ → ¥   THAT CONVERSION IS FOREX"),

    beat("It happens at an airport currency counter, when a company pays an "
         "overseas supplier, or when an investor buys a foreign bond.",
         "evidence", "stock", ch="02", dur=6.0,
         intent="Real airport currency exchange kiosk, a traveler at the counter",
         q="airport currency exchange counter traveler",
         kw=("currency exchange booth airport", "foreign exchange kiosk travel")),

    # ── 03 · CURRENCY PAIRS: EUR/USD ─────────────────────────────────────── #
    beat("Because you're always trading one currency FOR another, forex prices "
         "always come as a pair.",
         "context", "mgfx", ch="03", dur=4.8, tr="fade",
         intent="Two currency codes locking together as one unit",
         q="EUR / USD"),

    beat("The world's most heavily traded pair is the euro against the US dollar "
         "— written EUR slash USD.",
         "context", "chart", ch="03", dur=5.4,
         intent="EUR/USD rendered as the hero pair, branded card",
         q="EUR/USD — the world's most traded currency pair",
         data={"kind": "counter", "title": "World's most traded currency pair", "points": [
                {"label": "EUR / USD", "value": 1, "emphasis": "primary"}],
               "prefix": "", "suffix": "", "decimals": 0, "abbreviate": False}),

    beat("The first currency is the 'base.' The second is the 'quote.' The price "
         "tells you how many dollars it takes to buy one euro.",
         "mechanism", "mgfx", ch="03", dur=6.0,
         intent="BASE / QUOTE labeled directly on the EUR/USD pair",
         q="BASE  /  QUOTE"),

    beat("So if EUR/USD is quoted at, say, one-ten, that means one euro costs you "
         "a dollar ten.",
         "evidence", "chart", ch="03", dur=5.0,
         intent="A simple illustrative price example — explicitly framed as an example, not a live quote",
         q="illustrative example: EUR/USD = 1.10",
         data={"kind": "counter", "title": "Example quote (illustrative)", "points": [
                {"label": "1 EUR =", "value": 1.10, "emphasis": "auto"}],
               "prefix": "$", "suffix": "", "decimals": 2, "abbreviate": False,
               "note": "Example only — not a live market price"},
         conf="confirmed"),

    # ── 04 · BID, ASK, SPREAD ─────────────────────────────────────────────── #
    beat("Here's something most beginners never get explained: every forex quote "
         "is actually two prices, not one.",
         "tension", "stock", ch="04", dur=5.0, tr="fade",
         intent="Real trading terminal close-up, two-sided price ladder visible",
         q="trading terminal screen bid ask price ladder close up",
         kw=("forex trading screen close up", "trading terminal price ladder")),

    beat("The 'bid' is what a broker pays you. The 'ask' is what they charge you "
         "— and it's always a little higher.",
         "mechanism", "chart", ch="04", dur=6.0,
         intent="Bid vs ask shown as a clean delta — illustrative values",
         q="Bid vs Ask (illustrative)",
         data={"kind": "delta", "title": "Bid vs. Ask (illustrative)", "points": [
                {"label": "Bid", "value": 1.099, "emphasis": "normal"},
                {"label": "Ask", "value": 1.100, "emphasis": "negative"}],
               "prefix": "$", "suffix": "", "decimals": 3, "abbreviate": False,
               "note": "Example only — not a live market price"}),

    beat("That gap is called the spread — and it's how most brokers make money, "
         "whether you win or lose your trade.",
         "reveal", "mgfx", ch="04", dur=5.4,
         intent="THE SPREAD, isolated and defined",
         q="THE SPREAD — THE GAP BETWEEN BID AND ASK"),

    # ── 05 · WHY EXCHANGE RATES MOVE ─────────────────────────────────────── #
    beat("So why does the price of a currency change at all?",
         "question", "mgfx", ch="05", dur=3.4, tr="fade",
         intent="The chapter question, simple and direct",
         q="WHY DO CURRENCIES MOVE?", emo="curious"),

    beat("Simple version: supply and demand. More demand pushes the price up. "
         "Less demand pushes it down.",
         "mechanism", "chart", ch="05", dur=5.6,
         intent="A demand-up / demand-down comparison, minimal and clean",
         q="Currency demand vs price",
         data={"kind": "bar_compare", "title": "Demand and price", "points": [
                {"label": "More demand", "value": 8, "emphasis": "positive"},
                {"label": "Less demand", "value": 3, "emphasis": "negative"}],
               "prefix": "", "suffix": "", "decimals": 0, "abbreviate": False,
               "note": "Conceptual illustration"}),

    beat("What drives that demand is interest rates, inflation, trade flows, "
         "politics, and market sentiment.",
         "evidence", "stock", ch="05", dur=5.4,
         intent="Real newsroom / financial broadcast screens, headlines moving",
         q="financial news broadcast screens headlines",
         kw=("financial news studio screens", "business news broadcast monitors")),

    # ── 06 · CENTRAL BANKS AND INTEREST RATES ────────────────────────────── #
    beat("The single biggest driver, most of the time, is what central banks do "
         "with interest rates.",
         "context", "archival", ch="06", dur=5.4, tr="fade",
         intent="Real Federal Reserve building exterior, Washington D.C.",
         q="Federal Reserve building Washington DC exterior",
         kw=("Federal Reserve building exterior", "Marriner Eccles building Washington"),
         ent="Federal Reserve", loc="Washington, D.C."),

    beat("When the Fed raises interest rates, global investors want to hold "
         "dollars more — because their money earns more just sitting in them.",
         "mechanism", "mgfx", ch="06", dur=6.6,
         intent="Higher rate → higher return → more demand, shown as a simple causal chain",
         q="HIGHER RATES → HIGHER RETURN → MORE DEMAND"),

    beat("That pulls in foreign capital chasing the better return, pushing the "
         "currency's value up.",
         "evidence", "threejs", ch="06", dur=5.4,
         intent="Capital flowing INTO one economy — comparison towers, rates vs capital inflow",
         q="Interest rate differential and capital flow"),

    beat("So when the Fed and the European Central Bank move rates in different "
         "directions, EUR/USD tends to move too.",
         "payoff", "archival", ch="06", dur=6.0,
         intent="Real European Central Bank building exterior, Frankfurt",
         q="European Central Bank building Frankfurt exterior",
         kw=("European Central Bank building Frankfurt", "ECB tower Frankfurt skyline"),
         ent="European Central Bank", loc="Frankfurt, Germany"),

    # ── 07 · ECONOMIC DATA AND MARKET EXPECTATIONS ───────────────────────── #
    beat("This is also why traders obsess over jobs reports, inflation numbers, "
         "and GDP growth.",
         "context", "stock", ch="07", dur=5.0, tr="fade",
         intent="Real economic data on screen, spreadsheets, analyst reviewing charts",
         q="financial analyst reviewing economic data charts screen",
         kw=("analyst reviewing financial charts", "economic data spreadsheet screen")),

    beat("Not because the number matters alone — but because it changes what "
         "people expect the central bank to do next.",
         "mechanism", "mgfx", ch="07", dur=5.6,
         intent="DATA changing into EXPECTATION, kinetic type",
         q="THE DATA → THE EXPECTATION"),

    beat("Markets don't just react to the news. They react to the news being "
         "different from what everyone already expected.",
         "reveal", "mgfx", ch="07", dur=6.0,
         intent="EXPECTED vs ACTUAL, the gap between them highlighted",
         q="EXPECTED vs. ACTUAL — THE GAP IS WHAT MOVES THE PRICE", emo="surprising"),

    beat("That's why 'good' news can send a currency DOWN — if traders expected "
         "something even better.",
         "consequence", "chart", ch="07", dur=5.6,
         intent="A counterintuitive good-news-down illustration",
         q="Good news, currency down (conceptual)",
         data={"kind": "bar_compare", "title": "Expected vs. delivered (conceptual)", "points": [
                {"label": "Expected", "value": 9, "emphasis": "normal"},
                {"label": "Delivered", "value": 7, "emphasis": "negative"}],
               "prefix": "", "suffix": "", "decimals": 0, "abbreviate": False,
               "note": "Conceptual illustration"}),

    # ── 08 · LEVERAGE ─────────────────────────────────────────────────────── #
    beat("Now here's the part that draws in a lot of beginners — and hurts a lot "
         "of them too: leverage.",
         "tension", "stock", ch="08", dur=5.2, tr="fade",
         intent="Real trading app / platform interface, order ticket visible",
         q="forex trading platform order ticket interface screen",
         kw=("trading app interface screen", "forex order entry platform")),

    beat("Leverage lets you control a large position with a small amount of your "
         "own money. US regulators cap retail forex leverage at fifty-to-one on "
         "major pairs.",
         "mechanism", "chart", ch="08", dur=7.4,
         intent="The 50:1 cap, branded and sourced to the CFTC",
         q="US retail forex maximum leverage: 50:1 on major pairs",
         data={"kind": "counter", "title": "Max. US retail leverage, major pairs", "points": [
                {"label": "Cap", "value": 50, "emphasis": "primary"}],
               "prefix": "", "suffix": ":1", "decimals": 0, "abbreviate": False,
               "source": "CFTC, 17 CFR § 5.9"},
         src="cftc59", nums=("50:1",)),

    beat("That means with two thousand dollars of your own money, you could "
         "control a hundred thousand dollars in currency.",
         "evidence", "chart", ch="08", dur=6.0,
         intent="$2,000 controlling $100,000 — the multiplier made concrete",
         q="$2,000 controls $100,000 at 50:1 leverage",
         data={"kind": "delta", "title": "What 50:1 leverage controls", "points": [
                {"label": "Your money", "value": 2000, "emphasis": "normal"},
                {"label": "Position size", "value": 100000, "emphasis": "primary"}],
               "prefix": "$", "suffix": "", "decimals": 0}),

    beat("Leverage multiplies your gains. But it multiplies your losses exactly "
         "the same way.",
         "turn", "mgfx", ch="08", dur=5.0,
         intent="Symmetric arrows — gains up, losses down, same size",
         q="LEVERAGE MULTIPLIES BOTH DIRECTIONS", emo="tense"),

    beat("A move that would barely register without leverage can wipe out your "
         "account with it. That's just the math.",
         "consequence", "mgfx", ch="08", dur=5.8,
         intent="The math stated plainly, no dramatization needed",
         q="THAT'S NOT A WARNING. THAT'S THE MATH.", emo="cautionary"),

    # ── 09 · INSTITUTIONAL VS. RETAIL FOREX ──────────────────────────────── #
    beat("Which raises something most retail traders don't realize: this market "
         "wasn't really built for them.",
         "turn", "stock", ch="09", dur=5.4, tr="fade",
         intent="Real institutional trading floor, scale and seriousness",
         q="institutional trading floor bank professionals wide shot",
         kw=("bank trading floor wide shot", "institutional dealing room professionals")),

    beat("More than four trillion dollars a day moves through FX swaps alone — "
         "used almost entirely by banks and institutions moving real money.",
         "evidence", "chart", ch="09", dur=7.2,
         intent="FX swaps as the largest single instrument, branded and sourced",
         q="FX swaps: the largest single instrument in forex",
         data={"kind": "counter", "title": "FX swaps — daily turnover", "points": [
                {"label": "Per day", "value": 4.0, "emphasis": "primary"}],
               "prefix": "$", "suffix": "T", "decimals": 1,
               "source": "BIS, 2025 Triennial Survey", "note": "Largest single FX instrument"},
         src="bis25stats", nums=("$4 trillion",)),

    beat("Individual retail traders make up a small slice of that "
         "nine-point-six-trillion-dollar total.",
         "mechanism", "mgfx", ch="09", dur=5.2,
         intent="Retail slice shown as small against the total",
         q="RETAIL TRADERS: A SMALL SLICE OF A HUGE MARKET"),

    beat("Institutions get tighter spreads, faster execution, and far more "
         "information. Retail gets access — not the same playing field.",
         "payoff", "chart", ch="09", dur=6.4,
         intent="Institutional vs retail advantages, side by side",
         q="Institutional vs. retail forex (conceptual)",
         data={"kind": "bar_compare", "title": "Execution advantage (conceptual)", "points": [
                {"label": "Institutional", "value": 9, "emphasis": "primary"},
                {"label": "Retail", "value": 4, "emphasis": "normal"}],
               "prefix": "", "suffix": "", "decimals": 0, "abbreviate": False,
               "note": "Conceptual illustration"}),

    # ── 10 · WHY BEGINNERS MISUNDERSTAND FOREX ───────────────────────────── #
    beat("That gap is exactly what a lot of 'get rich trading forex' content "
         "online quietly leaves out.",
         "tension", "stock", ch="10", dur=5.6, tr="fade",
         intent="Real phone/social media scrolling footage, generic and unbranded",
         q="scrolling phone social media screen close up",
         kw=("phone screen scrolling social media", "smartphone browsing hand close up")),

    beat("Forex isn't a shortcut. It's one of the most competitive markets on "
         "Earth — and you're trading against professionals who do this all day.",
         "mechanism", "mgfx", ch="10", dur=6.2,
         intent="The reframe, stated plainly",
         q="NOT A SHORTCUT. THE MOST COMPETITIVE MARKET ON EARTH."),

    beat("Most beginners don't fail because forex is rigged. They oversize "
         "trades, ignore the spread, and treat leverage like free money instead "
         "of borrowed risk.",
         "consequence", "mgfx", ch="10", dur=6.4,
         intent="Three concrete failure modes, listed plainly",
         q="OVERSIZED TRADES. IGNORED SPREADS. LEVERAGE MISTAKEN FOR FREE MONEY.",
         emo="cautionary"),

    # ── 11 · CLOSING ──────────────────────────────────────────────────────── #
    beat("So — forex isn't secretive, and it isn't rigged. It's just enormous, "
         "fast, and mostly invisible.",
         "payoff", "stock", ch="11", dur=5.4, tr="fade",
         intent="Wide dusk establishing shot, callback to the cold open",
         q="financial district skyline dusk wide cinematic",
         kw=("financial district skyline dusk", "city skyline sunset wide shot")),

    beat("Nine point six trillion dollars a day — moving between banks, "
         "corporations and traders, every hour the sun is up somewhere on "
         "Earth.",
         "payoff", "chart", ch="11", dur=6.8,
         intent="Callback to the hook counter — same number, now understood",
         q="Global daily FX turnover — callback",
         data={"kind": "counter", "title": "Global daily FX turnover", "points": [
                {"label": "Per day", "value": 9.6, "emphasis": "primary"}],
               "prefix": "$", "suffix": "T", "decimals": 1,
               "source": "BIS, 2025 Triennial Survey"},
         src="bis25"),

    beat("It's a market — not a machine that prints money. Understanding how it "
         "actually works is the difference between using it, and being used by "
         "it.",
         "cta", "mgfx", ch="11", dur=6.8,
         intent="The thesis line, closing the loop opened in the cold open",
         q="A MARKET. NOT A MACHINE."),

    beat("If you want to actually understand how markets work — instead of "
         "guessing at them — that's exactly what this channel is for.",
         "cta", "mgfx", ch="11", dur=6.0,
         intent="Channel CTA card, calm and simple",
         q="K70 — UNDERSTAND THE ECONOMY",
         ov=({"type": "lower_third", "text": "K70 FINANCE", "sub": "Understand the economy.", "y": 0.5},)),
]


def estimate(text: str, override: float | None) -> float:
    """Director-side duration estimate. Overwritten by measured TTS at render."""
    if override is not None:
        return round(min(12.0, max(0.8, override)), 2)
    words = len(text.split())
    return round(min(12.0, max(1.6, words / 2.55 + 0.85)), 2)


def build():
    from app.schemas.scene import (DataViz, Overlay, Scene, SceneGraph, SceneMeta,
                                   StoryboardData, StoryboardScene, Visual)

    scenes: list[Scene] = []
    sb_scenes: list[StoryboardScene] = []
    asset_plan: list[dict] = []

    for i, b in enumerate(BEATS, start=1):
        sid = f"s{i}"
        spec = CHANNELS[b["vis"]]
        dur = estimate(b["n"], b["dur"])

        overlays = [Overlay(**o) for o in b["ov"]]
        if b["vis"] == "mgfx" and b["q"] and not any(
                o.type == "headline" for o in overlays):
            overlays.insert(0, Overlay(type="headline", text=b["q"], y=0.30))
        if b["src"] and not any(o.type == "source" for o in overlays):
            overlays.append(Overlay(type="source", text=SOURCES[b["src"]]["label"][:48],
                                    y=0.1))

        visual = Visual(
            type=spec["type"], strategy=spec["strategy"],
            budget_channel=spec["channel"], scene_visual_type=spec["svt"],
            motion=spec["motion"], query=b["q"], broll_keywords=b["kw"],
            visual_intent=b["intent"],
            decision_reason=f"{b['ch']} · {b['role']} · {spec['channel']}",
        )

        scenes.append(Scene(
            id=sid, narration=b["n"], duration_sec=dur, visual=visual,
            overlays=overlays, data=DataViz(**b["data"]) if b["data"] else None,
            beat_role=b["role"], transition_in=b["tr"] or "cut",
            keywords=b["kw"], confidence=b["conf"],
        ))

        sb_scenes.append(StoryboardScene(
            scene_id=f"sb_{sid}", source_scene_id=sid, narration=b["n"],
            duration_estimate=dur, visual_objective=b["intent"],
            primary_entity=b["ent"], secondary_entities=[], company="",
            location=b["loc"], year=b["year"], financial_numbers=b["nums"],
            emotion=b["emo"] or EMOTION.get(b["role"], "neutral"),
            recommended_visual_type=spec["sb"],
            recommended_camera_movement=spec["motion"],
            motion_graphics_needed=b["vis"] in ("mgfx", "chart"),
            threejs_candidate=b["vis"] == "threejs",
            ai_broll_candidate=False,
            asset_priority=spec["prio"],
            transition=b["tr"] or "cut",
            overlay_text=[o.text for o in overlays if o.type != "source"],
            visual_confidence_score=0.92 if b["vis"] in ("mgfx", "chart", "threejs")
            else (0.8 if b["vis"] == "archival" else 0.72),
        ))

        src = SOURCES.get(b["src"]) if b["src"] else None
        asset_plan.append({
            "scene_id": sid, "chapter": b["ch"], "beat_role": b["role"],
            "channel": spec["channel"], "strategy": spec["strategy"],
            "acquisition": ("rendered in-pipeline"
                            if spec["channel"] in ("motion_gfx", "threejs", "charts")
                            else ("archival / official — real photograph, sourced"
                                  if spec["channel"] == "official"
                                  else "stock video API (Pexels/Pixabay) — real footage")),
            "query_or_prompt": b["q"] or (b["kw"][0] if b["kw"] else ""),
            "search_terms": b["kw"],
            "citation": {"label": src["label"], "url": src["url"],
                         "license": src["license"]} if src else None,
            "confidence": b["conf"],
            "synthetic": False,
        })

    total = round(sum(s.duration_sec for s in scenes), 2)

    meta = SceneMeta(
        video_id="forex_ep01_how_the_market_works",
        channel_id="k70_economy",
        niche="usa_finance",
        structure_id="one_number_story",
        title="How The $9.6 Trillion-A-Day Currency Market Actually Works | Forex Explained",
        hook="While you watch this video, tens of billions of dollars will change "
             "hands in a market almost nobody outside a bank has ever actually seen work.",
        description=(
            "FOREX EXPLAINED — How the foreign exchange market actually works, "
            "in plain English.\n\n"
            "The global forex market now moves more than $9.6 trillion a day "
            "(BIS, 2025 Triennial Survey) — more than any other market on Earth. "
            "This video breaks down what forex actually is, why currencies need "
            "to be exchanged, how currency pairs like EUR/USD work, what bid, "
            "ask and spread actually mean, why exchange rates move, how central "
            "banks and interest rates drive the market, why economic data moves "
            "prices, how leverage works (and why it's dangerous), how "
            "institutional forex differs from retail forex, and why so many "
            "beginners misunderstand this market.\n\n"
            "SOURCES: Bank for International Settlements, 2025 Triennial Central "
            "Bank Survey of Foreign Exchange — https://www.bis.org/press/p250930.htm "
            "· U.S. Commodity Futures Trading Commission, 17 CFR § 5.9 — "
            "https://www.ecfr.gov/current/title-17/chapter-I/part-5/section-5.9\n\n"
            "This video is educational and describes how the forex market works. "
            "It does not recommend buying, selling or trading any currency. "
            "Trading foreign exchange, especially with leverage, carries a high "
            "risk of loss. See disclaimer."
        ),
        tags=["forex", "forex trading", "foreign exchange market", "how forex works",
              "eur usd", "bid ask spread", "leverage trading", "currency trading",
              "central banks", "interest rates", "forex explained", "trading for beginners",
              "bank for international settlements", "finance documentary"],
        hashtags=["#forex", "#forextrading", "#finance", "#investing", "#k70finance"],
        thumbnail_text="HOW FOREX REALLY WORKS",
        disclaimer=("Educational content. Not financial advice. Forex trading, "
                    "especially with leverage, carries a high risk of loss."),
    )

    graph = SceneGraph(
        meta=meta, fps=30, width=1920, height=1080, brand_id="k70",
        scenes=scenes,
        storyboard=StoryboardData(version="1.0", scenes=sb_scenes),
    )
    return graph, asset_plan, total


def write_narration(total: float) -> str:
    lines = [f"# Forex Explained — Ep. 1 narration\n",
             f"Total estimated runtime: {total:.1f}s (~{total/60:.2f} min)\n"]
    for i, b in enumerate(BEATS, start=1):
        lines.append(f"**s{i}** [{b['ch']} · {b['role']} · {b['vis']}]  \n{b['n']}\n")
    return "\n".join(lines)


def write_sources() -> str:
    lines = ["# Forex Explained — Ep. 1 sources\n"]
    for sid, s in SOURCES.items():
        lines.append(f"- **{s['label']}** — {s['url']} ({s['license']})")
    lines.append("\n## Claims and their sources\n")
    for i, b in enumerate(BEATS, start=1):
        if b["src"]:
            s = SOURCES[b["src"]]
            lines.append(f"- s{i}: \"{b['n'][:80]}...\" — {s['label']}")
    return "\n".join(lines)


def main() -> int:
    graph, asset_plan, total = build()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "scene_graph.json").write_text(graph.model_dump_json(indent=2), encoding="utf-8")
    (OUT_DIR / "narration.md").write_text(write_narration(total), encoding="utf-8")
    (OUT_DIR / "sources.md").write_text(write_sources(), encoding="utf-8")
    (OUT_DIR / "asset_plan.json").write_text(json.dumps(asset_plan, indent=2), encoding="utf-8")
    print(f"scenes: {len(graph.scenes)}")
    print(f"estimated total: {total:.1f}s (~{total/60:.2f} min)")
    print(f"wrote: {OUT_DIR / 'scene_graph.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
