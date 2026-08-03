"""
Visual Decision Engine — which of the five visual tiers each beat gets.

The audit's finding was that numbers were being paired with random stock clips and
abstract claims were being illustrated with generic corporate footage. Both are the
same failure: falling back to stock as a DEFAULT rather than as a last resort.

The ladder, strictly in priority order:

  1. SUBJECT-SPECIFIC  — the exact thing the line names. Real footage of that
     subject if it exists; an AI recreation of that exact subject if no camera
     could have been there. Never "a football match" for "Brazil, 1970".
  2. MOTION GRAPHICS   — the claim itself, built on screen in the channel's type
     over a live branded field. For beats whose content IS the words: mechanisms,
     definitions, contrasts, reveals with no filmable subject.
  3. ANIMATED CHARTS   — every important number. This one OUTRANKS the others in
     practice: a beat that states a real figure gets a chart of that figure, not
     footage that happens to be nearby. It is the most explicit instruction in the
     brief and the one the old pipeline got most wrong.
  4. BRANDED GRAPHICS  — a branded plate. The floor a beat lands on when nothing
     above fits.
  5. STOCK FOOTAGE     — only when a subject-specific search actually returns
     something on-topic. Generic stock is no longer a default; it is a rescue.

Everyday-realism beats (grocery aisles, gas pumps, voting lines, crowds) remain a
hard veto on AI: those look uncanny generated and are exactly what real footage is
good at. That rule predates this rewrite and survives it.

The engine is a PURE function — no I/O, deterministic — so it is cheap to dry-run
and easy to test. `broll.py` turns the decision into a file on disk and keeps a
safety net under every tier.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..config import settings
from ..schemas.scene import Scene, SceneGraph
from ..schemas.video_spec import VideoSpec
from . import dataviz

# strategy labels (mirror schema Visual.strategy)
DATAVIZ = "dataviz"
REAL = "real"
AI_IMAGE = "ai_image"
AI_VIDEO = "ai_video"
MOTION_GFX = "motion_gfx"
BRANDED = "branded"
HYBRID = "hybrid"

# Target mix over a whole short. Charts and graphics are no longer a rounding
# error: a documentary explainer that never shows a number or a built claim is
# just narrated stock footage.
#   ~45% subject-specific real · ~20% charts · ~15% motion graphics
#   ~15% AI recreation · ~5% branded plate
MIX_TARGET: dict[str, tuple[float, float]] = {
    REAL: (0.38, 0.52),
    DATAVIZ: (0.15, 0.28),
    MOTION_GFX: (0.10, 0.22),
    AI_IMAGE: (0.10, 0.20),
}

# OPT-IN image-to-video band (Picsart), allocated only when both
# settings().enable_image_to_video and spec.allow_ai_video are on.
AI_VIDEO_BAND: tuple[float, float] = (0.10, 0.20)

# --------------------------------------------------------------------------- #
# Subject taxonomy
# --------------------------------------------------------------------------- #
# AI-eligible buckets: subjects a camera cannot truthfully shoot, or that look
# fake as stock. A match here makes the beat a candidate for an AI RECREATION of
# that exact subject — not for generic AI mood imagery.
_AI_SUBJECTS: dict[str, list[str]] = {
    "history": [
        "history", "historic", "historical", "1800s", "1900s", "century",
        "decade", "era", "ancient", "old newspaper", "newspaper headline",
        "archival", "scandal", "watergate", "cover-up", "coverup", "resign",
        "resignation", "disgrace", "secret meeting", "behind closed doors",
        "president", "white house", "oval office", "administration", "regime",
        "empire", "founding", "war crime", "assassinat", "conspiracy",
        "corridor", "dark hallway", "smoke-filled room", "back room",
    ],
    "politics": [
        "election", "elections", "swing state", "swing states", "electoral",
        "electoral college", "ballot", "campaign", "rally", "candidate",
        "red state", "blue state", "red vs blue", "partisan", "congress",
        "senate", "capitol", "supreme court", "primary", "primaries",
        "political", "politics", "vote count", "battleground", "landslide",
        "power", "democracy", "republic",
    ],
    "business": [
        "billionaire", "billionaires", "monopoly", "monopolies", "boardroom",
        "ceo", "corporate empire", "merger", "acquisition", "wall street",
        "silicon valley", "startup", "tech giant", "trillion dollar",
        "market cap", "luxury", "private jet", "yacht", "skyscraper",
        "data center", "artificial intelligence", "ai future", "robot",
        "automation", "algorithm", "future of",
    ],
    "abstract": [
        "inflation", "fear", "anxiety", "anxious", "broke", "broken",
        "middle class", "the squeeze", "squeezed", "psychology", "hidden",
        "invisible", "the system", "the systems", "rigged", "trap",
        "debt", "shrinking", "vanish", "disappear", "dissolve", "erode",
        "illusion", "secret", "loophole", "loopholes", "why nobody",
        "what they don't", "the truth about", "the real reason", "tipping point",
        "money", "wealth gap", "inequality", "power dynamic",
    ],
}

# Everyday realism — a hard veto on AI. These read uncanny when generated and are
# precisely what stock footage libraries are genuinely good at.
_FORCE_REAL: list[str] = [
    "restaurant", "diner", "cafe", "café", "waiter", "waitress",
    "tip ", "tipping", "tips ", "menu", "grocery", "groceries", "supermarket",
    "checkout", "cashier", "shopping cart", "shopper", "shoppers",
    "gas station", "gas pump", "gas prices", "filling up", "pump ", "fuel",
    "street", "sidewalk", "crosswalk", "traffic", "highway", "neighborhood",
    "suburb", "voting line", "polling station", "polling place", "ballot box",
    "at the polls", "line to vote", "lines to vote", "crowd", "crowds",
    "commute", "commuter", "subway", "bus stop", "parking lot", "drive-thru",
    "kitchen table", "everyday", "ordinary people",
]

# Beat roles whose content IS the words — prime motion-graphics territory.
_GFX_ROLES = {"mechanism", "myth", "reveal", "turn", "lesson", "contrast"}

# Search phrases so generic they signal "no real subject was identified". A beat
# whose keywords are all of this shape has nothing specific to film.
_GENERIC_KEYWORDS = re.compile(
    r"^(business|corporate|office|meeting|handshake|money|finance|financial|"
    r"success|growth|technology|abstract|concept|background|professional|"
    r"team|teamwork|working|computer|data|chart|graph|stock market|economy)"
    r"[a-z ]*$", re.IGNORECASE)


@dataclass
class Decision:
    """The engine's verdict for one scene (also written onto scene.visual)."""
    scene_id: str
    strategy: str
    reason: str
    tier: int                     # 1..5 — which rung of the ladder
    ai_eligible: bool
    force_real: bool
    score: float                  # AI-recreation affinity
    has_data: bool = False        # a real figure the chart engine can render
    concrete: bool = False        # names a specific, filmable subject
    category: str = ""
    hero: bool = False


@dataclass
class MixReport:
    decisions: list[Decision]
    counts: dict[str, int] = field(default_factory=dict)
    pct: dict[str, float] = field(default_factory=dict)

    def format(self) -> str:
        parts = [f"{k} {v}" for k, v in self.counts.items() if v]
        return "visual mix: " + " · ".join(parts)


def _scene_text(s: Scene) -> str:
    v = s.visual
    return " ".join([
        s.narration, v.visual_intent, v.query, " ".join(v.broll_keywords),
        " ".join(s.keywords), " ".join(o.text for o in s.overlays),
    ]).lower()


def _is_concrete(s: Scene) -> bool:
    """Does this beat name something specific enough to actually film?

    Two signals: a proper noun that isn't just the sentence opener, and
    subject-specific search keywords. Beats whose keywords are all generic
    ("business meeting", "financial growth") have nothing to point a camera at,
    and that is precisely when the old pipeline reached for stock.
    """
    words = s.narration.split()
    proper = sum(1 for w in words[1:]
                 if w[:1].isupper() and len(w) > 2 and w.isalpha())
    has_year = bool(re.search(r"\b(1[5-9]\d{2}|20\d{2})\b", s.narration))
    specific_kw = [k for k in s.visual.broll_keywords
                   if k and not _GENERIC_KEYWORDS.match(k.strip())]
    return bool(proper or has_year) and bool(specific_kw)


def _has_showable_text(s: Scene) -> bool:
    """Is there a line worth setting in type? A headline always is; a narration
    line is only if it's short enough to read at speed — a 30-word sentence on
    screen is a wall, not a graphic."""
    if any(o.type == "headline" and o.text.strip() for o in s.overlays):
        return True
    return 3 <= len(s.narration.split()) <= 16


def _classify(s: Scene, niche: str) -> Decision:
    text = _scene_text(s)
    v = s.visual
    force_real = any(k in text for k in _FORCE_REAL)

    matched: list[str] = []
    hits = 0
    for cat, kws in _AI_SUBJECTS.items():
        n = sum(1 for k in kws if k in text)
        if n:
            matched.append(cat)
            hits += n

    score = 0.0
    bits: list[str] = []
    if v.type == "ai_video":
        score += 5.0
        bits.append("Director flagged ai_video")
    if v.scene_visual_type == "abstract":
        score += 3.0
        bits.append("abstract concept")
    elif v.scene_visual_type == "dramatic":
        score += 1.5
        bits.append("dramatic beat")
    if matched:
        score += 1.5 * len(matched) + 0.4 * hits
        bits.append(f"subject={'+'.join(matched)}")

    lean = _NICHE_AI_LEAN.get(niche, 0.4)
    score += lean
    if force_real:
        bits = ["everyday realism → real footage (AI would look fake)"]
        score = -10.0

    return Decision(
        scene_id=s.id, strategy=REAL, reason="; ".join(bits) or "literal subject",
        tier=1,
        ai_eligible=bool(matched or v.type == "ai_video"
                         or v.scene_visual_type == "abstract") and not force_real,
        force_real=force_real, score=score,
        has_data=dataviz.from_scene(s) is not None,
        concrete=_is_concrete(s),
        category=matched[0] if matched else "",
    )


_NICHE_AI_LEAN: dict[str, float] = {
    "usa_history": 1.0, "usa_politics": 0.7, "usa_election": 0.7,
    "usa_business": 0.7, "usa_finance": 0.3, "usa_facts": 0.2,
    "cybersecurity": 0.85,
}


def _cap(n: int, lo: float, hi: float) -> int:
    return int(round(n * (lo + hi) / 2))


# --------------------------------------------------------------------------- #
def decide(graph: SceneGraph, spec: VideoSpec) -> MixReport:
    """Assign a visual tier to every scene. Mutates `scene.visual.strategy` and
    `.decision_reason`, and sets `visual.type` for the locally-rendered tiers."""
    scenes = graph.scenes
    n = len(scenes)
    if not n:
        return MixReport(decisions=[])
    decisions = [_classify(s, graph.meta.niche) for s in scenes]
    by_id = {d.scene_id: d for d in decisions}

    # ── TIER 3 first: every important NUMBER gets its own animated chart. ──────
    # Ranked above the others deliberately. When a beat states a real figure, the
    # figure IS the visual; pairing it with footage that merely feels related is
    # the exact behaviour this rewrite exists to remove.
    #
    # AUTHORED data (the Director wrote out a series) is never capped: it said
    # this beat is about these numbers, and capping it would drop the chart and
    # substitute footage — the precise failure being fixed. The cap applies only
    # to charts PROMOTED from a bare stat overlay, which is a guess and can
    # reasonably be rationed so a short doesn't become a slide deck.
    promoted_cap = max(1, _cap(n, *MIX_TARGET[DATAVIZ]))
    promoted = 0
    for s in scenes:
        d = by_id[s.id]
        if not d.has_data:
            continue
        authored = s.data is not None and s.data.valid()
        if not authored:
            if promoted >= promoted_cap:
                continue
            promoted += 1
        viz = dataviz.from_scene(s)
        d.strategy, d.tier = DATAVIZ, 3
        d.reason = (f"states a real figure → animated chart ({viz.kind})"
                    + ("" if authored else ", promoted from its stat overlay"))
        s.data = viz
        s.visual.type = "dataviz"

    remaining = [by_id[s.id] for s in scenes if by_id[s.id].strategy != DATAVIZ]

    # ── TIER 1: subject-specific footage / recreation ────────────────────────
    # A beat that names something concrete is filmable. Whether that resolves to
    # real footage or an AI recreation of the SAME subject is decided by whether a
    # camera could plausibly have been there.
    ai_cap = _cap(n, *MIX_TARGET[AI_IMAGE]) if spec.allow_ai_image else 0
    ai_used = 0
    for d in sorted(remaining, key=lambda x: -x.score):
        if not d.concrete:
            continue
        if d.ai_eligible and ai_used < ai_cap and not d.force_real:
            d.strategy, d.tier = AI_IMAGE, 1
            d.reason = f"specific subject a camera couldn't reach → AI recreation — {d.reason}"
            ai_used += 1
        else:
            d.strategy, d.tier = REAL, 1
            d.reason = f"specific subject → exact-match footage — {d.reason}"

    # ── TIER 2: motion graphics for beats whose content is the WORDS ─────────
    gfx_cap = max(1, _cap(n, *MIX_TARGET[MOTION_GFX]))
    gfx_used = 0
    for s in scenes:
        d = by_id[s.id]
        if d.strategy != REAL or d.concrete or gfx_used >= gfx_cap:
            continue
        role = (s.beat_role or "").lower()
        wordy = role in _GFX_ROLES or s.visual.scene_visual_type == "abstract"
        if wordy or not d.concrete:
            d.strategy, d.tier = MOTION_GFX, 2
            d.reason = ("no filmable subject; the claim IS the content → "
                        "kinetic typography")
            s.visual.type = "motion_gfx"
            gfx_used += 1

    # ── TIER 4: branded plate — the floor, and genuinely a last resort ───────
    # A beat that reached here has no filmable subject. If it has a line worth
    # putting on screen, motion graphics is strictly better than a blank plate,
    # so the tier-2 budget is allowed to overflow rather than leave the frame
    # empty — a run of three identical plates would be worse than the stock
    # footage this whole ladder replaced.
    for s in scenes:
        d = by_id[s.id]
        if d.strategy != REAL or d.concrete:
            continue
        if _has_showable_text(s):
            d.strategy, d.tier = MOTION_GFX, 2
            d.reason = ("no filmable subject, but the line carries the beat → "
                        "kinetic typography")
            s.visual.type = "motion_gfx"
        else:
            d.strategy, d.tier = BRANDED, 4
            d.reason = ("nothing specific to show and nothing worth setting in "
                        "type → branded plate")
            s.visual.type = "branded"

    # ── OPT-IN: AI video on the highest-emotion beat ─────────────────────────
    cfg = settings()
    if cfg.enable_image_to_video and spec.allow_ai_video:
        cands = sorted((d for d in decisions if d.strategy == AI_IMAGE),
                       key=lambda d: -d.score)
        cap = min(cfg.max_ai_video_scenes, max(1, _cap(n, *AI_VIDEO_BAND)))
        for i, d in enumerate(cands[:cap]):
            d.strategy, d.hero = AI_VIDEO, i == 0
            d.reason = f"{'HERO ' if i == 0 else ''}image→video motion — {d.reason}"

    # ── HYBRID: a visual carrying on-screen graphics too ─────────────────────
    for s in scenes:
        d = by_id[s.id]
        if d.strategy in (AI_IMAGE, REAL) and any(
                o.type in ("stat", "headline") for o in s.overlays):
            if d.strategy == AI_IMAGE:
                d.strategy = HYBRID
                d.reason = f"AI base + on-screen graphics — {d.reason}"

    for s in scenes:
        d = by_id[s.id]
        s.visual.strategy = d.strategy
        s.visual.decision_reason = d.reason

    counts = {k: 0 for k in (DATAVIZ, REAL, AI_IMAGE, AI_VIDEO, MOTION_GFX,
                             BRANDED, HYBRID)}
    for d in decisions:
        counts[d.strategy] += 1
    pct = {k: round(100 * c / n, 1) for k, c in counts.items()}
    return MixReport(decisions=decisions, counts=counts, pct=pct)
