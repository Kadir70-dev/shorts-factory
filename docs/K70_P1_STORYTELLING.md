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


## P1.2: From story plan to grounded chapter narration (new)

The K70 long-form Director handoff is now executable via the existing
scripts/k70_p1_storytelling.py CLI. This is deliberately SEPARATE from the
20–45-second Shorts Director, and does not modify protected documentary layers.

First, have a researcher/editor read primary sources and create an evidence
pack JSON. A planning source reference is NOT proof of accuracy.

Example SHAPE (text and URL placeholders; not real sourced facts):

    {
      "facts": [
        {
          "id": "fact-001",
          "source_id": "source-001",
          "claim": "A verified factual point from the referenced document",
          "excerpt": "A short relevant quotation from the actual source"
        }
      ]
    }

Every source_id must exist in the story plan's source_manifest, which is
populated by the plan command's --sources file. **Read and verify** the actual
source before approval; the software marks excerpts as unverified.

Generate only the constrained chapter writing prompt (offline, NO model call):

    python3 scripts/k70_p1_storytelling.py draft \
      --plan data/finance_p1/gold_standard_v1/story_plan.json \
      --evidence PATH/verified_evidence_pack.json \
      --out-dir data/finance_p1/gold_standard_draft_prompt

When your laptop's Claude Code CLI is installed, you may EXPLICITLY opt in to
a locally invoked model writing the eight chapter narrations:

    python3 scripts/k70_p1_storytelling.py draft \
      --plan data/finance_p1/gold_standard_v1/story_plan.json \
      --evidence PATH/verified_evidence_pack.json \
      --out-dir data/finance_p1/gold_standard_draft_generation \
      --generate

The local CLI is run with no tools, maximum one turn and no paid-API
fallback. It uses the user's existing Claude CLI configuration and may
consume subscription usage. The system does not claim that CLI execution
occurred just because the option exists. Use a NEW output folder.

Files generated when --generate is requested:

- chapter_draft_prompt.md — exact instructions and source evidence.
- chapter_narration_draft.json — eight chapters, text and linked FACT IDs.
- chapter_narration_review.json — word-count/time estimate, question and
  analogy checks, unknown-number flags, human-review requirements.

Validate any manually edited narration JSON in a separate read-only pass:

    python3 scripts/k70_p1_storytelling.py review \
      --plan data/finance_p1/gold_standard_v1/story_plan.json \
      --evidence PATH/verified_evidence_pack.json \
      --draft PATH/edited_chapter_narration.json \
      --out-dir data/finance_p1/gold_standard_edited_review

Validation rejects unknown fact IDs, wrong chapter order and empty text, and
flags unmatched numerical claims. It does NOT establish historical truth or
guarantee word-level source fidelity. A responsible editor still checks
figures, primary sources, fair framing and analogy limitations.

**Crucial production boundary:** these files are editorial chapter drafts.
They do not replace a rendered, voiced SceneGraph. After human approval, use
the existing K70 storyboarding/scene-authoring workflow to produce a NEW
SceneGraph, then TTS, full captions and 14-layer rendering as normal. Never
overwrite a finished job or silently retime existing audio.

### Additional isolated tests

    .venv/bin/python -m pytest -q tests/test_k70_p1_story_draft.py \
      tests/test_k70_p1_storytelling.py

This PR-free direct-main change adds no GPU requirement or paid API.
