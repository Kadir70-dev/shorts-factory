# Visual Engine (Phase 2.5) — retention upgrade

Motion-first overhaul of the Remotion layer **only**. No FastAPI / Director /
SceneGraph / pipeline changes. Everything is derived from existing SceneGraph
fields and is frame-deterministic (Remotion `random(seed)`), transform-based, and
blur-light so it renders fast in headless Chromium.

Critical invariant: **scenes stay sequential (no overlapping transitions)** so the
voiceover + caption master timeline never desyncs. All "transitions" are
entrance animations inside each scene's own window.

## What each piece does
| File | Upgrade |
|---|---|
| `anim.ts` | Deterministic core: `kenBurns` (continuous pan+zoom), `punch` (metronome + speech-beat zoom bumps), `emphasisOf`, `bounceIn` |
| `components/AnimatedBackground.tsx` | Solid scenes get a rotating gradient + 2 drifting glows + 22 particles + vignette (no flat color) |
| `components/VisualLayer.tsx` | Always-moving Ken Burns + speech-driven punch zoom; manim charts dampened for legibility; readability scrim over footage |
| `components/Captions.tsx` | Hormozi: 92–104px, word-by-word bounce, active-word highlight box, emphasis (numbers/$/%) accent + extra scale, center-safe |
| `components/OverlayLayer.tsx` | Kinetic typography (staggered word entrance + float), stat **count-up** with accent flash, exit fade, hook intensity |
| `components/SceneEnter.tsx` | Per-scene entrance mapped from `transition_in`: whip(whoosh+blur streak) / slide / cut(snap) / fade(zoom) + exit fade |
| `components/SfxLayer.tsx` | Schedules the pre-computed `graph.sfx` cue list (no heuristics here). See Phase 4.5 below. |

## Tuning knobs
- Punch intensity / cadence: `anim.ts` `punch()` (period, window, bump size).
- Ken Burns range: `anim.ts` `kenBurns()` variants (min scale 1.10 keeps edges safe).
- Caption size/colors: `Captions.tsx` (`HIGHLIGHT`, `EMPHASIS`, `baseSize`).
- Per-niche accent: `compositions/Short.tsx` `ACCENT`.

---

# Phase 4.5 — Premium documentary engine

Two upgrades that span the pipeline (not Remotion-only), all schema-driven.

## 1. Micro-editing / retention SFX (`api/app/pipeline/sfx.py`)
The sound design is **computed once in Python** and shared by BOTH renderers via
a new contract field `SceneGraph.sfx` (`SfxCue[]`; SCHEMA_VERSION 1.3).

- `ensure_pack()` synthesizes an 8-piece palette with ffmpeg →
  `data/assets/sfx/{whoosh,pop,ring,bell,hit,bass,riser,swipe}.wav` (no external
  samples; generated once). A missing file just doesn't play.
- `build_cues(graph)` is the **restrained documentary micro-editor** — emphasis
  moments ONLY, never per word, never on plain cuts:
  - HOOK → deep `bass` impact on reveal (strongest sound design)
  - big stat/number → subtle `hit` + `ring`
  - real section transition (`fade`→`whoosh`, `whip`/`slide_l`→`swipe`) — plain
    cuts stay silent
  - CTA → subtle `riser` building in
- `SfxLayer.tsx` (Remotion) and `render_ffmpeg._mux` (ffmpeg) both just SCHEDULE
  `graph.sfx`. Gains sit well under the VO; `pop`/`bell` are in the palette for
  future/Director use but the auto-editor stays sparse.

## 2. Audio ducking
`AudioTrack.duck_music` / `duck_amount_db`. ffmpeg path sidechain-compresses the
music keyed to the VO so narration always cuts through; Remotion (no realtime
sidechain) applies a static extra dip while VO is present.

## 3. Hybrid visual engine (`api/app/pipeline/broll.py`)
Resolver priority: **Pexels video → Pixabay video → AI cinematic insert (1–3s,
eligible beats only) → real photo (Ken Burns) → animated gradient.** AI is used
SELECTIVELY — only `visual.type: "ai_video"` (Director-flagged recreation /
impossible shot) or `scene_visual_type: "abstract"` (concept/metaphor), and only
when `spec.allow_ai_video` + a provider key are set. Providers stay gated stubs
(`providers.ai_video_generate` → veo3/seedance) that fall through to real footage
until wired. Realism preferred; AI is seasoning, never the whole video.

## Per-niche accent
`compositions/Short.tsx` `ACCENT` — all 6 K70 niches mapped.

---

# Phase 5 — Premium documentary music system

The emotional cinematic layer (`api/app/pipeline/music.py`). Schema-driven like
SFX; SCHEMA_VERSION 1.4 adds `AudioTrack.music_envelope` (`MusicKeyframe[]`),
`music_mood`, `music_fade_in_sec`, `music_fade_out_sec`.

## Per-niche scoring presets
Each K70 bucket gets a mood + synthesized bed + level shape:
- FACTS → `curiosity` (subtle curiosity, light tension)
- HISTORY → `dark` (cinematic dark ambience, mystery/suspense)
- POLITICS/ELECTIONS → `newsroom` (urgent but serious)
- ECONOMY → `finance` (Bloomberg financial tension)
- BUSINESS → `business` (premium intelligent tech)

## Copyright-safe beds
`ensure_beds()` synthesizes ambient pads (detuned sine chords + lowpass +
tremolo + aecho) with ffmpeg → `data/assets/music/beds/<mood>.wav` (46s, no
licensed tracks). Drop a royalty-free track in a channel's `music_dir` and it
wins over the synth bed.

## Smart timeline envelope
`build_envelope()` reads scene roles → a `MusicKeyframe` curve: **hook** stronger
emotional entry, **middle** low/subtle under narration, **reveal** (stat beats)
tension rise, **CTA** soft uplift. Keyframes HOLD within a scene and RAMP at
boundaries (smooth swells, never abrupt cuts). Both renderers apply it:
- ffmpeg `_mux`: piecewise-linear `volume=volume=<expr>:eval=frame` (escaped
  commas) + top/tail `afade`, then sidechain-ducked under the VO.
- Remotion `Short.tsx`: `musicVolume()` interpolates the dB envelope per frame
  (+ static duck) × a fade factor.

## Audio doctrine
Narration ALWAYS dominant — low envelope levels (−16…−24 dB) + sidechain ducking
+ smooth fades. Documentary only; never meme/TikTok. Pipeline order: assets →
**music** → sfx → render.

---

# Phase 5.5 — Cinematic AI Visual Layer

Turns K70 from "real footage + occasional AI" into a **premium documentary**
look, by making the AI imagery a first-class, automatically-placed layer — while
keeping real footage the majority. SCHEMA_VERSION 1.5 adds `Visual.type:
"ai_image"`, plus render-irrelevant `Visual.strategy` / `Visual.decision_reason`
(the decision engine's verdict, surfaced in metadata + verification).

## Smart Scene Decision Engine (`api/app/pipeline/scene_director.py`)
A PURE, deterministic function `decide(graph, spec)` that assigns EVERY scene one
visual strategy and enforces the visual-mix budget:

  A `real` · B `ai_image` · C `ai_video` · D `motion_gfx` · E `hybrid`

- SUBJECT ELIGIBILITY: AI is used for HISTORY (recreations, presidents,
  scandals, old newspapers, White House mood), POLITICS (symbolic/dramatic
  election imagery, red-vs-blue, campaign tension), BUSINESS/TECH (billionaire /
  boardroom / monopoly / AI-future), and ABSTRACT concepts (inflation fear,
  broken middle class, hidden systems, money psychology). Everyday realism —
  restaurants, grocery, gas stations, normal streets, voting lines, crowds — is
  a HARD veto → real footage (AI there reads as uncanny slop).
- MIX BUDGET: real 60–70% · ai_video 15–20% · ai_image 10–15% · motion_gfx
  5–10%. The ratio becomes integer caps for the scene count; AI slots go to the
  highest-affinity eligible beats. When AI video is OFF (cost gate), the image
  slot ABSORBS the video budget so combined AI still lands ~25–35% (vital for
  history recreations). Charts are always motion graphics.

## AI image generation (`api/app/pipeline/providers.py`)  — Phase 5.6: Google only
`ai_image_generate()` chain (NO OpenAI): **Google AI Studio** (`GOOGLE_API_KEY`,
`gemini-2.5-flash-image` → `imagen-4.0-generate-001`) PRIMARY → **Pollinations**
(free, no key, `flux`) FALLBACK → real footage. Pollinations calls are serialized
(`_POLLI_LOCK`) and retried with backoff to respect its 1-concurrent free tier; a
free `POLLINATIONS_TOKEN` lifts the limit. Results are
content-addressed by prompt hash (generated once, reused free). Quality rules
(cinematic, documentary realism, dramatic lighting, USA, no text/uncanny faces)
are baked into the prompt. It logs `[ai-image] sN: …` showing exactly where a
Google image was inserted, or why it fell back. **Mix is now 70% real / 20% AI
image / 10% motion-graphics, no AI video.**

> ⚠️ Google AI Studio image generation needs **billing enabled** — the free tier
> is 0 image requests (Gemini-image 429 "limit 0"; Imagen "paid plans only"). The
> wiring is correct and the key authenticates; with billing the same code inserts
> real images, otherwise each AI beat falls back to real footage (Pexels/Pixabay).
> `AI_IMAGE_DEMO=true` enables a free offline local plate for testing.

## Hybrid resolver (`api/app/pipeline/broll.py`)
The resolver acts on the chosen strategy but ALWAYS keeps a real-footage safety
net, so a missing key or a transient generation/download failure degrades to real
footage → photo → gradient; it never crashes (`_first_hit` now swallows per-term
network errors). AI stills get role-based Ken Burns / zoom / pan motion (never
static), graded + vignetted by `VisualLayer` exactly like footage.

## Render note
`ai_image` renders as a still (`<Img>` + motion) in Remotion and as a Ken-Burns
clip in the ffmpeg fallback — no renderer-specific code, it rides the existing
image path (extension/type based). Verified end-to-end via the Remotion-CLI
render (data/ mounted by `remotion.config.ts` setPublicDir): a real 1080×1920
H.264 short with AI plates on the eligible beats, real footage elsewhere, 0
gradient fallbacks. (Caveat: the bundle-once warm service can't serve per-job
assets created after boot — pre-existing; real jobs use the CLI fallback.)

## Verify
`scripts/verify_visual_layer.py` runs the engine on the 3 reference topics and
prints WHERE/WHY AI was inserted, the mix vs target, and a heuristic retention
projection (AI-on vs forced-all-real); `--render N` proves one full MP4.
