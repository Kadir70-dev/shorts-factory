"""Prompt library loader. Assembles: base system + niche playbook + channel DNA,
and the per-request user prompt (with optional research brief)."""
from __future__ import annotations

from pathlib import Path

from ..config import ChannelConfig, settings

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
}


def system_prompt(channel: ChannelConfig) -> str:
    base = (DIR / "system.md").read_text().format(
        channel_name=channel.name,
        niche=channel.niche,
        style_notes=channel.style_notes,
        cta=channel.cta,
        banned=", ".join(channel.banned_topics) or "none",
        min_s=20, max_s=45,
    )
    niche = (DIR / _NICHE_FILE.get(channel.niche, "niche_finance.md")).read_text()
    return f"{base}\n\n---\n\n{niche}{grounding_addendum()}"


def user_prompt(topic: str, tone: str, video_id: str, channel_id: str,
                niche: str, research: str | None = None) -> str:
    parts = [
        f"Produce ONE Short.\n",
        f"Topic: {topic}",
        f"Tone: {tone}",
        f"Target length: 20–45 seconds (aim ~32s).\n",
    ]
    if research:
        parts.append("Research brief (use these facts; cite the named sources "
                     "in `source` overlays):\n" + research + "\n")
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
