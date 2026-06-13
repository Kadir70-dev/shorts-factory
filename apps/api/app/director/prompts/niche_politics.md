# Niche playbook: USA POLITICS EXPLAINED

Goal: explain ONE mechanism per short (how a filibuster works, what a CR is, how
impeachment proceeds) — not who to root for.

Structure (4–6 scenes, documentary pace — let each beat breathe):
1. HOOK — a question or surprising fact about the mechanism ("One senator can
   freeze the entire Senate. Here's how.").
2. THE SETUP — the normal state of things.
3. THE MECHANISM — the core move, step by step. This is the payload.
4. THE VISUAL — `manim` flow/diagram or `broll` of the institution (Capitol,
   Supreme Court, White House).
5. WHY IT MATTERS — the real-world consequence, neutrally framed.
6. CTA close.

Neutrality rules:
- Explain the process, not the partisanship. No personal attacks (banned).
- If a contested example is needed, present it even-handedly with attribution.
- Define jargon the moment you use it.

Visuals: process diagrams → `manim` (`scene_visual_type: "data_viz"`);
everything else → `broll` of the institution. Fill `visual.broll_keywords` on
EVERY scene (3–5 concrete footage phrases), e.g. ["white house", "congress",
"american flag", "press conference"] or ["us capitol dome", "supreme court
building", "senate floor", "voting"]. HOOK → `scene_visual_type: "dramatic"`;
CTA → `"subtle"`. Use `headline` overlays to name each step.
