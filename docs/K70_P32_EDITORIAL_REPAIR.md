# K70 P3.2 Editorial Repair

`scripts/k70_p32_editorial_repair.py` applies a **reviewed** decision file (JSON) to a **new** copy of a voiced SceneGraph. The input graph, masters, voiceover and captions are read-only. It never runs TTS or a render.

```bash
.venv/bin/python scripts/k70_p32_editorial_repair.py \
  --graph data/finance_p31/bitcoin_repaired_v1/scene_graph_p31_repaired.json \
  --decisions data/finance_p32/bitcoin_editorial_v1/p32_decisions.json \
  --out-dir data/finance_p32/bitcoin_editorial_v1 --fetch
```

## What the decision file can do

- **`scenes[]`:**
  - `archival_plate`, `triptych` or `typography_plate`: builds a 1080×1920 plate (`tools/k70_scene_engine/editorial_plates.py`). The whole source stays visible over a blurred copy of itself, with an honest identity/date label inside the ken-burns safe area.
  - `keep` or `manual_review`: recorded in the change log only.
  - `run_break: true`: keeps the scene's crossfade (used when a card becomes an image).
- **Sources:** Wikimedia Commons files are fetched only by exact title. The download is refused if the file URL changed since review.
- **`narration_corrections[]`:** allowed only when the corrected words equal the timed caption words already in that scene. That is, the recorded speech must already say it. Otherwise the script stops with "needs re-TTS".
- **`overlay_corrections[]`:** an exact before/after replacement of one overlay.

## Automatic transition polish

Crossfade becomes cut between consecutive cards (motion_gfx/dataviz) and on beats shorter than 2 s. Dissolves into or out of Three.js and AI cinematic scenes are kept, and so are s35 and s67.

In `render_ffmpeg`, transitions are in-clip, duration-preserving effects, so a cut never shifts audio or caption sync.

## Hard guards (`p32_editorial.validate`)

The script fails unless all of these hold:

- Scene IDs and order, every `duration_sec`, captions, audio, SFX, meta, storyboard and provenance blocks are unchanged.
- Three.js and AI-video visuals and transitions are unchanged, and so are the s35/s67 sourced charts.
- Every new `asset_path` exists on disk.

## Licensing

Licence data is copied from Commons and is **not** a legal clearance. See `data/finance_p32/bitcoin_editorial_v1/P32_ASSET_CREDITS.md` for the per-asset credits and the release gate.
