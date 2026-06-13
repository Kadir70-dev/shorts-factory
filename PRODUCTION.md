# v1-production — FROZEN architecture

**Status:** frozen 2026-06-12. The Phase 1–4 pipeline is the production baseline.
**Do not add new features to the pipeline.** Only configuration (presets) and
orchestration (the production workflow) sit on top. Bug-fix-only on the frozen core.

This is a CPU-first, GPU-free shorts factory for an Intel i5 / no-GPU / ~12GB box.
Measured worst case across 3 niches: render ≤102s/short, ffmpeg peak ~756MB,
≥4GB RAM always free, character consistency 100%.

## Frozen pipeline (what each stage is and where it lives)

| Stage | Module | Notes |
|------|--------|-------|
| Topic → Research → Script → Scene + **grounding** | `director/` | strict narration↔visual lock authored here |
| Character memory + per-scene **layer plan** | `pipeline/storyboard.py`, `pipeline/character.py` | nominates ONE hero beat; locks a reusable character (seed+desc) |
| Voiceover (TTS) | `pipeline/tts.py` | Kokoro local → Piper → espeak → tone |
| Captions | `pipeline/captions.py` | whisper.cpp word-level |
| **Exact real footage** (no random stock) | `pipeline/broll.py::resolve_assets` | strict tiers: exact → AI recreation → supporting → generic → solid |
| **Exact AI hero generation** (cache-first) | `pipeline/broll.py::resolve_layers` | the ONLY AI-still source; hard ≤2 stills / ≤1 hero |
| **Layered composition** (bg▸subject▸fx) | `pipeline/layers.py` + `pipeline/render_ffmpeg.py` | 2-plane parallax, subtle motion, RAM guard, simple-render fallback |
| Sound design | `pipeline/music.py`, `pipeline/sfx.py` | niche bed + smart envelope + retention SFX |
| **QA** (black-frame / RAM / budget / consistency) | `pipeline/qa.py` | non-fatal audit, gated `QA_ENABLED` |
| RAM safety | `pipeline/ram.py` | /proc/meminfo + getrusage, no psutil |

All feature flags **default OFF** — the legacy single-asset pipeline is byte-identical
unless a preset turns them on.

## Production guarantees (how the doctrine is enforced)

- **Point-to-point grounding / no random stock** — `VISUAL_ACCURACY_MODE=strict`:
  the resolver tries the Director's *exact* per-line keywords first; generic stock is
  the demoted last resort, never the default; cross-scene anti-repeat dedupe.
- **Max 2 AI stills / short, 1 hero scene** — the production workflow runs
  `resolve_assets` with `allow_ai_image=False` (every non-hero beat is exact REAL
  footage, zero AI), so `resolve_layers` is the *only* AI source, hard-capped at
  `LAYERED_AI_STILL_BUDGET=2` inside the single `LAYERED_MAX_HERO_SCENES=1` hero.
- **Reusable character consistency** — `pipeline/character.py` locks a description +
  a deterministic sha1 seed on first sight; same seed+prompt → byte-identical
  content-addressed still on every reuse/re-render (measured 100%).
- **Cache-first** — every generator short-circuits on a content-addressed cache hit;
  re-runs reuse instantly.
- **CPU-safe** — no AnimateDiff / RIFE / depth / GPU; ffmpeg does all motion +
  compositing; threads pinned; RAM-floor guard falls back to a simple render.
- **Hook-first** — scene 0 is the hook (no fade-in so it hits instantly).

## Production presets (`config/presets/<name>.yaml`)

| Preset | Channel / niche | Character | Use |
|--------|-----------------|-----------|-----|
| `cybersecurity` | k70_cyber / cybersecurity | — (recreated scene) | dark cybercrime documentary |
| `dark_history` | k70_history / usa_history | — (archival) | forgotten/dark true stories |
| `educational` | k70_facts / usa_facts | — (concept-led) | why/how explainers + diagrams |
| `anime_storytelling` | k70_cyber / cybersecurity | **kade** (reusable) | anime cyber-thriller micro-stories |

Each preset locks the CPU-safe env (`RENDER_BACKEND=ffmpeg`, strict grounding,
layered hero, QA, budgets) and the creative direction (pacing, hook style, doctrine).

## Run

```bash
# from a fixed spec (deterministic, recommended for testing):
.venv/bin/python scripts/produce.py --preset anime_storytelling \
    --from-json data/demos/anime_ghost_key.json --keep

# from a live topic (needs the Claude director):
.venv/bin/python scripts/produce.py --preset cybersecurity --topic "the breach nobody noticed"
```

Output: `data/jobs/<video_id>/final.mp4` + `scene_graph.json`, plus a QA report.

## Recommended `.env` for this laptop

```
RENDER_BACKEND=ffmpeg
VISUAL_ACCURACY_MODE=strict
LAYERED_RENDER=1
CHARACTER_MEMORY=1
QA_ENABLED=1
LAYERED_AI_STILL_BUDGET=2
LAYERED_MAX_HERO_SCENES=1
LAYERED_FFMPEG_THREADS=4
LAYERED_SUBJECT_MATTE=oval        # =rembg only if the rembg package is installed
LAYERED_MIN_FREE_MB=2000
AI_VIDEO_ENABLED=0
ENABLE_IMAGE_TO_VIDEO=0
COMFYUI_ENABLED=0                 # HF FLUX-schnell is the free image workhorse here
```
Plus: arq `max_jobs=1` (one render at a time) and an 8GB swapfile for headroom.

## Validation harnesses (proof the frozen baseline works)

- `scripts/verify_phase3_layers.py` — composer + all fallbacks, on cached stills.
- `scripts/verify_phase4_qa.py` — 3 real shorts (cyber / anime / educational) + QA.
- `scripts/produce.py --preset anime_storytelling --from-json data/demos/anime_ghost_key.json`
  — the end-to-end production reference run.
