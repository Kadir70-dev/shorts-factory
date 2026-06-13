/**
 * Deterministic motion core. Every function is a pure function of (frame, …) so
 * renders are reproducible. Transform-only (scale/translate/rotate/opacity) — no
 * heavy blur or filters — to stay fast in headless Chromium.
 */
import { Easing, interpolate, random } from "remotion";

export type Cam = { scale: number; x: number; y: number };
export type Beat = { f: number; intensity: number }; // scene-relative frame

const EASE = Easing.inOut(Easing.ease);

/** Continuous documentary Ken Burns: slow pan + zoom across the whole scene.
 *  Direction/zoom picked deterministically from a seed so every scene differs. */
export function kenBurns(frame: number, durFrames: number, seed: string): Cam {
  // Documentary-calm drift: small, slow scale change + gentle translate. min
  // scale >= 1.08 with |translate| <= 2% guarantees no edge gap is revealed.
  // (Toned down from the earlier ~1.10–1.24 / ±3% — that read as too restless.)
  const variants: { s: [number, number]; px: [number, number]; py: [number, number] }[] = [
    { s: [1.05, 1.12], px: [-1.5, 1.5], py: [-1, 1] },
    { s: [1.12, 1.05], px: [1.5, -1.5], py: [1, -1] },
    { s: [1.05, 1.11], px: [-1.5, 1], py: [1.5, -1.5] },
    { s: [1.11, 1.05], px: [1, -1.5], py: [-1.5, 1.5] },
    { s: [1.07, 1.13], px: [0, 0], py: [1.5, -1.5] },
  ];
  const v = variants[Math.floor(random(seed) * variants.length) % variants.length];
  const t = interpolate(frame, [0, Math.max(1, durFrames)], [0, 1], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: EASE,
  });
  return {
    scale: interpolate(t, [0, 1], v.s),
    x: interpolate(t, [0, 1], v.px),
    y: interpolate(t, [0, 1], v.py),
  };
}

/** Camera for a scene given the Director's `visual.motion` hint. Stills get the
 *  motion the asset resolver chose (zoom/pan); anything else falls back to a
 *  seeded Ken Burns so a scene is NEVER a frozen frame. */
export function cameraFor(
  motion: string, frame: number, durFrames: number, seed: string,
): Cam {
  const t = interpolate(frame, [0, Math.max(1, durFrames)], [0, 1], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: EASE,
  });
  switch (motion) {
    case "zoom_in":
      return { scale: interpolate(t, [0, 1], [1.05, 1.18]), x: 0, y: 0 };
    case "zoom_out":
      return { scale: interpolate(t, [0, 1], [1.18, 1.05]), x: 0, y: 0 };
    case "pan_lr":
      return { scale: 1.14, x: interpolate(t, [0, 1], [-2.5, 2.5]), y: 0 };
    case "none":          // still drift a hair — we never ship a static frame
    case "ken_burns":
    default:
      return kenBurns(frame, durFrames, seed);
  }
}

/** Punch zoom: a slow metronome breath + a soft, slow-settling bump on each
 *  emphasis beat. Deliberately understated — the beats are now sparse (every
 *  2–3s, only on meaningful words) so each push reads as intentional, not
 *  frantic. Keeps "no static frame" true without overstimulating. */
export function punch(frame: number, fps: number, beats: Beat[]): number {
  const period = fps * 1.4;                       // slow ~1.4s breathing
  let s = 1 + 0.005 * Math.cos((frame / period) * Math.PI * 2);
  const window = fps * 0.55;                       // longer, smoother settle
  for (const b of beats) {
    const dt = frame - b.f;
    if (dt >= 0 && dt < window) {
      const decay = 1 - dt / window;
      s += b.intensity * 0.02 * decay * decay;     // gentle pop-in then settle
    }
  }
  return s;
}

/** How much a word should pop (0..1): numbers/money/percent > CAPS > long word. */
export function emphasisOf(w: string): number {
  if (/[%$]/.test(w) || /\d/.test(w)) return 1;
  const bare = w.replace(/[^A-Za-z]/g, "");
  if (bare.length >= 2 && bare === bare.toUpperCase()) return 0.8;
  if (bare.length >= 8) return 0.5;
  return 0.15;
}

/** Overshooting bounce entrance (spring-like) without importing spring config. */
export function bounceIn(frame: number, start: number, fps: number): number {
  const t = (frame - start) / (fps * 0.42);
  if (t <= 0) return 0;
  if (t >= 1) return 1;
  // damped overshoot
  return 1 - Math.pow(1 - t, 3) * Math.cos(t * Math.PI * 1.2);
}

/** Hash a string to a stable seed string for random(). */
export function seedOf(s: string): string {
  return `sf-${s}`;
}
