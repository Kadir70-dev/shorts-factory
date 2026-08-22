"""Prompt library loader. Assembles: base system + niche playbook + channel DNA,
and the per-request user prompt (with optional research brief)."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ..config import ChannelConfig, settings

if TYPE_CHECKING:                    # avoids a cycle: structures imports config
    from . import structures

DIR = Path(__file__).parent / "prompts"

# GLOBAL storytelling rule — appended to the system prompt ONLY when the
# narration→visual grounding lock is on (settings().strict_visuals). Niche-
# agnostic: it forces point-to-point grounding for ANY topic (history, politics,
# business, sports, crime, cybersecurity, finance, documentary, dark facts,
# anime). Off → the prompt is exactly as before (backward compatible).
_STRICT_GROUNDING = """
---

# VISUAL ACCURACY MODE: STRICT — narration↔visual LOCK (NON-NEGOTIABLE)
Every visual must EXACTLY show what the line says. No generic visuals, no random
stock, no unrelated AI art. The viewer must feel: "the visuals show exactly what
is being said." This applies to ANY topic — history, politics, business, sports,
crime, cybersecurity, finance, documentary, dark facts, anime.

For EVERY scene, ground the visual point-to-point to that sentence's specific
subject — the exact people, place, object, event, year, team, or action named or
implied. Populate these five, all locked to THIS line:
  1. EXACT visual intent  → `visual.visual_intent`: the precise shot (named
     subject + setting + action), e.g. "Brazil's 1970 team lifting the World Cup
     trophy as the crowd erupts" — NOT "a football match".
  2. Matching footage/image → `visual.broll_keywords`: 3–5 SPECIFIC search phrases
     naming the exact subject/event ("brazil 1970 world cup final", "pele trophy
     celebration", "estadio azteca 1970 crowd"). Best-first, no generic filler.
  3. Motion direction      → `visual.motion` (zoom_in for impact, pan_lr to reveal,
     ken_burns to hold, zoom_out to open up).
  4. Emotion               → `visual.scene_visual_type` (dramatic / data_viz /
     real_footage / subtle / abstract) matching the beat's feeling.
  5. Overlay text          → `overlays`: the key claim (`headline`), the number
     (`stat`), the attribution (`source`) — only what belongs on THIS beat.

STRICT VISUAL PRIORITY (author intent so the resolver can honor it):
  Tier 1 — EXACT matching real footage of the subject/event.
  Tier 2 — AI RECREATION of the EXACT event (set `ai_video` for a hero recreation,
           or write `visual_intent` so an exact still can be generated) — used
           when no real footage of that exact moment exists (recreations: a CCTV
           re-enactment, a phishing email + login page, a 1920s street, a ship's
           hull tearing open). The recreation must depict the SPECIFIC event, not
           a mood.
  Tier 3 — hybrid (exact base + on-screen graphics).
  Tier 4 — generic b-roll: AVOID. Only acceptable as a non-black safety net.

HARD BANS:
  • No generic/symbolic filler when the line names something concrete
    ("generic rich businessman" for "he started with $20" → instead: small shop,
    old photos, empty wallet, first product).
  • No repeated footage — every beat shows a DIFFERENT, on-point shot.
  • Everyday-realism beats (grocery, gas, streets, crowds, voting lines) STILL use
    real footage, just exactly matched — never an uncanny AI version.
Bad examples to NEVER emit: "random football footage", "random ocean clip",
"generic rich businessman", "random criminal image", "hoodie hacker typing".
"""


def grounding_addendum() -> str:
    """The STRICT grounding block when the lock is on, else empty (no-op)."""
    return _STRICT_GROUNDING if settings().strict_visuals else ""

_NICHE_FILE = {
    "usa_finance": "niche_finance.md",
    "usa_election": "niche_election.md",
    "usa_politics": "niche_politics.md",
    "usa_facts": "niche_facts.md",
    "usa_history": "niche_history.md",
    "usa_business": "niche_business.md",
    "cybersecurity": "niche_cyber.md",
    # Fashion vertical — one shared playbook; the channel's own style_notes carry
    # the per-bucket register (luxury restraint vs streetwear energy).
    "fashion_business": "niche_fashion.md",
    "fashion_luxury": "niche_fashion.md",
    "fashion_history": "niche_fashion.md",
    "fashion_trends": "niche_fashion.md",
    "fashion_manufacturing": "niche_fashion.md",
    "fashion_supply_chain": "niche_fashion.md",
    "streetwear": "niche_fashion.md",
    "sneaker_culture": "niche_fashion.md",
    "textile_industry": "niche_fashion.md",
}


# The visual doctrine, in the pipeline's actual priority order. Replaces the old
# "pick broll or manim" guidance, which is what produced numbers over random stock.
_VISUAL_LADDER = """
---

# VISUAL PLANNING — the five-tier ladder (the pipeline enforces this order)

Do NOT think in terms of "find a stock clip". Think about what this specific beat
should SHOW, and fill the fields that let the pipeline build it.

## Tier 3 (highest priority in practice): EVERY IMPORTANT NUMBER GETS A CHART

If a beat states a figure, fill `data` with the ACTUAL numbers. That beat renders
as a custom animated chart in the channel's own palette — never stock footage
standing next to a number.

```
"data": {
  "kind": "delta",                       // counter | bar_compare | line_trend | delta | donut | meter
  "title": "Median US home price",       // what the number measures
  "points": [{"label": "2019", "value": 274600},
             {"label": "2024", "value": 419200}],
  "prefix": "$", "suffix": "", "decimals": 0,
  "source": "Census Bureau"              // REQUIRED — it renders under the chart
}
```

Pick the form from the data's shape:
  counter     one hero figure                   ("$1.50", "3.4%")
  meter       a percentage of a whole            (0–100 only)
  donut       one share of a total
  delta       exactly two values: before → after
  bar_compare 3–6 named categories
  line_trend  4+ points over time (year labels)

NEVER invent a number to get a chart. If the figure isn't in the research brief or
common public knowledge, don't state it — and then this beat isn't a data beat.

## Tier 1: SUBJECT-SPECIFIC visuals

For a beat that names something concrete — a person, company, place, event, year —
write `visual.visual_intent` as the EXACT shot and `visual.broll_keywords` as 3–5
search phrases naming that exact subject. "brazil 1970 world cup final", not
"a football match". These are the only beats that will use footage at all.

## Tier 2: MOTION GRAPHICS

For a beat whose content IS the words — a mechanism, a definition, a contrast, a
reveal with nothing filmable — put the key line in a `headline` overlay and keep
`broll_keywords` short or empty. The pipeline builds that line on screen as
kinetic typography over a branded field. This is BETTER than footage for these
beats; do not force a stock clip onto an abstract claim.

## Tier 4: BRANDED PLATE

Automatic. A beat with nothing specific to show and no line worth setting in type
gets a branded background. You never request this.

## Tier 5: STOCK FOOTAGE — a rescue, not a default

Generic stock is now the LAST thing the pipeline reaches for. Vague keywords
("business meeting", "financial growth", "corporate handshake") tell it there is
no real subject, and it will correctly build a graphic instead. So: be specific,
or be textual. Never be vague.
"""


def system_prompt(channel: ChannelConfig,
                  structure: "structures.StructureChoice | None" = None) -> str:
    base = (DIR / "system.md").read_text().format(
        channel_name=channel.name,
        niche=channel.niche,
        style_notes=channel.style_notes,
        cta=channel.cta,
        banned=", ".join(channel.banned_topics) or "none",
        min_s=20, max_s=45,
    )
    niche = (DIR / _NICHE_FILE.get(channel.niche, "niche_finance.md")).read_text()
    out = f"{base}\n\n---\n\n{niche}{grounding_addendum()}{_VISUAL_LADDER}"
    out += _SAFETY_BLOCK
    if structure is not None:
        out += "\n\n---\n\n" + structure.prompt_block()
    return out


# Monetisation safety, stated to the model rather than left to the post-hoc
# rewriter. Catching it here produces a properly-written line; catching it after
# produces a patched one, and these lines get SPOKEN.
_SAFETY_BLOCK = """
---

# MONETISATION SAFETY (this is checked automatically and will be sent back)

This channel describes; it does not advise. Never write:
  guaranteed · risk-free · get rich · easy money · best stock to buy · buy now ·
  last chance · to the moon · you should buy/sell · double your money · scam ·
  "they don't want you to know"

Write the descriptive equivalent instead:
  "guaranteed returns"        → "returns that have historically been consistent"
  "the best stock to buy"     → "the company drawing the most attention"
  "you should buy this"       → "some investors have moved into this"
  "it's a scam"               → "an alleged scam" / "a scheme regulators challenged"
  "it will crash"             → "analysts warn it could fall"

A line with several of these gets rejected wholesale rather than patched, because
patching a promotional sentence produces something that sounds wrong when spoken.
Write it descriptively the first time.

Also set `beat_role` on EVERY scene to the role given in the structure below
(hook, tension, evidence, reveal, cta, …). The music envelope, sound design and
visual engine all key off it.
"""


def user_prompt(topic: str, tone: str, video_id: str, channel_id: str,
                niche: str, research: str | None = None,
                structure: "structures.StructureChoice | None" = None) -> str:
    parts = [
        "Produce ONE Short.\n",
        f"Topic: {topic}",
        f"Tone: {tone}",
        f"Target length: 20–45 seconds (aim ~32s).\n",
    ]
    if structure is not None:
        parts.append(
            f"Story structure: {structure.structure.name} — "
            f"EXACTLY {structure.scene_count} scenes, one per beat, in order.\n")
    if research:
        parts.append("Research brief (use these facts; cite the named sources "
                     "in `source` overlays and in `data.source`):\n"
                     + research + "\n")
    parts.append(
        "Fill meta exactly with:\n"
        f"  video_id: {video_id}\n"
        f"  channel_id: {channel_id}\n"
        f"  niche: {niche}\n"
        "  plus title, hook, description, tags, hashtags, thumbnail_text.\n"
    )
    if topic.startswith("__trending__:"):
        parts.append("This is a trending slot: pick the single most newsworthy "
                     "angle in this niche today and write about that.")
    return "\n".join(parts)
