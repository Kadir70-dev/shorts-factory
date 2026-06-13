import React from "react";
import { Audio, Sequence, staticFile } from "remotion";
import { z } from "zod";
import { SceneGraph } from "../schemas/scene";

/**
 * Retention sound design. The pipeline's sound-design stage (api/app/pipeline/
 * sfx.py) already computed a RESTRAINED, role-based cue list — emphasis moments
 * only (hook bass, stat hit+ring, real-transition whoosh/swipe, CTA riser) — so
 * Remotion just SCHEDULES `graph.sfx` deterministically. No per-word triggers,
 * no heuristics here: the editorial decisions live once, in Python, shared with
 * the ffmpeg renderer.
 *
 * Files: data/assets/sfx/<sound>.wav (Remotion publicDir is data/, so the path
 * is "assets/sfx/<sound>.wav"). Synthesized by sfx.ensure_pack(); if a file is
 * absent the cue simply doesn't play.
 */
const dbToGain = (db: number) => Math.pow(10, db / 20);

export const SfxLayer: React.FC<{ graph: z.infer<typeof SceneGraph>; fps: number }> = ({
  graph,
  fps,
}) => {
  const cues = graph.sfx ?? [];
  if (cues.length === 0) return null;
  return (
    <>
      {cues.map((cue, i) => {
        const from = Math.max(0, Math.round(cue.at * fps));
        return (
          <Sequence key={i} from={from} durationInFrames={Math.round(fps * 1.5)}>
            <Audio
              src={staticFile(`assets/sfx/${cue.sound}.wav`)}
              volume={dbToGain(cue.gain_db)}
            />
          </Sequence>
        );
      })}
    </>
  );
};
