# K70 P3 — Intelligent Documentary Editor

**Status:** implemented on main as an independent, deterministic, pre-render
whole-film editorial pass. Pure Python stdlib, CPU-only, offline.

The frozen **K70-PRODUCTION-v1.0 14 layers**, visual-budget allocation,
source narration, charts, authenticated media, 3D frames, cinematic clips, TTS,
captions, music, existing jobs and master MP4s are untouched.

The P3 planner reads a complete SceneGraph and issues transparent editorial
recommendations **without silently applying visual replacements**. That is
intentional: replacing an actual Japan 3D globe or verified chart with guessed
stock just to meet an automatic visual quota would make a worse documentary.

## What it actually does

1. **Narration-to-visual reasoning:** prioritizes a sourced chart when a real
   data series exists; identifies numeric claims needing manual source checks;
   recognizes named geography, the logic of an economic mechanism, and
   documentary-specific literal visuals. Author-assigned real 3D, charts,
   AI cinematic material and resolved asset files are protected.
2. **Whole-film continuity:** measures the exact visual mix in each quarter,
   identifies 25+ seconds or 4+ consecutive full-screen text-card scenes,
   warns about cinematic clips concentrated in too few quarters, and highlights
   episodes whose 20+ scenes are >40% cards by count.
3. **Relevance checker:** flags generic financial B-roll queries, visually
   suspicious foreign banknotes during narration specifically about US dollars,
   and possible keyword mismatches between narration and visual direction
   (footage-type visuals only; cards, charts and 3D show authored content).
   Also flags sourced chart data shown as a non-chart visual
   (`sourced_chart_not_shown`), stock clips standing in for a resolved licensed
   archival asset (`resolved_archival_source_not_used`), and stock clips for a
   named person/place/year (`named_subject_on_generic_stock`).
   Text-match warnings are heuristic: inspect frames before changing clips.
   Film-level: reused asset files (`duplicate_visual_asset`), one soft
   transition on >50% of scenes (`transition_monotony`), and narration changed
   by the compliance layer (`compliance_rewrite_changed_narration`).
4. **Editorial transitions:** recommends restrained cuts or crossfades at real
   argument/chapter changes; preserves already-authored transition effects.
5. **Non-destructive reports:** produces JSON per-scene rationale and source
   graph SHA256 fingerprint, plus a readable Markdown full-film review.
6. **Optional revised copy:** with an explicit flag, creates a NEW SceneGraph
   that adjusts only eligible cut -> crossfade transitions on unrendered,
   asset-free scenes and promotes *fallback text/solid cards* carrying sourced
   numeric points into the existing dataviz engine. A named source alone is not
   independently verified: authors must verify numbers. Refuses existing audio,
   captions, SFX, rendered provenance, resolved footage/layers or stale plans.
   Keeps authored 3D, AI video, actual footage and existing charts untouched.

**P3 does NOT:** inspect actual video pixels, create 3D or AI content, fetch
source evidence, rewrite narration, replace footage, bypass the existing visual
budget, or perform paid API calls. Recommendations still need editorial approval.

## Review the actual Bitcoin history SceneGraph

    python3 scripts/k70_p3_editor.py \
      --graph data/series/bitcoin_history/ep01/scene_graph.json \
      --out-dir data/finance_p3/bitcoin_ep01_editor_v1

Produces:

- editorial_plan.json — original source SHA256, per-scene visual intent,
  transition proposal, provenance protection, runtime/quarter mix, QA issues.
- editorial_review.md — compact issue list and visual breakdown.

Use a fresh output directory each time. This mode never writes back to the
source graph, never starts a render, and does not need any Claude API key.

Compare a later pass with its earlier graph (read-only, both files):

    python3 scripts/k70_p3_editor.py \
      --graph data/finance_p0/cinematic_balanced/scene_graph_p0.json \
      --baseline data/series/bitcoin_history/ep01/scene_graph.json \
      --out-dir data/finance_p3/bitcoin_ep01_p0_review_v2

Adds `baseline_comparison` to the plan: scene order, visual type changes,
sourced charts and authored 3D/cinematic scenes that were replaced, and every
narration change.

## Only for an unrendered NEW episode

    python3 scripts/k70_p3_editor.py \
      --graph path/to/NEW_UNRENDERED_EPISODE.json \
      --out-dir data/finance_p3/new_episode_cut_v1 \
      --apply-transitions-to-copy

Adds a third output: scene_graph_editorial_copy.json. The only visual
changes allowed are sourced-data fallback cards -> existing dataviz type.
Other visual improvements stay proposals pending real evidence/asset review.

The copy is still **not a finished documentary**. Have a human reviewer approve
cut points before handing the copy to the existing (frozen) storyboarding,
voiceover, captions, assets and renderer stages.

## P1 + P0 + P3 in the authoring workflow

Research & fact-check → P1 story plan → P1 reviewed chapter narration → new
SceneGraph authoring → **P3 editorial report / approved transition copy** →
existing frozen K70 voiceover & renderer → P0 3D/cinematic treatment as supported
→ final MP4 → human video+audio QA.

Existing P0 finished scenes can be audited in P3, but their media assignment and
source videos will not be overwritten by a heuristic algorithm.

## Regression tests

    python3 -m pytest -q tests/test_k70_p3_intelligent_editor.py tests/test_k70_p1_p3_workflow.py

Dedicated workflow: .github/workflows/k70-p3-editor.yml.

**Remaining to confirm:** GitHub Actions / local test pass, inspecting the
156-scene Bitcoin film's report with its local assets, and human reviewing the
full Premium V2 MP4. Those are NOT implied by this code delivery.
