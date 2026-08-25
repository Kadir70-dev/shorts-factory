# Job production reference — Finance Shorts 30-day backlog

Read this once. It defines the exact output schema and house rules for every
evergreen job you produce.

## Channel
channel_id: `usa_finance`, niche: `usa_finance`. Style notes from
`config/channels/usa_finance.yaml`: explain macro/markets like a sharp analyst,
not a hype channel. Lead with the number that matters. No financial advice —
describe, don't recommend. Banned: specific stock buy/sell calls, crypto pump
predictions.

## Two files per job, both in `data/calendar/jobs/`

### 1. `<job_id>.scene.json` — a real SceneGraph, must `pydantic` validate

This is the EXACT existing render schema (`apps/api/app/schemas/scene.py`,
`SceneGraph`/`SceneMeta`/`Scene`/`Visual`). It is fed straight into
`scripts/produce.py --from-json <path>` later — do not invent new fields.
Model these two files closely, they are real production jobs from this same
channel: `data/demos/fin_costco_hotdog.json` and `data/demos/fin_buffett_coke.json`.

Top-level shape:
```json
{
  "schema_version": "2.0",
  "meta": {
    "video_id": "vid_fin_<job_id>",
    "channel_id": "usa_finance",
    "niche": "usa_finance",
    "title": "<hooky platform title, <=90 chars, curiosity+clarity, no hashtag stuffing>",
    "hook": "<first ~1.5s on-screen hook text, matches scene 1 narration's opening idea>",
    "description": "<2-4 sentences, plain language, cites the real sourced numbers, ends with a soft educational framing — NOT personalized advice. If the topic touches investing/trading, end description with one short educational-disclaimer sentence, e.g. 'Educational content only, not financial advice.'>",
    "tags": ["...", "..."],
    "hashtags": ["#...", "#shorts"],
    "thumbnail_text": "<2-4 punchy words/number>"
  },
  "fps": 60,
  "width": 1080,
  "height": 1920,
  "scenes": [ { ...Scene... }, ... ]
}
```

Scene object (repeat 6-9 times per job):
```json
{
  "id": "s1",
  "narration": "<spoken line, natural American English, TTS-friendly (spell out
     ambiguous numbers as words the way the two reference demos do — e.g.
     'one point three billion dollars', 'nineteen ninety-four')>",
  "duration_sec": 3.5,
  "confidence": "confirmed | probable | speculative",
  "transition_in": "cut | fade | slide_l | whip | dip_to_black | push_up | crossfade",
  "keywords": ["...", "..."],
  "visual": {
    "type": "broll",
    "strategy": "real",
    "scene_visual_type": "real_footage | data_viz | dramatic | subtle | abstract",
    "motion": "none | ken_burns | zoom_in | zoom_out | pan_lr",
    "query": "<primary stock-footage search phrase>",
    "visual_intent": "<one vivid sentence describing exactly what's on screen and why, cinematic language>",
    "broll_keywords": ["<3 alternate search phrases the resolver tries in order>"],
    "decision_reason": "<why this visual, and for confirmed facts: cite WHERE the number/date came from, e.g. 'exact figures from company FY2024 10-K' or 'BLS CPI release, June 2026'>"
  },
  "overlays": [
    {"type": "stat", "text": "<short on-screen text — a number, date, name, or key contrast, NEVER the full narration line>", "y": 0.18}
  ]
}
```
`overlays` is optional per scene (omit the whole key or use `[]` if nothing
needs on-screen text this beat) but MOST scenes carrying a number, date, or
company name should carry one short overlay per the task's on-screen-text rule.
Every field not shown above has a safe default — do not add fields that
aren't in the schema (extra keys are silently dropped, so don't rely on them
for anything that matters; put research/sources in the sidecar file instead).

Scene-count / pacing target: 6-9 scenes, total `duration_sec` summing to
**35-55 seconds**, ~90-130 spoken words total, following:
- 0-2s HOOK (scene 1, `transition_in: "cut"`, no fade-in, the single most
  interesting/surprising fact stated immediately — never "did you know",
  "hey guys", "in today's video")
- 2-8s SETUP (scene 2, sometimes 3)
- 8-30s STORY / EXPLANATION (the bulk of scenes — causal, specific, visual)
- 30-45s PAYOFF / SURPRISE (the reveal / the "here's why that matters" turn)
- final seconds MEMORABLE CLOSING (a sharp one-line takeaway; end with
  "Follow for more." only if it fits naturally — don't force generic CTAs)

### 2. `<job_id>.meta.json` — calendar/production bookkeeping sidecar

```json
{
  "id": "<job_id>",
  "day": 1,
  "slot": "A",
  "category": "business_wealth_story",
  "content_type": "evergreen",
  "topic": "<short topic label>",
  "sources": [
    {"claim": "<the specific number/date/quote it supports>",
     "source": "<publisher/filing name>", "url": "<url used, if web-searched>",
     "type": "primary|reputable_secondary"}
  ],
  "pronunciation_notes": [{"term": "10-K", "note": "said as 'ten K'"}],
  "quality_scores": {"hook": 0, "clarity": 0, "retention": 0,
                      "fact_confidence": 0, "visual_potential": 0,
                      "us_relevance": 0, "originality": 0, "average": 0.0},
  "rewritten": false,
  "disclaimer": "Educational content only. Not financial advice.  (only include a non-empty string here if the topic is investing/trading-adjacent; empty string otherwise)",
  "status": "READY"
}
```

## Research & fact-safety rules (hard requirements)
- Every number, date, valuation, statistic, or quote in the script must trace
  to a real source, listed in `sources` in the sidecar file.
- Prefer: SEC filings/EDGAR, Federal Reserve, BLS, BEA, FDIC, Treasury,
  company 10-K/investor-relations pages, or the company's own official
  statements. For older business/history anecdotes, reputable secondary
  sources (major business press, well-corroborated business-history
  reporting) are acceptable — use WebSearch to verify, don't rely on memory
  alone for anything with a specific number attached.
- If you cannot verify a specific number/date/quote with reasonable
  confidence, DELETE that specific claim from the script and either replace
  it with a verified one or make the sentence structural/qualitative instead
  (e.g. "for decades" instead of an invented exact year). Never invent a
  number to make the hook better.
- Never write: "guaranteed return", "risk-free", "buy this stock now", "will
  10x", get-rich-quick framing, or a specific personalized buy/sell call.

## Do not duplicate these two already-produced shorts
- `data/demos/fin_costco_hotdog.json` — Costco's $1.50 hot dog / membership
  fee profit model. Do NOT write this story again in any form.
- `data/demos/fin_buffett_coke.json` — Buffett's 1994 Coca-Cola stake /
  dividend compounding. Do NOT write this story again in any form. (A
  different Coca-Cola angle, e.g. the secret-formula/New Coke story, or a
  different Berkshire angle, e.g. the textile-mill origin, is fine — those
  are materially different stories, already assigned to you if in your batch.)
- Also avoid writing 2+ scripts in YOUR batch that reduce to the same generic
  point (e.g. don't let two different "compound interest" framings collapse
  into the same "it grows exponentially" beat — keep each job's causal
  mechanism/specific example distinct).

## Self-scoring gate (do this before finalizing each job)
Score your own finished script 0-10 on: hook, clarity, retention, fact
confidence, visual potential, US relevance, originality. If hook < 7, OR
fact_confidence < 9, OR the average < 8: rewrite that job once before
finalizing (tighten the hook, cut an unverifiable claim, add causal
specificity). Record the final scores and whether you rewrote in the sidecar
`quality_scores` / `rewritten` fields. Do not spend more than one rewrite pass
per job — if a claim still can't clear fact_confidence 9 after removing it,
simplify the story rather than stalling.
