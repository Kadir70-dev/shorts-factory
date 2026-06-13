import React from "react";
import { AbsoluteFill, Audio, Series, interpolate, staticFile } from "remotion";
import { z } from "zod";
import { SceneGraph } from "../schemas/scene";
import { VisualLayer } from "../components/VisualLayer";
import { OverlayLayer } from "../components/OverlayLayer";
import { Captions } from "../components/Captions";
import { SceneEnter } from "../components/SceneEnter";
import { SfxLayer } from "../components/SfxLayer";
import { Beat, emphasisOf } from "../anim";

/**
 * Short — pure function SceneGraph -> frames. Motion-first.
 *  Layers (bottom -> top): animated visual (Ken Burns + punch zoom) wrapped in a
 *  dynamic entrance transition, kinetic overlays, Hormozi captions, audio + SFX.
 *  Scenes are laid sequentially (no overlap) so audio/captions stay in sync.
 */
const ACCENT: Record<string, string> = {
  usa_finance: "#19d27a",
  usa_election: "#ff4d4d",
  usa_politics: "#4d8cff",
  usa_facts: "#f5c518",
  usa_history: "#c0392b",
  usa_business: "#f5c518",
};

export const Short: React.FC<z.infer<typeof SceneGraph>> = (g) => {
  const fps = g.fps;
  const accent = ACCENT[g.meta.niche] ?? "#f5c518";

  // cumulative scene start time -> per-scene speech beats (scene-relative frames)
  let acc = 0;
  const starts = g.scenes.map((s) => {
    const start = acc;
    acc += s.duration_sec;
    return start;
  });
  const n = g.scenes.length;

  // Rhythm (documentary, not frantic): the HOOK runs energetic, the MIDDLE
  // settles into a slower premium cadence, and the CTA picks up slightly.
  // `tempo` scales how hard the punch zoom hits; `minGap` spaces pattern
  // interrupts so they land every ~2–3s instead of on every word.
  const tempoOf = (i: number): number => (i === 0 ? 1.0 : i === n - 1 ? 0.8 : 0.6);
  const gapOf = (i: number): number =>
    fps * (i === 0 ? 1.4 : i === n - 1 ? 2.0 : 2.6);

  // Caption mute windows (one-hero rule): captions yield whenever another
  // element owns the frame — the HOOK (big headline only) and any scene whose
  // hero is a big stat. Everywhere else, captions are the hero over footage.
  const muteRanges: [number, number][] = g.scenes
    .map((s, i): [number, number] | null =>
      i === 0 || s.overlays.some((o) => o.type === "stat" && o.sub)
        ? [starts[i], starts[i] + s.duration_sec]
        : null,
    )
    .filter((r): r is [number, number] => r !== null);

  const beatsFor = (sIdx: number): Beat[] => {
    const start = starts[sIdx];
    const end = start + g.scenes[sIdx].duration_sec;
    const minGap = gapOf(sIdx);
    const out: Beat[] = [];
    let lastF = -Infinity;
    for (const c of g.captions) {
      for (const w of c.words) {
        if (w.s < start || w.s >= end) continue;
        const e = emphasisOf(w.w);
        if (e < 0.7) continue;                     // only meaningful words (numbers / CAPS)
        const f = Math.round((w.s - start) * fps);
        if (f - lastF < minGap) continue;          // keep pattern interrupts sparse
        out.push({ f, intensity: 0.6 + e });
        lastF = f;
      }
    }
    return out;
  };

  return (
    <AbsoluteFill style={{ backgroundColor: "#000" }}>
      <Series>
        {g.scenes.map((scene, i) => {
          const durFrames = Math.round(scene.duration_sec * fps);
          return (
            <Series.Sequence key={scene.id} durationInFrames={durFrames}>
              <SceneEnter transition={scene.transition_in} durFrames={durFrames}>
                <VisualLayer scene={scene} beats={beatsFor(i)} accent={accent}
                             tempo={tempoOf(i)} hook={i === 0} />
                <OverlayLayer overlays={scene.overlays} durFrames={durFrames}
                              intense={i === 0} accent={accent} confidence={scene.confidence} />
              </SceneEnter>
            </Series.Sequence>
          );
        })}
      </Series>

      {/* captions span the whole timeline (absolute); they yield to big stats */}
      <Captions captions={g.captions} fps={fps} brand={g.meta.channel_id} muteRanges={muteRanges} />

      {/* audio — music sits UNDER the narration via the smart intensity
          envelope (hook swell → subtle middle → reveal rise → CTA uplift) with
          smooth top/tail fades. Remotion has no realtime sidechain, so the
          envelope already carries ducked levels plus a static dip while VO runs. */}
      {g.audio.voiceover_path && <Audio src={staticFile(rel(g.audio.voiceover_path))} />}
      {g.audio.music_path && (
        <Audio
          src={staticFile(rel(g.audio.music_path))}
          volume={musicVolume(g.audio, fps, Math.round(acc * fps))}
        />
      )}
      <SfxLayer graph={g} fps={fps} />
    </AbsoluteFill>
  );
};

const rel = (p: string) => p.replace(/^.*\/data\//, "");
const dbToGain = (db: number) => Math.pow(10, db / 20);

// Smooth 0..1 top/tail fade so music never starts or ends on an abrupt cut.
function fadeFactor(f: number, fiF: number, foF: number, total: number): number {
  const fin = fiF > 0 ? f / fiF : 1;
  const outStart = total - foF;
  const fout = foF > 0 && f >= outStart ? (total - f) / foF : 1;
  return Math.max(0, Math.min(1, Math.min(fin, fout)));
}

// Per-frame music volume: interpolate the dB envelope (+ static duck while VO
// plays), convert to gain, and apply the fade. Falls back to a flat level when
// no envelope is present. Mirrors render_ffmpeg._env_expr.
function musicVolume(
  a: z.infer<typeof SceneGraph>["audio"],
  fps: number,
  total: number,
): number | ((f: number) => number) {
  const duckDb = a.duck_music && a.voiceover_path ? a.duck_amount_db : 0;
  const fiF = Math.max(1, Math.round(a.music_fade_in_sec * fps));
  const foF = Math.max(1, Math.round(a.music_fade_out_sec * fps));
  const env = a.music_envelope ?? [];
  if (env.length === 0) {
    const base = dbToGain(a.music_gain_db + duckDb);
    return (f: number) => base * fadeFactor(f, fiF, foF, total);
  }
  // strictly-increasing frame positions (interpolate requires it)
  const xs: number[] = [];
  const ys: number[] = [];
  for (const k of env) {
    let x = Math.round(k.at * fps);
    if (xs.length && x <= xs[xs.length - 1]) x = xs[xs.length - 1] + 1;
    xs.push(x);
    ys.push(k.gain_db + duckDb);
  }
  return (f: number) => {
    const db = interpolate(f, xs, ys, {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
    return dbToGain(db) * fadeFactor(f, fiF, foF, total);
  };
}
