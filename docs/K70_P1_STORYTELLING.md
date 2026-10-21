# K70 P1 — Advanced Documentary Storytelling Engine

Status: implemented as a **pre-production editorial planning + read-only
SceneGraph narration QA layer**. Pure Python, no GPU, model API, web requests,
voice cloning or rendering required. Designed for K70's original 8–12 minute
USA-finance documentaries; accepts 4–20 minutes for other episodes.

This is **not** a Dhruv Rathee imitation and does not alter the frozen
14-layer production architecture.

## What P1 adds

- Eight-act chapter outline: researched cold open, what/how/impact roadmap,
  origin, actual mechanism, evidence, turning point/counterargument,
  consequences and resolution.
- Time-boxed question/payoff prompts for 4–7 meaningful questions with answers,
  plus two analogy slots (mechanism and consequences).
- Primary-source requirement: no unsourced numbers, quotes or dates fabricated.
  Supplied citations are marked **unverified** pending verification.
- A director-ready writing brief in Markdown, suitable for passing into your
  existing Claude Code production workflow **before** narration is generated.
- An editorial QA pass over a real SceneGraph: opening question, roadmap in
  the first 90 seconds, analogy signals, quarter-by-quarter question count,
  visible source attributions and numeric claims requiring verification.
- Reports warnings for an editor to investigate rather than pretending to
  measure engagement or repair facts automatically.

## Generate a new episode writing brief

Run the CLI on your laptop, from the repository root:

    python3 scripts/k70_p1_storytelling.py plan \
      --topic "How the US Dollar Left the Gold Standard" \
      --minutes 11 \
      --out-dir data/finance_p1/gold_standard_v1

Generated (in a NEW folder):

- story_plan.json — deterministic beats and chapter timing targets
- director_story_brief.md — story-writing instructions with research guardrails

You can provide researched citations as an optional JSON file. Example:

    [
      {
        "id": "source-001",
        "title": "Primary institution publication",
        "url": "https://www.example.org/source",
        "claim": "Specific claim the writer must verify in the original document"
      }
    ]

Supply it with --sources path/to/research_sources.json. The example above
is a FORMAT EXAMPLE ONLY, not an actual reference or verified fact.

If no references are supplied, the writing brief explicitly says
RESEARCH REQUIRED. Neither a sourced title nor a URL proves claim accuracy:
the human/writer must actually verify contents before production.

Use the generated director brief to guide **new scripts** prior to the existing
voiceover and caption stages. Do NOT paste edited narration into an already
voiced/rendered graph, which would break timeline sync.

## Audit existing finance narration without editing it

    python3 scripts/k70_p1_storytelling.py audit \
      --graph data/series/bitcoin_history/ep01/scene_graph.json \
      --out-dir data/finance_p1/bitcoin_history_audit_v1

Outputs:

- narrative_qa.json — transparent heuristic counts, scene IDs, timing and flags
- narrative_editorial_review.md — prioritized review notes

These are TEXT metrics, not footage or real YouTube retention measurements.
Question detection reads punctuation, analogy detection looks for cue phrases,
and visible-source checks cannot validate whether a citation is authentic.
Review source content manually. Numeric evidence flags are a conservative
editorial watchlist, NOT proof of a false financial claim.

All output destinations use exclusive file creation and refuse to overwrite an
existing plan. Existing SceneGraphs, final videos, 3D assets, TTS, full captions
and locked architectural components remain unchanged.

## Suggested Claude production handoff

1. Gather and independently verify source documents relevant to the episode.
2. Generate P1 story_plan.json + director_story_brief.md using the CLI.
3. Write ORIGINAL finance narration following the beat objectives, with grounded
   everyday analogies, honest counterarguments and timely answers to the hook.
4. Run the P1 audit on the new SceneGraph before generating TTS.
5. Review warnings and correct the SCRIPT/GRAPH COPY **before voiceover**.
6. Continue through the existing frozen K70 production pipeline and P0 visuals.
7. Validate actual audio, timing, original captions and video separately.

## Tests

    .venv/bin/python -m pytest -q tests/test_k70_p1_storytelling.py

P1 does not assert that a whole new documentary has been rendered or that a
completed documentary has reached a professional reference quality level.
Actual A/B video quality requires listening and watching the rendered file.

## Architecture safety

- No modification to the frozen 14-layer production scripts, manifests,
  protected reference masters, real-footage/source data or systemwide settings.
- No paid API calls, outside datasets or new mandatory dependencies.
- No edits to existing source narration, timestamps or 3D/AI assets.
- The CLI produces authored writing guidance, not an automatic TTS rewrite.
