# Niche playbook: CYBERSECURITY / CYBERCRIME (Netflix cybercrime doc)

Goal: tell ONE gripping cybercrime story per short — a breach, a leak, a hack, a
scam, an insider mistake — in a dark, suspenseful, documentary voice. The hook is
almost always the HUMAN story behind the headline: one tired developer, one
clicked link, one setting nobody changed. Evergreen: focus on how these things
HAPPEN, not on a fast-moving live incident.

Structure (5–6 scenes, documentary pace — let each beat breathe):
1. HOOK — drop into the most shocking or counter-intuitive fact in the first 2s
   ("Everyone called it an elite hack. It wasn't."). Tease the mystery.
2. THE SETUP — the exact person/company/system right before it happened. Stakes.
3. THE EVENT — the breach/leak/attack, told step-by-step as a story with
   momentum. The payload.
4. THE CONSEQUENCE — the real-world impact: victims, exposed records, the scramble.
   Put any hard, SOURCED figure in a `stat` overlay + a `source` overlay; never
   invent victim counts.
5. WHY IT HAPPENED — the grounded root cause (a phishing email, a default setting,
   a reused password, an unpatched server). Demystify it.
6. CTA close.

# POINT-TO-POINT VISUAL GROUNDING (mandatory)
Every visual must show EXACTLY what the line says. If the narration says X, the
screen shows X. No generic filler.
- `broll` for what a camera CAN film, matched exactly: a real SOC / security
  operations center, analysts at monitors, a developer at a desk, a server room /
  data center, office buildings, a phone receiving an alert email, journalists,
  law enforcement / a press conference (only when the line references them).
- For what no camera can show — the EXACT event — recreate it. Use
  `visual.type: "ai_video"` (a short cinematic insert) on 1–2 HERO beats (the
  moment of exposure, a database going public, a phishing email being opened), and
  `visual.type: "ai_image"` for an exact still (a leaked plaintext password table,
  a fake login page, a config screen with one toggle on). Write `visual_intent`
  as the precise shot so the recreation depicts THIS event, not a vague mood.
- `manim` (`data_viz`) for a breach TIMELINE or an exposed-records counter.
- Fill `visual.broll_keywords` (3–5 exact phrases) on EVERY scene, naming the real
  thing: ["security operations center monitors", "data center server room",
  "phishing email on screen", "developer terminal dark office"].
- HOOK scene → `dramatic`; CTA scene → `subtle`.

# ANTI-CLICHÉ — BANNED unless the narration literally references it
Cybersecurity stock is full of garbage. NEVER author these unless the line
explicitly says so:
- a hooded "hacker" in the dark / a person in a hoodie at a laptop,
- green "matrix" code rain / falling green characters,
- a generic glowing laptop with abstract neon code,
- a faceless figure in a Guy-Fawkes/anonymous mask,
- random binary spam as a background.
Use them ONLY if the narration is literally about, e.g., "the Matrix-style code on
his screen" or "he wore a mask". Otherwise show the REAL thing — the actual
office, the actual email, the actual leaked table, the actual server.

# Visual realism rules
- Realistic > stylized. SOC rooms, real offices, real email/login UIs, real server
  racks, real breach-notification emails on phones.
- A "screen" shot (terminal, dashboard, email, database) is fine and ENCOURAGED
  when the line is about the screen — that is NOT a cliché, that is grounding.
- Show consequences on real people (phones buzzing with alerts, a company
  scrambling), not abstract neon.

# Tone
Dark, suspenseful, emotional tension — Netflix cybercrime documentary. Slow and
weighty. Build dread honestly: the drama comes from REAL stakes (millions of real
people, one human mistake), never from fabricated detail. Never give operational
hacking instructions. If a number/victim-count isn't sourced, don't state it as
fact — tell it as a representative composite or hedge it.
