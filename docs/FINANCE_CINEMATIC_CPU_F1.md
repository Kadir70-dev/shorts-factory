# F1 — Finance Cinematic CPU Motion Engine (opt-in, no GPU)

**Purpose:** Shorts Factory already makes the 8–10 minute U.S. finance documentaries. This extension only supplies 3–8-second *moving illustrative B-roll clips* in selected scenes. It does not replace script, data, voice, captions, existing chart renderer or the frozen 14-layer K70 production architecture.

## Capabilities and limits

Input: original/licensed **still image** plus optional 1–4 transparent, full-frame near/far layers. Use ChatGPT-generated original art or another image provider first; this module does **NOT generate AI image assets**.

Output: **CPU-composited 2.5D H.264 MP4**, not neural image-to-video. Animated parallax/camera dolly and truck movements, independent cloud drift, atmosphere/light/dust. Existing FFmpeg handles voice/captions/mux and scales 360p scenes into a matching-aspect 1080p video. Avoid claiming this is genuine archival, live or documentary evidence.

Default 640×360, 18 FPS, five seconds, two FFmpeg threads. Input images are sandboxed to the manifest's own folder. Video is silent and SHA-256 cached against actual asset bytes. No GPU, video API key, financial numbers or new models.

## Quick working test

Run from repo root, with Pillow, ffmpeg, ffprobe and pytest installed:

    python scripts/finance_cinematic_demo.py --out-dir data/finance_f1_demo
    ffprobe -v error -show_entries stream=codec_name,width,height,r_frame_rate -show_entries format=duration -of json data/finance_f1_demo/demo.mp4
    python -m pytest -q tests/test_finance_cinematic_cpu.py

The demo artwork is procedural, not actual AI art, Wall Street photography or generated neural motion.

## Use your own finance AI stills

Place two matching-size 16:9 original/licensed assets in a folder:
- background.png — sky, architecture, trading background, or other finance visual
- foreground.png — cut-out buildings/objects on transparent RGBA, same framing, **real alpha** (optional)

Alongside these assets place shot.json:

    {
      "background": "background.png",
      "layers": [{"path":"foreground.png","depth":0.95,"opacity":0.92}],
      "width":640, "height":360, "fps":18, "duration_sec":5,
      "camera":"dolly_in", "camera_strength":0.12, "seed":23,
      "effects":{"clouds":true,"dust":true,"light_glow":true}
    }

Then run:

    python scripts/finance_cinematic_render.py \
      --spec data/finance_shots/shot1/shot.json \
      --out data/finance_shots/shot1/clip.mp4 \
      --cache-dir data/cache/finance_cinematic_cpu

Camera options: dolly_in, dolly_out, truck_left, truck_right, static. Scene duration 0.2–20 sec. Don't use a flattened still as a transparent foreground. Character/people motion (walking, lip movement) is not synthesized.

## Put clips into an existing completed 8–10 minute K70 finance video

After your **existing** K70 job produces a fully populated scene_graph.json (with measured scene duration and resolved assets), identify desired **illustrative** scene IDs. Do NOT replace factual charts, official evidence or verified data.

Create data/finance_shots/mapping.json, using real scene IDs:

    {
      "scene_03": "shot1/shot.json"
    }

The shot duration must match that scene's duration_sec (within roughly one frame).

    python scripts/finance_cinematic_inject.py \
      --graph data/jobs/VIDEO_ID/scene_graph.json \
      --mapping data/finance_shots/mapping.json \
      --out-graph data/jobs/VIDEO_ID/scene_graph_finance_f1.json \
      --clip-dir data/jobs/VIDEO_ID/finance_cinematic_clips \
      --cache-dir data/cache/finance_cinematic_cpu

This writes **a NEW graph** and silent MP4 clips. Nothing overwrites the existing video or original SceneGraph.

To optionally re-render a new final documentary MP4 with the existing K70 FFmpeg renderer, add:

    --out-video data/jobs/VIDEO_ID/finance_cinematic_final.mp4

This rerender has NOT yet been tried on the target HP laptop or a complete production job. It may take substantial CPU time for 8–10 minutes. Final video keeps existing audio, branding and captions.

## Finance integrity safeguards

- Illustrative scenes are never presented as archival news, financial evidence or actual stock footage.
- Existing source-based charts/data, official allocation and evidence-card scenes are protected in the adapter.
- No invented stock prices, fabricated SEC filings or financial claims are rendered.
- Original/appropriately licensed input images required; disclose synthetic visuals when appropriate.
- Defaults are unchanged unless the sidecar is explicitly run. Main K70 code and schemas are not edited.

## Verified / pending

In isolated test environment: 11 focused tests passed (image movement, invalid transparency, path traversal, bounds, data/official protection, silent MP4, cache hit, scene replacement, 1920×1080 same-aspect fit); procedural 5.00 s demo verified as H.264 640×360 at 18 FPS, 90 frames. Target laptop has **not** been tested.

Next: test with real ChatGPT-generated finance plates and inspect layering; run against a completed actual 8–10 minute scene_graph.json; profile HP i5 CPU/memory; choose safe scene placement policy (F2 auto selection) if desired.
