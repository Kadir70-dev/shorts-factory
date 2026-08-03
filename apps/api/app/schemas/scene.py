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
from pydantic import BaseModel, Field, model_validator

SCHEMA_VERSION = "2.0"


# --------------------------------------------------------------------------- #
# DataViz — a REAL animated data visualisation for a beat that states a figure.
#
# The old pipeline paired numbers with random stock footage and had a Manim
# template stuffed with placeholder values ([2.1, 2.4, 2.9] regardless of topic),
# which is worse than no chart: it renders a confident-looking graph of numbers
# nobody asserted. This model makes the data EXPLICIT and Director-authored, so
# what animates on screen is exactly what the narration claims and what the
# `source` overlay attributes.
#
# `pipeline/dataviz.py` renders these locally with numpy + ffmpeg — no Manim, no
# network, no placeholder data. A beat with no usable figure simply gets no
# chart; it never gets an invented one.
# --------------------------------------------------------------------------- #
class DataPoint(BaseModel):
    label: str                        # "2019", "Costco", "Before" — the x axis
    value: float
    # colour role; `auto` lets the renderer infer up/down from the series
    emphasis: Literal["auto", "normal", "primary", "positive", "negative"] = "auto"


class DataViz(BaseModel):
    kind: Literal[
        "counter",       # one hero figure, rolled up from zero
        "bar_compare",   # 2–6 categories side by side
        "line_trend",    # a time series drawing left-to-right
        "delta",         # before → after, with the change between them
        "donut",         # one share of a whole
        "meter",         # a percentage as a filling bar
    ] = "counter"
    title: str = ""                   # what the number measures
    points: list[DataPoint] = []
    prefix: str = ""                  # "$"
    suffix: str = ""                  # "%", " jobs", "bps"
    decimals: int = Field(1, ge=0, le=3)
    abbreviate: bool = True           # 1_200_000_000 → "1.2B"
    highlight: int = -1               # index that carries the emphasis (-1 = last)
    source: str = ""                  # attribution burned under the chart
    note: str = ""                    # one short clarifying line

    def valid(self) -> bool:
        """A chart is only worth rendering when it has real numbers behind it."""
        if not self.points:
            return False
        if self.kind in ("counter", "meter", "donut"):
            return len(self.points) >= 1
        if self.kind == "delta":
            return len(self.points) >= 2
        return len(self.points) >= 2


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
    #   dataviz  = locally-rendered BRANDED animated chart driven by real numbers
    #   motion_gfx = kinetic typography over a live branded field
    #   branded  = a branded plate (the floor, instead of unrelated stock)
    #   manim    = legacy chart path (only used when manim is installed AND the
    #              beat carries real data; `dataviz` supersedes it)
    #   image    = real stock photo (gets Ken Burns motion)
    #   solid    = flat-colour last resort
    type: Literal[
        "broll", "ai_video", "ai_image", "dataviz", "motion_gfx", "threejs", "branded",
        "manim", "image", "solid"
    ] = "broll"
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
    # Ladder order (see pipeline/scene_director.py):
    #   dataviz    — the beat states a real figure → branded animated chart
    #   real       — SUBJECT-SPECIFIC footage of the exact thing named
    #   ai_image   — AI recreation of that exact subject (no camera could have)
    #   motion_gfx — kinetic typography: the claim itself, moving, on brand
    #   branded    — a branded plate; the floor, instead of unrelated stock
    #   hybrid     — a base visual composited with on-screen graphics
    #   ai_video   — opt-in cinematic motion insert
    strategy: Literal[
        "dataviz", "real", "ai_image", "ai_video", "motion_gfx", "branded",
        "hybrid"
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
    # Real numbers for THIS beat. When present and valid, the beat renders as a
    # branded animated chart instead of borrowing a stock clip — the "every
    # important number gets a custom visualisation" rule.
    data: Optional[DataViz] = None
    # The narrative role this beat plays in the chosen story structure (hook,
    # tension, evidence, reveal, cta, …). Set by the Director from the structure
    # block; drives the music envelope, sound design and visual strategy.
    beat_role: str = ""
    transition_in: Literal[
        "cut", "fade", "slide_l", "whip", "dip_to_black", "push_up", "crossfade"
    ] = "cut"
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

    # --- storytelling ------------------------------------------------------- #
    # Which narrative spine this short was built on (config/story_structures.yaml).
    # Recorded so the rotation is auditable and a render is reproducible.
    structure_id: str = ""

    # --- compliance (pipeline/compliance.py) -------------------------------- #
    # The educational disclaimer burned into the video AND prepended to the
    # description. Set by the compliance stage.
    disclaimer: str = ""
    # Every automatic rewrite the safety pass made, so the artifact explains itself
    # during review instead of silently changing the script.
    compliance_notes: list[str] = []
    # YouTube "Altered or Synthetic Content": true when the finished video contains
    # realistic AI-generated people, places or events a viewer could mistake for
    # real. The pipeline cannot tick that box for you — it flags it loudly.
    requires_ai_disclosure: bool = False
    ai_disclosure_reasons: list[str] = []


# --------------------------------------------------------------------------- #
# Storyboard — semantic beat metadata produced after Visual Intelligence.
# It is advisory structured data only: renderers and asset providers remain the
# owners of pixels and files. `None` means the gated engine did not run.
# --------------------------------------------------------------------------- #
class StoryboardScene(BaseModel):
    scene_id: str
    source_scene_id: str
    narration: str
    duration_estimate: float = Field(ge=0.8, le=12.0)
    visual_objective: str
    primary_entity: str = ""
    secondary_entities: list[str] = []
    company: str = ""
    location: str = ""
    year: Optional[int] = Field(None, ge=1000, le=2200)
    financial_numbers: list[str] = []
    emotion: Literal[
        "urgent", "curious", "tense", "surprising", "confident", "neutral",
        "hopeful", "cautionary",
    ] = "neutral"
    recommended_visual_type: Literal[
        "dataviz", "real", "ai_image", "ai_video", "motion_gfx", "branded",
        "hybrid",
    ]
    recommended_camera_movement: Literal[
        "none", "ken_burns", "zoom_in", "zoom_out", "pan_lr",
    ] = "ken_burns"
    motion_graphics_needed: bool = False
    threejs_candidate: bool = False
    ai_broll_candidate: bool = False
    asset_priority: list[Literal[
        "exact_footage", "licensed_image", "local_graphics", "ai_recreation",
        "branded_fallback",
    ]]
    transition: Literal[
        "cut", "fade", "slide_l", "whip", "dip_to_black", "push_up", "crossfade",
    ] = "cut"
    overlay_text: list[str] = []
    visual_confidence_score: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_required_content(self):
        if not self.scene_id.strip() or not self.source_scene_id.strip():
            raise ValueError("storyboard scene ids cannot be blank")
        if not self.narration.strip():
            raise ValueError("storyboard narration cannot be blank")
        if not self.visual_objective.strip():
            raise ValueError("storyboard visual objective cannot be blank")
        if not self.asset_priority:
            raise ValueError("storyboard asset_priority cannot be empty")
        if len(self.asset_priority) != len(set(self.asset_priority)):
            raise ValueError("storyboard asset_priority must not contain duplicates")
        return self


class StoryboardData(BaseModel):
    version: str = "1.0"
    scenes: list[StoryboardScene]

    @model_validator(mode="after")
    def validate_scene_ids(self):
        ids = [scene.scene_id for scene in self.scenes]
        if not ids:
            raise ValueError("storyboard must contain at least one semantic beat")
        if len(ids) != len(set(ids)):
            raise ValueError("storyboard scene ids must be unique")
        return self


class AssetCandidate(BaseModel):
    """Auditable asset considered for one semantic storyboard beat."""
    source_url: str
    provider_institution: str
    asset_type: Literal["video", "image", "document", "ai_request"]
    license: str
    commercial_use_status: Literal["allowed", "prohibited", "unclear"]
    attribution_requirement: str = ""
    retrieval_date: str
    scene_id: str
    local_cache_path: Optional[str] = None
    relevance_score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    synthetic_status: Literal["no", "yes", "requested"] = "no"
    subject_specificity: float = Field(0.5, ge=0.0, le=1.0)
    visual_quality: float = Field(0.5, ge=0.0, le=1.0)
    originality: float = Field(0.5, ge=0.0, le=1.0)
    mobile_readability: float = Field(0.5, ge=0.0, le=1.0)


class AssetResolution(BaseModel):
    scene_id: str
    query: str
    status: Literal["resolved", "ai_requested", "manual_review"]
    selected_source_url: Optional[str] = None
    candidates: list[AssetCandidate] = []
    legacy_query: str = ""
    comparison: str = ""


class ThreeJSRenderProvenance(BaseModel):
    scene_id: str
    storyboard_scene_id: str
    template: Literal[
        "number_counter", "comparison_towers", "share_ownership",
        "dividend_cashflow", "timeline_flythrough", "compound_growth",
    ]
    template_version: str
    status: Literal["rendered", "cache_hit", "unresolved"]
    render_path: Optional[str] = None
    cache_key: str
    seed: int
    fps: Literal[30, 60]
    width: int
    height: int
    quality: Literal["preview", "final"]
    brand_id: str
    brand_fingerprint: str
    render_ms: float = Field(ge=0)
    peak_rss_mb: float = Field(ge=0)
    error: str = ""
    legacy_decision: str = ""


class MotionGraphicsRenderProvenance(BaseModel):
    scene_id: str
    storyboard_scene_id: str
    template: Literal[
        "stat_card", "bar_chart_comparison", "percentage_split",
        "timeline_events", "before_after", "revenue_profit_waterfall",
        "price_inflation", "document_highlight", "quote_card",
        "company_ecosystem",
    ]
    template_version: str
    status: Literal["rendered", "cache_hit", "unresolved"]
    render_path: Optional[str] = None
    cache_key: str
    seed: int
    fps: int
    width: int
    height: int
    quality: Literal["preview", "final"]
    brand_id: str
    brand_fingerprint: str
    render_ms: float = Field(ge=0)
    peak_rss_mb: float = Field(ge=0)
    error: str = ""
    existing_decision: str = ""
    clarity_reason: str = ""


class AICinematicSpec(BaseModel):
    cinematic_prompt: str
    negative_prompt: str
    camera_angle: str
    focal_length: str
    lighting: str
    color_palette: list[str]
    composition: str
    movement: str
    mood: str
    realism_level: Literal["photorealistic", "stylized_documentary"]
    continuity_seed: int
    brand_style: str
    duration: float = Field(gt=0, le=12)
    aspect_ratio: Literal["9:16"] = "9:16"


class AIBrollRenderProvenance(BaseModel):
    scene_id: str
    storyboard_scene_id: str
    status: Literal["rendered", "cache_hit", "unresolved", "rejected"]
    provider: str
    model: str
    asset_type: Literal["image", "video"]
    synthetic: bool = True
    render_path: Optional[str] = None
    cache_key: str
    prompt_spec: AICinematicSpec
    quality: Literal["preview", "final"]
    prompt_generation_ms: float = Field(ge=0)
    provider_dispatch_ms: float = Field(ge=0)
    peak_rss_mb: float = Field(ge=0)
    error: str = ""
    selection_reason: str = ""


class BrandIdentityProvenance(BaseModel):
    brand_id: str
    brand_fingerprint: str
    manager_version: str
    enabled: bool = True
    modules: list[str] = []
    palette: dict[str, str] = {}
    fonts: dict[str, str] = {}
    safe_margins: dict[str, float] = {}
    consistency_checks: dict[str, bool] = {}


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
    # Optional Phase 2 output. Disabled production graphs keep this as None.
    storyboard: Optional[StoryboardData] = None
    # Phase 3 output; empty when the feature gate is disabled.
    asset_provenance: list[AssetResolution] = []
    # Phase 4 output; empty when its feature gate is disabled.
    threejs_provenance: list[ThreeJSRenderProvenance] = []
    # Phase 5 output; empty when its feature gate is disabled.
    motion_graphics_provenance: list[MotionGraphicsRenderProvenance] = []
    # Phase 6 output; empty when its feature gate is disabled.
    ai_broll_provenance: list[AIBrollRenderProvenance] = []
    # Phase 7 central brand receipt; absent when the feature gate is disabled.
    brand_identity_provenance: Optional[BrandIdentityProvenance] = None

    # The per-video VARIETY PLAN (pipeline/variety.py): which caption animation,
    # transition palette, motion style, colour grade and CTA shape this short
    # drew. Persisted so a render is reproducible and so the anti-repeat ledger
    # can be audited against what actually shipped.
    variety: dict[str, str] = {}
    # Brand the short was rendered with (config/brand/<id>.yaml).
    brand_id: str = "k70"

    @property
    def total_duration_sec(self) -> float:
        return round(sum(s.duration_sec for s in self.scenes), 3)

    @property
    def total_frames(self) -> int:
        return int(self.total_duration_sec * self.fps)
