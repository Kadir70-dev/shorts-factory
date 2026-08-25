#!/usr/bin/env python3
"""
XAU/USD EXPLAINED · Episode 1 — "How Gold Trading Against the US Dollar
Actually Works"

Single-source-of-truth authoring script for one long-form (16:9, ~5 minute)
K70 Finance explainer. Same pattern as `build_forex_ep01.py`: narration,
per-beat visual plan, chart data and source citations are authored ONCE in
`BEATS` below and emitted as a validated SceneGraph plus supporting docs.

No `ai` (ai_image) beats are used by design: real footage, real charts and
motion graphics over synthetic imagery, matching the Forex episode's bar
(the user's stated minimum-quality benchmark for this channel).

    .venv-win/Scripts/python.exe scripts/build_xauusd_ep01.py
    .venv-win/Scripts/python.exe scripts/produce.py --preset documentary_finance \
        --from-json data/series/xauusd_explainer/ep01/scene_graph.json --keep
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

OUT_DIR = ROOT / "data" / "series" / "xauusd_explainer" / "ep01"

# --------------------------------------------------------------------------- #
# Visual channel vocabulary — identical shape to build_forex_ep01.py's
# CHANNELS. No "ai" channel: documentary_finance ships AI generation off.
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
# Source register — every figure spoken in this episode traces to one of
# these, checked directly against the primary source during authoring
# (Aug 2026). No "current" gold price is quoted anywhere in this script.
# --------------------------------------------------------------------------- #
SOURCES: dict[str, dict] = {
    "wgc25": {"label": "World Gold Council, Gold Demand Trends — Full Year 2024",
              "url": "https://www.gold.org/goldhub/research/gold-demand-trends/gold-demand-trends-full-year-2024",
              "license": "public data / editorial use"},
    "ecb25": {"label": "European Central Bank, International Role of the Euro "
                        "(June 2025) — gold overtakes euro as 2nd-largest reserve asset",
              "url": "https://www.cnbc.com/2025/06/11/gold-overtakes-euro-as-second-biggest-global-reserve-asset.html",
              "license": "public data / editorial use"},
    "cftc_gold": {"label": "CFTC, \"Gold Is No Safe Investment\" consumer advisory",
              "url": "https://www.cftc.gov/LearnAndProtect/AdvisoriesAndArticles/gold_is_no_safe_investment.htm",
              "license": "US government work (public domain)"},
    "cftc_monex": {"label": "CFTC press release 8643-22 — Monex Deposit Co. ordered "
                             "to pay $38M for off-exchange leveraged precious metals fraud",
              "url": "https://www.cftc.gov/PressRoom/PressReleases/8643-22",
              "license": "US government work (public domain)"},
}

CHAPTERS = [
    ("00", "Cold Open"),
    ("01", "What XAU/USD Actually Means"),
    ("02", "Why Gold Is Quoted In Dollars"),
    ("03", "How To Read An XAU/USD Price"),
    ("04", "What Actually Moves Gold"),
    ("05", "US Dollar Strength"),
    ("06", "The Federal Reserve And Interest Rates"),
    ("07", "Real Yields"),
    ("08", "Inflation Expectations"),
    ("09", "Safe-Haven Demand And Geopolitics"),
    ("10", "Central Bank Gold Demand"),
    ("11", "Why Gold Surprises Beginners"),
    ("12", "Leverage And Risk"),
    ("13", "Understanding vs. Predicting"),
    ("14", "Closing"),
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
    beat("Gold has been money, a war chest, a crisis hedge, and one of the most "
         "closely watched prices on Earth.",
         "hook", "stock", ch="00", dur=5.8,
         intent="Cinematic macro shot of stacked physical gold bars, warm dramatic lighting, premium and real",
         q="gold bars stacked macro cinematic lighting",
         kw=("gold bars stacked macro shot", "gold bullion close up cinematic"),
         emo="urgent"),

    beat("But when traders say XAU/USD is moving — what are they actually "
         "looking at?",
         "hook", "mgfx", ch="00", dur=4.6,
         intent="The question that opens the video, held on black",
         q="WHAT IS XAU/USD, ACTUALLY?", emo="curious"),

    beat("XAU/USD is simply the price of one troy ounce of gold, quoted in US "
         "dollars.",
         "context", "chart", ch="00", dur=5.4,
         intent="A hero card naming the pair plainly, branded",
         q="XAU / USD — one troy ounce of gold, in US dollars",
         data={"kind": "counter", "title": "XAU / USD", "points": [
                {"label": "1 troy oz. gold, priced in", "value": 1, "emphasis": "primary"}],
               "prefix": "", "suffix": " USD", "decimals": 0, "abbreviate": False}),

    beat("One number. And underneath it — interest rates, currency strength, "
         "inflation, and global fear, all priced in at once.",
         "evidence", "mgfx", ch="00", dur=5.6, tr="dip_to_black",
         intent="Four forces converging into one price, kinetic type",
         q="RATES · THE DOLLAR · INFLATION · FEAR — ONE PRICE"),

    # ── 01 · WHAT XAU/USD ACTUALLY MEANS ─────────────────────────────────── #
    beat("XAU is gold's currency code — the 'X' marks it as a commodity, the "
         "same way EUR marks the euro or JPY marks the yen.",
         "context", "stock", ch="01", dur=6.2, tr="fade",
         intent="Real gold bars with visible hallmark stamps, close and tactile",
         q="gold bar hallmark stamp close up macro",
         kw=("gold bullion bar stamp close up", "gold bar serial number macro")),

    beat("So XAU/USD isn't a stock ticker. It's an exchange rate — gold, "
         "priced as if it were a currency of its own.",
         "reveal", "mgfx", ch="01", dur=6.0,
         intent="XAU treated visually as a currency symbol alongside EUR, JPY, GBP",
         q="XAU — TREATED AS A CURRENCY, NOT A STOCK"),

    # ── 02 · WHY QUOTED IN DOLLARS ────────────────────────────────────────── #
    beat("It's quoted in dollars because the dollar is still the world's "
         "reserve currency — the common language most global prices get "
         "translated through.",
         "context", "archival", ch="02", dur=6.8, tr="fade",
         intent="Real Federal Reserve building exterior, Washington D.C., establishing the dollar's role",
         q="Federal Reserve building Washington DC exterior",
         kw=("Federal Reserve building exterior", "US Treasury building Washington"),
         ent="Federal Reserve", loc="Washington, D.C."),

    beat("Oil, gold, most international trade — priced in dollars first, then "
         "converted into whatever currency you actually spend.",
         "evidence", "stock", ch="02", dur=6.0,
         intent="Real global trade / shipping port footage, international scale",
         q="cargo shipping port containers international trade wide",
         kw=("cargo shipping port wide shot", "international trade containers port")),

    beat("That's a structural fact of the current monetary system — not a "
         "comment on any single country's economy.",
         "context", "mgfx", ch="02", dur=5.4,
         intent="A calm, careful caveat, avoiding any USD-bearish framing",
         q="A STRUCTURAL FACT — NOT A PREDICTION"),

    # ── 03 · HOW TO READ AN XAU/USD PRICE ────────────────────────────────── #
    beat("So if XAU/USD reads two thousand, that means one troy ounce of gold "
         "costs two thousand US dollars. Nothing more complicated than that.",
         "mechanism", "chart", ch="03", dur=7.0,
         intent="A simple illustrative price example — explicitly framed as an example, not a live quote",
         q="illustrative example: XAU/USD = 2,000",
         data={"kind": "counter", "title": "Example quote (illustrative)", "points": [
                {"label": "1 troy oz. gold =", "value": 2000, "emphasis": "auto"}],
               "prefix": "$", "suffix": "", "decimals": 0, "abbreviate": False,
               "note": "Example only — not a live market price"}),

    beat("The number rises, gold got more expensive in dollars. It falls, "
         "gold got cheaper — or the dollar simply got stronger.",
         "mechanism", "mgfx", ch="03", dur=6.4,
         intent="Price up / price down, dual causes labeled",
         q="PRICE UP: GOLD COSTS MORE.  PRICE DOWN: GOLD, OR THE DOLLAR, CHANGED."),

    # ── 04 · WHAT ACTUALLY MOVES GOLD (framing) ──────────────────────────── #
    beat("So what actually moves that number? It's rarely one thing. It's "
         "usually four.",
         "question", "mgfx", ch="04", dur=4.4, tr="fade",
         intent="The chapter question that structures the rest of the video",
         q="WHAT MOVES XAU/USD? USUALLY FOUR THINGS.", emo="curious"),

    # ── 05 · US DOLLAR STRENGTH ───────────────────────────────────────────── #
    beat("First: the dollar itself. Gold is priced in dollars, so when the "
         "dollar weakens against other currencies, gold usually costs more in "
         "dollar terms — even if nothing about gold changed.",
         "mechanism", "stock", ch="05", dur=8.4, tr="fade",
         intent="Real US currency close-up, tactile and premium, dollar as the denominator",
         q="US dollar bills close up macro cinematic",
         kw=("US dollar bills close up macro", "hundred dollar bills stack cinematic")),

    beat("A weaker dollar buys less of almost everything priced in dollars. "
         "Gold is no exception.",
         "evidence", "chart", ch="05", dur=5.2,
         intent="Dollar strength vs gold price, inverse relationship shown conceptually",
         q="USD strength vs. gold price (conceptual)",
         data={"kind": "bar_compare", "title": "USD strength vs. gold price (conceptual)", "points": [
                {"label": "Dollar weaker", "value": 8, "emphasis": "positive"},
                {"label": "Dollar stronger", "value": 3, "emphasis": "negative"}],
               "prefix": "", "suffix": "", "decimals": 0, "abbreviate": False,
               "note": "Conceptual illustration — gold priced in USD"}),

    # ── 06 · FED AND INTEREST RATES ──────────────────────────────────────── #
    beat("Second: what the Federal Reserve does with interest rates.",
         "context", "archival", ch="06", dur=4.2, tr="fade",
         intent="Real Federal Reserve building, a different angle from the ch02 shot",
         q="Federal Reserve seal building entrance Washington DC",
         kw=("Federal Reserve entrance sign", "Federal Reserve building columns"),
         ent="Federal Reserve", loc="Washington, D.C."),

    beat("Interest rates change how attractive it is to hold cash and bonds "
         "instead of an asset that pays you nothing to hold it.",
         "mechanism", "mgfx", ch="06", dur=6.6,
         intent="Cash/bonds (yield) vs gold (no yield), framed as a simple choice",
         q="BONDS PAY YOU TO WAIT. GOLD DOESN'T."),

    # ── 07 · REAL YIELDS ──────────────────────────────────────────────────── #
    beat("Here's the concept that actually drives it: real yield. Take the "
         "interest rate. Subtract expected inflation. What's left is the real "
         "yield.",
         "reveal", "mgfx", ch="07", dur=7.4,
         intent="Custom motion graphic: the real-yield formula assembling piece by piece",
         q="NOMINAL YIELD − EXPECTED INFLATION = REAL YIELD",
         emo="surprising"),

    beat("Traders don't watch the interest rate on its own. They watch it "
         "against inflation expectations — because that gap is what actually "
         "matters to an asset like gold that pays no yield at all.",
         "mechanism", "mgfx", ch="07", dur=7.8,
         intent="Reinforcing the formula: the GAP is what matters, not the rate alone",
         q="THE GAP BETWEEN RATE AND INFLATION IS WHAT MOVES GOLD"),

    beat("When real yields are high, bonds beat gold easily. When real "
         "yields fall toward zero — or below it — gold's zero yield stops "
         "being a disadvantage.",
         "mechanism", "chart", ch="07", dur=8.0,
         intent="Custom motion graphic: real yield rising = opportunity cost of holding gold rising, and vice versa",
         q="High real yields vs. low real yields (conceptual)",
         data={"kind": "bar_compare", "title": "Real yield vs. gold's appeal (conceptual)", "points": [
                {"label": "High real yield", "value": 3, "emphasis": "negative"},
                {"label": "Low/negative real yield", "value": 8, "emphasis": "positive"}],
               "prefix": "", "suffix": "", "decimals": 0, "abbreviate": False,
               "note": "Conceptual illustration — not a forecast"}),

    beat("That's the opportunity cost of holding gold — what you give up by "
         "not earning interest — rising and falling with real rates.",
         "payoff", "mgfx", ch="07", dur=6.0,
         intent="The term named plainly: opportunity cost, tied back to the formula",
         q="OPPORTUNITY COST: WHAT YOU GIVE UP TO HOLD GOLD INSTEAD"),

    # ── 08 · INFLATION EXPECTATIONS ───────────────────────────────────────── #
    beat("Third: inflation expectations. Gold has a long reputation as a "
         "store of value when a currency's purchasing power looks likely to "
         "erode.",
         "context", "stock", ch="08", dur=6.8, tr="fade",
         intent="Real everyday consumer/retail footage suggesting purchasing power, grounded not abstract",
         q="grocery store shopping receipt prices everyday",
         kw=("grocery store aisle shopping", "retail checkout receipt close up")),

    beat("Traders don't just react to today's inflation number. They react "
         "to where they expect inflation to go next.",
         "mechanism", "mgfx", ch="08", dur=5.6,
         intent="TODAY'S NUMBER vs THE EXPECTATION, the forward-looking distinction",
         q="NOT TODAY'S NUMBER — WHERE INFLATION IS EXPECTED TO GO"),

    # ── 09 · SAFE-HAVEN DEMAND AND GEOPOLITICS ───────────────────────────── #
    beat("Fourth: fear. When markets get nervous — a banking scare, a war, a "
         "shock nobody priced in — investors often rotate into gold.",
         "tension", "stock", ch="09", dur=6.6, tr="fade",
         intent="Real newsroom / financial broadcast screens, headlines moving, tension without sensationalism",
         q="financial news broadcast screens headlines wide",
         kw=("financial news studio screens", "business news broadcast monitors")),

    beat("Not because gold is exciting. Because its value isn't tied to any "
         "single government's promise.",
         "reveal", "threejs", ch="09", dur=5.8,
         intent="Globe visualization — gold as a cross-border asset, no single national flag",
         q="Gold as a cross-border, no-single-issuer asset"),

    # ── 10 · CENTRAL BANK GOLD DEMAND ────────────────────────────────────── #
    beat("That same logic applies to central banks. They've bought more than "
         "a thousand tonnes of gold a year, three years running.",
         "evidence", "chart", ch="10", dur=6.8,
         intent="Central bank gold buying, branded and sourced to the World Gold Council",
         q="Central bank gold purchases — three straight years over 1,000 tonnes",
         data={"kind": "counter", "title": "Central bank gold purchases, 2024", "points": [
                {"label": "Tonnes bought", "value": 1045, "emphasis": "primary"}],
               "prefix": "", "suffix": "t", "decimals": 0,
               "source": "World Gold Council, Gold Demand Trends FY2024"},
         src="wgc25", nums=("1,045 tonnes",)),

    beat("That's more than double the average pace from the decade before "
         "it.",
         "evidence", "chart", ch="10", dur=4.8,
         intent="A simple before/after comparison, sourced",
         q="Central bank gold buying: 2010s average vs. now (conceptual)",
         data={"kind": "bar_compare", "title": "Central bank gold buying pace", "points": [
                {"label": "2010s average", "value": 4, "emphasis": "normal"},
                {"label": "Since 2022", "value": 9, "emphasis": "positive"}],
               "prefix": "", "suffix": "", "decimals": 0, "abbreviate": False,
               "note": "Illustrative scale, based on WGC reported figures"},
         src="wgc25"),

    beat("Gold recently passed the euro to become the world's second-largest "
         "reserve asset — behind only the US dollar itself.",
         "payoff", "chart", ch="10", dur=6.8,
         intent="Reserve asset share, branded and sourced to the ECB",
         q="Share of global reserves, 2024",
         data={"kind": "bar_compare", "title": "Share of global official reserves, 2024", "points": [
                {"label": "US Dollar", "value": 46, "emphasis": "primary"},
                {"label": "Gold", "value": 20, "emphasis": "positive"},
                {"label": "Euro", "value": 16, "emphasis": "normal"}],
               "prefix": "", "suffix": "%", "decimals": 0,
               "source": "European Central Bank, June 2025"},
         src="ecb25", nums=("20%", "16%", "46%")),

    # ── 11 · WHY GOLD SURPRISES BEGINNERS ────────────────────────────────── #
    beat("Here's what trips up a lot of beginners: gold doesn't always do "
         "what the textbook says it should.",
         "tension", "mgfx", ch="11", dur=5.4, tr="fade",
         intent="The counterintuitive setup line",
         q="GOLD DOESN'T ALWAYS FOLLOW THE TEXTBOOK"),

    beat("Rates can rise and gold can still rise too — if inflation "
         "expectations are climbing even faster, or fear is doing more work "
         "than rates that week.",
         "evidence", "stock", ch="11", dur=7.2,
         intent="Real analyst reviewing multiple charts, complexity shown as a real working environment",
         q="financial analyst reviewing multiple charts screens",
         kw=("analyst reviewing financial charts", "trading desk multiple monitors analysis")),

    beat("Gold isn't reacting to one input. It's pricing all four at once — "
         "and they don't always agree.",
         "mechanism", "mgfx", ch="11", dur=5.8,
         intent="All four forces shown pulling in different directions at once",
         q="FOUR FORCES. PRICED AT ONCE. NOT ALWAYS ALIGNED."),

    # ── 12 · LEVERAGE AND RISK ────────────────────────────────────────────── #
    beat("Now, XAU/USD isn't just a price to understand — for some, it's "
         "also something to trade. That's where people get into trouble.",
         "tension", "stock", ch="12", dur=6.4, tr="fade",
         intent="Real trading platform interface, order ticket visible, neutral not sensational",
         q="trading platform interface order ticket screen",
         kw=("trading app interface screen", "trading platform order entry close up")),

    beat("In the US, federal law has restricted leveraged retail gold "
         "trading since 2010 — these contracts must either deliver real "
         "metal within twenty-eight days, or trade on a regulated exchange.",
         "mechanism", "chart", ch="12", dur=8.4,
         intent="The 28-day delivery rule, branded and sourced to the CFTC",
         q="US law: leveraged retail metals — 28-day delivery or a regulated exchange",
         data={"kind": "counter", "title": "US leveraged retail metals rule", "points": [
                {"label": "Actual delivery required within", "value": 28, "emphasis": "primary"}],
               "prefix": "", "suffix": " days", "decimals": 0,
               "source": "Commodity Exchange Act § 2(c)(2)(D)"},
         src="cftc_gold", nums=("28 days",)),

    beat("The CFTC has taken multi-million dollar enforcement action against "
         "offshore platforms offering exactly this kind of leveraged gold "
         "trading.",
         "consequence", "mgfx", ch="12", dur=6.4,
         intent="Enforcement fact, stated plainly, sourced",
         q="CFTC ENFORCEMENT: $38M ORDERED AGAINST AN UNREGISTERED LEVERAGED-METALS SCHEME",
         src="cftc_monex", nums=("$38 million",)),

    beat("That doesn't mean gold can't be traded responsibly. It means "
         "leverage on a volatile asset is exactly as risky as it sounds.",
         "payoff", "mgfx", ch="12", dur=5.8, emo="cautionary",
         intent="The balanced, non-alarmist close to the risk section",
         q="LEVERAGE ON A VOLATILE ASSET IS EXACTLY AS RISKY AS IT SOUNDS"),

    # ── 13 · UNDERSTANDING VS. PREDICTING ────────────────────────────────── #
    beat("Here's the honest distinction: understanding why gold moves is not "
         "the same as predicting where it moves next.",
         "turn", "mgfx", ch="13", dur=6.0, tr="fade",
         intent="The thesis-adjacent line, calm and direct",
         q="UNDERSTANDING WHY ≠ PREDICTING WHAT'S NEXT"),

    beat("Professionals who study this for a living still get the short "
         "term wrong constantly. The mechanics are knowable. The next candle "
         "isn't.",
         "consequence", "stock", ch="13", dur=6.6,
         intent="Real institutional trading floor, professionals at work, humility not spectacle",
         q="institutional trading floor professionals wide shot",
         kw=("bank trading floor wide shot", "institutional dealing room professionals")),

    # ── 14 · CLOSING ──────────────────────────────────────────────────────── #
    beat("So — XAU/USD isn't mysterious. It's the dollar, interest rates, "
         "inflation, fear, and global demand, compressed into a single "
         "number.",
         "payoff", "stock", ch="14", dur=6.8, tr="fade",
         intent="Wide cinematic gold bars shot, callback to the cold open, dusk-toned",
         q="gold bars stacked wide cinematic warm light",
         kw=("gold bullion bars wide shot", "gold bars vault cinematic lighting")),

    beat("One troy ounce. Priced in dollars. Moved by four forces most "
         "people never learn to see.",
         "payoff", "chart", ch="14", dur=5.6,
         intent="Callback to the hook card — same pair, now understood",
         q="XAU / USD — callback",
         data={"kind": "counter", "title": "XAU / USD", "points": [
                {"label": "1 troy oz. gold, priced in", "value": 1, "emphasis": "primary"}],
               "prefix": "", "suffix": " USD", "decimals": 0, "abbreviate": False}),

    beat("Understanding those forces won't tell you tomorrow's price. But "
         "it's the difference between reacting to gold, and actually "
         "understanding it.",
         "cta", "mgfx", ch="14", dur=6.6,
         intent="The thesis line, closing the loop opened in the cold open",
         q="REACTING TO GOLD. OR UNDERSTANDING IT."),

    beat("If you want to keep understanding markets instead of guessing at "
         "them — that's exactly what this channel is for.",
         "cta", "mgfx", ch="14", dur=6.0,
         intent="Channel CTA card, calm and simple, matching the Forex episode's closing card",
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
        video_id="xauusd_ep01_how_gold_trading_works",
        channel_id="k70_economy",
        niche="usa_finance",
        structure_id="one_number_story",
        title="XAU/USD Explained — How Gold Trading Against the US Dollar Actually Works",
        hook="Gold has been money, a war chest, a crisis hedge, and one of the "
             "most closely watched prices on Earth. But when traders say "
             "XAU/USD is moving — what are they actually looking at?",
        description=(
            "XAU/USD EXPLAINED — How gold trading against the US dollar actually "
            "works, in plain English.\n\n"
            "This video breaks down what XAU/USD actually means, why gold is "
            "quoted in US dollars, how to read a gold price quote, and the four "
            "forces that actually move it: US dollar strength, Federal Reserve "
            "interest rate policy, real yields (the opportunity cost of holding "
            "an asset that pays no interest), inflation expectations, and "
            "safe-haven demand during geopolitical uncertainty. It also covers "
            "record central bank gold buying, why gold sometimes defies simple "
            "textbook expectations, how US law treats leveraged retail gold "
            "trading, and the difference between understanding a market and "
            "trying to predict its next move.\n\n"
            "SOURCES: World Gold Council, Gold Demand Trends Full Year 2024 — "
            "https://www.gold.org/goldhub/research/gold-demand-trends/gold-demand-trends-full-year-2024 "
            "· European Central Bank, International Role of the Euro report, "
            "June 2025 · U.S. Commodity Futures Trading Commission, "
            "\"Gold Is No Safe Investment\" — "
            "https://www.cftc.gov/LearnAndProtect/AdvisoriesAndArticles/gold_is_no_safe_investment.htm "
            "· CFTC press release 8643-22\n\n"
            "This video is educational and describes how the XAU/USD market "
            "works. It does not recommend buying, selling or trading gold. "
            "Trading gold, especially with leverage, carries a high risk of "
            "loss. See disclaimer."
        ),
        tags=["xauusd", "xau usd", "gold trading", "how gold trading works",
              "gold price explained", "gold vs dollar", "real yields",
              "federal reserve gold", "safe haven gold", "central bank gold buying",
              "gold explained", "trading for beginners", "finance documentary",
              "world gold council"],
        hashtags=["#xauusd", "#gold", "#finance", "#investing", "#k70finance"],
        thumbnail_text="XAU/USD EXPLAINED",
        disclaimer=("Educational content. Not financial advice. Trading gold, "
                    "especially with leverage, carries a high risk of loss."),
    )

    graph = SceneGraph(
        meta=meta, fps=30, width=1920, height=1080, brand_id="k70",
        scenes=scenes,
        storyboard=StoryboardData(version="1.0", scenes=sb_scenes),
    )
    return graph, asset_plan, total


def write_narration(total: float) -> str:
    lines = [f"# XAU/USD Explained — Ep. 1 narration\n",
             f"Total estimated runtime: {total:.1f}s (~{total/60:.2f} min)\n"]
    for i, b in enumerate(BEATS, start=1):
        lines.append(f"**s{i}** [{b['ch']} · {b['role']} · {b['vis']}]  \n{b['n']}\n")
    return "\n".join(lines)


def write_sources() -> str:
    lines = ["# XAU/USD Explained — Ep. 1 sources\n"]
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
