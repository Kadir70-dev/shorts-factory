import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { z } from "zod";
import { Overlay } from "../schemas/scene";
import { FONT_FAMILY } from "../fonts";
import { bounceIn } from "../anim";

// Muted documentary palette — readable accents, never neon "TikTok shouting".
const EMPH: Record<string, string> = {
  normal: "#f2f2f0",     // soft white
  alert: "#e9c46a",      // muted gold (was harsh #f5c518)
  positive: "#5cbf8f",   // calm green (was neon #19d27a)
  negative: "#e08163",   // warm terracotta (replaces aggressive #ff4d4d)
};

/**
 * Kinetic motion graphics with a hard CLUTTER BUDGET — exactly ONE hero element
 * per scene (premium documentary, not TikTok shouting):
 *   - HOOK (`intense`): the big HEADLINE only. (If a hook has no headline, the
 *     shock number stands in.) Captions are muted underneath (see Short.tsx).
 *   - Any scene with a `stat`: the number is the hero — big figure, small
 *     context label; captions muted.
 *   - Otherwise: a single headline (top) while captions own the lower third.
 * Source attribution is a tiny, dim, self-fading credit that never competes.
 */
export const OverlayLayer: React.FC<{
  overlays: z.infer<typeof Overlay>[];
  durFrames: number;
  intense?: boolean;
  accent?: string;
  confidence?: "confirmed" | "probable" | "speculative";
}> = ({ overlays, durFrames, intense, accent = "#f5c518", confidence = "confirmed" }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const exit = interpolate(f, [durFrames - 8, durFrames], [1, 0], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  });

  const stat = overlays.find((o) => o.type === "stat" && o.sub);
  const headline = overlays.find((o) => o.type === "headline");
  const source = overlays.find((o) => o.type === "source");

  // Resolve the single hero for this scene.
  const heroHeadline = headline && (intense || !stat);   // hook -> headline only
  const heroStat = stat && !heroHeadline;                // else the number

  return (
    <AbsoluteFill style={{ pointerEvents: "none", opacity: exit }}>
      {heroHeadline && (
        <Kinetic top={`${headline!.y * 100}%`} color={EMPH[headline!.emphasis] ?? "#fff"}
                 text={headline!.text} f={f} fps={fps} start={intense ? 0 : 2}
                 intense={!!intense} accent={accent} />
      )}

      {heroStat && (
        <Stat top={`${stat!.y * 100}%`} color={EMPH[stat!.emphasis] ?? "#fff"}
              sub={stat!.sub!} label={stat!.text} f={f} fps={fps}
              start={2} intense={!!intense}
              tag={confidence === "probable" ? "FORECAST"
                 : confidence === "speculative" ? "UNCONFIRMED" : null} />
      )}

      {/* Attribution: tiny, dim, fades after ~2.5s — never a dominant element. */}
      {source && <SourceCredit text={source.text} f={f} fps={fps} />}
    </AbsoluteFill>
  );
};

const Kinetic: React.FC<{
  top: string; color: string; text: string;
  f: number; fps: number; start: number; intense: boolean; accent: string;
}> = ({ top, color, text, f, fps, start, intense, accent }) => {
  const words = text.split(/\s+/);
  const size = intense ? 80 : 56;               // bold on the hook, restrained elsewhere
  const float = Math.sin(f / 32) * 3;           // gentler drift
  const kicker = bounceIn(f, start, fps);
  return (
    <div style={{ position: "absolute", top, left: 0, right: 0, padding: "0 7%",
                  textAlign: "center", transform: `translateY(${float}px)` }}>
      {/* documentary kicker bar on the hook — a confident accent, not a shout */}
      {intense && (
        <div style={{ width: 96 * kicker, height: 6, background: accent,
                      margin: "0 auto 20px", borderRadius: 4,
                      boxShadow: `0 0 12px ${accent}aa` }} />
      )}
      <div style={{ display: "inline-flex", flexWrap: "wrap", justifyContent: "center",
                    gap: "0 14px", lineHeight: 1.04,
                    background: "rgba(0,0,0,0.55)",
                    padding: intense ? "16px 28px" : "12px 22px", borderRadius: 14 }}>
        {words.map((w, j) => {
          const e = bounceIn(f, start + j * (intense ? 1.8 : 2.2), fps);
          return (
            <span key={j} style={{
              display: "inline-block", fontFamily: FONT_FAMILY, fontWeight: 800,
              fontSize: size, color,
              letterSpacing: intense ? 0.5 : 0,
              textTransform: intense ? "uppercase" : "none",
              transform: `translateY(${(1 - e) * 20}px) scale(${0.86 + 0.14 * e})`,
              opacity: e,
              textShadow: "0 3px 0 #000, 0 0 14px rgba(0,0,0,0.7)",
            }}>{w}</span>
          );
        })}
      </div>
    </div>
  );
};

/** Big number reveal with count-up + subtle flash. The figure is the hero; the
 *  context label sits quietly beneath it (premium hierarchy). */
const Stat: React.FC<{
  top: string; color: string; sub: string; label: string;
  f: number; fps: number; start: number; intense: boolean; tag?: string | null;
}> = ({ top, color, sub, label, f, fps, start, intense, tag }) => {
  const e = bounceIn(f, start, fps);
  const float = Math.sin(f / 30) * 3;
  const flash = interpolate(f, [start, start + 6, start + 16], [0, 0.6, 0], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  });
  const size = intense ? 148 : 130;             // ~22% smaller than before — refined, not shouting
  return (
    <div style={{ position: "absolute", top, left: 0, right: 0, textAlign: "center",
                  transform: `translateY(${float}px)` }}>
      {/* credibility tag — forecasts/unconfirmed figures are labelled, not faked */}
      {tag && (
        <div style={{ marginBottom: 10, opacity: bounceIn(f, start, fps) * 0.9 }}>
          <span style={{ display: "inline-block",
                         fontFamily: FONT_FAMILY, fontWeight: 700, fontSize: 24,
                         letterSpacing: 2, color: "#cfcfcf",
                         border: "1.5px solid rgba(255,255,255,0.45)", borderRadius: 6,
                         padding: "3px 12px" }}>
            {tag}
          </span>
        </div>
      )}
      <div style={{ position: "relative", display: "inline-block" }}>
        {/* accent flash ring — quick and subtle */}
        <div style={{ position: "absolute", inset: "-10% -7%", borderRadius: 32,
                      boxShadow: `0 0 0 4px ${color}`, opacity: flash }} />
        <div style={{ fontFamily: FONT_FAMILY, fontWeight: 900, fontSize: size, color,
                      letterSpacing: -1,
                      transform: `scale(${0.7 + 0.3 * e})`, opacity: e,
                      textShadow: "0 5px 0 #000, 0 0 24px rgba(0,0,0,0.55)" }}>
          {countUp(sub, e)}
        </div>
      </div>
      <div style={{ marginTop: 6, fontFamily: FONT_FAMILY, fontWeight: 600, fontSize: 38,
                    color: "#d6d6d6", textTransform: "uppercase", letterSpacing: 2,
                    opacity: bounceIn(f, start + 4, fps) * 0.92,
                    textShadow: "0 2px 0 #000" }}>{label}</div>
    </div>
  );
};

/** Tiny attribution credit, top of frame, self-fading. Never dominant. */
const SourceCredit: React.FC<{ text: string; f: number; fps: number }> = ({ text, f, fps }) => {
  const inOp = bounceIn(f, 6, fps);
  const out = interpolate(f, [fps * 2.4, fps * 3.0], [1, 0], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  });
  return (
    <div style={{ position: "absolute", top: "6.5%", left: 0, right: 0, textAlign: "center",
                  fontFamily: FONT_FAMILY, fontWeight: 600, fontSize: 26, color: "#d6d6d6",
                  letterSpacing: 0.5, opacity: inOp * out * 0.85,
                  textShadow: "0 2px 0 #000" }}>
      {text}
    </div>
  );
};

/** Animate the numeric part of e.g. "+3.4%", "$120", "44.8" from 0 -> target. */
function countUp(sub: string, progress: number): string {
  const m = sub.match(/^([^0-9-]*)(-?\d+(?:\.\d+)?)(.*)$/);
  if (!m) return sub;
  const [, pre, num, post] = m;
  const target = parseFloat(num);
  const dec = num.includes(".") ? 1 : 0;
  const val = (target * Math.min(1, progress * 1.1)).toFixed(dec);
  return `${pre}${val}${post}`;
}
