// Bundle Inter so renders don't fall back to the system serif.
import { loadFont } from "@remotion/google-fonts/Inter";

const { fontFamily } = loadFont("normal", {
  weights: ["600", "700", "800", "900"],
});

export const FONT_FAMILY = fontFamily;
