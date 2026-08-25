# Shorts Factory

Production-grade AI video factory for **USA politics / election / finance** Shorts
(20–45s, vertical). Type a prompt → get a finished `.mp4` + thumbnail + metadata,
ready to approve and upload.

```
VideoSpec → Director(Claude) → Story structure → SceneGraph → Compliance gate
          → Variety plan → Cloned-voice TTS → Captions(whisper)
          → Visual ladder (charts / graphics / footage) → Branded render
          → FFmpeg post → approve → upload
```

> **Start here if you are setting this up:**
> **[docs/PIPELINE_UPGRADE.md](docs/PIPELINE_UPGRADE.md)** — the current
> architecture: cloned narration, rotating story structures, the five-tier visual
> ladder, the brand package, and the monetisation-safety gate.
> **[docs/VOICE_CLONING.md](docs/VOICE_CLONING.md)** — the one-off setup that
> makes every video use your own voice.

## Visual ladder
Stock footage is the LAST resort, not the default. Each beat resolves down a
five-tier ladder (`app/pipeline/scene_director.py` decides, `broll.py` resolves):

```
1. subject-specific footage / AI recreation of the exact subject
2. motion graphics  — the claim built on screen in the channel's type
3. animated charts  — every important number, from real authored data
4. branded plate    — the floor
5. generic stock    — a rescue, only when it is genuinely on-topic
```

Numbers never get paired with unrelated footage: a beat carrying a figure renders
as a branded animated chart of *that* figure, with its source attribution.
Charts, kinetic type and plates are drawn locally with numpy + ffmpeg — no Manim,
no network, no GPU.

> Real footage needs `PEXELS_API_KEY` (and optionally `PIXABAY_API_KEY`) in
> `.env`. Without them the pipeline still ships a fully branded video — tiers 2–4
> need no keys at all.

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
cp .env.example .env          # fill ANTHROPIC + asset-provider keys
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

## Topic intelligence (Phase 2A)
Don't know what to make today? `app/topic_intelligence/` picks the topic. It
collects real signals (finance RSS, YouTube, Reddit, X, an economic calendar,
Google Trends, Gemini Search grounding), clusters them into stories, rejects
duplicates and unsafe finance framings, scores every candidate deterministically,
and uses **Gemini** to judge angle/hook/why-now — never to invent facts or set the
score.

```bash
cd apps/api
python -m app.topic_intelligence status                       # what's configured
python -m app.topic_intelligence run --channel usa_trading    # pick the next topic
python -m app.topic_intelligence run --channel usa_trading --enqueue   # ...and queue it
```

Works with **zero keys** (free finance RSS + the deterministic ranker). Add
`GEMINI_API_KEY` for reasoning and `YOUTUBE_DATA_API_KEY` for competition
analysis. Every provider is optional; a Gemini outage falls back, and when
nothing credible and safe survives it returns `NO_SAFE_TOPIC_AVAILABLE` rather
than filler. Full docs: **[`docs/TOPIC_INTELLIGENCE.md`](docs/TOPIC_INTELLIGENCE.md)**.

## K70 Finance long-form (`tools/k70_scene_engine/`)
A separate Blender-based scene engine for K70's long-form finance documentaries
(Fed policy, forex, XAU/USD, etc.), independent of the Shorts pipeline above.
See **[tools/k70_scene_engine/README.md](tools/k70_scene_engine/README.md)** for
the engine itself and **[docs/K70_SCENE_ENGINE_LICENSE_AUDIT.md](docs/K70_SCENE_ENGINE_LICENSE_AUDIT.md)**
for asset licensing.

Finance long-form content is restricted to a strict visual language: **cinematic
real footage, premium 3D motion graphics, animated charts/graphs, and real-footage
+ chart hybrids only** — no Minecraft/voxel, isometric miniature, clay, sketch,
paper-collage, 2.5D illustration, or standalone vector-explainer scenes. Every
shot must earn its place against the exact narration line it's paired with;
generic-relevance filler is treated as a defect, not a placeholder. The engine's
generic `growth_stage`/milestone "capital block" 3D-motion template was removed
for producing meaningless pillar visuals with no real financial mechanism behind
them (`tools/k70_scene_engine/blender/_motion_graphics_3d_script.py`) — 3D Motion
Graphics shots now require a real semantic visualization (money flow, balance
sheet, network/flow diagram) or the beat must be reclassified to a different
shot type instead of falling back to a generic shape.

## Phase map
- **P1** skeleton + schemas + infra ✅ (this repo)
- **P2** Director engine (`app/director/`) — structured tool-use + repair loop
- **P2A** Gemini finance trend intelligence (`app/topic_intelligence/`) ✅ — topic selection
- **P3** pipeline hardening (`app/pipeline/`) — manim templates, music, effects
- **P4** Next.js dashboard (`apps/web/`)
- **P5** upload adapters (`app/uploaders/`)
- **P6** scale: batching, cost ceilings, dedup, schedule
