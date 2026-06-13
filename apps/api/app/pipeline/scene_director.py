"""
Smart Scene Decision Engine (Phase 5.5) — the brain of the cinematic visual layer.

For EVERY scene it decides, automatically, ONE primary visual strategy:

  A) real       — real moving footage (Pexels/Pixabay).            [the default]
  B) ai_image   — AI cinematic documentary still + Ken Burns motion.
  C) motion_gfx — chart / animated graphics (manim).
  D) hybrid     — AI base composited WITH on-screen graphics (overlays/stat).

  (ai_video is disabled in the local CPU pipeline — never allocated.)

It is a PURE function (no I/O, deterministic) so it is cheap to dry-run and easy
to verify. The asset resolver (`broll.py`) consumes the decision and still keeps
real footage as the safety net for every AI beat — so a generation failure or a
missing provider key degrades to real footage; it never breaks the render.

Two things drive the decision:

1. SUBJECT ELIGIBILITY (what the beat is ABOUT) — the Phase-5.5 doctrine:
   USE AI for things a camera can't truthfully shoot or that look fake as stock:
     • HISTORY      — recreations, presidents, scandals, secret meetings, old
                      newspapers, dark corridors, White House atmosphere.
     • POLITICS     — symbolic/dramatic election imagery, campaign tension,
                      red-vs-blue mood, cinematic White House.
     • BUSINESS/TECH— billionaire / luxury boardroom / monopoly / AI-future mood.
     • ABSTRACT     — inflation fear, broken middle class, anxiety, hidden
                      systems, money psychology.
   DO NOT use AI for everyday realism — restaurants, grocery stores, gas
   stations, normal streets, voting lines, crowds. Those MUST be real footage
   (AI versions read as uncanny stock slop). These are hard `force_real`.

2. MIX BUDGET — across the whole short we target the local ratio:
     real ~70% · ai_image ~20% · motion_gfx 5–10% · ai_video 0%
   We turn the ratio into integer caps for this scene count and allocate the AI
   slots to the highest-affinity eligible beats, so a typical 4–6 scene short
   gets ~1 AI image, ~0–1 chart, and the rest real.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..config import settings
from ..schemas.scene import Scene, SceneGraph
from ..schemas.video_spec import VideoSpec

# strategy labels (mirror schema Visual.strategy)
REAL = "real"
AI_IMAGE = "ai_image"
AI_VIDEO = "ai_video"
MOTION_GFX = "motion_gfx"
HYBRID = "hybrid"

# Local-only visual-mix target (fractions of the timeline). AI VIDEO is disabled
# for the stable CPU pipeline, so its budget is folded into real footage + AI
# stills: real footage is the backbone, local AI images are the cinematic
# seasoning on beats a camera can't truthfully shoot, charts fill the rest.
#   ~70% real footage · ~20% local AI images · 5–10% charts · 0% AI video
MIX_TARGET: dict[str, tuple[float, float]] = {
    REAL: (0.65, 0.78),         # ~70% (absorbs the old AI-video budget)
    AI_IMAGE: (0.15, 0.25),     # ~20% cinematic stills (Ken Burns motion)
    MOTION_GFX: (0.05, 0.10),   # 5–10% charts / motion graphics
}

# OPT-IN image-to-video band (Picsart). Allocated ONLY when
# settings().enable_image_to_video AND spec.allow_ai_video — otherwise this band
# is ignored and the mix is exactly as above (no ai_video beats). Hard-capped by
# settings().max_ai_video_scenes so a weak laptop / budget never overspends. The
# slots come out of the AI-image budget (a still that would have gotten Ken Burns
# instead gets real cinematic motion), so real footage stays the backbone.
AI_VIDEO_BAND: tuple[float, float] = (0.10, 0.20)   # ~15% of the timeline, when ON

# --- subject taxonomy ------------------------------------------------------- #
# AI-eligible buckets. A scene matching one of these is a candidate for an AI
# image/video — the "cinematic seasoning" beats real footage can't serve.
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

# Everyday-realism subjects that MUST stay real footage (hard veto on AI).
# Phase-5.5: restaurants, grocery, gas, streets, voting lines, crowds.
_FORCE_REAL: list[str] = [
    # NOTE: no bare "server " — it false-matches computer servers (cyber/tech
    # recreations). Restaurant context is covered by waiter/waitress/diner/menu.
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

# Niche-level lean: history/politics/business niches are AI-friendlier overall;
# facts/finance lean real (they live on everyday cost-of-living realism).
_NICHE_AI_LEAN: dict[str, float] = {
    "usa_history": 1.0,
    "usa_politics": 0.7,
    "usa_election": 0.7,
    "usa_business": 0.7,
    "usa_finance": 0.3,
    "usa_facts": 0.2,
    # Cybercrime is recreation-heavy: leaked tables, login pages, exposure moments
    # rarely exist as real footage → lean AI for the exact-event recreations.
    "cybersecurity": 0.85,
}


@dataclass
class Decision:
    """The engine's verdict for one scene (also written onto scene.visual)."""

    scene_id: str
    strategy: str                 # real / ai_image / ai_video / motion_gfx / hybrid
    reason: str                   # human-readable WHY (verification artifact)
    ai_eligible: bool             # subject qualifies for AI at all
    force_real: bool              # everyday realism — AI vetoed
    score: float                  # AI affinity (higher = stronger AI candidate)
    category: str = ""            # which AI subject bucket matched (if any)
    hero: bool = False            # the single highest-emotion ai_video beat (→ hero model)


@dataclass
class MixReport:
    """Summary of one short's visual mix vs the Phase-5.5 target."""

    decisions: list[Decision]
    counts: dict[str, int] = field(default_factory=dict)
    pct: dict[str, float] = field(default_factory=dict)


def _scene_text(s: Scene) -> str:
    v = s.visual
    return " ".join([
        s.narration, v.visual_intent, v.query, " ".join(v.broll_keywords),
        " ".join(s.keywords), " ".join(o.text for o in s.overlays),
    ]).lower()


def _classify(s: Scene, niche: str) -> Decision:
    """Score one scene's AI affinity from its subject, role and niche."""
    text = _scene_text(s)
    v = s.visual

    force_real = any(k in text for k in _FORCE_REAL)

    # which AI buckets does the subject hit, and how strongly
    matched: list[str] = []
    hits = 0
    for cat, kws in _AI_SUBJECTS.items():
        n = sum(1 for k in kws if k in text)
        if n:
            matched.append(cat)
            hits += n
    category = matched[0] if matched else ""

    score = 0.0
    bits: list[str] = []

    # Director explicitly asked for an AI motion insert — strongest signal.
    director_ai_video = v.type == "ai_video"
    if director_ai_video:
        score += 5.0
        bits.append("Director flagged ai_video")

    # editorial role
    if v.scene_visual_type == "abstract":
        score += 3.0
        bits.append("abstract concept (no literal footage)")
    elif v.scene_visual_type == "dramatic":
        score += 1.5
        bits.append("dramatic/high-tension beat")

    # subject buckets
    if matched:
        score += 1.5 * len(matched) + 0.4 * hits
        bits.append(f"subject={'+'.join(matched)}")

    # niche lean
    lean = _NICHE_AI_LEAN.get(niche, 0.4)
    score += lean
    if lean >= 0.7:
        bits.append(f"{niche.replace('usa_','')} niche leans cinematic")

    # everyday realism vetoes AI no matter the score
    if force_real:
        bits = ["everyday realism → real footage (AI would look fake)"]
        score = -10.0

    reason = "; ".join(bits) or "literal subject → real footage"
    ai_eligible = bool(matched or director_ai_video or
                       v.scene_visual_type == "abstract") and not force_real
    return Decision(
        scene_id=s.id,
        strategy=REAL,                 # provisional; allocator may upgrade
        reason=reason,
        ai_eligible=ai_eligible,
        force_real=force_real,
        score=score,
        category=category,
    )


def _cap(n: int, lo: float, hi: float) -> int:
    """Integer slot cap for a mix band over n scenes (round to the band mid)."""
    return int(round(n * (lo + hi) / 2))


def decide(graph: SceneGraph, spec: VideoSpec) -> MixReport:
    """Assign a visual strategy to every scene, enforcing the Phase-5.5 mix.
    Mutates `scene.visual.strategy` / `.decision_reason` and returns a report."""
    scenes = graph.scenes
    n = len(scenes)
    decisions = [_classify(s, graph.meta.niche) for s in scenes]
    by_id = {d.scene_id: d for d in decisions}

    # 1) MOTION GRAPHICS — charts are charts. manim or a data_viz numbers beat.
    gfx_cap = max(1, _cap(n, *MIX_TARGET[MOTION_GFX])) if any(
        s.visual.type == "manim" or s.visual.scene_visual_type == "data_viz"
        for s in scenes
    ) else 0
    gfx_used = 0
    for s in scenes:
        d = by_id[s.id]
        is_chart = s.visual.type == "manim" or s.visual.scene_visual_type == "data_viz"
        if is_chart and gfx_used < gfx_cap:
            d.strategy = MOTION_GFX
            d.reason = "numbers/trend beat → animated chart (motion graphics)"
            gfx_used += 1

    # candidates = AI-eligible scenes not already locked to a chart, best-first
    cands = sorted(
        (by_id[s.id] for s in scenes
         if by_id[s.id].ai_eligible and by_id[s.id].strategy != MOTION_GFX),
        key=lambda d: d.score, reverse=True,
    )

    # 2) AI VIDEO (Picsart image→video) — OPT-IN. Off by default → never allocated
    #    (folded into real + AI images, exactly as the stable CPU pipeline). When
    #    ENABLE_IMAGE_TO_VIDEO=1 and the request allows it, the highest-emotion
    #    eligible beats (hero / dramatic / anime — `cands` is score-sorted) get a
    #    cinematic motion clip, hard-capped by MAX_AI_VIDEO_SCENES. The resolver
    #    still keeps the still + real footage as the safety net, so a failure
    #    degrades gracefully — it never breaks the render.
    cfg = settings()
    vid_used = 0
    if cfg.enable_image_to_video and spec.allow_ai_video and cands:
        vid_cap = min(cfg.max_ai_video_scenes, _cap(n, *AI_VIDEO_BAND))
        vid_cap = max(1, vid_cap) if cfg.max_ai_video_scenes >= 1 else 0
        for d in cands:
            if vid_used >= vid_cap:
                break
            d.strategy = AI_VIDEO
            d.hero = vid_used == 0          # top-scored beat → optional hero model
            tag = "HERO " if d.hero else ""
            d.reason = f"{tag}high-emotion beat → image→video motion — {d.reason}"
            vid_used += 1

    # 3) AI IMAGE — cinematic stills on the best eligible beats (~20%). Guarantees
    #    at least one when an eligible beat remains and images are allowed. Beats
    #    already promoted to ai_video above are excluded here.
    img_cands = [d for d in cands if d.strategy != AI_VIDEO]
    img_cap = _cap(n, *MIX_TARGET[AI_IMAGE]) if spec.allow_ai_image else 0
    if spec.allow_ai_image and img_cands:
        img_cap = max(1, img_cap)

    img_used = 0
    for d in img_cands:
        if img_used >= img_cap:
            break                       # budget spent → remaining beats stay real
        scene = next(s for s in scenes if s.id == d.scene_id)
        has_gfx = any(o.type in ("stat", "headline") for o in scene.overlays)
        # hybrid = AI image that ALSO carries on-screen graphics composited.
        d.strategy = HYBRID if has_gfx else AI_IMAGE
        kind = "hybrid AI image + on-screen graphics" if has_gfx \
            else "AI cinematic documentary image"
        d.reason = f"{kind} — {d.reason}"
        img_used += 1

    # write back onto the scene graph
    for s in scenes:
        d = by_id[s.id]
        s.visual.strategy = d.strategy
        s.visual.decision_reason = d.reason

    counts: dict[str, int] = {REAL: 0, AI_IMAGE: 0, AI_VIDEO: 0,
                              MOTION_GFX: 0, HYBRID: 0}
    for d in decisions:
        counts[d.strategy] += 1
    pct = {k: round(100 * c / n, 1) for k, c in counts.items()} if n else {}
    return MixReport(decisions=decisions, counts=counts, pct=pct)
