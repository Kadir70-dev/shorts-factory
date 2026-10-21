# K70 Finance P0 — premium visual quality pass (opt-in; no new render)

Scope: visual presentation only, learned from the K70 F5 quality report; do not imitate another creator's branding. This change does not touch the frozen 14-layer finance pipeline or initiate a documentary render.

## P0.1 Six editorial motion-card layouts

Existing kinetic fallback cards were almost always center-stacked on one dark theme. The new style rotation includes editorial_center, split_left, split_right, masthead, lower_focus and side_accent with different geometry and text positioning.

- First headline line is visible on the first frame; subsequent lines arrive quickly.
- Styles rotate deterministically based on scene position rather than Python's process-randomized hash.
- Different treatment and layout are part of the cache key, preventing old cards from being reused in error.
- Existing kinetic callers with no explicit layout remain backwards compatible.
- 2D drawing only: no GPU or model API needed.

## P0.2 Three.js missing dependency guard

The worker now checks for actual installed three, puppeteer and TypeScript tooling before compilation. A missing package gives a meaningful npm-ci hint. It does NOT auto-install dependencies while production is running.

When no production job is running:

    cd ~/shorts-factory/apps/remotion
    npm ci
    npm run threejs:build

Compile success alone does not prove Chromium can launch. Test an isolated 3D scene before another full render. Browser/Chromium may add substantial RAM load on the HP laptop.

## P0.3 Balanced finance cinematic illustrations (opt-in)

F3 originally selected the first eight safe candidates. The new --balanced flag keeps all the existing finance safeguards, then picks safe AI illustration prompts spread across the complete documentary timeline.

Example on an existing graph with exported missing image prompts:

    .venv/bin/python scripts/finance_cinematic_f3.py \
      --graph data/series/bitcoin_history/ep01/scene_graph.json \
      --missing data/series/bitcoin_history/ep01/assets/missing_ai_images.json \
      --out-dir data/finance_f3/bitcoin_ep01_balanced_p0 \
      --limit 8 --balanced --render-clips

This is opt-in real image generation using the existing provider. Respect free-tier pacing and watermark terms; no paid provider without approval. Use a fresh output directory. This DOES NOT make a complete documentary by itself.

## P0.4 Read-only 3D/visual readiness audit

    .venv/bin/python scripts/k70_p0_visual_audit.py \
      --graph data/series/bitcoin_history/ep01/scene_graph.json

For an EXISTING finished MP4 (will decode the video and can take time):

    .venv/bin/python scripts/k70_p0_visual_audit.py \
      --graph PATH/scene_graph.json --video PATH/final.mp4 \
      --strict --report PATH/p0_visual_audit.json

It reports planned 3D, actually resolved types, AI clips in four time segments, file readiness, FFmpeg black intervals and 1+ second freezes on motion graphics. An intentional static historical photo is not automatically rejected. Strict mode exits nonzero when planned 3D packages are absent or a motion-graphics freeze is found.

## P0.5 Verified on the HP EliteBook (CPU-only), 2026-10-21

### 3D restore — 20/20 authored Three.js scenes rendered

Root cause of "20 planned 3D → 2D cards" was NOT only missing packages:

1. `config/visual_budget.yaml` sets `threejs: {lo: 0, hi: 0}` (Day 04 rule,
   "engine disabled here"), so the allocator re-channelled every authored
   `visual.type: threejs` scene to official / motion_gfx / ai_broll and the
   storyboard never marked them as 3D candidates. Only s26 reached the worker,
   and it failed with an empty `RuntimeError` (packages missing at the time).
2. Beats had no `location`, so prose won the globe target: 9/20 flew to the
   wrong country (e.g. "Japan" → United States).
3. At the 360px preview size, long region labels ran off the frame.

Fixes: the allocator honours authored 3D within the band ceiling (no change
while the band stays at 0); for 3D beats the storyboard uses the authored
`visual.query` as the location; the worker shrinks labels to fit the frame
(`TEMPLATE_VERSION` 1.1.1). Packages verified: three 0.179.1, puppeteer
24.16.0, Chromium 139 (puppeteer cache), Node v22.23.0; worker compiles in about 3s.

    THREEJS_VISUAL_ENGINE_ENABLED=1 .venv/bin/python scripts/k70_p0_threejs_restore.py \
      --job data/jobs/k70_f4_bitcoin_ep01 \
      --authored data/series/bitcoin_history/ep01_f4/scene_graph.json \
      --out data/finance_p0/threejs_restore --quality preview

Result: **20 rendered, 0 failed**, all `globe_flight` to the authored place
(s7 Maryland, s14 New Hampshire, s17 Germany, s22 India, s31 Japan, s37 France,
s47 USA, s62 Ohio, s72 Thailand, s73 Indonesia, s74 Russia, s76 New York,
s86 Netherlands, s87 Switzerland, s90 California, s104 Florida, s116 Argentina,
s124 Zimbabwe, s128 Hungary, s131 United Kingdom). Every clip's decoded length
is within ±0.02 s of its scene. 13.6–41.5 s per scene, about 5.5 min total,
peak worker RSS 1.45 GB. Each frame was checked visually: the correct region
is highlighted and labelled. The motion-graphics fallback is unchanged: a
failed render still returns `unresolved` and the dispatcher ladder handles it.

### Balanced cinematic clips — 8 clips across all four quarters

`scripts/k70_p0_cinematic_balance.py` works on the job's voiced timing.
It uses F3 eligibility and the P0 spread to pick stills, then F2
`select_scenes(balanced=True)` and F1 `auto_apply`, starting from the 3D-restored graph:

| Scene | Start | Quarter | Still |
|---|---|---|---|
| s1 | 0:00.0 | Q1 | recovered |
| s33 | 2:19.5 | Q1 | recovered |
| s46 | 3:13.1 | Q2 | recovered |
| s71 | 5:05.6 | Q2 | generated (free Pollinations) |
| s79 | 5:36.8 | Q3 | generated |
| s101 | 7:14.2 | Q3 | generated |
| s123 | 8:38.6 | Q4 | generated |
| s145 | 10:15.6 | Q4 | generated |

F4 had six clips, all before 4:00. Narration, overlays, chart data and timing
are identical for all 156 scenes, and all 20 charts are untouched. Only 28
scenes change visual: 20 → 3D and 8 → clips. Motion cards drop from 71 to 54.
Review before approving a render: the s71 and s145 stills only loosely match
their prompts (a corridor rather than a mainframe hall or a foreclosure
notice). Re-roll them with F3 `--variant` if needed.

Output (new files only; the job and both final MP4s are untouched):
`data/finance_p0/cinematic_balanced/scene_graph_p0.json`. **No documentary
render was launched**; composing this graph needs approval.

To route 3D in FUTURE renders, `threejs.hi` in `config/visual_budget.yaml`
must be raised (e.g. 0.20). That is a global policy change for Shorts too and
needs approval.

## Tests

    .venv/bin/python -m pytest -q tests/        # 70 passed (incl. tests/test_k70_p0_restore.py)

`apps/api/tests` with `pytest-asyncio==0.25.2` (pinned in requirements.txt but
missing from `.venv`): 328 passed, including `test_threejs_engine.py`. The same 13
failures and 30 collection errors appear on the PR base, so none are caused by
these changes. They come from captions fonts, the multi-source resolver,
topic-intelligence DB isolation and DB/auth imports.
