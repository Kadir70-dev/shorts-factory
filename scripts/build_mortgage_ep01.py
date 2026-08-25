#!/usr/bin/env python3
"""MORTGAGE EXPLAINED · Episode 1 — "How a $500,000 Mortgage Actually Works"

First real production use of tools/k70_scene_engine/ alongside the proven
existing pipeline. Same authoring pattern as build_forex_ep01.py /
build_xauusd_ep01.py: narration, visual plan, chart data and citations are
authored ONCE in BEATS and emitted as a validated SceneGraph.

All dollar figures trace to data/series/mortgage_explainer/ep01/amortization.py
(a real, standard-formula amortization calculator, run and verified
separately -- see amortization_results.json). Nothing here is hand-typed
math. The interest rate (6.5%) is an explicit stated HYPOTHETICAL, not a
live quote -- said as such in the narration itself.

    .venv-win/Scripts/python.exe scripts/build_mortgage_ep01.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

OUT_DIR = ROOT / "data" / "series" / "mortgage_explainer" / "ep01"
AMORT = json.loads((OUT_DIR / "amortization_results.json").read_text(encoding="utf-8"))

CHANNELS: dict[str, dict] = {
    "mgfx":    {"type": "motion_gfx", "strategy": "motion_gfx", "channel": "motion_gfx",
                "svt": "dramatic",     "motion": "none",
                "sb": "motion_gfx", "prio": ["local_graphics", "branded_fallback"]},
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
    "character": {"type": "image",   "strategy": "real",        "channel": "stock",
                "svt": "real_footage", "motion": "ken_burns",
                "sb": "real",      "prio": ["local_graphics"]},
    "voxel":   {"type": "image",     "strategy": "real",        "channel": "stock",
                "svt": "real_footage", "motion": "ken_burns",
                "sb": "real",      "prio": ["local_graphics"]},
}

EMOTION = {
    "hook": "urgent", "tension": "tense", "stakes": "tense", "context": "neutral",
    "evidence": "confident", "turn": "surprising", "reveal": "surprising",
    "contrast": "curious", "mechanism": "curious", "consequence": "cautionary",
    "payoff": "confident", "cta": "urgent", "question": "curious",
}

SOURCES: dict[str, dict] = {
    "cfpb_pmi": {"label": "CFPB — When can I remove private mortgage insurance (PMI) from my loan?",
                "url": "https://www.consumerfinance.gov/ask-cfpb/when-can-i-remove-private-mortgage-insurance-pmi-from-my-loan-en-202/",
                "license": "US government work (public domain)"},
    "cfpb_pmi_what": {"label": "CFPB — What is private mortgage insurance?",
                "url": "https://www.consumerfinance.gov/ask-cfpb/what-is-private-mortgage-insurance-en-122/",
                "license": "US government work (public domain)"},
}

CHAPTERS = [
    ("00", "Hook"), ("01", "The House And The Loan"), ("02", "Down Payment And Principal"),
    ("03", "Rate And Term"), ("04", "Monthly Principal And Interest"),
    ("05", "Taxes, Insurance, PMI"), ("06", "Amortization"), ("07", "Total Interest"),
    ("08", "Rate Comparison"), ("09", "Extra Payments"), ("10", "Affordability"), ("11", "Closing"),
]


def beat(text: str, role: str, vis: str, *, ch: str, intent: str, q: str = "",
         kw: tuple[str, ...] = (), ov: tuple[dict, ...] = (), data: dict | None = None,
         conf: str = "confirmed", tr: str = "", src: str = "", ent: str = "",
         loc: str = "", year: int | None = None, nums: tuple[str, ...] = (),
         emo: str = "", dur: float | None = None,
         character: str | None = None, character_angle: str = "three_quarter") -> dict:
    return {"n": text, "role": role, "vis": vis, "ch": ch, "intent": intent,
            "q": q, "kw": list(kw), "ov": [dict(o) for o in ov], "data": data,
            "conf": conf, "tr": tr, "src": src, "ent": ent, "loc": loc,
            "year": year, "nums": list(nums), "emo": emo, "dur": dur,
            "character": character, "character_angle": character_angle}


A = AMORT["assumptions"]
S = AMORT["base_schedule_summary"]
E = AMORT["extra_payment_schedule_summary"]

BEATS: list[dict] = [

    # ── 00 · HOOK ─────────────────────────────────────────────────────────── #
    beat("A five hundred thousand dollar house doesn't cost five hundred thousand "
         "dollars. Finance it for thirty years, and the number that actually "
         "leaves your pocket can look completely different.",
         "hook", "stock", ch="00", dur=7.6,
         intent="Real, attractive American home exterior, warm daylight, premium establishing shot",
         q="beautiful american suburban house exterior daylight",
         kw=("american house exterior daylight", "suburban home for sale exterior"),
         emo="urgent"),

    # ── 01 · THE HOUSE AND THE LOAN ───────────────────────────────────────── #
    beat("Meet John. John found a home he loves — listed at five hundred "
         "thousand dollars.",
         "context", "character", ch="01", dur=4.6, tr="fade",
         intent="John, K70 recurring character, front three-quarter studio shot",
         character="john", character_angle="three_quarter"),

    beat("Almost nobody pays that in cash. Most buyers borrow the difference "
         "between what they put down, and what the home actually costs.",
         "context", "mgfx", ch="01", dur=6.0,
         intent="The core mechanic stated plainly",
         q="PRICE − DOWN PAYMENT = WHAT YOU BORROW"),

    # ── 02 · DOWN PAYMENT AND PRINCIPAL ───────────────────────────────────── #
    beat(f"For this example, John puts down {A['down_payment_pct']*100:.0f} percent — "
         f"{A['down_payment']:,.0f} dollars. That's his choice for this scenario; real "
         "buyers put down anywhere from a few percent to twenty percent or more.",
         "evidence", "chart", ch="02", dur=8.4,
         intent="Down payment counter, explicitly framed as one illustrative choice",
         q="Down payment (illustrative)",
         data={"kind": "counter", "title": "Down payment (illustrative example)", "points": [
                {"label": f"{A['down_payment_pct']*100:.0f}% of price", "value": A["down_payment"], "emphasis": "primary"}],
               "prefix": "$", "suffix": "", "decimals": 0, "abbreviate": False,
               "note": "One possible scenario — not a requirement"}),

    beat(f"The rest — {A['principal']:,.0f} dollars — is what he actually "
         "borrows. That's the mortgage principal.",
         "reveal", "chart", ch="02", dur=5.4,
         intent="Principal counter card",
         q="Mortgage principal",
         data={"kind": "counter", "title": "Mortgage principal", "points": [
                {"label": "Amount borrowed", "value": A["principal"], "emphasis": "primary"}],
               "prefix": "$", "suffix": "", "decimals": 0, "abbreviate": False}),

    # ── 03 · RATE AND TERM ────────────────────────────────────────────────── #
    beat("The bank agrees to lend him that principal over thirty years, at a "
         "fixed interest rate. For this example, we'll use six and a half "
         "percent — a hypothetical rate for illustration, not a live market quote.",
         "mechanism", "archival", ch="03", dur=8.6, tr="fade",
         intent="Real bank exterior, grounding the loan concept in a real institution",
         q="local bank branch exterior daylight",
         kw=("bank branch exterior", "credit union building exterior")),

    beat("Fixed means the rate never changes. Whatever John's payment is in "
         "year one, it's the same in year thirty.",
         "mechanism", "mgfx", ch="03", dur=5.4,
         intent="30-year fixed defined plainly",
         q="30-YEAR FIXED: SAME RATE, START TO FINISH"),

    # ── 04 · MONTHLY PRINCIPAL AND INTEREST ───────────────────────────────── #
    beat(f"Run those numbers through a standard mortgage formula, and John's "
         f"principal-and-interest payment comes out to "
         f"{AMORT['monthly_pi']:,.0f} dollars a month.",
         "reveal", "chart", ch="04", dur=6.8,
         intent="Monthly P&I hero counter, calculated not guessed",
         q="Monthly principal + interest",
         data={"kind": "counter", "title": "Monthly principal + interest", "points": [
                {"label": "Per month", "value": AMORT["monthly_pi"], "emphasis": "primary"}],
               "prefix": "$", "suffix": "", "decimals": 0, "abbreviate": False,
               "note": f"{A['principal']:,.0f} at {A['annual_rate_hypothetical']*100:.1f}%, 30-yr fixed (hypothetical rate)"}),

    # ── voxel transition (used exactly once, deliberately) ───────────────── #
    beat("But that single number doesn't all go to the bank as profit. Here's "
         "where a payment like that actually travels.",
         "turn", "voxel", ch="04", dur=5.6,
         intent="ONE deliberate voxel-style transition -- payment splitting into destinations, used sparingly as instructed",
         character="john"),

    # ── 05 · TAXES, INSURANCE, PMI ─────────────────────────────────────────── #
    beat("Property taxes, homeowners insurance, and — because John put down "
         "less than twenty percent — private mortgage insurance, all get "
         "added on top of that principal-and-interest payment.",
         "evidence", "stock", ch="05", dur=7.6,
         intent="Real family/home context, grounding the escrow concept",
         q="family in front of new home real estate",
         kw=("family new home exterior", "homebuyers standing outside house")),

    beat("Lenders usually bundle all of that into one monthly bill, called an "
         "escrow payment.",
         "context", "mgfx", ch="05", dur=4.6,
         intent="Escrow defined",
         q="ESCROW: TAXES + INSURANCE + PMI, ONE BILL"),

    beat(f"For this illustrative example: taxes add roughly "
         f"{AMORT['monthly_property_tax_illustrative']:,.0f} dollars a month. Insurance, about "
         f"{AMORT['monthly_insurance_illustrative']:,.0f}. PMI, about "
         f"{AMORT['monthly_pmi_initial_illustrative']:,.0f}. Together, John's real monthly "
         f"payment is closer to {AMORT['total_monthly_payment_initial_illustrative']:,.0f} dollars.",
         "evidence", "chart", ch="05", dur=10.5,
         intent="Full monthly payment breakdown, clearly labeled illustrative",
         q="Estimated total monthly payment (illustrative)",
         data={"kind": "bar_compare", "title": "Estimated monthly payment (illustrative)", "points": [
                {"label": "Principal + interest", "value": AMORT["monthly_pi"], "emphasis": "primary"},
                {"label": "Taxes (est.)", "value": AMORT["monthly_property_tax_illustrative"], "emphasis": "normal"},
                {"label": "Insurance (est.)", "value": AMORT["monthly_insurance_illustrative"], "emphasis": "normal"},
                {"label": "PMI (est.)", "value": AMORT["monthly_pmi_initial_illustrative"], "emphasis": "normal"}],
               "prefix": "$", "suffix": "", "decimals": 0, "abbreviate": False,
               "note": "Taxes/insurance/PMI are illustrative estimates, not quotes"}),

    beat("PMI protects the bank, not John — and by federal law, it has to "
         "come off automatically once his loan balance drops to seventy-eight "
         "percent of the home's original value.",
         "payoff", "mgfx", ch="05", dur=8.0,
         intent="CFPB-verified PMI automatic termination rule",
         q="PMI ENDS AUTOMATICALLY AT 78% LOAN-TO-VALUE",
         src="cfpb_pmi", nums=("78%",)),

    # ── 06 · AMORTIZATION ──────────────────────────────────────────────────── #
    beat("Here's the part almost nobody explains well: not every one of "
         "John's payments works the same way.",
         "tension", "mgfx", ch="06", dur=5.0, tr="fade",
         intent="The chapter hook",
         q="NOT EVERY PAYMENT WORKS THE SAME WAY", emo="curious"),

    beat(f"In year one, {S['year1_interest_share']*100:.0f} percent of every payment John "
         f"makes is interest. Only about {100-S['year1_interest_share']*100:.0f} percent actually "
         "reduces what he owes.",
         "evidence", "chart", ch="06", dur=7.0,
         intent="Year 1 amortization split, calculated from the real schedule",
         q="Year 1: payment split",
         data={"kind": "donut", "title": "Year 1 — where the payment goes", "points": [
                {"label": "Interest", "value": round(S["year1_interest_share"]*100), "emphasis": "negative"},
                {"label": "Principal", "value": round(100-S["year1_interest_share"]*100), "emphasis": "positive"}],
               "prefix": "", "suffix": "%", "decimals": 0, "abbreviate": False}),

    beat(f"By year fifteen, that's shifted — {S['year15_interest_share']*100:.0f} percent "
         f"interest, {100-S['year15_interest_share']*100:.0f} percent principal.",
         "evidence", "chart", ch="06", dur=5.6,
         intent="Year 15 split -- midpoint, matches CFPB's PMI-termination midpoint rule too",
         q="Year 15: payment split",
         data={"kind": "donut", "title": "Year 15 — where the payment goes", "points": [
                {"label": "Interest", "value": round(S["year15_interest_share"]*100), "emphasis": "negative"},
                {"label": "Principal", "value": round(100-S["year15_interest_share"]*100), "emphasis": "positive"}],
               "prefix": "", "suffix": "%", "decimals": 0, "abbreviate": False}),

    beat("By year thirty, it's flipped almost completely: less than one "
         "percent interest, the rest is pure principal.",
         "reveal", "chart", ch="06", dur=5.8,
         intent="Year 30 split -- the payoff",
         q="Year 30: payment split",
         data={"kind": "donut", "title": "Year 30 — where the payment goes", "points": [
                {"label": "Interest", "value": round(S["year30_interest_share"]*100, 1), "emphasis": "negative"},
                {"label": "Principal", "value": round(100-S["year30_interest_share"]*100, 1), "emphasis": "positive"}],
               "prefix": "", "suffix": "%", "decimals": 1, "abbreviate": False},
         emo="surprising"),

    beat("That's amortization: the bank collects most of its interest early, "
         "while John owes the most money — and less interest later, as the "
         "balance shrinks.",
         "payoff", "mgfx", ch="06", dur=7.0,
         intent="Amortization named and explained",
         q="AMORTIZATION: MORE INTEREST EARLY, MORE PRINCIPAL LATE"),

    beat("Here's why: interest is calculated on whatever John still owes, "
         "not on the original loan. Early on, he still owes almost all of "
         "it, so interest takes the bigger share of the payment.",
         "mechanism", "mgfx", ch="06", dur=8.2,
         intent="Explains the actual mechanism, not just the observed pattern",
         q="INTEREST IS CALCULATED ON WHAT'S LEFT TO OWE"),

    beat("As his balance drops, month after month, there's less principal "
         "left to charge interest on — so a shrinking slice goes to "
         "interest, and a growing slice chips away at what he owes.",
         "mechanism", "mgfx", ch="06", dur=8.0,
         intent="Second half of the mechanism explanation, closes the loop",
         q="SMALLER BALANCE → LESS INTEREST → FASTER PRINCIPAL PAYOFF"),

    # ── 07 · TOTAL INTEREST ────────────────────────────────────────────────── #
    beat(f"Add up every interest payment over all thirty years, and here's the "
         f"number that surprises most buyers: {S['total_interest']:,.0f} dollars in "
         "interest alone.",
         "reveal", "chart", ch="07", dur=8.2,
         intent="The big surprising total-interest number",
         q="Total interest over 30 years",
         data={"kind": "counter", "title": "Total interest over 30 years", "points": [
                {"label": "Interest paid", "value": S["total_interest"], "emphasis": "negative"}],
               "prefix": "$", "suffix": "", "decimals": 0, "abbreviate": False},
         emo="surprising"),

    beat(f"That's more than John originally borrowed. Borrow "
         f"{A['principal']:,.0f}, and — on this schedule — he ends up paying "
         f"{S['total_paid']:,.0f} dollars total.",
         "consequence", "chart", ch="07", dur=8.0,
         intent="Principal borrowed vs total paid, the contrast",
         q="Borrowed vs. total paid",
         data={"kind": "delta", "title": "Borrowed vs. total paid over 30 years", "points": [
                {"label": "Borrowed", "value": A["principal"], "emphasis": "normal"},
                {"label": "Total paid", "value": S["total_paid"], "emphasis": "negative"}],
               "prefix": "$", "suffix": "", "decimals": 0, "abbreviate": False}),

    # ── 08 · RATE COMPARISON ──────────────────────────────────────────────── #
    beat(f"And that total is extremely sensitive to the rate. The exact same "
         f"loan, at {AMORT['rate_comparison'][0]['rate']*100:.1f} percent instead of "
         f"{AMORT['rate_comparison'][1]['rate']*100:.1f}, costs about "
         f"{AMORT['rate_comparison'][1]['total_interest']-AMORT['rate_comparison'][0]['total_interest']:,.0f} "
         "dollars less in interest over the life of the loan.",
         "evidence", "chart", ch="08", dur=9.4, tr="fade",
         intent="Rate sensitivity comparison, three hypothetical rates on the identical loan",
         q="Total interest at three hypothetical rates",
         data={"kind": "bar_compare", "title": "Total interest, same loan, different hypothetical rates", "points": [
                {"label": f"{AMORT['rate_comparison'][0]['rate']*100:.1f}%", "value": AMORT["rate_comparison"][0]["total_interest"], "emphasis": "positive"},
                {"label": f"{AMORT['rate_comparison'][1]['rate']*100:.1f}%", "value": AMORT["rate_comparison"][1]["total_interest"], "emphasis": "normal"},
                {"label": f"{AMORT['rate_comparison'][2]['rate']*100:.1f}%", "value": AMORT["rate_comparison"][2]["total_interest"], "emphasis": "negative"}],
               "prefix": "$", "suffix": "", "decimals": 0, "abbreviate": False,
               "note": "Same principal and term throughout -- educational comparison, not a forecast"}),

    beat(f"Go the other way — {AMORT['rate_comparison'][2]['rate']*100:.1f} percent instead "
         f"of {AMORT['rate_comparison'][1]['rate']*100:.1f} — and it costs about "
         f"{AMORT['rate_comparison'][2]['total_interest']-AMORT['rate_comparison'][1]['total_interest']:,.0f} "
         "dollars more. Same house, same amount borrowed, a very different "
         "outcome — just from the rate.",
         "payoff", "mgfx", ch="08", dur=8.4,
         intent="Completes the rate-sensitivity comparison with the higher-rate side",
         q="SAME LOAN. DIFFERENT RATE. VERY DIFFERENT COST."),

    # ── 09 · EXTRA PAYMENTS ────────────────────────────────────────────────── #
    beat("Now here's a choice that's actually in John's control: what if he "
         "pays an extra three hundred dollars toward principal, every single "
         "month?",
         "question", "character", ch="09", dur=6.8, tr="fade",
         intent="John, second distinct shot -- same character, different angle for continuity + variety",
         character="john", character_angle="front"),

    beat(f"On this schedule, that alone pays off the loan about "
         f"{(S['months_paid']-E['months_paid'])/12:.0f} years early — and saves him over "
         f"{AMORT['interest_saved_with_extra_payment']:,.0f} dollars in interest.",
         "reveal", "chart", ch="09", dur=8.0,
         intent="Extra-payment comparison, calculated",
         q="Interest saved with $300/month extra principal",
         data={"kind": "delta", "title": "Total interest: normal vs. extra $300/mo principal", "points": [
                {"label": "Normal schedule", "value": S["total_interest"], "emphasis": "negative"},
                {"label": "With extra payments", "value": E["total_interest"], "emphasis": "positive"}],
               "prefix": "$", "suffix": "", "decimals": 0, "abbreviate": False},
         emo="surprising"),

    beat("It isn't free money — it's real cash out of his budget every "
         "month, and it isn't automatically the best move for everyone. But "
         "it shows how much leverage extra principal has, especially early "
         "in a loan.",
         "consequence", "mgfx", ch="09", dur=8.2,
         intent="Balanced caveat -- not universal advice",
         q="REAL MONEY, EVERY MONTH — NOT AUTOMATICALLY RIGHT FOR EVERYONE",
         emo="cautionary"),

    # ── 10 · AFFORDABILITY ─────────────────────────────────────────────────── #
    beat("Which is really the point: the sticker price was never the full "
         "story. What actually matters is the rate John gets, how long he "
         "finances it, and what he chooses to do with his payment every "
         "single month.",
         "payoff", "stock", ch="10", dur=8.4, tr="fade",
         intent="Real family/home context, broader affordability framing",
         q="family relaxing outside home real estate",
         kw=("family outside home relaxing", "homeowners porch real estate")),

    beat("A five hundred thousand dollar house can mean very different total "
         "costs for two different buyers, on two different mortgages.",
         "payoff", "mgfx", ch="10", dur=5.6,
         intent="The thesis line",
         q="SAME STICKER PRICE. DIFFERENT TOTAL COST."),

    beat("And the sticker price still isn't the whole picture — closing "
         "costs, ongoing maintenance, and how those escrow items change "
         "over time all shape what a home really costs to own, well beyond "
         "the number on the listing.",
         "consequence", "mgfx", ch="10", dur=8.4,
         intent="Rounds out affordability point without inventing specific closing-cost figures",
         q="STICKER PRICE ≠ TOTAL COST OF OWNERSHIP"),

    # ── 11 · CLOSING ────────────────────────────────────────────────────────── #
    beat("This has been one hypothetical example — not a prediction for "
         "your mortgage, your rate, or your local taxes. A real lender can "
         "run your actual numbers.",
         "cta", "mgfx", ch="11", dur=7.0,
         intent="Explicit disclaimer per brief requirements",
         q="ONE HYPOTHETICAL EXAMPLE — NOT PERSONAL ADVICE"),

    beat("If you want to actually understand how money works — instead of "
         "guessing at it — that's exactly what this channel is for.",
         "cta", "mgfx", ch="11", dur=6.0,
         intent="Channel CTA card, matching Forex/XAU-USD closing style",
         q="K70 — UNDERSTAND THE ECONOMY",
         ov=({"type": "lower_third", "text": "K70 FINANCE", "sub": "Understand the economy.", "y": 0.5},)),
]


def estimate(text: str, override: float | None) -> float:
    if override is not None:
        return round(min(14.0, max(0.8, override)), 2)
    words = len(text.split())
    return round(min(14.0, max(1.6, words / 2.55 + 0.85)), 2)


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
            decision_reason=f"{b['ch']} · {b['role']} · {spec['channel']} · vis={b['vis']}",
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
            threejs_candidate=False,
            ai_broll_candidate=False,
            asset_priority=spec["prio"],
            transition=b["tr"] or "cut",
            overlay_text=[o.text for o in overlays if o.type != "source"],
            visual_confidence_score=0.92 if b["vis"] in ("mgfx", "chart") else 0.8,
        ))

        src = SOURCES.get(b["src"]) if b["src"] else None
        asset_plan.append({
            "scene_id": sid, "chapter": b["ch"], "beat_role": b["role"],
            "channel": spec["channel"], "strategy": spec["strategy"], "vis": b["vis"],
            "character": b["character"], "character_angle": b["character_angle"],
            "acquisition": ("rendered in-pipeline"
                            if spec["channel"] in ("motion_gfx", "charts")
                            else ("k70_scene_engine (Blender)" if b["vis"] in ("character", "voxel")
                                  else ("archival / official — real photograph, sourced"
                                        if spec["channel"] == "official"
                                        else "stock video API (Pexels/Pixabay) — real footage"))),
            "query_or_prompt": b["q"] or (b["kw"][0] if b["kw"] else ""),
            "search_terms": b["kw"],
            "citation": {"label": src["label"], "url": src["url"],
                         "license": src["license"]} if src else None,
            "confidence": b["conf"],
            "synthetic": False,
        })

    total = round(sum(s.duration_sec for s in scenes), 2)

    meta = SceneMeta(
        video_id="mortgage_ep01_how_500k_mortgage_works",
        channel_id="k70_economy",
        niche="usa_finance",
        structure_id="one_number_story",
        title="How a $500,000 Mortgage Actually Works | Mortgage Explained",
        hook="A five hundred thousand dollar house doesn't cost five hundred "
             "thousand dollars. Finance it for thirty years, and the number "
             "that actually leaves your pocket can look completely different.",
        description=(
            "MORTGAGE EXPLAINED — How a $500,000 mortgage actually works, in "
            "plain English, through one hypothetical buyer's story.\n\n"
            "This video breaks down the down payment, mortgage principal, "
            "fixed interest rate, monthly principal-and-interest payment, "
            "property taxes, homeowners insurance, and PMI, how amortization "
            "shifts the interest/principal split from year 1 to year 30, the "
            "real total interest cost over 30 years, how sensitive that "
            "total is to the interest rate, what an extra principal payment "
            "actually does to the payoff timeline and total interest, and "
            "why affordability is about more than a home's sticker price.\n\n"
            "All calculations use a standard fixed-rate amortization formula "
            "with one clearly-stated hypothetical scenario ($500,000 home, "
            "10% down, 6.5% hypothetical rate, 30-year fixed) -- not a "
            "prediction or personalized advice.\n\n"
            "SOURCES: Consumer Financial Protection Bureau — "
            "https://www.consumerfinance.gov/ask-cfpb/when-can-i-remove-private-mortgage-insurance-pmi-from-my-loan-en-202/ "
            "· https://www.consumerfinance.gov/ask-cfpb/what-is-private-mortgage-insurance-en-122/\n\n"
            "This video is educational and uses a hypothetical example. It "
            "does not constitute mortgage, tax, or financial advice. Speak "
            "with a licensed lender for your actual numbers. See disclaimer."
        ),
        tags=["mortgage explained", "how mortgages work", "500000 house",
              "mortgage amortization", "down payment", "PMI explained",
              "30 year fixed mortgage", "principal and interest", "escrow",
              "home buying", "mortgage interest", "extra mortgage payments",
              "personal finance", "finance documentary"],
        hashtags=["#mortgage", "#realestate", "#personalfinance", "#homebuying", "#k70finance"],
        thumbnail_text="THE REAL COST",
        disclaimer=("Educational content using a hypothetical example. Not "
                    "mortgage, tax, or financial advice."),
    )

    graph = SceneGraph(
        meta=meta, fps=30, width=1920, height=1080, brand_id="k70",
        scenes=scenes,
        storyboard=StoryboardData(version="1.0", scenes=sb_scenes),
    )
    return graph, asset_plan, total


def write_narration(total: float) -> str:
    lines = [f"# Mortgage Explained — Ep. 1 narration\n",
             f"Total estimated runtime: {total:.1f}s (~{total/60:.2f} min)\n"]
    for i, b in enumerate(BEATS, start=1):
        lines.append(f"**s{i}** [{b['ch']} · {b['role']} · {b['vis']}]  \n{b['n']}\n")
    return "\n".join(lines)


def write_sources() -> str:
    lines = ["# Mortgage Explained — Ep. 1 sources\n"]
    for sid, s in SOURCES.items():
        lines.append(f"- **{s['label']}** — {s['url']} ({s['license']})")
    lines.append("\n## All dollar figures — computed source\n")
    lines.append("- `data/series/mortgage_explainer/ep01/amortization.py` "
                 "(standard fixed-rate amortization formula), verified output in "
                 "`amortization_results.json`\n")
    lines.append("## Claims and their sources\n")
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
    words = sum(len(b["n"].split()) for b in BEATS)
    print(f"scenes: {len(graph.scenes)}")
    print(f"words: {words} (~{words/2.67:.1f}s narration @ 2.67wps)")
    print(f"estimated total: {total:.1f}s (~{total/60:.2f} min)")
    print(f"wrote: {OUT_DIR / 'scene_graph.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
