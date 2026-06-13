import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { z } from "zod";
import { Caption } from "../schemas/scene";
import { FONT_FAMILY } from "../fonts";
import { bounceIn, emphasisOf } from "../anim";

/**
 * Hormozi-style captions: big, heavy, center-safe, word-by-word. Each word in
 * the active segment bounces in (staggered), the spoken word scales up with a
 * highlight box, and emphasis words (numbers/$/%) get an extra accent pop.
 * Driven entirely by whisper word timings on the absolute master timeline.
 */
const HIGHLIGHT = "#ffd98a"; // active word — soft warm gold, not aggressive yellow
const EMPHASIS = "#86d0b4";  // numbers / money / percent — muted mint, not neon green

export const Captions: React.FC<{
  captions: z.infer<typeof Caption>[];
  fps: number;
  brand: string;
  /** [start,end] seconds where a big stat is the hero — captions yield to it so
   *  only ONE dominant text element is ever on screen. */
  muteRanges?: [number, number][];
}> = ({ captions, fps, muteRanges = [] }) => {
  const f = useCurrentFrame();
  const t = f / fps;

  // one dominant element rule: while a stat owns the frame, hold captions back
  if (muteRanges.some(([s, e]) => t >= s && t < e)) return null;

  const seg = captions.find((c) => t >= c.start && t <= c.end + 0.05);
  if (!seg) return null;

  const segStart = seg.start * fps;
  const words = seg.words.length
    ? seg.words
    : seg.text.split(/\s+/).map((w, i, a) => ({
        w,
        s: seg.start + (i / a.length) * (seg.end - seg.start),
        e: seg.start + ((i + 1) / a.length) * (seg.end - seg.start),
      }));

  return (
    <AbsoluteFill style={{ justifyContent: "flex-end", alignItems: "center", paddingBottom: "23%" }}>
      <div
        style={{
          maxWidth: "86%",
          textAlign: "center",
          display: "flex",
          flexWrap: "wrap",
          justifyContent: "center",
          gap: "10px 18px",
          lineHeight: 1.05,
          fontFamily: FONT_FAMILY,
          fontWeight: 900,
        }}
      >
        {words.map((w, i) => {
          const enter = bounceIn(f, segStart + i * 1.6, fps); // staggered entrance
          const active = t >= w.s && t <= w.e + 0.04;
          const isEmph = emphasisOf(w.w) >= 1;
          const baseSize = isEmph ? 68 : 60;     // ~21% smaller again — footage is the hero
          const scale = (active ? (isEmph ? 1.14 : 1.08) : 1) * (0.82 + 0.18 * enter);
          const color = active ? (isEmph ? EMPHASIS : HIGHLIGHT) : "#ffffff";
          return (
            <span
              key={i}
              style={{
                display: "inline-block",
                fontSize: baseSize,
                color,
                transform: `translateY(${(1 - enter) * 20}px) scale(${scale})`,
                opacity: enter,
                padding: active ? "2px 10px" : "2px 4px",
                borderRadius: 12,
                background: active ? "rgba(0,0,0,0.32)" : "transparent",
                WebkitTextStroke: "2.5px #000",
                textShadow: "0 2px 0 #000, 0 0 14px rgba(0,0,0,0.75)",
                willChange: "transform",
              }}
            >
              {w.w}
            </span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
