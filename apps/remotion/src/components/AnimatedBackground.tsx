import React from "react";
import { AbsoluteFill, random, useCurrentFrame } from "remotion";

/**
 * Always-moving background for `solid` scenes (and as an underlay). Cheap:
 * two drifting radial glows + a slowly rotating gradient + ~22 deterministic
 * particles + vignette. Transform/gradient only — no blur filters.
 */
export const AnimatedBackground: React.FC<{ color: string; accent: string; seed: string }> = ({
  color, accent, seed,
}) => {
  const f = useCurrentFrame();
  const ang = (f * 0.4) % 360;                    // slow gradient rotation
  const g1x = 30 + 18 * Math.sin(f / 70);
  const g1y = 28 + 14 * Math.cos(f / 55);
  const g2x = 72 + 16 * Math.cos(f / 60);
  const g2y = 70 + 15 * Math.sin(f / 48);

  return (
    <AbsoluteFill style={{ overflow: "hidden", backgroundColor: color }}>
      {/* rotating base gradient */}
      <AbsoluteFill
        style={{
          background: `linear-gradient(${ang}deg, ${color} 0%, ${shade(color, -18)} 55%, ${shade(color, 14)} 100%)`,
        }}
      />
      {/* drifting accent glows */}
      <AbsoluteFill
        style={{
          background:
            `radial-gradient(40% 30% at ${g1x}% ${g1y}%, ${hexA(accent, 0.40)} 0%, transparent 70%),` +
            `radial-gradient(46% 34% at ${g2x}% ${g2y}%, ${hexA(shade(accent, -30), 0.34)} 0%, transparent 72%)`,
        }}
      />
      <Particles seed={seed} accent={accent} />
      {/* vignette for focus */}
      <AbsoluteFill
        style={{ background: "radial-gradient(70% 60% at 50% 42%, transparent 55%, rgba(0,0,0,0.55) 100%)" }}
      />
    </AbsoluteFill>
  );
};

const Particles: React.FC<{ seed: string; accent: string }> = ({ seed, accent }) => {
  const f = useCurrentFrame();
  const dots = Array.from({ length: 22 }, (_, i) => {
    const x = random(`${seed}-x${i}`) * 100;
    const baseY = random(`${seed}-y${i}`) * 100;
    const speed = 0.05 + random(`${seed}-s${i}`) * 0.12;
    const size = 3 + random(`${seed}-r${i}`) * 7;
    const y = (baseY - f * speed + 100) % 100;     // drift upward, wrap
    const tw = 0.25 + 0.55 * (0.5 + 0.5 * Math.sin(f / 18 + i));
    return { x, y, size, tw };
  });
  return (
    <AbsoluteFill>
      {dots.map((d, i) => (
        <div
          key={i}
          style={{
            position: "absolute", left: `${d.x}%`, top: `${d.y}%`,
            width: d.size, height: d.size, borderRadius: "50%",
            background: accent, opacity: d.tw * 0.5,
          }}
        />
      ))}
    </AbsoluteFill>
  );
};

// --- tiny color utils (hex only) ---
function clamp(n: number) { return Math.max(0, Math.min(255, Math.round(n))); }
function parse(hex: string): [number, number, number] {
  const h = hex.replace("#", "");
  const n = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
  return [parseInt(n.slice(0, 2), 16), parseInt(n.slice(2, 4), 16), parseInt(n.slice(4, 6), 16)];
}
function toHex(n: number) { return clamp(n).toString(16).padStart(2, "0"); }
function shade(hex: string, amt: number): string {
  const [r, g, b] = parse(hex);
  return `#${toHex(r + amt)}${toHex(g + amt)}${toHex(b + amt)}`;
}
function hexA(hex: string, a: number): string {
  const [r, g, b] = parse(hex);
  return `rgba(${r}, ${g}, ${b}, ${a})`;
}
