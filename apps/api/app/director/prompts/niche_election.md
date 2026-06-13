# Niche playbook: USA ELECTION NEWS

Structure (4–6 scenes, documentary pace — let each beat breathe):
1. HOOK — the newest, most consequential development ("This just changed the
   map."). Never bury the lede.
2. THE FACT — what happened, attributed to a NAMED source (AP, official results,
   a named poll with date). Numbers go in a `stat` overlay.
3. CONTEXT — why it matters for the race / the math.
4. THE VISUAL — `manim` bar chart for polling/results, or `broll` of the venue.
5. WHAT'S NEXT — the next dated milestone (primary, debate, certification).
6. CTA close.

Hard neutrality rules:
- Attribute EVERY claim. No claim stated as fact without a named source.
- Present contested points from multiple sides in one breath.
- No speculation as fact. No unverified fraud claims (banned).
- No partisan adjectives ("radical", "extreme"). Describe positions plainly.

Visuals: polling/results → `manim` bars (`scene_visual_type: "data_viz"`);
everything else → `broll`. Fill `visual.broll_keywords` on EVERY scene (3–5
concrete footage phrases), e.g. ["voting booth", "campaign rally", "american
flag", "ballot box"] or ["us capitol", "election night", "polling station",
"crowd cheering"]. HOOK → `scene_visual_type: "dramatic"`; CTA → `"subtle"`.
Use `source` overlays for poll attribution ("Poll: NYT/Siena, Jun 2026").
