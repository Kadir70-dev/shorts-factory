import React from "react";
import { AbsoluteFill, Easing, interpolate, useCurrentFrame, useVideoConfig } from "remotion";

/**
 * Entrance transition, applied INSIDE each scene's own window (first ~10-12
 * frames) so scenes never overlap and the audio/caption master timeline stays
 * perfectly aligned. Maps SceneGraph `transition_in` to a motion style.
 *   cut     -> a TRUE hard cut (no flash, no scale snap) — the documentary default
 *   fade    -> gentle fade + subtle zoom settle (use between sections)
 *   slide_l -> slide in from left (deliberate pivot only)
 *   whip    -> whoosh slide + brief motion-blur streak (sparing, high-energy)
 * No exit fade: scenes hand off as clean cuts. Animated transitions are meant to
 * be rare, so most boundaries are calm — the Director picks `cut` by default.
 */
type T = "cut" | "fade" | "slide_l" | "whip" | "dip_to_black" |
  "push_up" | "crossfade";

export const SceneEnter: React.FC<{
  transition: T;
  durFrames: number;
  children: React.ReactNode;
}> = ({ transition, durFrames, children }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const inN = Math.round(fps * 0.55);   // a touch longer -> smoother, premium settle

  const tIn = interpolate(f, [0, inN], [0, 1], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.out(Easing.cubic),
  });

  let transform = "";
  let opacity = 1;
  let filter = "none";

  switch (transition) {
    case "whip": {
      // softened: shorter throw + lighter blur so it whooshes, not slams
      const x = interpolate(tIn, [0, 1], [36, 0]);
      const blur = interpolate(f, [0, inN * 0.6], [5, 0], { extrapolateRight: "clamp" });
      transform = `translateX(${x}%) scale(${interpolate(tIn, [0, 1], [1.08, 1])})`;
      filter = blur > 0.5 ? `blur(${blur}px)` : "none";
      opacity = interpolate(tIn, [0, 0.5], [0, 1], { extrapolateRight: "clamp" });
      break;
    }
    case "slide_l": {
      transform = `translateX(${interpolate(tIn, [0, 1], [-22, 0])}%)`;
      opacity = interpolate(tIn, [0, 0.6], [0, 1], { extrapolateRight: "clamp" });
      break;
    }
    case "fade":
    case "dip_to_black":
    case "crossfade": {
      transform = `scale(${interpolate(tIn, [0, 1], [1.06, 1])})`;
      opacity = tIn;
      break;
    }
    case "push_up": {
      transform = `translateY(${interpolate(tIn, [0, 1], [10, 0])}%)`;
      opacity = interpolate(tIn, [0, 0.5], [0, 1], { extrapolateRight: "clamp" });
      break;
    }
    default: {
      // cut: a genuine hard cut — instantly fully visible, no flash, no snap.
      transform = "";
      opacity = 1;
    }
  }

  return (
    <AbsoluteFill style={{ transform, opacity, filter, willChange: "transform" }}>
      {children}
    </AbsoluteFill>
  );
};
