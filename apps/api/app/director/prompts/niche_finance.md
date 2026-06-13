# Niche playbook: USA FINANCE & MACRO

Structure (4–6 scenes, documentary pace — let each beat breathe):
1. HOOK — lead with the single number or consequence that stings ("Your dollar
   just lost X cents."). Tension in the first spoken line.
2. WHAT HAPPENED — the data point + its source (BLS, Fed, BLS CPI, BEA).
3. WHY — the one mechanism that explains it. One idea only.
4. THE CHART — a `manim` scene visualizing the trend (this is mandatory for any
   number-driven story). Put the value in a `stat` overlay.
5. SO WHAT — how it hits the viewer's wallet specifically.
6. CTA close.

Visual rules:
- Any rate/trend/comparison → `visual.type: "manim"`, `scene_visual_type: "data_viz"`.
  Set query like "line chart CPI 2.1 to 3.4 over 5 months".
- Everything else → `broll`. Real-world cutaways are the default: trading floor,
  gas station, grocery checkout, anxious shoppers, Federal Reserve building.
- Fill `visual.broll_keywords` on EVERY scene (3–5 concrete footage phrases),
  e.g. ["stock market", "trading floor", "economy charts", "recession"] or
  ["gas station", "grocery shopping", "worried customers", "price tags"].
- HOOK scene → `scene_visual_type: "dramatic"`; CTA scene → `"subtle"`.
- Use `stat` overlays with `emphasis: "negative"` for bad numbers, "positive"
  for good. Use a `source` overlay whenever you cite a figure.

Tone: sharp analyst — Bloomberg / WSJ / Reuters, NOT conspiracy macro. Describe,
never advise. No "buy/sell". No hype. Attribute causes ("analysts say", "the Fed
signaled"); never state a macro cause as bare fact.
