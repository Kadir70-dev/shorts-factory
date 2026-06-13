# Shorts Factory

Production-grade AI video factory for **USA politics / election / finance** Shorts
(20–45s, vertical). Type a prompt → get a finished `.mp4` + thumbnail + metadata,
ready to approve and upload.

```
VideoSpec → Director(Claude) → SceneGraph → TTS → Captions(whisper)
          → Assets(pexels/manim/veo3) → Remotion render → FFmpeg post
          → approve → upload
```

## B-roll / footage engine
Every scene is backed by REAL moving footage — never an empty text card. The
Director emits per-scene `visual.broll_keywords` + `scene_visual_type`, and the
asset resolver (`app/pipeline/broll.py`) walks a priority chain:

```
Pexels video → Pixabay video → Pexels image → Pixabay image → animated gradient
```

Images get Ken Burns / pan / zoom motion (chosen by the scene's editorial role:
`dramatic` hook, `data_viz` chart, `subtle` CTA). Downloads are content-addressed
and de-duplicated, so footage is fetched once and reused — deterministic & fast.

> Real footage needs `PEXELS_API_KEY` (and optionally `PIXABAY_API_KEY`) in
> `.env`. Without them the pipeline still ships — it falls back to the animated
> gradient — but you won't see the gas-station/shoppers/economy clips.

## The one contract that matters
`apps/api/app/schemas/scene.py` (Pydantic) ⇆ `apps/remotion/src/schemas/scene.ts`
(Zod). The Director emits a **SceneGraph**; Remotion is a pure function of it.
Change one side → change the other → bump `SCHEMA_VERSION`.

## Make a REAL short (Claude Director → MP4)
```bash
python make_gen.py "Why Americans are worried about inflation"
python make_gen.py "New swing-state poll shifts the map" --niche election
python make_gen.py "How a filibuster works" --niche politics --no-research
```
The Director runs on **your Claude MAX plan via the local `claude` CLI** (no API
billing) — that's `--backend cli` (default). `--backend api` uses
`ANTHROPIC_API_KEY` instead. Flow: web-search **research** → SceneGraph + metadata
(title/desc/tags/hashtags) → schema-validated with a repair loop and sanity gates
(20–45s, word budgets, hook, pacing) → TTS → captions → assets → render → MP4.

> Note: a Claude **Max subscription ≠ an API key**. The `cli` backend is what
> lets Max drive generation; the `api` backend needs a console.anthropic.com key.

## Prove it in 30s — ZERO keys required
```bash
python3 -m venv .venv && .venv/bin/pip install pydantic pydantic-settings pyyaml httpx
DIRECTOR_MODE=mock .venv/bin/python scripts/smoke.py
# -> data/jobs/<id>/final.mp4  (1080x1920 H.264, burned captions + overlays + audio)
```
Runs the whole pipeline offline: **mock Director** (no Anthropic) → **local TTS**
(espeak/silence fallback) → **script-timed captions** (no Whisper) → solid/Manim
assets → **pure-ffmpeg renderer** (no Remotion/Node). Every stage has a graceful
fallback, so missing a key/tool degrades quality — it never breaks the pipeline.

## Run (local-first, full quality)
```bash
cp .env.example .env          # fill ANTHROPIC + ELEVENLABS + PEXELS keys
docker compose up --build     # redis + api + worker + remotion
make gen                      # one finance short
make batch                    # 5 election shorts
open http://localhost:8000/docs
```

## Architecture decisions (CTO notes)
| Concern | v1 choice | Why |
|---|---|---|
| Queue | arq (async Redis) | matches FastAPI asyncio; Celery is overkill |
| DB | SQLite + JSON blobs | local-first; swap URL → Postgres later |
| Render | warm Remotion service | avoid per-job webpack bundle cost |
| Timing | TTS-first, measure, rewrite | captions/visuals match real audio |
| AI video | stubbed behind interface | Veo3/Seedance gated on cost |
| Captions | whisper.cpp word-level | karaoke highlight, no API cost |
| Upload | YouTube first | only sane official API |

## What is intentionally NOT in v1
Veo3/Seedance hero shots, TikTok/IG/FB upload, analytics, auto-scheduling,
multi-channel rotation. All have seams; none block the spine.

## Phase map
- **P1** skeleton + schemas + infra ✅ (this repo)
- **P2** Director engine (`app/director/`) — structured tool-use + repair loop
- **P3** pipeline hardening (`app/pipeline/`) — manim templates, music, effects
- **P4** Next.js dashboard (`apps/web/`)
- **P5** upload adapters (`app/uploaders/`)
- **P6** scale: batching, cost ceilings, dedup, schedule
