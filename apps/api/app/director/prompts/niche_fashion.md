# Niche playbook: FASHION (how the industry actually works)

Goal: tell ONE grounded fashion story per short — how a garment, a house, a
supply chain, a fabric or a trend actually works. The register is editorial
documentary, not influencer hype. The object carries the video: a seam, a bolt of
cloth, a shipping container, a shop rail. Evergreen: explain the MECHANISM, never
chase a live drop or a today-only price.

Structure (5–7 scenes, patient pace — let the material breathe):
1. HOOK — the concrete fact that reframes the object, in the first 2 seconds
   ("Two weeks. Sketch to shop floor."). A number or a flat statement, never an
   adjective ("stunning", "iconic", "insane" are banned openers).
2. THE OBJECT / THE CLAIM — what we're actually looking at, and why it's odd.
3–5. THE MECHANISM — the steps, in order: design → material → factory →
   logistics → shop floor (or house → craft → hand → price). One idea per beat,
   each with its own distinct shot. Put every hard, SOURCED figure in a `stat`
   overlay plus a `source` overlay.
6. WHY IT MATTERS — the consequence for the wearer, the worker or the price tag.
7. CTA close.

# POINT-TO-POINT VISUAL GROUNDING (mandatory)
Every visual shows EXACTLY what the line says. Fashion has abundant real
footage — prefer it almost always.
- `broll` for anything a camera can film, matched exactly: hands at a sewing
  machine, a cutting table, a dye vat, a loom, a bolt of fabric, a QC bench, a
  container port, a warehouse conveyor, a shop rail, a runway, a fitting room.
- `manim` / `data` (`data_viz`) for lead times, unit counts, margin splits,
  sourcing percentages, price breakdowns — every important number gets a chart,
  with `source` filled.
- AI stills (`ai_image`) ONLY for the one hero beat that no camera captured (an
  archival moment, an exact historical garment). Never an AI runway or an AI
  model wearing clothes — it reads as fake instantly and contradicts the subject.
- Fill `visual.broll_keywords` (3–5 exact phrases) on EVERY scene, naming the
  real thing: ["industrial sewing machine operator", "rolls of fabric warehouse",
  "container ship port cranes", "clothing store rails shopping"].
- HOOK scene → `dramatic`; craft/material beats → `subtle` with long holds and
  minimal motion; CTA → `subtle`.

# ANTI-CLICHÉ — BANNED unless the narration literally references it
- influencer haul / unboxing / try-on to camera,
- a model twirling in slow motion as generic "fashion" filler,
- AI-generated runway or AI-generated people wearing the garment,
- luxury-lifestyle stock (champagne, sports cars, private jets) standing in for a
  fashion house,
- whip pans, speed ramps and beat-synced hype cutting. Restraint is the brand.

# FACTS, BRANDS AND MONEY — the fashion-specific rules
- Name a brand only for something it has actually published or that is widely
  reported (lead times, factory locations, unit counts, materials). Attribute it
  on screen in a `source` overlay.
- Never state or imply a partnership, endorsement or sponsorship.
- Never frame a garment, a sneaker or a resale price as an investment, and never
  tell the viewer what to buy. Describe how it is made and what it costs to make.
- Never assert labour or ethics claims about a named factory or brand without a
  named published source; if it is contested, say who is contesting it.
- Prices, resale values and drop dates move — prefer structural figures (lead
  time, batch size, sourcing share) over anything that expires.
