# F2 — auto-select safe AI stills for existing K70 long-form documentary

F1 GPU-free CPU 2.5D clip engine was verified on the user's HP EliteBook 840 G1:
5 seconds @ 640x360 18 FPS in **4.766 seconds**. F2 adds scene selection
and safe non-destructive insertion **outside** the frozen 14-layer K70
production pipeline; existing finance documentary generation is unchanged.

## First: inspect a real completed finance SceneGraph

From repo root, use **python3** (Ubuntu does not have a python alias):

    git pull origin main
    find data/jobs -name scene_graph.json -type f | tail -10

Pick the exact job you want to test (replace VIDEO_ID), then dry-run:

    python3 scripts/finance_cinematic_auto.py \
      --graph data/jobs/VIDEO_ID/scene_graph.json \
      --out-dir data/jobs/VIDEO_ID/finance_f2 \
      --max-clips 8 --spacing-sec 25

**Dry-run is the default:** prints eligible scene IDs, timestamps,
durations, source stills, and skip count. It does not create files
or overwrite existing renders. If selected_count = 0, your finished
job has no qualifying local AI stills; this tool DOES NOT invent them.
You first need genuine, original/licensed finance illustrative AI images
selected by the existing pipeline.

Eligibility is intentionally narrow:
- visual.type **must be ai_image**, with a local readable JPG/PNG/WebP
- visual budget channel is blank or ai_broll
- skips source/stat overlays, evidenced documents, layered scenes,
  official footage, factual data charts, pre-existing MP4 and stock video
- skips scenes with text suggesting real/archival/official footage
- scenes are 2–12 seconds; priority for hook/reveal/dramatic beats
- minimum separation 25 seconds; maximum 8 clips by default

## Render (explicit opt-in)

Only after reviewing the dry run:

    python3 scripts/finance_cinematic_auto.py \
      --graph data/jobs/VIDEO_ID/scene_graph.json \
      --out-dir data/jobs/VIDEO_ID/finance_f2 \
      --max-clips 8 --spacing-sec 25 \
      --apply

Creates:
- new scene_graph_finance_f2.json (original untouched)
- selection_report.json
- specs/<scene_hash>/plate.jpg + shot.json (CPU-sized 640x360)
- clips/finance_cinematic_*.mp4 (silent; source narration is NOT re-generated)
- cache/ (content-addressed reused F1 MP4)

Output is **2.5D animated still footage**, not GPU-based neural image-to-video.
With only a single still, F2 gives camera movement/glow/particles; no
true independent parallax unless you supply cutout layers using F1 manual specs.
A 5-second scene may take roughly 5 seconds locally based on F1 benchmark,
but 8–10 minute whole-video time is NOT measured.

## Optional new 8–10 min final video

To rerender full documentary, append a **new and nonexisting** output path:

    --out-video data/jobs/VIDEO_ID/finance_f2_final.mp4

The CLI uses the existing FFmpeg renderer, voiceover, captions,
music and branding. It does **not** touch any file in the original job
or change scripts/produce.py. Note that long-form end-to-end render
has not yet been verified on the user's actual finance video.

For tests:

    python3 -m pytest -q tests/test_finance_cinematic_cpu.py tests/test_finance_cinematic_auto.py

## Finance safety

Never present animated illustrations as real trading-floor/news/archival
footage. Do not animate SEC filings, sourced charts or official documents
as fabricated evidence. Use original/licensed input art; visually inspect
each injected scene before uploading. Use platform disclosure where appropriate.
