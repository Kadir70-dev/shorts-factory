# Shorts Factory: opt-in CPU cartoon animation

This feature is **not** a diffusion image-to-video model. It animates layered,
transparent PNG sprites on a CPU, with deterministic waving, walking, blinking,
nodding, simple audio-amplitude mouth movement and optional near/far parallax.
It builds clips for the pre-existing renderer to add existing brand, captions,
TTS, soundtrack and final MP4. It does not create missing body geometry or
perform automatic image segmentation/rigging.

## Linux demo (no GPU, no API key)

Run from repo root (requires Pillow and ffmpeg):

    python scripts/cartoon_cpu_demo.py --out-dir data/cartoon_demo
    ffprobe -v error -show_entries format=duration -of json data/cartoon_demo/demo.mp4
    PYTHONPATH=apps/api pytest -q tests/test_cartoon_motion_cpu.py

Alternate landscape demo:

    python scripts/cartoon_cpu_demo.py --landscape --out-dir data/cartoon_landscape

The demo creates an editable cartoon.json manifest and assets directory.
Replace procedural demo sprites with original *transparent part images*
(body/head/arms/legs/eyes/mouth). A single flat screenshot cannot automatically
walk or talk naturally. Each part has an anchor (canvas joint location)
and pivot (joint location relative to the sprite).

Render any manifest:

    python apps/api/app/pipeline/cartoon_motion_cpu.py \
      --manifest data/cartoon_demo/cartoon.json \
      --out data/cartoon_demo/custom.mp4

Motions: idle, wave, walk, blink, talk, nod.

Optional manifest voice_wav points to relative PCM 16-bit WAV, muxed into
standalone output. For timing-only mouth movement, lip_sync_wav may point
to a local WAV. This is coarse RMS mouth movement, not phoneme-level lip sync.

## Opt-in SceneGraph bridge

After existing TTS sets real scene.duration_sec and before existing
render_ffmpeg.render(), run the bridge for cartoon projects only:

    from pathlib import Path
    from app.pipeline.cartoon_motion_adapter import apply_cartoon_to_graph

    graph = apply_cartoon_to_graph(
        graph,
        {'scene_01': Path('data/cartoon_demo/cartoon.json')},
        Path('data/jobs/VIDEO_ID/cartoon_motion'),
        scene_voice_wavs={'scene_01': Path('data/jobs/VIDEO_ID/vo/scene_00.wav')},
    )

The adapter deep-copies the Pydantic SceneGraph, sets chosen scenes to pre-rendered
moving MP4s via visual.type='broll', and clears old still-image layers.
The existing FFmpeg pipeline remains responsible for final voice, branding and
captions. SceneGraph schemas, K70 documents and main production flows remain
unchanged. Using a silent cartoon manifest prevents duplicated voice audio.

CPU baseline: 360x640, 12 FPS, 2 FFmpeg threads, 5–10 second scenes.
Tests executed in an isolated tool environment, not on the target HP laptop.
Higher resolutions and full videos require that laptop's render benchmark.

## Remaining milestones

- Integrate as a selectable Director/worker cartoon job with config flags.
- Take actual ChatGPT-generated PNG body-part assets and validate pivots.
- Improve character rig (joints, knees/elbows and proper walk cycle).
- Phoneme-aligned Hindi voice/lip sync (currently voice amplitude only).
- Multi-scene assembly and 60-second Short / long-form soak tests on the laptop.
- Per-asset caching, performance budgets and upload/publishing QA.

No changes to protected K70 14-layer documentary architecture.
