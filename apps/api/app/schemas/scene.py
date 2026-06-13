"""
SceneGraph — THE contract between the Claude Director and the Remotion renderer.

Design rules that make this robust:
  1. The Director emits NARRATION + VISUAL INTENT, never asset URLs or exact
     pixel timings. It does not know how long TTS will take.
  2. `duration_sec` on each scene is an ESTIMATE from the Director. The pipeline
     OVERWRITES it with the real measured TTS duration before rendering.
  3. Everything Remotion needs is in this one JSON. Remotion is a pure function
     of SceneGraph -> frames. No network calls inside Remotion.
  4. Mirror of this schema lives in apps/remotion/src/schemas/scene.ts (Zod).
     Keep them in lockstep. `SCHEMA_VERSION` gates compatibility.
"""
from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field

SCHEMA_VERSION = "1.5"


# --------------------------------------------------------------------------- #
# Layer — one plane in the CPU multi-layer cinematic stack (Phase 2/3). Optional:
# a scene with an empty `layers` list renders exactly as before (single asset).
# The FFmpeg Layer Composer stacks these back-to-front; parallax = different
# zoompan rates per plane (fake depth, no GPU). Anime-first, CPU-safe.
# --------------------------------------------------------------------------- #
class Layer(BaseModel):
    # back-to-front role: background plate → subject cutout → foreground fx → ui
    role: Literal["background", "subject", "fx", "ui"] = "background"
    # how this plane is sourced
    kind: Literal["ai_image", "footage", "image", "asset", "procedural"] = "ai_image"
    prompt: str = ""                  # generation prompt (ai_image layers)
    query: str = ""                   # search/asset query (footage/asset layers)
    asset_path: Optional[str] = None  # resolved file (set during the assets stage)
    # character binding — which reusable character this layer depicts (subject layers)
    character: str = ""
    # per-layer motion + 2.5D parallax: 0 = static/far, 1 = strong near-plane drift
    motion: Literal["none", "ken_burns", "zoom_in", "zoom_out", "pan_lr"] = "ken_burns"
    parallax: float = Field(0.0, ge=0.0, le=1.0)
    # compositing: how this plane blends onto the stack below it
    blend: Literal["normal", "screen", "add", "multiply", "overlay"] = "normal"
    opacity: float = Field(1.0, ge=0.0, le=1.0)


# --------------------------------------------------------------------------- #
# Visual layer — what fills the screen behind the captions
# --------------------------------------------------------------------------- #
class Visual(BaseModel):
    # how the pipeline RESOLVED the footage (final source after the asset stage):
    #   broll    = real moving footage (Pexels/Pixabay video)
    #   ai_video = short cinematic AI video insert (veo3/seedance)
    #   ai_image = AI-generated documentary still (gets Ken Burns motion) — Phase 5.5
    #   manim    = locally-rendered chart / motion-graphic
    #   image    = real stock photo (gets Ken Burns motion)
    #   solid    = animated-gradient last resort
    type: Literal["broll", "ai_video", "ai_image", "manim", "image", "solid"] = "broll"
    # search query (pexels/pixabay) OR generation prompt (veo3/seedance)
    # OR manim scene name for type=="manim"
    query: str = ""
    # --- B-roll engine (Director-authored visual intent) ---------------------
    # ordered footage search phrases for the asset resolver. The resolver tries
    # these against Pexels/Pixabay video, then image, before any fallback.
    # e.g. ["gas station", "grocery shopping", "worried customers"]
    broll_keywords: list[str] = []
    # one line on what the viewer should SEE & FEEL this beat (resolver hint /
    # human-readable rationale). e.g. "anxious shoppers facing rising prices"
    visual_intent: str = ""
    # the editorial role of the shot — steers smart matching (motion, footage
    # ordering, fallback). real_footage is the default the Director should pick.
    scene_visual_type: Literal[
        "real_footage", "data_viz", "dramatic", "subtle", "abstract"
    ] = "real_footage"
    # filled by the asset router during the `assets` stage. None until resolved.
    asset_path: Optional[str] = None
    # ken-burns / zoom give static images life; ignored for video
    motion: Literal["none", "ken_burns", "zoom_in", "zoom_out", "pan_lr"] = "ken_burns"
    # fallback color if asset resolution fails (never ship a BLACK frame — this is
    # a visible dark slate, not near-black, so a solid safety net still reads on
    # screen and passes the Phase-4 QA non-black gate).
    fallback_color: str = "#15233a"
    # --- Smart Scene Decision Engine (Phase 5.5) -----------------------------
    # The strategy the decision engine PICKED for this beat, independent of what
    # finally resolved (a strategy can fall back). Drives the asset resolver and
    # is surfaced in metadata / verification. real = literal footage; ai_image =
    # cinematic documentary still; ai_video = AI motion insert; motion_gfx =
    # chart/animated graphics; hybrid = AI base composited with on-screen graphics.
    strategy: Literal[
        "real", "ai_image", "ai_video", "motion_gfx", "hybrid"
    ] = "real"
    # one line on WHY the engine chose this strategy (debug / verification).
    decision_reason: str = ""
    # --- CPU multi-layer cinematic stack (Phase 2/3) -------------------------
    # Optional. EMPTY by default → the scene renders as a single asset exactly as
    # before (backward compatible). When the Storyboard Agent fills this, the
    # FFmpeg Layer Composer stacks the planes (background ▸ subject ▸ fx ▸ ui)
    # with per-layer parallax. Only used when LAYERED_RENDER=1.
    layers: list[Layer] = []


# --------------------------------------------------------------------------- #
# Overlays — motion-graphic elements composited ON TOP of the visual
# --------------------------------------------------------------------------- #
class Overlay(BaseModel):
    type: Literal["headline", "lower_third", "stat", "ticker", "quote", "source"]
    text: str
    # secondary line, e.g. the number under a "stat" or attribution under a quote
    sub: Optional[str] = None
    # 0..1 vertical anchor; captions own the lower third (~0.78) so keep clear
    y: float = Field(0.18, ge=0.0, le=1.0)
    emphasis: Literal["normal", "alert", "positive", "negative"] = "normal"


# --------------------------------------------------------------------------- #
# Scene — one beat of the short (typically 2.5–6s)
# --------------------------------------------------------------------------- #
class Scene(BaseModel):
    id: str                                   # "s1", "s2", ...
    # The spoken line for THIS scene. The pipeline TTS's this and measures it.
    narration: str
    # Director's estimate (chars/word heuristic). Overwritten post-TTS.
    duration_sec: float = Field(3.5, ge=0.8, le=12.0)
    visual: Visual = Visual()
    overlays: list[Overlay] = []
    transition_in: Literal["cut", "fade", "slide_l", "whip"] = "cut"
    # b-roll keywords help the router when `visual.query` is too literal
    keywords: list[str] = []
    # FACTUAL RELIABILITY — the Director's honest confidence in this beat's claim:
    #   confirmed   = a sourced, reported fact (cite it in a `source` overlay)
    #   probable    = a forecast / expectation ("economists expect", "on track")
    #   speculative = unconfirmed / opinion — MUST be hedged ("analysts warn")
    # The sanity gate enforces that the narration's language matches this label.
    confidence: Literal["confirmed", "probable", "speculative"] = "confirmed"


# --------------------------------------------------------------------------- #
# Caption — produced by Whisper.cpp AFTER voiceover, word/segment level
# --------------------------------------------------------------------------- #
class Caption(BaseModel):
    start: float          # seconds, absolute on the master timeline
    end: float
    text: str
    # word-level boxes enable karaoke-style highlight (Remotion reads these)
    words: list[dict] = []   # [{"w": "inflation", "s": 1.2, "e": 1.6}]


class MusicKeyframe(BaseModel):
    """One point on the SMART MUSIC ENVELOPE — the emotional intensity curve
    over the timeline. Computed by `pipeline/music.py` from scene roles (hook
    louder, middle low under narration, reveal rise, CTA uplift). Both renderers
    interpolate music gain LINEARLY between consecutive keyframes, so the bed
    swells and settles smoothly — never an abrupt cut."""
    at: float                         # absolute seconds on the master timeline
    gain_db: float                    # target music level at this instant
    role: str = ""                    # hook/middle/reveal/cta — debug


class AudioTrack(BaseModel):
    voiceover_path: Optional[str] = None
    music_path: Optional[str] = None
    music_gain_db: float = -18.0      # base level (used when envelope is empty)
    voiceover_gain_db: float = 0.0
    # sidechain-duck the music UNDER the narration so speech always stays clear.
    # The renderer compresses music keyed to the VO; this is how hard it dips.
    duck_music: bool = True
    duck_amount_db: float = -9.0      # extra attenuation applied while VO is loud
    # --- smart documentary music (Phase 5) -----------------------------------
    music_mood: str = ""              # per-niche preset label (debug / metadata)
    # emotional intensity curve; empty => flat `music_gain_db`. Renderers ramp
    # between keyframes for smooth swells. Ducking still applies on top.
    music_envelope: list[MusicKeyframe] = []
    music_fade_in_sec: float = 1.5    # smooth entry — never an abrupt start
    music_fade_out_sec: float = 2.0   # soft tail — never an abrupt cut


# --------------------------------------------------------------------------- #
# SFX — micro-editing / retention sound design (timeline-triggered one-shots)
# --------------------------------------------------------------------------- #
class SfxCue(BaseModel):
    """One scheduled sound effect on the master timeline. These are COMPUTED by
    the pipeline's sound-design stage (`pipeline/sfx.py`) from scene roles —
    documentary restraint, emphasis moments only — NOT authored per-word. Both
    renderers (Remotion + ffmpeg) consume this same list so sound design is
    identical across render paths. Files: data/assets/sfx/<sound>.wav."""
    # the 8-piece premium documentary SFX palette
    sound: Literal[
        "whoosh", "pop", "ring", "bell", "hit", "bass", "riser", "swipe"
    ]
    at: float                         # absolute seconds on the master timeline
    gain_db: float = -12.0            # per-cue level; well under the VO (0 dB)
    role: str = ""                    # why it fired (hook/stat/transition/cta) — debug


class SceneMeta(BaseModel):
    video_id: str
    channel_id: str
    niche: str
    title: str                        # platform title (<= ~90 chars, hooky)
    hook: str                         # first 1.5s on-screen hook text
    # upload metadata — generated by the Director in the same pass
    description: str = ""             # platform description / caption
    tags: list[str] = []             # search tags
    hashtags: list[str] = []         # ["#inflation", "#shorts", ...]
    thumbnail_text: str = ""         # 2-4 word punchy overlay for the thumbnail


class SceneGraph(BaseModel):
    """Complete, self-contained render package. Remotion's only input."""

    schema_version: str = SCHEMA_VERSION
    meta: SceneMeta
    fps: int = 30
    width: int = 1080
    height: int = 1920

    scenes: list[Scene]
    audio: AudioTrack = AudioTrack()
    captions: list[Caption] = []      # empty until captioning stage
    sfx: list[SfxCue] = []            # empty until the sound-design stage

    @property
    def total_duration_sec(self) -> float:
        return round(sum(s.duration_sec for s in self.scenes), 3)

    @property
    def total_frames(self) -> int:
        return int(self.total_duration_sec * self.fps)
