import React from "react";
import {
  AbsoluteFill, Easing, Img, interpolate, OffthreadVideo, staticFile,
  useCurrentFrame, useVideoConfig,
} from "remotion";
import { z } from "zod";
import { Scene } from "../schemas/scene";
import { Beat, cameraFor, punch, seedOf } from "../anim";
import { AnimatedBackground } from "./AnimatedBackground";

const rel = (p: string) => p.replace(/^.*\/data\//, "");

/**
 * Motion-first visual. ALWAYS moving (no static frame): continuous Ken Burns
 * pan+zoom layered with a speech-driven punch zoom. Solid scenes render the
 * AnimatedBackground instead of a flat fill. Manim charts get a gentler push so
 * the data stays readable. Footage gets a cinematic grade + vignette for a
 * premium documentary look; the HOOK adds a stronger first-frame push-in.
 */
export const VisualLayer: React.FC<{
  scene: z.infer<typeof Scene>;
  beats: Beat[];
  accent: string;
  tempo?: number;   // section rhythm: scales punch strength (hook 1.0, middle 0.6, CTA 0.8)
  hook?: boolean;   // first scene: stronger first-frame treatment
}> = ({ scene, beats, accent, tempo = 1, hook = false }) => {
  const v = scene.visual;
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const durFrames = Math.round(scene.duration_sec * fps);

  // motion the asset resolver chose for this shot (zoom/pan for stills, Ken
  // Burns for footage); manim charts always get the gentle seeded drift.
  const motion = v.type === "manim" ? "ken_burns" : v.motion;
  const kb = cameraFor(motion, frame, durFrames, seedOf(scene.id));
  // charts must stay legible -> dampen punch; footage/photos get the full bump.
  // `tempo` further softens the punch through the calmer middle of the video.
  const damp = (v.type === "manim" ? 0.4 : 1) * tempo;
  const p = 1 + (punch(frame, fps, beats) - 1) * damp;
  // hook: a quick first-frame push-in (~0.5s) so the open hits harder.
  const hookPunch = hook
    ? interpolate(frame, [0, fps * 0.5], [1.07, 1], {
        extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.out(Easing.cubic),
      })
    : 1;
  const scale = kb.scale * p * hookPunch;
  const transform = `translate(${kb.x}%, ${kb.y}%) scale(${scale})`;

  if (!v.asset_path || v.type === "solid") {
    return (
      <AbsoluteFill style={{ overflow: "hidden" }}>
        <AbsoluteFill style={{ transform, willChange: "transform" }}>
          <AnimatedBackground color={v.fallback_color} accent={accent} seed={seedOf(scene.id)} />
        </AbsoluteFill>
        <FilmGrain frame={frame} />
        <AbsoluteFill style={{ background: vignette(hook) }} />
      </AbsoluteFill>
    );
  }

  const isVideo = v.type === "broll" || v.type === "ai_video" || v.type === "manim";
  const src = staticFile(rel(v.asset_path));

  return (
    <AbsoluteFill style={{ overflow: "hidden", backgroundColor: "#000" }}>
      {/* cinematic grade — contrast + crushed blacks + restrained saturation
          reads as "graded footage" rather than flat stock (Vox/Bloomberg). */}
      <AbsoluteFill style={{ transform, willChange: "transform", filter: GRADE }}>
        {isVideo ? (
          <OffthreadVideo src={src} muted style={cover} />
        ) : (
          <Img src={src} style={cover} />
        )}
      </AbsoluteFill>
      {/* readability scrim so captions/overlays always pop over footage */}
      <AbsoluteFill
        style={{ background: "linear-gradient(180deg, rgba(0,0,0,0.34) 0%, transparent 26%, transparent 58%, rgba(0,0,0,0.6) 100%)" }}
      />
      {/* tiny film grain — premium texture, no blur/GPU cost */}
      <FilmGrain frame={frame} />
      {/* cinematic vignette — a touch stronger on the hook for urgency */}
      <AbsoluteFill style={{ background: vignette(hook) }} />
    </AbsoluteFill>
  );
};

const cover: React.CSSProperties = { width: "100%", height: "100%", objectFit: "cover" };
// SOFTER cinematic grade — gentle contrast, restrained saturation, a hair lifted
// for a filmic matte (Netflix/Vox documentary), not a punchy TikTok edit.
const GRADE = "contrast(1.04) saturate(1.0) brightness(0.98)";
const vignette = (hook: boolean) =>
  `radial-gradient(74% 66% at 50% 44%, transparent 54%, rgba(0,0,0,${hook ? 0.5 : 0.4}) 100%)`;

// Static SVG noise tile (rasterised once, then just repositioned per frame).
const GRAIN =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='140' height='140'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E\")";

/** Subtle film grain. Cheap by design: the noise is a cached background image;
 *  each frame only nudges its position so it shimmers like real grain. No blur,
 *  no per-pixel filters, no GPU effects — render speed is unaffected. */
const FilmGrain: React.FC<{ frame: number }> = ({ frame }) => (
  <AbsoluteFill
    style={{
      backgroundImage: GRAIN,
      backgroundSize: "180px 180px",
      backgroundPosition: `${(frame * 41) % 140}px ${(frame * 23) % 140}px`,
      opacity: 0.05,                 // subtler — texture, not noise
      mixBlendMode: "overlay",
      pointerEvents: "none",
    }}
  />
);
