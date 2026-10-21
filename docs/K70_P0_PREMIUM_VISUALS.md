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

## Tests to run on the HP laptop before merging

The code changes were made through the GitHub connector; a local clone is not available in this execution environment, so target-repository test results are NOT yet verified.

    .venv/bin/python -m pytest -q \
      tests/test_k70_p0_visuals.py \
      tests/test_finance_cinematic_cpu.py \
      tests/test_finance_cinematic_auto.py \
      tests/test_finance_cinematic_f3.py \
      tests/test_render_ffmpeg_filter_flag.py

After tests, do a short NEW scene preview and manual frame review. Do not overwrite F4 production files or start a full 8–10 minute render without approval.

Deferred until target laptop verification: 20/20 genuine Three.js restores; full documentary re-render; voice/storytelling changes (P1).
