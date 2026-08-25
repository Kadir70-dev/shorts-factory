#!/usr/bin/env python3
"""
THE COMPLETE HISTORY OF BITCOIN · EPISODE 1 — "The World Before Bitcoin (1970-2008)"

Single source of truth for the episode. The narration, the per-sentence visual
plan, the charts, the storyboard and the source citations are authored ONCE in
`BEATS` below and emitted as:

    data/series/bitcoin_history/ep01/scene_graph.json   validated SceneGraph
    data/series/bitcoin_history/ep01/narration.md       the read script
    data/series/bitcoin_history/ep01/asset_plan.json    per-beat sourcing plan
    data/series/bitcoin_history/ep01/timeline.md        the fact/date spine

Nothing here fakes a render receipt: `threejs_provenance`,
`motion_graphics_provenance`, `ai_broll_provenance` and `asset_provenance` stay
EMPTY in the graph because those are written by the pipeline stages that
actually rendered or fetched something. The intent that drives them lives in
`visual.strategy`, `visual.query`, `visual.visual_intent` and the storyboard.

    .venv/bin/python scripts/build_bitcoin_ep01.py
    .venv/bin/python scripts/produce.py --preset documentary_series \
        --from-json data/series/bitcoin_history/ep01/scene_graph.json --keep
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

OUT_DIR = ROOT / "data" / "series" / "bitcoin_history" / "ep01"

# --------------------------------------------------------------------------- #
# Visual channel vocabulary.
#
# `vis` on a beat names ONE of the six visual-budget channels. Everything the
# renderer needs (Visual.type, Visual.strategy, camera motion, storyboard
# recommendation, asset priority) is derived from it, so a beat can never claim
# a strategy its channel cannot serve.
# --------------------------------------------------------------------------- #
CHANNELS: dict[str, dict] = {
    # kinetic typography over the branded field — the claim itself, moving
    "mgfx":     {"type": "motion_gfx", "strategy": "motion_gfx", "channel": "motion_gfx",
                 "svt": "dramatic",    "motion": "none",
                 "sb": "motion_gfx", "prio": ["local_graphics", "branded_fallback"]},
    # 3D geography / scale / flythrough — the Three.js worker
    "threejs":  {"type": "threejs",    "strategy": "threejs",    "channel": "threejs",
                 "svt": "data_viz",    "motion": "none",
                 "sb": "threejs",   "prio": ["local_graphics", "branded_fallback"]},
    # branded animated chart driven by real, cited numbers
    "chart":    {"type": "dataviz",    "strategy": "dataviz",    "channel": "charts",
                 "svt": "data_viz",    "motion": "none",
                 "sb": "dataviz",   "prio": ["local_graphics", "branded_fallback"]},
    # archival: government, central-bank, newspaper, museum, public-domain photo
    "archival": {"type": "image",      "strategy": "real",       "channel": "official",
                 "svt": "real_footage", "motion": "ken_burns",
                 "sb": "real",      "prio": ["licensed_image", "exact_footage",
                                             "local_graphics", "branded_fallback"]},
    # real moving footage of an everyday, genuinely filmable subject
    "stock":    {"type": "broll",      "strategy": "real",       "channel": "stock",
                 "svt": "real_footage", "motion": "ken_burns",
                 "sb": "real",      "prio": ["exact_footage", "licensed_image",
                                             "local_graphics", "branded_fallback"]},
    # cinematic recreation of a moment no camera was in the room for
    "ai":       {"type": "ai_image",   "strategy": "ai_image",   "channel": "ai_broll",
                 "svt": "dramatic",    "motion": "zoom_in",
                 "sb": "ai_image",  "prio": ["ai_recreation", "licensed_image",
                                             "local_graphics", "branded_fallback"]},
}

# beat_role → storyboard emotion. The role also drives the music envelope
# (pipeline/music.py): hook loud, context/mechanism quiet, turn/reveal/evidence
# swell, cta uplift. Choreographing roles IS choreographing the score.
EMOTION = {
    "hook": "urgent", "tension": "tense", "stakes": "tense", "context": "neutral",
    "evidence": "confident", "turn": "surprising", "reveal": "surprising",
    "contrast": "curious", "mechanism": "curious", "consequence": "cautionary",
    "payoff": "confident", "cta": "urgent",
}

# --------------------------------------------------------------------------- #
# Source register. Every id here was opened and checked during authoring; the
# `source` overlay and the asset plan both cite by id so a claim can never drift
# away from the document that supports it.
# --------------------------------------------------------------------------- #
SOURCES: dict[str, dict] = {
    "wb_bw":     {"label": "World Bank Group Archives",
                  "url": "https://www.worldbank.org/en/about/archives/history/exhibits/bretton-woods-monetary-conference.print",
                  "license": "public affairs / editorial use"},
    "frh_bw":    {"label": "Federal Reserve History",
                  "url": "https://www.federalreservehistory.org/essays/bretton-woods-created",
                  "license": "US government work"},
    "triffin":   {"label": "R. Triffin, Joint Economic Committee, Oct 1959",
                  "url": "https://www.nber.org/system/files/working_papers/w24195/w24195.pdf",
                  "license": "academic / editorial"},
    "frh_gold":  {"label": "Federal Reserve History",
                  "url": "https://www.federalreservehistory.org/essays/gold-convertibility-ends",
                  "license": "US government work"},
    "nixon":     {"label": "American Presidency Project",
                  "url": "https://www.presidency.ucsb.edu/documents/address-the-nation-outlining-new-economic-policy-the-challenge-peace",
                  "license": "US government work (public domain)"},
    "mint":      {"label": "U.S. Mint",
                  "url": "https://www.usmint.gov/about/tours-and-locations/fort-knox",
                  "license": "US government work (public domain)"},
    "myb52":     {"label": "USGS Minerals Yearbook 1952",
                  "url": "https://search.library.wisc.edu/digital/AIJCIPOFHBEI7U8K",
                  "license": "US government work (public domain)"},
    "bls":       {"label": "U.S. Bureau of Labor Statistics, CPI-U",
                  "url": "https://www.bls.gov/opub/mlr/2014/article/one-hundred-years-of-price-change-the-consumer-price-index-and-the-american-inflation-experience.htm",
                  "license": "US government work (public domain)"},
    "lbma":      {"label": "London gold fixing, 21 Jan 1980",
                  "url": "https://www.bullionvault.com/gold-news/opinion-analysis/gold-spike-january-1980-11062007",
                  "license": "editorial"},
    "frh_volck": {"label": "Federal Reserve History",
                  "url": "https://www.federalreservehistory.org/essays/anti-inflation-measures",
                  "license": "US government work"},
    "frh_snl":   {"label": "Federal Reserve History / GAO 1996",
                  "url": "https://www.federalreservehistory.org/essays/savings-and-loan-crisis",
                  "license": "US government work"},
    "fdic":      {"label": "FDIC, History of the Eighties",
                  "url": "https://www.fdic.gov/resources/publications/history-eighties/volume-1/history-80s-volume-1-part1-01.pdf",
                  "license": "US government work (public domain)"},
    "chaum":     {"label": "D. Chaum, Blind Signatures for Untraceable Payments (1982)",
                  "url": "https://en.wikipedia.org/wiki/DigiCash",
                  "license": "academic / editorial"},
    "cypher":    {"label": "E. Hughes, A Cypherpunk's Manifesto (Mar 1993)",
                  "url": "https://en.wikipedia.org/wiki/Eric_Hughes_(cypherpunk)",
                  "license": "editorial"},
    "doj_eg":    {"label": "U.S. DOJ, 27 Apr 2007",
                  "url": "https://www.justice.gov/archive/opa/pr/2007/April/07_crm_301.html",
                  "license": "US government work (public domain)"},
    "usss_eg":   {"label": "U.S. Secret Service, Jul 2008",
                  "url": "https://www.secretservice.gov/press/releases/2008/07/us-secret-service-led-investigation-digital-currency-business-e-gold-pleads",
                  "license": "US government work (public domain)"},
    "libdol":    {"label": "FBI raid, 14 Nov 2007 (court record)",
                  "url": "https://en.wikipedia.org/wiki/Bernard_von_NotHaus",
                  "license": "editorial"},
    "corralito": {"label": "Corralito, Decree 1570/2001",
                  "url": "https://en.wikipedia.org/wiki/Corralito",
                  "license": "editorial"},
    "frbsf_ar":  {"label": "Federal Reserve Bank of San Francisco",
                  "url": "https://www.frbsf.org/research-and-insights/publications/economic-letter/2002/10/learning-from-argentina-crisis/",
                  "license": "US government work"},
    "hanke":     {"label": "Hanke & Kwok, Cato Journal 29(2), 2009",
                  "url": "https://www.cato.org/sites/cato.org/files/serials/files/cato-journal/2009/5/cj29n2-8.pdf",
                  "license": "academic / editorial"},
    "boe_nr":    {"label": "H.S. Shin, Reflections on Northern Rock (BIS)",
                  "url": "https://www.bis.org/publ/shin_2009.pdf",
                  "license": "editorial"},
    "fed_bear":  {"label": "Federal Reserve Board, Bear Stearns / Maiden Lane",
                  "url": "https://www.federalreserve.gov/regreform/reform-bearstearns.htm",
                  "license": "US government work (public domain)"},
    "fhfa":      {"label": "FHFA, conservatorship history",
                  "url": "https://www.fhfa.gov/conservatorship/history",
                  "license": "US government work (public domain)"},
    "lehman":    {"label": "Lehman Brothers Holdings Chapter 11 petition, 15 Sep 2008",
                  "url": "https://en.wikipedia.org/wiki/Bankruptcy_of_Lehman_Brothers",
                  "license": "editorial"},
    "fed_aig":   {"label": "Federal Reserve Board press release, 16 Sep 2008",
                  "url": "https://www.federalreserve.gov/newsevents/pressreleases/other20080916a.htm",
                  "license": "US government work (public domain)"},
    "eesa":      {"label": "Emergency Economic Stabilization Act, 3 Oct 2008",
                  "url": "https://ballotpedia.org/Emergency_Economic_Stabilization_Act_of_2008",
                  "license": "US government work / editorial"},
    "corelogic": {"label": "CoreLogic, Foreclosure Crisis Decade in Review (2017)",
                  "url": "https://www.alta.org/news-and-publications/news/20170330-CoreLogic-US-Residential-Foreclosure-Crisis-Decade-in-Review",
                  "license": "editorial"},
    "csi":       {"label": "S&P/Case-Shiller national index",
                  "url": "https://www.cmegroup.com/trading/real-estate/files/SP-CSI-2009-Year-in-Review.pdf",
                  "license": "editorial"},
}


def beat(text: str, role: str, vis: str, *, ch: str, intent: str, q: str = "",
         kw: tuple[str, ...] = (), ov: tuple[dict, ...] = (), data: dict | None = None,
         conf: str = "confirmed", tr: str = "", src: str = "", ent: str = "",
         loc: str = "", year: int | None = None, nums: tuple[str, ...] = (),
         emo: str = "", dur: float | None = None) -> dict:
    return {"n": text, "role": role, "vis": vis, "ch": ch, "intent": intent,
            "q": q, "kw": list(kw), "ov": [dict(o) for o in ov], "data": data,
            "conf": conf, "tr": tr, "src": src, "ent": ent, "loc": loc,
            "year": year, "nums": list(nums), "emo": emo, "dur": dur}


# Chapter register — drives the timeline deliverable and the chapter markers.
CHAPTERS = [
    ("00", "Cold Open — The Vault That Could Not Pay"),
    ("01", "The Promise (1944)"),
    ("02", "The Drain (1952-1971)"),
    ("03", "Sunday Night (15 August 1971)"),
    ("04", "The Decade The Money Died (1971-1981)"),
    ("05", "The Machine That Kept Breaking (1986-1998)"),
    ("06", "The Ones Who Tried (1982-2007)"),
    ("07", "When Money Breaks In Real Life (2001-2008)"),
    ("08", "The Collapse (2007-2008)"),
    ("09", "Cliffhanger"),
]


# =========================================================================== #
#  THE EPISODE
# =========================================================================== #
BEATS: list[dict] = [

    # ── 00 · COLD OPEN ───────────────────────────────────────────────────── #
    beat("In the second week of August, 1971, a message reached the United States Treasury.",
         "hook", "ai", ch="00", dur=5.4,
         intent="A night-lit Treasury corridor, one telex machine still running — the moment before anyone knows",
         q="1971 documentary still, empty marble corridor of the US Treasury at night, single desk lamp, telex machine mid-print, deep navy shadow, 35mm grain, anamorphic, cold tungsten key light",
         ov=({"type": "headline", "text": "AUGUST 1971", "y": 0.14},),
         ent="U.S. Treasury", loc="Washington", year=1971, emo="tense"),

    beat("The British government was asking to convert about three billion dollars into gold.",
         "tension", "mgfx", ch="00", dur=5.2,
         intent="The demand set in type: $3,000,000,000 → GOLD",
         q="$3,000,000,000  →  GOLD",
         ov=({"type": "stat", "text": "BRITISH REQUEST", "sub": "$3,000,000,000 in gold", "y": 0.2},),
         src="frh_gold", ent="United Kingdom", year=1971, nums=("$3 billion",), conf="probable"),

    beat("They were entitled to it. That was the deal. That had always been the deal.",
         "context", "archival", ch="00", dur=5.2,
         intent="The Bretton Woods signature page — the contract being invoked",
         q="Bretton Woods Agreement 1944 signature page document scan",
         kw=("bretton woods agreement document", "1944 monetary conference signing"),
         src="wb_bw", year=1944),

    beat("There was only one problem.",
         "turn", "mgfx", ch="00", dur=3.0, tr="dip_to_black",
         intent="Hard type on black — the pivot",
         q="ONE PROBLEM"),

    beat("The gold was not there.",
         "reveal", "ai", ch="00", dur=4.2,
         intent="An almost-empty bullion vault: bare steel shelving, a handful of bars, cold light",
         q="documentary still, interior of a government bullion vault, mostly EMPTY steel shelving, three gold bars remaining, harsh overhead light, dust in the air, wide anamorphic, cold blue-grey, photoreal",
         ov=({"type": "headline", "text": "NOT ENOUGH GOLD", "y": 0.16},), emo="surprising"),

    beat("On Friday the thirteenth, the President of the United States boarded a helicopter and disappeared.",
         "tension", "archival", ch="00", dur=6.0,
         intent="Marine One lifting off the South Lawn, 1971 — the vanishing",
         q="Richard Nixon boarding Marine One helicopter White House 1971",
         kw=("marine one helicopter 1971", "nixon boarding helicopter white house"),
         src="frh_gold", ent="Richard Nixon", year=1971),

    beat("He took fifteen men with him to a mountain retreat in Maryland.",
         "context", "threejs", ch="00", dur=5.0,
         intent="Globe flight: world → United States of America → the Maryland highlands",
         q="Maryland", loc="Maryland", ent="Camp David", year=1971,
         ov=({"type": "lower_third", "text": "CAMP DAVID", "sub": "Catoctin Mountain, Maryland", "y": 0.24},),
         src="frh_gold"),

    beat("No press. No announcement. No record of where they had gone.",
         "tension", "mgfx", ch="00", dur=4.6,
         intent="Three redactions striking through in sequence",
         q="NO PRESS.  NO ANNOUNCEMENT.  NO RECORD."),

    beat("For three days, the most powerful economy on earth held a secret meeting about its own money.",
         "stakes", "ai", ch="00", dur=6.2,
         intent="Recreation: a lodge room, fifteen silhouettes around a table, one lamp, notes face-down",
         q="cinematic documentary recreation, 1971 wood-panelled lodge conference room at night, fifteen men in suits silhouetted around a long table, single warm lamp, papers face down, heavy shadow, 35mm, shallow depth of field",
         ov=({"type": "lower_third", "text": "13-15 AUGUST 1971", "sub": "no minutes released at the time", "y": 0.24},),
         src="frh_gold", conf="probable", emo="tense"),

    beat("And when they came back down, the thing in your wallet was no longer what you thought it was.",
         "turn", "mgfx", ch="00", dur=5.8, tr="dip_to_black",
         intent="A dollar bill dissolving into pure type — the promise leaving the paper",
         q="WHAT IS THIS, REALLY?", emo="surprising"),

    beat("This is the story of how the world lost trust in money.",
         "context", "mgfx", ch="00", dur=4.4,
         intent="Series title card in the brand display face",
         q="THE COMPLETE HISTORY OF BITCOIN",
         ov=({"type": "headline", "text": "THE COMPLETE HISTORY OF BITCOIN", "y": 0.34},
             {"type": "lower_third", "text": "EPISODE ONE", "sub": "The World Before Bitcoin · 1970-2008", "y": 0.46})),

    beat("To understand why a stranger would one day try to build money without banks, you have to understand what the banks did first.",
         "stakes", "mgfx", ch="00", dur=7.0,
         intent="The thesis line, set quietly, in the lower half of frame",
         q="MONEY WITHOUT BANKS"),

    # ── 01 · THE PROMISE (1944) ──────────────────────────────────────────── #
    beat("Twenty-seven years earlier, the war was not yet over.",
         "context", "archival", ch="01", dur=4.4, tr="fade",
         intent="1944 newsreel frame — Europe still at war",
         q="1944 wartime newsreel public domain footage",
         kw=("1944 world war two newsreel", "wartime archive footage 1944"), year=1944),

    beat("And in a hotel in the mountains of New Hampshire, more than seven hundred delegates from forty-four nations sat down to redesign the world.",
         "context", "threejs", ch="01", dur=8.0,
         intent="Globe flight: world → United States → New Hampshire, pin on the conference",
         q="New Hampshire", loc="New Hampshire", ent="Bretton Woods Conference", year=1944,
         ov=({"type": "lower_third", "text": "BRETTON WOODS, NEW HAMPSHIRE", "sub": "1-22 July 1944 · 44 nations", "y": 0.24},),
         src="wb_bw", nums=("44 nations", "730 delegates")),

    beat("They had watched what happens when money dies.",
         "tension", "archival", ch="01", dur=4.0,
         intent="Weimar hyperinflation: children stacking bricks of banknotes",
         q="Weimar Germany 1923 hyperinflation children playing with stacks of banknotes",
         kw=("weimar hyperinflation banknotes 1923", "german inflation money bundles 1923"),
         year=1923),

    beat("Germany, nineteen twenty-three. A wheelbarrow of paper for a loaf of bread.",
         "reveal", "archival", ch="01", dur=5.4,
         intent="The wheelbarrow-of-marks photograph, slow push in",
         q="1923 Germany wheelbarrow of banknotes to buy bread photograph",
         kw=("wheelbarrow money weimar", "1923 german marks wheelbarrow"), year=1923),

    beat("Currencies devalued like weapons. Trade wars. Then real wars.",
         "consequence", "threejs", ch="01", dur=5.0,
         intent="Globe: 1930s devaluations firing between capitals like ordnance, then the map going dark",
         q="Germany", loc="Germany", ent="competitive devaluation", year=1931,
         ov=({"type": "lower_third", "text": "DEVALUE · RETALIATE · WAR", "y": 0.24},)),

    beat("So they built a chain.",
         "mechanism", "stock", ch="01", dur=3.2,
         intent="Real macro footage of a heavy steel chain link taking the load",
         q="heavy steel chain link macro",
         kw=("steel chain link close up", "heavy chain tension macro", "iron chain detail")),

    beat("Every currency on earth would be pegged to the American dollar.",
         "mechanism", "mgfx", ch="01", dur=5.2,
         intent="Currency marks arriving from every side and locking, one by one, onto a single dollar anchor",
         q="EVERY CURRENCY → THE DOLLAR",
         src="frh_bw", year=1944),

    beat("And the American dollar would be pegged to gold. Thirty-five dollars an ounce. Fixed.",
         "reveal", "chart", ch="01", dur=6.2,
         intent="The peg as a single locked figure, rolled up and then frozen",
         data={"kind": "counter", "title": "The Bretton Woods peg",
               "points": [{"label": "1944-1971", "value": 35, "emphasis": "primary"}],
               "prefix": "$", "suffix": " / oz", "decimals": 0, "abbreviate": False,
               "source": "Bretton Woods Agreement, 1944",
               "note": "Fixed for 27 years"},
         ov=({"type": "source", "text": "Federal Reserve History", "y": 0.1},),
         src="frh_bw", nums=("$35",), year=1944),

    beat("Bring your dollars to Washington, and America would hand you the metal.",
         "mechanism", "ai", ch="01", dur=5.2,
         intent="Recreation: gloved hands sliding a gold bar across a counter to a foreign official",
         q="documentary recreation, 1950s, gloved hands sliding a single gold bar across a polished counter towards a man in a dark suit, bank vault interior, warm key light on the bar, everything else in shadow, 35mm macro, photoreal"),

    beat("For the first time in history, the entire planet's money hung from a single promise.",
         "stakes", "threejs", ch="01", dur=6.0,
         intent="Globe flight to the far side of the world — India, a Bretton Woods signatory — tethered by one thread back to Washington",
         q="India", loc="India", ent="Bretton Woods signatories", year=1944,
         ov=({"type": "lower_third", "text": "ONE PROMISE", "sub": "44 signatory nations", "y": 0.24},),
         src="wb_bw", emo="tense"),

    beat("And for a while, it worked beautifully.",
         "context", "stock", ch="01", dur=4.0,
         intent="Post-war prosperity: real footage of busy mid-century commerce",
         q="1950s american city street prosperity",
         kw=("vintage 1950s city street", "retro american downtown archive", "old cars busy street")),

    beat("Then one man did the arithmetic.",
         "turn", "mgfx", ch="01", dur=3.4,
         intent="A single line of longhand arithmetic working itself out across the field",
         q="ONE MAN DID THE ARITHMETIC", emo="surprising"),

    beat("In October nineteen fifty-nine, the economist Robert Triffin told the United States Congress the system was already doomed.",
         "evidence", "archival", ch="01", dur=7.9,
         intent="Triffin before the Joint Economic Committee — the hearing record, his name on the witness line",
         q="Robert Triffin Joint Economic Committee October 1959 testimony record",
         kw=("congressional hearing 1959 testimony", "economist testifying congress 1950s"),
         ov=({"type": "lower_third", "text": "ROBERT TRIFFIN", "sub": "Joint Economic Committee · October 1959", "y": 0.24},),
         src="triffin", ent="Robert Triffin", year=1959),

    beat("To keep the world supplied with dollars, America had to send out more of them than it could ever back.",
         "mechanism", "mgfx", ch="01", dur=8.4,
         intent="The dilemma built as a balance that cannot be levelled: supply the world, or hold the gold — never both",
         q="SUPPLY THE WORLD  ·  OR  ·  BACK THE DOLLAR",
         src="triffin", year=1959, emo="curious"),

    beat("Stop, and world trade starves. Carry on, and the promise breaks.",
         "consequence", "mgfx", ch="01", dur=5.4,
         intent="Two doors, both of them closing",
         q="BOTH ROADS END BADLY", src="triffin"),

    beat("Congress listened politely. Then it did nothing for twelve years.",
         "reveal", "mgfx", ch="01", dur=5.0,
         intent="A hearing transcript closing, then a year counter running 1959 → 1971 in silence",
         q="1959 → 1971", src="triffin", nums=("12 years",), emo="surprising"),

    beat("That was all the time the system had left.",
         "turn", "mgfx", ch="01", dur=4.4, tr="dip_to_black",
         intent="The counter stopping dead on 1971",
         q="TWELVE YEARS LEFT.", year=1971, emo="surprising"),

    # ── 02 · THE DRAIN (1952-1971) ───────────────────────────────────────── #
    beat("A war in Vietnam. A war on poverty. A race to the moon.",
         "context", "archival", ch="02", dur=5.4, tr="fade",
         intent="Three archival frames cut in rhythm — Vietnam, the Great Society, Apollo",
         q="1960s Vietnam war Great Society Apollo public domain archive",
         kw=("vietnam war archive footage", "apollo launch nasa public domain", "1960s america archive"),
         year=1965),

    beat("All of it paid for in dollars. Dollars that flowed out into the world.",
         "mechanism", "threejs", ch="02", dur=5.6,
         intent="Globe: the route of the dollar out of the United States and across the Pacific into Japan",
         q="Japan", loc="Japan", ent="dollar outflow", year=1965,
         ov=({"type": "lower_third", "text": "DOLLARS OUT", "sub": "balance of payments deficit", "y": 0.24},)),

    beat("And the world began to notice something.",
         "tension", "mgfx", ch="02", dur=3.6,
         intent="A ledger tally striking up in the dark, one mark at a time, faster than it can be read",
         q="SOMEONE WAS COUNTING"),

    beat("There were now far more dollars in circulation than there was gold in the vault.",
         "evidence", "ai", ch="02", dur=5.8,
         intent="Recreation: a vault holding one gold bar, buried under a drift of paper claims",
         q="cinematic documentary still, a bank vault interior containing a single gold bar on a plinth, surrounded and half-buried by an enormous drift of paper certificates, cold overhead light, deep shadow, wide anamorphic, photoreal, 35mm grain",
         emo="tense"),

    beat("In nineteen fifty-two, the United States held more than twenty thousand tonnes of gold.",
         "evidence", "chart", ch="02", dur=6.4,
         intent="The reserve at its peak, counted up, then held",
         data={"kind": "counter", "title": "U.S. official gold holdings, 1952",
               "points": [{"label": "1952", "value": 20748, "emphasis": "primary"}],
               "suffix": " t", "decimals": 0, "abbreviate": False,
               "source": "U.S. Treasury (Minerals Yearbook 1952) at $35/oz",
               "note": "Peak of the Bretton Woods era"},
         ov=({"type": "source", "text": "U.S. Treasury", "y": 0.1},),
         src="myb52", year=1952, nums=("20,748 t",)),

    beat("By nineteen seventy-one it held eight thousand, one hundred and thirty-three.",
         "reveal", "chart", ch="02", dur=6.2,
         intent="The same reserve nineteen years later — the collapse shown as a fall, not a number",
         data={"kind": "delta", "title": "U.S. official gold holdings",
               "points": [{"label": "1952", "value": 20748, "emphasis": "normal"},
                          {"label": "1971", "value": 8133, "emphasis": "negative"}],
               "suffix": " t", "decimals": 0, "abbreviate": False, "highlight": 1,
               "source": "U.S. Treasury / U.S. Mint",
               "note": "8,133.46 t — the figure the Mint still reports today"},
         ov=({"type": "source", "text": "U.S. Mint", "y": 0.1},),
         src="mint", year=1971, nums=("8,133 t",), emo="surprising"),

    beat("Sixty-one percent of the gold, gone. Redeemed. Shipped abroad.",
         "consequence", "chart", ch="02", dur=5.6,
         intent="The share that left, filling a meter to sixty-one percent",
         data={"kind": "meter", "title": "Share of U.S. gold reserves lost, 1952-1971",
               "points": [{"label": "gone", "value": 61, "emphasis": "negative"}],
               "suffix": "%", "decimals": 0, "abbreviate": False,
               "source": "U.S. Treasury / U.S. Mint"},
         src="mint", nums=("61%",)),

    beat("France, by most accounts, had been converting for years. Then others followed.",
         "tension", "threejs", ch="02", dur=6.0,
         intent="Globe flight from the United States across the Atlantic to France",
         q="France", loc="France", ent="Banque de France", year=1965,
         ov=({"type": "lower_third", "text": "PARIS CONVERTS", "y": 0.24},),
         conf="probable"),

    beat("It was, in every way that mattered, a bank run.",
         "reveal", "archival", ch="02", dur=5.0,
         intent="Depression-era bank run photograph — the shape of the thing, decades earlier",
         q="1930s bank run crowd outside bank photograph public domain",
         kw=("1933 bank run crowd", "great depression bank queue photograph"),
         year=1933, emo="surprising"),

    beat("Except the bank was the United States of America.",
         "stakes", "ai", ch="02", dur=4.6,
         intent="Recreation: a vault door the height of a building, the national seal cast into its face",
         q="cinematic documentary still, an enormous circular bank vault door filling the frame, a cast metal national seal at its centre, worn steel, single hard raking light from the left, deep shadow, no people, anamorphic, photoreal, 35mm grain",
         emo="tense"),

    beat("And then Britain asked for roughly three billion more.",
         "turn", "ai", ch="02", dur=4.4, tr="whip",
         intent="Recreation: a telex cable landing on an empty Treasury desk, the request half-printed",
         q="cinematic documentary still, a telex printout curling out of a machine onto an empty government desk at night, the paper half-printed, single desk lamp, rotary phone off the hook, deep shadow, macro, photoreal, 35mm grain",
         src="frh_gold", conf="probable", emo="surprising"),

    # ── 03 · SUNDAY NIGHT ────────────────────────────────────────────────── #
    beat("Sunday, the fifteenth of August, nineteen seventy-one. Prime time.",
         "context", "ai", ch="03", dur=5.4, tr="dip_to_black",
         intent="A dark American living room, one CRT glowing, nobody moving",
         q="documentary still, 1971 American living room at night, single wood-cased television glowing, empty armchair, deep shadow, curtains drawn, 35mm grain, warm CRT light as the only source, photoreal",
         ov=({"type": "headline", "text": "15 AUGUST 1971", "y": 0.14},), year=1971),

    beat("The President of the United States went on television and said this:",
         "tension", "archival", ch="03", dur=4.6,
         intent="Nixon at the desk, address to the nation — the actual broadcast frame",
         q="Nixon address to the nation August 15 1971 television broadcast",
         kw=("nixon televised address 1971", "president address to the nation archive"),
         src="nixon", ent="Richard Nixon", year=1971),

    beat("I have directed Secretary Connally to suspend temporarily the convertibility of the dollar into gold.",
         "reveal", "mgfx", ch="03", dur=8.2,
         intent="The quotation typed on screen, with the word temporarily isolated",
         q="\"...suspend temporarily the convertibility of the dollar into gold.\"",
         ov=({"type": "quote", "text": "“suspend temporarily the convertibility of the dollar into gold”",
              "sub": "Richard Nixon, 15 August 1971", "y": 0.3},),
         src="nixon", ent="Richard Nixon", year=1971, emo="surprising"),

    beat("Temporarily.",
         "turn", "mgfx", ch="03", dur=3.0,
         intent="One word, alone, in the display face",
         q="TEMPORARILY"),

    beat("More than fifty years later, it has never been un-suspended.",
         "reveal", "mgfx", ch="03", dur=5.2,
         intent="A counter running from 1971 to now under the word",
         q="STILL SUSPENDED", emo="surprising"),

    beat("In one sentence, on a Sunday night, the link between money and metal was cut.",
         "consequence", "ai", ch="03", dur=6.0,
         intent="Recreation: a heavy chain link severed, gold light draining out of frame",
         q="cinematic macro still, a heavy iron chain snapped mid-link, one half gold, one half paper, black background, single hard rim light, smoke, photoreal, anamorphic"),

    beat("From that moment, every dollar, every pound, every yen on earth was backed by exactly one thing.",
         "mechanism", "threejs", ch="03", dur=6.6,
         intent="Globe: currency nodes lighting up worldwide with nothing beneath them",
         q="United States of America", loc="United States of America", year=1971,
         ov=({"type": "lower_third", "text": "EVERY CURRENCY ON EARTH", "y": 0.24},)),

    beat("Trust.",
         "reveal", "mgfx", ch="03", dur=3.0,
         intent="One word, centred, the whole thesis of the series",
         q="TRUST"),

    beat("Trust that the people printing it would not print too much.",
         "stakes", "stock", ch="03", dur=5.2,
         intent="Real footage: banknote sheets moving through a printing press",
         q="banknote printing press money sheets",
         kw=("money printing press", "banknote sheets printing", "currency press machine")),

    beat("Nixon told the country their dollar would be worth just as much tomorrow as it was today.",
         "context", "archival", ch="03", dur=6.2,
         intent="The transcript page with that sentence underlined",
         q="Nixon 1971 economic policy address transcript document",
         src="nixon", ent="Richard Nixon", year=1971),

    beat("He was wrong by a distance almost nobody alive had imagined.",
         "turn", "chart", ch="03", dur=6.0, tr="dip_to_black",
         intent="What one 1971 dollar was worth by 2008",
         data={"kind": "delta", "title": "Purchasing power of one 1971 dollar",
               "points": [{"label": "1971", "value": 1.00, "emphasis": "normal"},
                          {"label": "2008", "value": 0.19, "emphasis": "negative"}],
               "prefix": "$", "decimals": 2, "abbreviate": False, "highlight": 1,
               "source": "BLS CPI-U (40.5 → 215.3)",
               "note": "An 81% loss of purchasing power"},
         ov=({"type": "source", "text": "U.S. Bureau of Labor Statistics", "y": 0.1},),
         src="bls", nums=("$0.19",), emo="surprising"),

    # ── 04 · THE DECADE THE MONEY DIED ───────────────────────────────────── #
    beat("The nineteen seventies did not feel like a monetary experiment. They felt like a mugging.",
         "hook", "stock", ch="04", dur=6.2, tr="fade",
         intent="Real footage: a supermarket aisle, price stickers, hands hesitating",
         q="supermarket price tags shopper hesitating",
         kw=("supermarket prices shopping", "grocery store price tag", "worried shopper receipt")),

    beat("Gold had been fixed at thirty-five dollars an ounce for a generation.",
         "context", "stock", ch="04", dur=5.0,
         intent="Real footage of stacked bullion bars, unchanging, while the number on screen does not move",
         q="gold bullion bars stacked vault",
         kw=("gold bars stacked", "bullion bar close up", "gold ingots vault"),
         src="frh_bw", nums=("$35",)),

    beat("On the twenty-first of January, nineteen eighty, it fixed in London at eight hundred and fifty.",
         "evidence", "chart", ch="04", dur=7.0,
         intent="The peg against the free market — a wall, not a line",
         data={"kind": "delta", "title": "Gold, London fixing",
               "points": [{"label": "1971 peg", "value": 35, "emphasis": "normal"},
                          {"label": "21 Jan 1980", "value": 850, "emphasis": "primary"}],
               "prefix": "$", "suffix": " / oz", "decimals": 0, "abbreviate": False,
               "highlight": 1, "source": "London gold fixing, 21 January 1980",
               "note": "All-time high of the fixing at the time"},
         ov=({"type": "source", "text": "London gold fixing", "y": 0.1},),
         src="lbma", year=1980, nums=("$850",), emo="surprising"),

    beat("That is not gold getting more valuable. That is the dollar getting smaller.",
         "reveal", "mgfx", ch="04", dur=5.6,
         intent="The same bar, unchanged, while the dollar shrinks beside it",
         q="THE DOLLAR GOT SMALLER"),

    beat("At the grocery store, prices moved while you shopped.",
         "consequence", "ai", ch="04", dur=4.8,
         intent="Recreation: a shelf where every price label has been over-stickered three times",
         q="documentary still, 1970s American supermarket shelf, price labels over-stickered three and four times, hand-written increases, harsh fluorescent light, muted film stock, photoreal, 35mm"),

    beat("By March nineteen eighty, American consumer prices were rising at fourteen point eight percent a year.",
         "evidence", "chart", ch="04", dur=7.2,
         intent="The full decade of inflation drawn left to right, ending at the spike",
         data={"kind": "line_trend", "title": "U.S. inflation rate, annual average",
               "points": [{"label": "1971", "value": 4.4}, {"label": "1972", "value": 3.2},
                          {"label": "1973", "value": 6.2}, {"label": "1974", "value": 11.0},
                          {"label": "1975", "value": 9.1}, {"label": "1976", "value": 5.8},
                          {"label": "1977", "value": 6.5}, {"label": "1978", "value": 7.6},
                          {"label": "1979", "value": 11.3}, {"label": "1980", "value": 13.5,
                                                             "emphasis": "negative"},
                          {"label": "1981", "value": 10.3}, {"label": "1982", "value": 6.2}],
               "suffix": "%", "decimals": 1, "abbreviate": False, "highlight": 9,
               "source": "U.S. Bureau of Labor Statistics, CPI-U",
               "note": "12-month CPI peaked at 14.8% in March 1980"},
         ov=({"type": "source", "text": "BLS CPI-U", "y": 0.1},),
         src="bls", year=1980, nums=("14.8%",)),

    beat("A raise was not a raise. A savings account was a slow leak.",
         "consequence", "stock", ch="04", dur=5.4,
         intent="Real footage: a payslip and a bank passbook on a table, coins being counted out beside them",
         q="payslip bank book counting coins on table",
         kw=("counting coins on table", "payslip paperwork close up",
             "savings book bank statement")),

    beat("People who had done everything right — worked, saved, never borrowed — were quietly being robbed.",
         "stakes", "ai", ch="04", dur=6.8,
         intent="Recreation: a kitchen table, a passbook savings book, an older couple's hands",
         q="documentary still, 1970s kitchen table at dusk, an open passbook savings book, two older working hands resting on it, unopened bills, single window light, desaturated, 35mm, photoreal",
         emo="cautionary"),

    beat("And the only man who could stop it decided to break the country to do it.",
         "turn", "archival", ch="04", dur=5.8,
         intent="Paul Volcker at the Federal Reserve, cigar, testimony",
         q="Paul Volcker Federal Reserve chairman 1979 testimony photograph",
         kw=("paul volcker federal reserve 1980", "volcker congressional testimony archive"),
         src="frh_volck", ent="Paul Volcker", year=1979, emo="surprising"),

    beat("Paul Volcker took interest rates to nineteen percent.",
         "evidence", "chart", ch="04", dur=5.6,
         intent="The rate spike as one hero figure",
         data={"kind": "counter", "title": "Effective federal funds rate, peak",
               "points": [{"label": "June 1981", "value": 19.1, "emphasis": "negative"}],
               "suffix": "%", "decimals": 1, "abbreviate": False,
               "source": "Federal Reserve",
               "note": "All-time high of the effective rate"},
         ov=({"type": "source", "text": "Federal Reserve", "y": 0.1},),
         src="frh_volck", year=1981, nums=("19.1%",)),

    beat("Mortgages became unaffordable. Factories closed. Unemployment passed ten percent.",
         "consequence", "threejs", ch="04", dur=6.2,
         intent="Globe flight down into the industrial Midwest — Ohio — where the 1981-82 recession landed hardest",
         q="Ohio", loc="Ohio", ent="1981-82 recession", year=1982,
         ov=({"type": "lower_third", "text": "THE INDUSTRIAL MIDWEST", "sub": "unemployment peaked at 10.8%", "y": 0.24},),
         src="fdic", nums=("10.8%",)),

    beat("It worked. Inflation broke.",
         "payoff", "mgfx", ch="04", dur=3.8,
         intent="The inflation line finally bending down, alone on the field",
         q="IT WORKED"),

    beat("The value of your money is a decision. And you are not the one making it.",
         "reveal", "mgfx", ch="04", dur=6.4, tr="dip_to_black",
         intent="The line broken across two cards, the second landing on black",
         q="YOU ARE NOT THE ONE DECIDING", emo="surprising"),

    # ── 05 · THE MACHINE THAT KEPT BREAKING ──────────────────────────────── #
    beat("Then came the pattern.",
         "hook", "mgfx", ch="05", dur=3.2, tr="fade",
         intent="The word pattern, repeating and receding into the frame",
         q="THE PATTERN"),

    beat("Between nineteen eighty-six and nineteen ninety-five, one thousand and forty-three American savings and loans failed.",
         "evidence", "chart", ch="05", dur=7.6,
         intent="Failed institutions against the total that existed",
         data={"kind": "bar_compare", "title": "U.S. savings & loans, 1986-1995",
               "points": [{"label": "Existed", "value": 3234, "emphasis": "normal"},
                          {"label": "Failed", "value": 1043, "emphasis": "negative"}],
               "decimals": 0, "abbreviate": False, "highlight": 1,
               "source": "FDIC / GAO (1996)",
               "note": "Nearly one in three"},
         ov=({"type": "source", "text": "FDIC", "y": 0.1},),
         src="frh_snl", year=1990, nums=("1,043", "3,234")),

    beat("The cleanup cost about a hundred and sixty billion dollars.",
         "evidence", "chart", ch="05", dur=5.4,
         intent="Total cost, then the share of it that came from the public",
         data={"kind": "bar_compare", "title": "Cost of the savings & loan crisis",
               "points": [{"label": "Total", "value": 160e9, "emphasis": "normal"},
                          {"label": "Taxpayers", "value": 132.1e9, "emphasis": "negative"}],
               "prefix": "$", "decimals": 1, "abbreviate": True, "highlight": 1,
               "source": "U.S. General Accounting Office, 1996"},
         ov=({"type": "source", "text": "GAO 1996", "y": 0.1},),
         src="frh_snl", nums=("$160B", "$132.1B")),

    beat("A hundred and thirty-two billion of it came from taxpayers.",
         "consequence", "mgfx", ch="05", dur=5.0,
         intent="The taxpayer share separating out and landing on the viewer's side",
         q="$132,100,000,000  ·  YOU", src="frh_snl", emo="cautionary"),

    beat("October nineteenth, nineteen eighty-seven. The Dow Jones fell twenty-two point six percent in a single day.",
         "turn", "chart", ch="05", dur=7.4,
         intent="Black Monday as a single vertical drop",
         data={"kind": "counter", "title": "Dow Jones, 19 October 1987",
               "points": [{"label": "One session", "value": -22.6, "emphasis": "negative"}],
               "suffix": "%", "decimals": 1, "abbreviate": False,
               "source": "Dow Jones Industrial Average",
               "note": "Largest one-day percentage fall on record"},
         year=1987, nums=("-22.6%",), emo="surprising"),

    beat("The worst day in the history of the American stock market.",
         "stakes", "archival", ch="05", dur=4.8,
         intent="Trading floor, 19 October 1987 — traders with their heads in their hands",
         q="Black Monday October 19 1987 stock exchange trading floor photograph",
         kw=("1987 stock market crash trading floor", "black monday traders 1987"),
         year=1987),

    beat("No war. No attack. Just the machine.",
         "reveal", "ai", ch="05", dur=4.4,
         intent="Recreation: a vast mainframe hall running with no human being in it",
         q="cinematic documentary still, an enormous 1980s mainframe computer hall, rows of tape drives spinning, indicator lights, absolutely no people, cold fluorescent light down a long corridor, wide anamorphic, photoreal, 35mm grain"),

    beat("Nineteen ninety-seven. Thailand's currency broke.",
         "turn", "threejs", ch="05", dur=4.8,
         intent="Globe flight down to Thailand",
         q="Thailand", loc="Thailand", ent="Thai baht", year=1997,
         ov=({"type": "lower_third", "text": "BANGKOK, JULY 1997", "sub": "the baht floats", "y": 0.24},)),

    beat("The contagion took Indonesia, South Korea and Malaysia with it.",
         "consequence", "threejs", ch="05", dur=5.4,
         intent="The globe spreading the failure outward from Bangkok across the region",
         q="Indonesia", loc="Indonesia", ent="Asian financial crisis", year=1997,
         ov=({"type": "lower_third", "text": "CONTAGION", "y": 0.24},)),

    beat("Nineteen ninety-eight: Russia defaulted on its own debt.",
         "turn", "threejs", ch="05", dur=5.2,
         intent="Globe flight from Asia across to Russia",
         q="Russia", loc="Russia", ent="Russian default", year=1998,
         ov=({"type": "lower_third", "text": "MOSCOW, AUGUST 1998", "y": 0.24},)),

    beat("Weeks later, one hedge fund in Connecticut had grown so large that its failure threatened the entire global system.",
         "stakes", "ai", ch="05", dur=7.4,
         intent="Recreation: a quiet suburban office park at night, one lit window, no signage",
         q="documentary still, anonymous low-rise office building in a wooded Connecticut business park at night, one window lit, no signage, empty car park, wet asphalt, cold blue moonlight, cinematic, photoreal",
         ov=({"type": "lower_third", "text": "LONG-TERM CAPITAL MANAGEMENT", "sub": "Greenwich, Connecticut · 1998", "y": 0.24},),
         ent="Long-Term Capital Management", loc="Connecticut", year=1998, emo="tense"),

    beat("The Federal Reserve gathered its rescuers in a room and organised a bailout.",
         "mechanism", "threejs", ch="05", dur=5.8,
         intent="Globe flight from Connecticut down into New York, landing on Liberty Street",
         q="New York", loc="New York", ent="Federal Reserve Bank of New York", year=1998,
         ov=({"type": "lower_third", "text": "LIBERTY STREET, NEW YORK", "sub": "September 1998", "y": 0.24},)),

    beat("Notice the pattern.",
         "turn", "mgfx", ch="05", dur=3.2,
         intent="Back to the chapter's word, now with four failures stacked behind it",
         q="NOTICE THE PATTERN"),

    beat("The gains were private. The losses became everyone's.",
         "reveal", "mgfx", ch="05", dur=5.2,
         intent="Two columns: profit flowing to a few, loss flowing to the many",
         q="PRIVATE GAINS.  PUBLIC LOSSES.", emo="surprising"),

    beat("And by the mid-nineties, a small, strange group of people had started asking a question nobody in finance was asking.",
         "turn", "ai", ch="05", dur=7.2,
         intent="Recreation: a dark bedroom, a CRT terminal, green text, one person's silhouette",
         q="documentary still, 1990s bedroom office at night, beige CRT monitor glowing green text, cables everywhere, a silhouette hunched close to the screen, single monitor light source, heavy grain, photoreal, anamorphic",
         emo="curious"),

    beat("Not: how do we fix the banks?",
         "mechanism", "stock", ch="05", dur=3.8,
         intent="Real footage: the stone facade and revolving door of an ordinary bank branch",
         q="bank branch entrance facade revolving door",
         kw=("bank building entrance", "bank branch facade", "revolving door office")),

    beat("But: what if you did not need one?",
         "reveal", "mgfx", ch="05", dur=4.6, tr="dip_to_black",
         intent="The real question, alone, held longer than comfortable",
         q="WHAT IF YOU DIDN'T NEED ONE?", emo="surprising"),

    # ── 06 · THE ONES WHO TRIED ──────────────────────────────────────────── #
    beat("The question started with a cryptographer named David Chaum.",
         "context", "archival", ch="06", dur=5.0, tr="fade",
         intent="Chaum, early eighties, academic portrait",
         q="David Chaum cryptographer 1980s photograph",
         kw=("david chaum cryptographer", "1980s computer science laboratory"),
         src="chaum", ent="David Chaum", year=1982),

    beat("In nineteen eighty-two, he published a paper called Blind Signatures for Untraceable Payments.",
         "evidence", "mgfx", ch="06", dur=6.6,
         intent="Document highlight: the paper's title page rebuilt in the brand type, the title sweeping into focus",
         q="BLIND SIGNATURES FOR UNTRACEABLE PAYMENTS · D. CHAUM · 1982",
         ov=({"type": "lower_third", "text": "BLIND SIGNATURES FOR UNTRACEABLE PAYMENTS", "sub": "D. Chaum, 1982", "y": 0.24},),
         src="chaum", ent="David Chaum", year=1982, nums=("1982",)),

    beat("The idea was almost impossible to believe: digital money a bank could validate without ever seeing who was spending it.",
         "mechanism", "mgfx", ch="06", dur=8.0,
         intent="A diagram building: payer → blinded token → bank signature → merchant, with the payer never identified",
         q="SIGN IT WITHOUT SEEING IT", emo="curious"),

    beat("Cash, but for computers. Private by mathematics, not by permission.",
         "reveal", "mgfx", ch="06", dur=5.6,
         intent="The distinction set as two contrasting lines",
         q="PRIVATE BY MATHEMATICS"),

    beat("In nineteen eighty-nine he founded a company in Amsterdam called DigiCash.",
         "context", "threejs", ch="06", dur=5.8,
         intent="Globe flight from the United States to the Netherlands",
         q="Netherlands", loc="Netherlands", ent="DigiCash", year=1989,
         ov=({"type": "lower_third", "text": "DIGICASH", "sub": "Amsterdam, 1989", "y": 0.24},),
         src="chaum"),

    beat("Deutsche Bank signed up. Credit Suisse signed up.",
         "evidence", "threejs", ch="06", dur=5.0,
         intent="Globe flight from Amsterdam east to Germany, then south to Switzerland, pinning each partner",
         q="Switzerland", loc="Switzerland", ent="Credit Suisse", year=1994,
         ov=({"type": "lower_third", "text": "DEUTSCHE BANK · CREDIT SUISSE", "y": 0.24},),
         src="chaum"),

    beat("It was, by a full decade, the future.",
         "payoff", "mgfx", ch="06", dur=4.0,
         intent="A decade-long gap drawn as distance on the field",
         q="TEN YEARS EARLY"),

    beat("In November nineteen ninety-eight, DigiCash filed for bankruptcy.",
         "turn", "chart", ch="06", dur=5.8,
         intent="Nine years, drawn as a lifespan that simply stops",
         data={"kind": "delta", "title": "DigiCash",
               "points": [{"label": "Founded", "value": 1989, "emphasis": "normal"},
                          {"label": "Bankrupt", "value": 1998, "emphasis": "negative"}],
               "decimals": 0, "abbreviate": False, "highlight": 1,
               "source": "Chapter 11 filing, November 1998"},
         src="chaum", ent="DigiCash", year=1998, emo="surprising"),

    beat("Meanwhile, in nineteen ninety-two, three men in the San Francisco Bay Area started a mailing list.",
         "context", "threejs", ch="06", dur=6.6,
         intent="Globe flight down to California and the Bay",
         q="California", loc="California", ent="Cypherpunks mailing list", year=1992,
         ov=({"type": "lower_third", "text": "SAN FRANCISCO BAY, 1992", "y": 0.24},),
         src="cypher"),

    beat("Tim May. Eric Hughes. John Gilmore.",
         "context", "mgfx", ch="06", dur=4.4,
         intent="Three names typed in, one per beat of the read",
         q="MAY  ·  HUGHES  ·  GILMORE", src="cypher", year=1992),

    beat("They called themselves cypherpunks.",
         "reveal", "ai", ch="06", dur=4.4,
         intent="Recreation: a cluttered nineties hacker meetup, printouts, laptops, cigarette smoke",
         q="documentary still, early 1990s informal technology meetup in a cramped apartment, paper printouts pinned to walls, beige laptops open, cigarette smoke in lamp light, no faces readable, warm tungsten, heavy grain, photoreal",
         src="cypher", year=1992),

    beat("In March nineteen ninety-three, Hughes published a manifesto with a line that would outlive all of them.",
         "tension", "archival", ch="06", dur=7.0,
         intent="The manifesto text, scrolling in a monospace terminal treatment",
         q="A Cypherpunk's Manifesto 1993 Eric Hughes text",
         src="cypher", ent="Eric Hughes", year=1993),

    beat("Cypherpunks write code.",
         "reveal", "mgfx", ch="06", dur=3.6,
         intent="The line alone, monospace, cursor blinking",
         q="CYPHERPUNKS WRITE CODE.",
         ov=({"type": "quote", "text": "“Cypherpunks write code.”",
              "sub": "Eric Hughes, March 1993", "y": 0.3},),
         src="cypher"),

    beat("And they did.",
         "turn", "stock", ch="06", dur=2.8,
         intent="Real footage: fingers moving fast on a mechanical keyboard, code filling a terminal",
         q="hands typing code terminal screen",
         kw=("typing on mechanical keyboard", "code scrolling terminal screen",
             "programmer typing close up")),

    beat("Nineteen ninety-seven: Adam Back builds Hashcash — a way to make sending something cost real computing work.",
         "mechanism", "mgfx", ch="06", dur=8.0,
         intent="Proof-of-work shown as a cost meter filling before a message can leave",
         q="HASHCASH · 1997 · PROOF OF WORK",
         ov=({"type": "lower_third", "text": "HASHCASH", "sub": "Adam Back, 1997", "y": 0.24},),
         ent="Adam Back", year=1997, emo="curious"),

    beat("Nineteen ninety-eight: Wei Dai publishes b-money — money created by solving computational problems, tracked by everyone at once.",
         "mechanism", "mgfx", ch="06", dur=8.4,
         intent="A ledger duplicating across many nodes rather than sitting in one place",
         q="B-MONEY · 1998 · EVERYONE KEEPS THE LEDGER",
         ov=({"type": "lower_third", "text": "B-MONEY", "sub": "Wei Dai, November 1998", "y": 0.24},),
         ent="Wei Dai", year=1998),

    beat("The same year, Nick Szabo designs bit gold.",
         "context", "mgfx", ch="06", dur=4.4,
         intent="The name set beside the previous two, building a lineage",
         q="BIT GOLD · 1998",
         ov=({"type": "lower_third", "text": "BIT GOLD", "sub": "Nick Szabo, 1998", "y": 0.24},),
         ent="Nick Szabo", year=1998),

    beat("Two thousand and four: Hal Finney builds reusable proofs of work.",
         "context", "mgfx", ch="06", dur=5.0,
         intent="The fourth name completing the chain of predecessors",
         q="RPOW · 2004",
         ov=({"type": "lower_third", "text": "REUSABLE PROOFS OF WORK", "sub": "Hal Finney, 2004", "y": 0.24},),
         ent="Hal Finney", year=2004),

    beat("Brilliant. Elegant. Every single one of them, unfinished.",
         "turn", "mgfx", ch="06", dur=5.4,
         intent="The four names dimming out one by one",
         q="ALL UNFINISHED", emo="surprising"),

    beat("Because they all ran into the same wall.",
         "tension", "ai", ch="06", dur=4.0,
         intent="Recreation: a lone figure at the foot of a blank concrete wall that fills the frame",
         q="cinematic documentary still, a single small figure standing at the base of an enormous blank concrete wall that fills the frame, cold overcast light, no door, no window, wide anamorphic, muted grade, photoreal, 35mm grain"),

    beat("A digital coin is a file. And a file can be copied.",
         "mechanism", "stock", ch="06", dur=5.4,
         intent="Real footage: a file being duplicated on screen, again and again, faster than it can be read",
         q="copying files on computer screen duplicate",
         kw=("file copy progress bar screen", "computer screen duplicating files",
             "hard drive platters spinning"), emo="curious"),

    beat("To stop someone spending the same coin twice, you need a referee who sees every transaction.",
         "mechanism", "mgfx", ch="06", dur=7.0,
         intent="Every arrow in the network routed through one central node",
         q="EVERYTHING THROUGH ONE POINT"),

    beat("And the moment you have a referee, you have a company. An address. A server. A person.",
         "reveal", "threejs", ch="06", dur=7.0,
         intent="Globe: the whole distributed network collapsing to one pin — and the pin lands on Florida, where e-gold's directors actually lived",
         q="Florida", loc="Florida", ent="e-gold", year=2007,
         ov=({"type": "lower_third", "text": "A COMPANY · AN ADDRESS · A PERSON", "y": 0.24},),
         src="doj_eg", emo="surprising"),

    beat("And a person can be arrested.",
         "turn", "ai", ch="06", dur=4.6, tr="whip",
         intent="Recreation: a server-room door being forced, torch beams cutting through racks",
         q="cinematic documentary recreation, a server room door forced open in darkness, torch beams cutting across equipment racks, dust and cable, blue emergency light, no faces, tense, photoreal, anamorphic, 35mm",
         emo="tense"),

    beat("Ask e-gold.",
         "context", "mgfx", ch="06", dur=2.8,
         intent="Two words as a hard chapter turn",
         q="ASK E-GOLD."),

    beat("Founded in nineteen ninety-six, backed by real bullion, with more than a million accounts.",
         "evidence", "archival", ch="06", dur=6.2,
         intent="An e-gold era web page and a bullion bar side by side",
         q="e-gold digital currency 1990s website screenshot",
         src="doj_eg", ent="e-gold", year=1996, conf="probable"),

    beat("In April two thousand and seven, the Justice Department indicted it.",
         "turn", "archival", ch="06", dur=5.6,
         intent="The DOJ press release, the charge lines highlighted",
         q="Department of Justice press release April 27 2007 e-gold indictment",
         ov=({"type": "source", "text": "U.S. DOJ, 27 April 2007", "y": 0.1},),
         src="doj_eg", ent="e-gold", year=2007, emo="surprising"),

    beat("In two thousand and eight, it pleaded guilty.",
         "consequence", "archival", ch="06", dur=4.4,
         intent="The plea agreement document, signature block in view",
         q="e-gold plea agreement July 2008 court document",
         ov=({"type": "source", "text": "U.S. Secret Service, July 2008", "y": 0.1},),
         src="usss_eg", ent="e-gold", year=2008),

    beat("Ask the Liberty Dollar.",
         "context", "mgfx", ch="06", dur=3.0,
         intent="The parallel case introduced the same way",
         q="ASK THE LIBERTY DOLLAR."),

    beat("On the fourteenth of November, two thousand and seven, federal agents raided its offices and seized the coins.",
         "turn", "archival", ch="06", dur=7.0,
         intent="Liberty Dollar silver rounds, then the seizure record",
         q="Liberty Dollar silver coin NORFED 2007 seizure",
         kw=("liberty dollar silver round", "seized coins evidence photograph"),
         src="libdol", ent="Liberty Dollar", year=2007),

    beat("Private money works right up until the moment it matters. Then somebody knocks on the door.",
         "reveal", "stock", ch="06", dur=7.4,
         intent="Real footage: a closed door from the inside, a hand knocking, nobody answering",
         q="knocking on closed door from inside",
         kw=("hand knocking on door", "closed front door interior",
             "door handle locked close up"), emo="surprising"),

    beat("Unless there is no door. And nobody to arrest.",
         "turn", "mgfx", ch="06", dur=5.4,
         intent="The door glyph erasing itself out of the frame",
         q="UNLESS THERE IS NO DOOR."),

    beat("Nobody knew how to build that.",
         "stakes", "ai", ch="06", dur=4.0, tr="dip_to_black",
         intent="Recreation: a doorway in a bare white room with no door and nothing beyond it",
         q="cinematic documentary still, a bare concrete room containing a single empty doorframe with no door and pure darkness beyond it, hard directional light, dust, minimal, wide anamorphic, photoreal, 35mm grain",
         emo="tense"),

    # ── 07 · WHEN MONEY BREAKS IN REAL LIFE ──────────────────────────────── #
    beat("And none of this was theory.",
         "hook", "stock", ch="07", dur=3.6, tr="fade",
         intent="Real footage: an ordinary person at a cash machine at night",
         q="person using atm cash machine at night",
         kw=("atm cash machine at night", "withdrawing money from atm",
             "hand taking cash from atm")),

    beat("December first, two thousand and one. Buenos Aires.",
         "context", "threejs", ch="07", dur=5.2,
         intent="Globe flight from North America down to Argentina",
         q="Argentina", loc="Argentina", ent="Argentina", year=2001,
         ov=({"type": "lower_third", "text": "BUENOS AIRES", "sub": "1 December 2001", "y": 0.24},),
         src="corralito"),

    beat("Argentines woke up to find their savings frozen.",
         "turn", "archival", ch="07", dur=4.6,
         intent="Locked bank shutters in Buenos Aires, 2001",
         q="Buenos Aires 2001 closed bank shutters corralito photograph",
         kw=("buenos aires bank closed 2001", "argentina crisis bank shutters"),
         src="corralito", loc="Argentina", year=2001, emo="surprising"),

    beat("The limit was two hundred and fifty pesos a week. Of their own money.",
         "evidence", "chart", ch="07", dur=6.4,
         intent="A weekly cap shown as a hard ceiling on an account",
         data={"kind": "counter", "title": "Weekly cash withdrawal limit",
               "points": [{"label": "Dec 2001", "value": 250, "emphasis": "negative"}],
               "prefix": "$", "suffix": " pesos / week", "decimals": 0,
               "abbreviate": False, "source": "Decree 1570/2001 (the corralito)"},
         ov=({"type": "source", "text": "Decree 1570/2001", "y": 0.1},),
         src="corralito", year=2001, nums=("250 pesos",)),

    beat("Dollar accounts were converted into pesos. Then the peso was devalued.",
         "mechanism", "mgfx", ch="07", dur=6.2,
         intent="A dollar balance re-labelled as pesos, then shrinking",
         q="CONVERTED.  THEN DEVALUED.",
         src="frbsf_ar", year=2002, emo="cautionary"),

    beat("Argentina defaulted on ninety-five billion dollars.",
         "evidence", "chart", ch="07", dur=5.4,
         intent="The default total as a single figure, counting up and stopping dead",
         data={"kind": "counter", "title": "Argentine sovereign default, 2001",
               "points": [{"label": "Dec 2001", "value": 95e9, "emphasis": "negative"}],
               "prefix": "$", "decimals": 0, "abbreviate": True,
               "source": "Republic of Argentina / IMF",
               "note": "Largest sovereign default of its time"},
         src="frbsf_ar", year=2001, nums=("$95B",)),

    beat("People beat on the shutters of closed banks with hammers and cooking pots.",
         "consequence", "archival", ch="07", dur=6.2,
         intent="Cacerolazo footage — pots and pans against bank shutters",
         q="cacerolazo Buenos Aires December 2001 protest pots and pans",
         kw=("argentina protest 2001 pots pans", "cacerolazo buenos aires"),
         src="corralito", loc="Argentina", year=2001),

    beat("On the twentieth of December, the President fled the roof of his palace by helicopter.",
         "turn", "archival", ch="07", dur=6.4,
         intent="De la Rúa's helicopter leaving the Casa Rosada roof",
         q="Fernando de la Rua helicopter Casa Rosada roof December 20 2001",
         kw=("casa rosada helicopter 2001", "argentina president resignation 2001"),
         src="corralito", ent="Fernando de la Rúa", loc="Argentina", year=2001,
         emo="surprising"),

    beat("A middle class had been erased in a fortnight, without a single bullet.",
         "stakes", "ai", ch="07", dur=6.6,
         intent="Recreation: a family apartment being emptied, boxes, a bank letter on the table",
         q="documentary still, a modest Buenos Aires apartment being emptied, cardboard boxes stacked, a bank letter left on a bare table, late afternoon light through shutters, muted colour, photoreal, 35mm",
         emo="cautionary"),

    beat("And in Zimbabwe, money stopped being money at all.",
         "turn", "threejs", ch="07", dur=5.0,
         intent="Globe flight from South America across the Atlantic to Zimbabwe",
         q="Zimbabwe", loc="Zimbabwe", ent="Zimbabwe", year=2008,
         ov=({"type": "lower_third", "text": "ZIMBABWE", "sub": "2008", "y": 0.24},),
         src="hanke"),

    beat("By November two thousand and eight, prices were doubling roughly every day.",
         "evidence", "chart", ch="07", dur=6.6,
         intent="The doubling interval, stated as a hero figure nobody can argue with",
         data={"kind": "counter", "title": "Zimbabwe price-doubling time, Nov 2008",
               "points": [{"label": "Nov 2008", "value": 24.7, "emphasis": "negative"}],
               "suffix": " hours", "decimals": 1, "abbreviate": False,
               "source": "Hanke & Kwok, Cato Journal 29(2), 2009",
               "note": "Monthly inflation of 79.6 billion percent"},
         ov=({"type": "source", "text": "Hanke & Kwok (2009)", "y": 0.1},),
         src="hanke", loc="Zimbabwe", year=2008, nums=("24.7 hours",)),

    beat("Within weeks the central bank would print a one hundred trillion dollar note.",
         "reveal", "archival", ch="07", dur=6.2,
         intent="The Z$100,000,000,000,000 banknote, held flat, all the zeroes readable",
         q="Zimbabwe 100 trillion dollar banknote 2009 photograph",
         kw=("zimbabwe 100 trillion dollar note", "hyperinflation banknote zimbabwe"),
         ov=({"type": "stat", "text": "Z$100,000,000,000,000", "sub": "issued 16 January 2009", "y": 0.2},),
         src="hanke", year=2009, nums=("100 trillion",), emo="surprising"),

    beat("It could not pay a bus fare.",
         "consequence", "stock", ch="07", dur=3.6,
         intent="Real footage: a fare being paid to board a bus — the smallest transaction there is",
         q="paying bus fare boarding bus",
         kw=("paying bus fare", "boarding a bus ticket", "bus conductor taking money"),
         src="hanke"),

    beat("Somewhere on earth, a currency dies almost every generation.",
         "context", "threejs", ch="07", dur=5.6,
         intent="Globe flight to Hungary — the 1946 pengő, the worst hyperinflation ever recorded — as the map lights up with the others",
         q="Hungary", loc="Hungary", ent="Hungarian pengő", year=1946,
         ov=({"type": "lower_third", "text": "IT KEEPS HAPPENING", "sub": "Hungary, 1946 · the worst on record", "y": 0.24},),
         conf="probable"),

    beat("The comforting thought was always: not here. Not to us.",
         "tension", "stock", ch="07", dur=5.2,
         intent="Real footage: an ordinary quiet Western suburban street in the afternoon, nothing happening",
         q="quiet suburban street houses afternoon",
         kw=("quiet suburban street", "residential neighbourhood houses",
             "empty street suburb daytime"), emo="tense"),

    beat("In two thousand and seven, that thought died too.",
         "turn", "mgfx", ch="07", dur=4.6, tr="dip_to_black",
         intent="The reassurance from the previous card dissolving letter by letter off the frame",
         q="THEN IT CAME HERE.", year=2007, emo="surprising"),

    # ── 08 · THE COLLAPSE ────────────────────────────────────────────────── #
    beat("September fourteenth, two thousand and seven. Newcastle, England.",
         "context", "threejs", ch="08", dur=5.6, tr="fade",
         intent="Globe flight across to the United Kingdom and down to the north-east coast",
         q="United Kingdom", loc="United Kingdom", ent="Northern Rock", year=2007,
         ov=({"type": "lower_third", "text": "NEWCASTLE, ENGLAND", "sub": "14 September 2007", "y": 0.24},),
         src="boe_nr"),

    beat("A queue formed outside a bank called Northern Rock.",
         "tension", "archival", ch="08", dur=4.8,
         intent="The first press photograph of the queue outside a branch",
         q="Northern Rock bank run queue September 2007 photograph",
         kw=("northern rock queue 2007", "bank run queue britain 2007"),
         src="boe_nr", ent="Northern Rock", year=2007),

    beat("It grew down the street. Then around the block.",
         "tension", "archival", ch="08", dur=4.6,
         intent="A wider frame of the same queue, extending out of shot",
         q="Northern Rock savers queue street 2007 wide shot",
         kw=("long queue outside bank 2007", "savers waiting bank branch queue"),
         src="boe_nr", year=2007, emo="tense"),

    beat("It was the first run on a British bank in a hundred and forty-one years.",
         "reveal", "chart", ch="08", dur=6.4,
         intent="The gap between the last British bank run and this one",
         data={"kind": "delta", "title": "Runs on a British retail bank",
               "points": [{"label": "1866", "value": 1866, "emphasis": "normal"},
                          {"label": "2007", "value": 2007, "emphasis": "negative"}],
               "decimals": 0, "abbreviate": False, "highlight": 1,
               "source": "Overend & Gurney, 1866 → Northern Rock, 2007",
               "note": "141 years between them"},
         src="boe_nr", year=2007, nums=("141 years",), emo="surprising"),

    beat("Six months later, Bear Stearns — eighty-five years old — was sold overnight for two dollars a share.",
         "turn", "chart", ch="08", dur=8.0,
         intent="The share price a year before against the price it was sold at",
         data={"kind": "bar_compare", "title": "Bear Stearns share price",
               "points": [{"label": "Jan 2007", "value": 171.51, "emphasis": "normal"},
                          {"label": "16 Mar 2008", "value": 2.00, "emphasis": "negative"},
                          {"label": "revised", "value": 10.00, "emphasis": "normal"}],
               "prefix": "$", "decimals": 2, "abbreviate": False, "highlight": 1,
               "source": "JPMorgan Chase / Federal Reserve",
               "note": "Deal raised to $10 a share on 24 March 2008"},
         ov=({"type": "source", "text": "Federal Reserve Board", "y": 0.1},),
         src="fed_bear", ent="Bear Stearns", year=2008, nums=("$2.00", "$171.51"),
         emo="surprising"),

    beat("The Federal Reserve put thirty billion dollars behind the deal to make it happen.",
         "evidence", "archival", ch="08", dur=6.0,
         intent="The Fed's own Bear Stearns / Maiden Lane page, figure highlighted",
         q="Federal Reserve Bear Stearns Maiden Lane March 2008 statement",
         ov=({"type": "source", "text": "Federal Reserve Board", "y": 0.1},),
         src="fed_bear", year=2008, nums=("$30B",)),

    beat("Then it accelerated.",
         "turn", "stock", ch="08", dur=3.0,
         intent="Real footage: a market ticker board flickering, every line red",
         q="stock ticker board falling red numbers",
         kw=("stock ticker screen red", "financial market board falling",
             "trading screen numbers dropping")),

    beat("September seventh: the United States government seized Fannie Mae and Freddie Mac.",
         "evidence", "archival", ch="08", dur=6.4,
         intent="The FHFA conservatorship announcement document",
         q="FHFA conservatorship Fannie Mae Freddie Mac September 7 2008 announcement",
         ov=({"type": "source", "text": "FHFA, 7 September 2008", "y": 0.1},),
         src="fhfa", year=2008),

    beat("September fifteenth, one forty-five in the morning: Lehman Brothers filed for bankruptcy.",
         "turn", "archival", ch="08", dur=7.0,
         intent="Staff carrying boxes out of 745 Seventh Avenue in the dark",
         q="Lehman Brothers employees carrying boxes September 15 2008 photograph",
         kw=("lehman brothers collapse employees boxes", "lehman headquarters 2008"),
         src="lehman", ent="Lehman Brothers", year=2008, emo="surprising"),

    beat("Six hundred and thirty-nine billion dollars in assets. The largest bankruptcy in American history.",
         "evidence", "chart", ch="08", dur=7.4,
         intent="The figure counting up, then the record label landing under it",
         data={"kind": "counter", "title": "Lehman Brothers assets at filing",
               "points": [{"label": "15 Sep 2008", "value": 639e9, "emphasis": "negative"}],
               "prefix": "$", "decimals": 0, "abbreviate": True,
               "source": "Chapter 11 petition, 15 September 2008",
               "note": "Largest bankruptcy filing in U.S. history"},
         src="lehman", year=2008, nums=("$639B",)),

    beat("Twenty-four hours later, the Federal Reserve lent eighty-five billion dollars to a single insurance company.",
         "turn", "chart", ch="08", dur=7.4,
         intent="The AIG facility as one hero figure against the days around it",
         data={"kind": "counter", "title": "Federal Reserve loan to AIG",
               "points": [{"label": "16 Sep 2008", "value": 85e9, "emphasis": "negative"}],
               "prefix": "$", "decimals": 0, "abbreviate": True,
               "source": "Federal Reserve Board, 16 September 2008",
               "note": "In exchange for 79.9% of the company"},
         ov=({"type": "source", "text": "Federal Reserve Board", "y": 0.1},),
         src="fed_aig", ent="AIG", year=2008, nums=("$85B",), emo="surprising"),

    beat("On the third of October, Congress authorised seven hundred billion dollars to buy the bad debt.",
         "evidence", "chart", ch="08", dur=7.2,
         intent="The three rescues stacked so the scale reads instantly",
         data={"kind": "bar_compare", "title": "The rescues, 2008",
               "points": [{"label": "Bear (Fed)", "value": 30e9, "emphasis": "normal"},
                          {"label": "AIG", "value": 85e9, "emphasis": "normal"},
                          {"label": "TARP", "value": 700e9, "emphasis": "negative"}],
               "prefix": "$", "decimals": 0, "abbreviate": True, "highlight": 2,
               "source": "Emergency Economic Stabilization Act, 3 October 2008"},
         ov=({"type": "source", "text": "EESA 2008", "y": 0.1},),
         src="eesa", year=2008, nums=("$700B",)),

    beat("And on the streets, the other half of the story.",
         "turn", "stock", ch="08", dur=4.0,
         intent="Real footage: a residential street of ordinary American houses, seen at ground level",
         q="american residential street houses",
         kw=("american suburb houses street", "residential street usa",
             "row of family homes")),

    beat("In the decade that followed, almost eight million American homes were lost to foreclosure.",
         "evidence", "chart", ch="08", dur=7.2,
         intent="Completed foreclosures counting up past eight million and holding",
         data={"kind": "counter", "title": "Completed U.S. foreclosures from 2007",
               "points": [{"label": "2007-2016", "value": 7.8e6, "emphasis": "negative"}],
               "decimals": 1, "abbreviate": True, "suffix": " homes",
               "source": "CoreLogic, Foreclosure Crisis Decade in Review (2017)"},
         ov=({"type": "source", "text": "CoreLogic", "y": 0.1},),
         src="corelogic", nums=("7.8 million",), emo="cautionary"),

    beat("Not bailed out. Not rescued. Foreclosed.",
         "consequence", "ai", ch="08", dur=5.4,
         intent="Recreation: a foreclosure notice taped to the inside of a suburban front window",
         q="documentary still, a printed foreclosure notice taped inside the glass of a suburban American front door, empty hallway behind it, overgrown lawn reflected, flat grey afternoon light, muted colour, photoreal, 35mm",
         emo="cautionary"),

    beat("The institutions that built the crisis were handed public money.",
         "reveal", "stock", ch="08", dur=5.6,
         intent="Real footage looking up the glass face of a banking tower — the money went up there",
         q="looking up glass bank tower skyscraper",
         kw=("looking up at skyscraper glass", "financial district tower low angle",
             "corporate glass building upward")),

    beat("The people who trusted them were handed eviction notices.",
         "reveal", "stock", ch="08", dur=5.4,
         intent="Real footage: a foreclosure / repossession sign staked on a front lawn",
         q="foreclosure sign front lawn house",
         kw=("foreclosure sign yard", "bank owned house sign", "for sale sign empty house"),
         emo="surprising"),

    beat("Something broke that autumn that was bigger than any bank.",
         "stakes", "ai", ch="08", dur=6.0,
         intent="Recreation: a wide, emptied trading floor at night, screens dark, chairs pushed back",
         q="documentary still, a completely emptied trading floor at night, dark monitors, chairs pushed back, scattered paper on the ground, one row of ceiling lights still on, cold cinematic wide shot, photoreal, anamorphic",
         emo="tense"),

    beat("For thirty-seven years the world had run on a single sentence. Trust us.",
         "reveal", "mgfx", ch="08", dur=7.0,
         intent="The two words that carried the entire system since 1971",
         q="“TRUST US.”", nums=("37 years",), emo="surprising"),

    beat("In the autumn of two thousand and eight, hundreds of millions of people stopped.",
         "payoff", "mgfx", ch="08", dur=6.0, tr="dip_to_black",
         intent="The two words from the card before breaking apart and falling out of the bottom of frame",
         q="THEY STOPPED.", year=2008, emo="surprising"),

    # ── 09 · CLIFFHANGER ─────────────────────────────────────────────────── #
    beat("And while the world was collapsing —",
         "tension", "ai", ch="09", dur=4.4, tr="fade",
         intent="Recreation: a city at night seen from far above, half the windows dark",
         q="documentary still, a vast city seen from high above at night, large districts of windows gone dark, thin fog, cold blue, cinematic wide, photoreal, anamorphic, 35mm grain",
         emo="tense"),

    beat("while governments printed, and banks failed, and families were carried out of their houses —",
         "tension", "ai", ch="09", dur=7.2,
         intent="Recreation: three fragments in one held frame — a press, a shuttered branch, a packed car",
         q="documentary still triptych, a banknote press running, a shuttered bank branch, a family car packed with boxes on a driveway at dusk, unified cold muted grade, cinematic, photoreal, 35mm",
         emo="cautionary"),

    beat("somewhere, in a room nobody has ever found,",
         "turn", "ai", ch="09", dur=5.4,
         intent="Recreation: an anonymous desk, one monitor's glow, the chair empty",
         q="documentary still, an anonymous desk in a dark room, a single monitor glowing with unreadable text, an empty chair pushed slightly back, no personal objects, no window, deep shadow, photoreal, anamorphic, 35mm grain",
         emo="surprising"),

    beat("someone was quietly writing a nine-page document",
         "reveal", "mgfx", ch="09", dur=5.0,
         intent="Nine blank pages fanning open, none of them legible",
         q="NINE PAGES", emo="surprising"),

    beat("that would change money forever.",
         "payoff", "mgfx", ch="09", dur=4.6, tr="dip_to_black",
         intent="The final line landing, then black",
         q="THAT WOULD CHANGE MONEY FOREVER."),

    beat("Episode two. The nine pages.",
         "cta", "mgfx", ch="09", dur=5.0,
         intent="Next-episode card in the series brand",
         q="EPISODE TWO — THE NINE PAGES",
         ov=({"type": "headline", "text": "EPISODE TWO", "y": 0.34},
             {"type": "lower_third", "text": "THE NINE PAGES", "sub": "The Complete History of Bitcoin", "y": 0.46})),
]


# --------------------------------------------------------------------------- #
# Derivation
# --------------------------------------------------------------------------- #
def estimate(text: str, override: float | None) -> float:
    """Director-side duration estimate. Overwritten by measured TTS at render."""
    if override is not None:
        return round(min(12.0, max(0.8, override)), 2)
    words = len(text.split())
    return round(min(12.0, max(1.6, words / 2.55 + 0.85)), 2)


def build() -> tuple["SceneGraph", list[dict], float]:  # noqa: F821 — imported inside
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
        # For a kinetic-type beat, `q` IS the card the viewer reads, so promote
        # it to a `headline` overlay — the schema's display-copy channel. The
        # renderer skips scene typography for pre-rendered visuals, so this is
        # consumed by the motion-graphics engine and never drawn twice.
        if b["vis"] == "mgfx" and b["q"] and not any(
                o.type == "headline" for o in overlays):
            overlays.insert(0, Overlay(type="headline", text=b["q"], y=0.30))
        # Every cited beat carries its attribution on screen unless the beat
        # already authored a `source` overlay of its own.
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
            ai_broll_candidate=b["vis"] == "ai",
            asset_priority=spec["prio"],
            transition=b["tr"] or "cut",
            overlay_text=[o.text for o in overlays if o.type != "source"],
            visual_confidence_score=0.92 if b["vis"] in ("mgfx", "chart", "threejs")
            else (0.78 if b["vis"] == "archival" else 0.7),
        ))

        src = SOURCES.get(b["src"]) if b["src"] else None
        asset_plan.append({
            "scene_id": sid, "chapter": b["ch"], "beat_role": b["role"],
            "channel": spec["channel"], "strategy": spec["strategy"],
            "acquisition": ("rendered in-pipeline"
                            if spec["channel"] in ("motion_gfx", "threejs", "charts")
                            else ("archival / official — manual clearance"
                                  if spec["channel"] == "official"
                                  else ("stock video API (Pexels/Pixabay)"
                                        if spec["channel"] == "stock"
                                        else "AI cinematic recreation (synthetic — must be disclosed)"))),
            "query_or_prompt": b["q"] or (b["kw"][0] if b["kw"] else ""),
            "search_terms": b["kw"],
            "citation": {"label": src["label"], "url": src["url"],
                         "license": src["license"]} if src else None,
            "confidence": b["conf"],
            "synthetic": spec["channel"] == "ai_broll",
        })

    total = round(sum(s.duration_sec for s in scenes), 2)

    meta = SceneMeta(
        video_id="btc_ep01_world_before_bitcoin",
        channel_id="k70_history",
        niche="usa_history",
        structure_id="timeline_twist_conclusion",
        title="The World Before Bitcoin | The Complete History of Bitcoin · Ep. 1",
        hook="In August 1971, Britain asked America for its gold. The gold wasn't there.",
        description=(
            "EPISODE 1 — THE WORLD BEFORE BITCOIN (1970-2008)\n\n"
            "In August 1971 the United States quietly broke the promise the entire "
            "world's money was built on. What followed was thirty-seven years of "
            "inflation, bank failures, frozen savings, hyperinflation and finally "
            "the largest bankruptcy in American history — and a small group of "
            "cryptographers who kept trying, and failing, to build money that no "
            "one could switch off.\n\n"
            "This is Part 1 of The Complete History of Bitcoin.\n\n"
            "SOURCES: Federal Reserve History · U.S. Treasury / U.S. Mint · "
            "Bureau of Labor Statistics (CPI-U) · FDIC / GAO 1996 · U.S. DOJ and "
            "Secret Service (e-gold) · FHFA · Federal Reserve Board · Emergency "
            "Economic Stabilization Act 2008 · Hanke & Kwok, Cato Journal 2009 · "
            "CoreLogic. Full citations in the pinned comment.\n\n"
            "Educational history and commentary. Not financial advice."
        ),
        tags=["bitcoin", "history of bitcoin", "bitcoin documentary", "1971",
              "nixon shock", "gold standard", "bretton woods", "inflation",
              "2008 financial crisis", "lehman brothers", "cypherpunks",
              "digicash", "hyperinflation", "argentina 2001", "zimbabwe",
              "federal reserve", "money", "documentary"],
        hashtags=["#bitcoin", "#documentary", "#history", "#money", "#2008crisis"],
        thumbnail_text="THE GOLD WASN'T THERE",
    )

    graph = SceneGraph(
        meta=meta, fps=30, width=1080, height=1920, brand_id="k70",
        scenes=scenes,
        storyboard=StoryboardData(version="1.0", scenes=sb_scenes),
    )
    return graph, asset_plan, total


def write_narration(total: float) -> str:
    lines = ["# The Complete History of Bitcoin",
             "## Episode 1 — The World Before Bitcoin (1970-2008)", "",
             f"**Runtime (Director estimate):** {total/60:.1f} min · "
             f"{len(BEATS)} beats · {sum(len(b['n'].split()) for b in BEATS)} words", "",
             "> Durations below are the Director's estimates. The pipeline overwrites",
             "> every one of them with the measured TTS duration before rendering.", ""]
    cursor = 0.0
    current = None
    for i, b in enumerate(BEATS, start=1):
        if b["ch"] != current:
            current = b["ch"]
            name = dict(CHAPTERS)[current]
            lines += ["", f"### {current} — {name}", ""]
        dur = estimate(b["n"], b["dur"])
        mm, ss = divmod(int(cursor), 60)
        lines.append(f"**[{mm:02d}:{ss:02d}] s{i}** · `{b['role']}` · "
                     f"`{CHANNELS[b['vis']]['channel']}`  \n{b['n']}  \n"
                     f"*Visual:* {b['intent']}")
        lines.append("")
        cursor += dur
    return "\n".join(lines)


def write_timeline() -> str:
    rows = ["# Episode 1 — fact & date spine", "",
            "Every dated claim in the narration, with the source it was checked",
            "against. Ids match `SOURCES` in `scripts/build_bitcoin_ep01.py`.", "",
            "| Scene | Date / period | Claim | Source | Confidence |",
            "|---|---|---|---|---|"]
    for i, b in enumerate(BEATS, start=1):
        if not b["year"] and not b["src"]:
            continue
        src = SOURCES.get(b["src"])
        cite = f"[{src['label']}]({src['url']})" if src else "—"
        claim = b["n"][:88] + ("…" if len(b["n"]) > 88 else "")
        rows.append(f"| s{i} | {b['year'] or '—'} | {claim} | {cite} | {b['conf']} |")
    return "\n".join(rows)


def main() -> int:
    graph, asset_plan, total = build()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    (OUT_DIR / "scene_graph.json").write_text(graph.model_dump_json(indent=2))
    (OUT_DIR / "narration.md").write_text(write_narration(total))
    (OUT_DIR / "timeline.md").write_text(write_timeline())
    (OUT_DIR / "asset_plan.json").write_text(json.dumps(
        {"episode": graph.meta.video_id, "beats": asset_plan}, indent=2))

    mix: dict[str, float] = {}
    for s in graph.scenes:
        mix[s.visual.budget_channel] = mix.get(s.visual.budget_channel, 0.0) + s.duration_sec

    print(f"scenes      : {len(graph.scenes)}")
    print(f"duration    : {total:.1f}s  ({total/60:.2f} min)")
    print(f"words       : {sum(len(b['n'].split()) for b in BEATS)}")
    print(f"charts      : {sum(1 for s in graph.scenes if s.data)}")
    print("authored mix:")
    for k in sorted(mix, key=lambda k: -mix[k]):
        print(f"   {k:11} {mix[k]/total*100:5.1f}%  ({mix[k]:6.1f}s)")
    print(f"\nwrote {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
