# Niche playbook: HISTORY / DARK HISTORY (Netflix doc)

Goal: tell ONE forgotten, dark, or jaw-dropping true story per short — a
scandal, a catastrophic mistake, a weird old law, a buried event. **Evergreen by
nature**: it already happened, so it never goes stale. USA-first, but a
world-historical story with a strong American hook is fine.

Structure (4–6 scenes, documentary pace — let each beat breathe):
1. HOOK — drop the reader straight into the most shocking fact or image in the
   first 2 seconds ("In 1919, a wall of molasses killed 21 people in Boston.").
   Tease the mystery, don't summarize it.
2. THE SETUP — the world right before it happened. Set the stakes.
3. WHAT HAPPENED — the event, told as a story with momentum. The payload.
4. THE TWIST / TOLL — the dark turn, the body count, the cover-up, the
   consequence. Put hard figures (deaths, dollars, dates) in a `stat` overlay
   with a `source` overlay. NEVER invent numbers, deaths, or events — only use
   what's in the research brief or is well-established public history.
5. WHY IT MATTERS NOW — the lesson, the law it changed, the eerie echo today.
6. CTA close.

Visual rules:
- `broll` leans archival/atmospheric: old black-and-white footage, vintage
  photographs, period newsreel, old newspapers, historic buildings, dim dramatic
  reenactment-style footage. `scene_visual_type: "dramatic"` on the tense beats.
- For a beat no archive can show — a recreation of the moment, shadow
  silhouettes, an atmospheric "you are there" shot — use `visual.type:
  "ai_video"` (a short 1–3s cinematic insert). Use it on 1–2 beats at most; keep
  the rest real archival footage so it stays a documentary, not an AI reel.
- Dates/tolls/timelines → `manim` (`data_viz`) for a clean timeline or counter.
- Fill `visual.broll_keywords` on EVERY scene (3–5 concrete phrases), e.g.
  ["vintage black and white city", "old newspaper headline", "historic disaster
  footage", "antique photographs"].
- HOOK scene → `dramatic`; CTA scene → `subtle`.

Tone: suspenseful Netflix true-crime / dark-history narration — slow, weighty,
ominous. Build dread honestly: the DRAMA comes from real stakes, never from
fabricated detail. Stay historically accurate and attribute contested claims.
