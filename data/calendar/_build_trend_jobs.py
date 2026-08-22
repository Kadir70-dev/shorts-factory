import json, pathlib

ROOT = pathlib.Path(__file__).parent
JOBS = ROOT / "jobs"

plan = json.loads((ROOT / "master_plan.json").read_text(encoding="utf-8"))
trend = [s for s in plan if not s["evergreen"]]
assert len(trend) == 15

SOURCE_REQS = {
    "business_wealth_story": [
        "Story must be corroborated by at least one primary source (company press release, SEC 8-K/press filing, official IR statement) OR two independent reputable business-press outlets (e.g. Reuters, AP, WSJ, Bloomberg, CNBC).",
        "Story must be less than 72 hours old at research time.",
        "Reject if the only coverage is a single outlet, a blog, or social-media speculation.",
    ],
    "markets_economics_education": [
        "Prefer the primary release itself: federalreserve.gov (FOMC statement/minutes), bls.gov (CPI/jobs report), bea.gov (GDP), treasury.gov.",
        "If explaining market reaction, corroborate the move with at least one reputable financial outlet (Reuters, Bloomberg, WSJ, AP) alongside the primary data release.",
        "Story must reference the most recent scheduled release/decision relative to the publish date — do not use stale data from a prior cycle.",
    ],
    "money_mechanics_finance": [
        "Prefer a primary source (regulator statement, bank/fintech official announcement, CFPB/FDIC release) OR two independent reputable outlets.",
        "Story must be less than 72 hours old at research time.",
        "Reject if the claim is a rumor, an unconfirmed leak, or a single-source scoop not yet corroborated.",
    ],
}

SCRIPT_TEMPLATE = (
    "0-2s HOOK: state the single most concrete, surprising fact from the "
    "verified story (a number, a decision, a name) — no 'breaking news' filler. "
    "2-8s SETUP: what happened, who, when — plain, specific. "
    "8-30s STORY/EXPLANATION: why it happened / the mechanism behind it, in "
    "causal, visual language — one central idea only. "
    "30-45s PAYOFF: what it actually means for the viewer or the wider economy "
    "— the 'so what', hedged per the story's real confidence level (confirmed "
    "vs analysts-expect language). "
    "Final seconds: one sharp, memorable closing line; 'Follow for more.' only "
    "if it fits naturally. Total 35-55s, ~90-130 spoken words, natural American "
    "English, no guaranteed-return or buy/sell-call language. Build the actual "
    "SceneGraph using the same schema as the evergreen jobs (see "
    "_job_spec_reference.md) once the real story and its sources are confirmed."
)

for s in trend:
    job_id = s["job_id"]
    meta = {
        "id": job_id,
        "day": s["day"],
        "slot": s["slot"],
        "category": s["category"],
        "content_type": "trend",
        "intended_category": s["category"],
        "research_query": s["angle"],
        "source_requirements": SOURCE_REQS[s["category"]],
        "script_template": SCRIPT_TEMPLATE,
        "freshness_requirements": (
            "Research must run within 24-48 hours of this slot's scheduled "
            "publish day (day %d of the 30-day cycle), not at backlog-build "
            "time. If no story clears the source requirements and the "
            "72-hour freshness bar, fall back to the next unused evergreen "
            "topic in the same category (do not force a weak or unverified "
            "story into this slot)." % s["day"]
        ),
        "sources": [],
        "quality_scores": None,
        "disclaimer": "Educational content only. Not financial advice." if s["category"] == "markets_economics_education" else "",
        "status": "TREND — RESEARCH ON PUBLISH DATE",
    }
    (JOBS / f"{job_id}.meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

print(f"wrote {len(trend)} trend-slot meta files")
