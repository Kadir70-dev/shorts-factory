/**
 * SceneGraph (Zod) — MIRROR of apps/api/app/schemas/scene.py.
 * Remotion validates the incoming JSON against this at composition load.
 * If you change one side, change the other and bump SCHEMA_VERSION.
 */
import { z } from "zod";

export const SCHEMA_VERSION = "1.5";

export const Visual = z.object({
  type: z
    .enum(["broll", "ai_video", "ai_image", "manim", "dataviz", "motion_gfx",
           "threejs", "branded", "image", "solid"])
    .default("broll"),
  query: z.string().default(""),
  // B-roll engine fields (Director-authored visual intent). Remotion ignores
  // them at render time — the asset resolver consumes them — but they must be
  // accepted so the props validate.
  broll_keywords: z.array(z.string()).default([]),
  visual_intent: z.string().default(""),
  scene_visual_type: z
    .enum(["real_footage", "data_viz", "dramatic", "subtle", "abstract"])
    .default("real_footage"),
  asset_path: z.string().nullable().default(null),
  motion: z
    .enum(["none", "ken_burns", "zoom_in", "zoom_out", "pan_lr"])
    .default("ken_burns"),
  fallback_color: z.string().default("#0a0a0a"),
  // Smart Scene Decision Engine (Phase 5.5) — render-irrelevant; the asset
  // resolver consumes these. Accepted so props validate.
  strategy: z
    .enum(["dataviz", "real", "ai_image", "ai_video", "motion_gfx", "branded", "hybrid"])
    .default("real"),
  decision_reason: z.string().default(""),
});

export const Overlay = z.object({
  type: z.enum(["headline", "lower_third", "stat", "ticker", "quote", "source"]),
  text: z.string(),
  sub: z.string().nullable().default(null),
  y: z.number().min(0).max(1).default(0.18),
  emphasis: z.enum(["normal", "alert", "positive", "negative"]).default("normal"),
});

export const Scene = z.object({
  id: z.string(),
  narration: z.string(),
  duration_sec: z.number().min(0.8).max(12),
  visual: Visual.default({}),
  overlays: z.array(Overlay).default([]),
  transition_in: z.enum(["cut", "fade", "slide_l", "whip", "dip_to_black",
                         "push_up", "crossfade"]).default("cut"),
  keywords: z.array(z.string()).default([]),
  // factual reliability label (see scene.py). Remotion uses it to tag forecasts.
  confidence: z.enum(["confirmed", "probable", "speculative"]).default("confirmed"),
});

export const Caption = z.object({
  start: z.number(),
  end: z.number(),
  text: z.string(),
  words: z
    .array(z.object({ w: z.string(), s: z.number(), e: z.number() }))
    .default([]),
});

// One point on the smart music intensity envelope (mirror of MusicKeyframe).
export const MusicKeyframe = z.object({
  at: z.number(),
  gain_db: z.number(),
  role: z.string().default(""),
});

export const AudioTrack = z.object({
  voiceover_path: z.string().nullable().default(null),
  music_path: z.string().nullable().default(null),
  music_gain_db: z.number().default(-18),
  voiceover_gain_db: z.number().default(0),
  duck_music: z.boolean().default(true),
  duck_amount_db: z.number().default(-9),
  music_mood: z.string().default(""),
  music_envelope: z.array(MusicKeyframe).default([]),
  music_fade_in_sec: z.number().default(1.5),
  music_fade_out_sec: z.number().default(2.0),
});

// SFX — timeline-triggered retention sound design. Computed by the pipeline's
// sound-design stage (mirror of SfxCue in scene.py). Files: assets/sfx/<sound>.wav
export const SfxCue = z.object({
  sound: z.enum(["whoosh", "pop", "ring", "bell", "hit", "bass", "riser", "swipe"]),
  at: z.number(),
  gain_db: z.number().default(-12),
  role: z.string().default(""),
});

// keep version constant in lockstep with apps/api/app/schemas/scene.py
export const SceneMeta = z.object({
  video_id: z.string(),
  channel_id: z.string(),
  niche: z.string(),
  title: z.string(),
  hook: z.string(),
  description: z.string().default(""),
  tags: z.array(z.string()).default([]),
  hashtags: z.array(z.string()).default([]),
  thumbnail_text: z.string().default(""),
});

export const SceneGraph = z.object({
  schema_version: z.string().default(SCHEMA_VERSION),
  meta: SceneMeta,
  fps: z.number().default(30),
  width: z.number().default(1080),
  height: z.number().default(1920),
  scenes: z.array(Scene),
  audio: AudioTrack.default({}),
  captions: z.array(Caption).default([]),
  sfx: z.array(SfxCue).default([]),
  threejs_provenance: z.array(z.object({
    scene_id: z.string(), storyboard_scene_id: z.string(), template: z.string(),
    template_version: z.string(), status: z.string(), render_path: z.string().nullable(),
    cache_key: z.string(), seed: z.number(), fps: z.number(), width: z.number(),
    height: z.number(), quality: z.string(), brand_id: z.string(),
    brand_fingerprint: z.string(), render_ms: z.number(), peak_rss_mb: z.number(),
    error: z.string(), legacy_decision: z.string(),
  })).default([]),
  motion_graphics_provenance: z.array(z.object({
    scene_id: z.string(), storyboard_scene_id: z.string(), template: z.string(),
    template_version: z.string(), status: z.string(), render_path: z.string().nullable(),
    cache_key: z.string(), seed: z.number(), fps: z.number(), width: z.number(),
    height: z.number(), quality: z.string(), brand_id: z.string(),
    brand_fingerprint: z.string(), render_ms: z.number(), peak_rss_mb: z.number(),
    error: z.string(), existing_decision: z.string(), clarity_reason: z.string(),
  })).default([]),
  ai_broll_provenance: z.array(z.object({
    scene_id: z.string(), storyboard_scene_id: z.string(), status: z.string(),
    provider: z.string(), model: z.string(), asset_type: z.string(),
    synthetic: z.boolean(), render_path: z.string().nullable(), cache_key: z.string(),
    prompt_spec: z.record(z.string(), z.unknown()), quality: z.string(),
    prompt_generation_ms: z.number(), provider_dispatch_ms: z.number(),
    peak_rss_mb: z.number(), error: z.string(), selection_reason: z.string(),
  })).default([]),
});

export type TSceneGraph = z.infer<typeof SceneGraph>;
export type TScene = z.infer<typeof Scene>;
export type TCaption = z.infer<typeof Caption>;
