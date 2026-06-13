# Niche playbook: USA FACTS (curiosity documentary)

Goal: answer ONE "wait, why is America like this?" question per short — the
hidden system behind an everyday American thing (why Americans tip, why
healthcare is so expensive, why houses are wood, why drug ads are on TV). These
are **evergreen** — they should be just as true and interesting in a year.

Structure (4–6 scenes, documentary pace — let each beat breathe):
1. HOOK — name the weird-but-normal thing as a question or flat surprise in the
   first 2 seconds ("Americans tip for almost everything. Here's the buried
   reason why."). Curiosity gap first.
2. THE NORM — how the thing actually works day-to-day (briefly, so everyone's
   oriented).
3. THE HIDDEN SYSTEM — the historical/legal/economic reason it exists. This is
   the payload: the "oh, THAT'S why" reveal. One mechanism only.
4. THE PROOF — a concrete number, law, or date that anchors it. Put figures in a
   `stat` overlay with a `source` overlay (attribute it — don't invent numbers).
5. WHY IT STICKS — why it never changed / who benefits. Neutral framing.
6. CTA close.

Visual rules:
- Default to `broll` of everyday American life: diners, suburbs, checkout lines,
  hospitals, wood-frame houses under construction, gas stations, US streets.
- A comparison or number (US vs other countries, cost over time) → `manim`,
  `scene_visual_type: "data_viz"`.
- Fill `visual.broll_keywords` on EVERY scene (3–5 concrete, American footage
  phrases), e.g. ["american diner tipping", "restaurant check tip", "us suburb
  houses", "american hospital bill"].
- HOOK scene → `scene_visual_type: "dramatic"`; CTA scene → `"subtle"`.

Tone: warm, curious explainer (Vox / "Half as Interesting" energy) — make the
mundane feel fascinating. Stay neutral and sourced; the FEELING can be playful,
the FACTS must be exact. Avoid breaking news entirely — this bucket is timeless.
