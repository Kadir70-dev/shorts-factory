"""
Visual variety planner — the anti-template layer.

A channel that publishes thousands of Shorts fails not because any one video is
bad but because upload #40 has the same rhythm as #12: same caption animation,
same slow push-in on every shot, same cut on every boundary, same grade, same
sign-off. The eye notices the pattern long before the brain does, and "this is
mass-produced" is the impression that costs a channel its audience and its
Partner Program review.

So every dimension that could ossify into a signature gets planned per video:

    scene count · transition palette · camera motion · zoom style ·
    caption animation · colour grade · CTA shape · music family

Two properties make this trustworthy rather than merely random:

  * DETERMINISTIC. Every choice derives from a seed hashed off the video id, so a
    re-run rebuilds the same short. Randomness that changes under you is
    impossible to debug and impossible to reproduce a bug in.
  * ANTI-REPEAT. Choices are weighted against the channel's recent history
    (`app.state`), so options genuinely take turns. Pure random clusters — five
    consecutive videos sharing a caption style is a perfectly likely coin-flip
    sequence and a perfectly visible pattern.

The variety is bounded by taste, not unbounded: transitions still favour the
documentary hard cut, motion still stays slow, and nothing here can produce a
short that looks like it belongs to a different channel.
"""
from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .. import state
from ..brand.theme import BrandTheme
from ..director.structures import StructureChoice, seed_for
from ..schemas.scene import SceneGraph

# --------------------------------------------------------------------------- #
# Option pools
# --------------------------------------------------------------------------- #
# Transition PALETTES, not individual transitions: a video picks a vocabulary and
# stays inside it, which is what makes an edit feel authored. Every palette keeps
# the documentary discipline — `cut` dominates, flourishes are punctuation.
TRANSITION_PALETTES: dict[str, dict] = {
    "hard_doc":      {"base": "cut",  "accent": "fade",         "accent_max": 1},
    "soft_doc":      {"base": "fade", "accent": "cut",          "accent_max": 3},
    "dip_black":     {"base": "cut",  "accent": "dip_to_black", "accent_max": 2},
    "push_forward":  {"base": "cut",  "accent": "push_up",      "accent_max": 2},
    "dissolve_essay": {"base": "crossfade", "accent": "cut",    "accent_max": 2},
    "single_pivot":  {"base": "cut",  "accent": "whip",         "accent_max": 1},
}

# Camera MOTION styles. Each maps beat position → motion, so a video has a
# consistent camera language instead of a per-scene coin flip.
MOTION_STYLES: dict[str, list[str]] = {
    "slow_push":    ["zoom_in", "zoom_in", "ken_burns", "zoom_in"],
    "breathe":      ["zoom_in", "zoom_out", "zoom_in", "zoom_out"],
    "lateral":      ["pan_lr", "ken_burns", "pan_lr", "zoom_in"],
    "pull_reveal":  ["zoom_out", "ken_burns", "zoom_out", "zoom_in"],
    "observational": ["ken_burns", "none", "ken_burns", "zoom_in"],
    "mixed_doc":    ["zoom_in", "pan_lr", "zoom_out", "ken_burns"],
}

# How far the camera travels over a shot. The renderer reads this; it is the
# difference between "cinematic" and "a slideshow with a zoom effect".
ZOOM_STYLES: dict[str, float] = {
    "restrained": 0.08,
    "standard": 0.15,
    "assertive": 0.22,
    "drift": 0.11,
}

# Closing shapes. The structure supplies the closing IDEA; this supplies its form.
CTA_STYLES: dict[str, str] = {
    "question": "End on an open question that invites the next video.",
    "lesson": "End on the portable lesson, stated plainly.",
    "forward": "End by pointing at what to watch for next.",
    "callback": "End by calling back to the hook and resolving it.",
    "invitation": "End by inviting the viewer to follow for the next one.",
}

MUSIC_FAMILIES = ["finance", "documentary", "mystery", "corporate", "premium"]

# Dimension names in the rotation ledger.
DIMS = ("caption_animation", "transitions", "motion", "zoom", "grade",
        "cta_style", "music_family")


@dataclass
class VarietyPlan:
    """One short's creative dice roll. Serialised onto the SceneGraph."""
    seed: int
    caption_animation: str
    transitions: str
    motion: str
    zoom: str
    grade: str
    cta_style: str
    music_family: str
    scene_count: int
    # per-scene assignments, filled by `apply()`
    scene_transitions: list[str] = field(default_factory=list)
    scene_motions: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, str]:
        return {
            "caption_animation": self.caption_animation,
            "transitions": self.transitions,
            "motion": self.motion,
            "zoom": self.zoom,
            "grade": self.grade,
            "cta_style": self.cta_style,
            "music_family": self.music_family,
            "scene_count": str(self.scene_count),
        }

    @property
    def zoom_travel(self) -> float:
        return ZOOM_STYLES.get(self.zoom, 0.15)

    def summary(self) -> str:
        return (f"captions={self.caption_animation} · cuts={self.transitions} · "
                f"camera={self.motion}/{self.zoom} · grade={self.grade} · "
                f"close={self.cta_style} · music={self.music_family}")


# --------------------------------------------------------------------------- #
# Planning
# --------------------------------------------------------------------------- #
def _pick(rng: random.Random, options: list[str], channel_id: str,
          dimension: str) -> str:
    """Weighted pick that demotes whatever this channel used most recently."""
    if not options:
        return ""
    history = state.recent(channel_id, dimension)
    weights = state.cooldown_weights(options, history)
    return rng.choices(options, weights=[max(1e-4, weights[o]) for o in options],
                       k=1)[0]


def freeze(path: Path, p: VarietyPlan) -> None:
    """Pin this job's dice roll to disk."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(p), indent=2))
    except OSError as exc:            # a lost plan only costs a re-roll
        print(f"[variety] could not freeze plan: {exc}", flush=True)


def thaw(path: Path) -> VarietyPlan | None:
    """The pinned plan for an existing job, or None to draw a fresh one.

    Re-rendering a job must not re-roll its creative dice. `_pick` rotates
    through the channel ledger so options take turns ACROSS videos, which means
    a second run of the SAME video got different cuts, camera, grade and zoom —
    every scene clip then had to be rebuilt because the render context had
    legitimately changed. Restoring the plan also leaves the ledger untouched,
    so a re-render no longer consumes a rotation slot meant for the next video.
    """
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    try:
        return VarietyPlan(**data)
    except TypeError:                 # plan shape changed under an old job
        return None


def plan(video_id: str, channel_id: str, theme: BrandTheme,
         structure: StructureChoice | None = None,
         record: bool = True) -> VarietyPlan:
    """Draw one video's variety plan."""
    rng = random.Random(seed_for(video_id, "variety"))
    caption_pool = list(theme.captions.get("animations") or ["word_pop"])
    grade_pool = theme.grade_names() or ["neutral_doc"]

    # The structure gets first say on music: a mystery spine shouldn't open on a
    # corporate bed. Its preference is a filter, not a lock, so rotation still
    # applies within what fits.
    music_pool = MUSIC_FAMILIES
    if structure is not None:
        preferred = [m for m in structure.structure.music if m in MUSIC_FAMILIES]
        if preferred:
            music_pool = preferred

    p = VarietyPlan(
        seed=seed_for(video_id, "variety"),
        caption_animation=_pick(rng, caption_pool, channel_id, "caption_animation"),
        transitions=_pick(rng, list(TRANSITION_PALETTES), channel_id, "transitions"),
        motion=_pick(rng, list(MOTION_STYLES), channel_id, "motion"),
        zoom=_pick(rng, list(ZOOM_STYLES), channel_id, "zoom"),
        grade=_pick(rng, grade_pool, channel_id, "grade"),
        cta_style=_pick(rng, list(CTA_STYLES), channel_id, "cta_style"),
        music_family=_pick(rng, music_pool, channel_id, "music_family"),
        scene_count=structure.scene_count if structure else 5,
    )
    if record:
        state.record_many(channel_id, {d: getattr(p, d) for d in DIMS})
    return p


def apply(graph: SceneGraph, p: VarietyPlan) -> SceneGraph:
    """Write the plan onto the scenes.

    Respects what the Director deliberately authored: a scene that already carries
    a non-default transition keeps it (that was an editorial choice), and chart
    beats never get camera motion because a chart is already animating.
    """
    rng = random.Random(p.seed ^ 0x5EED)
    n = len(graph.scenes)
    palette = TRANSITION_PALETTES.get(p.transitions, TRANSITION_PALETTES["hard_doc"])
    motions = MOTION_STYLES.get(p.motion, MOTION_STYLES["slow_push"])

    # Accent transitions go on real section boundaries, chosen from the middle of
    # the video — never the hook (which must land instantly) and never the close.
    accent_slots: list[int] = []
    if n > 2 and palette["accent_max"] > 0:
        candidates = list(range(1, n - 1))
        rng.shuffle(candidates)
        accent_slots = sorted(candidates[:min(palette["accent_max"], len(candidates))])

    p.scene_transitions, p.scene_motions = [], []
    for i, scene in enumerate(graph.scenes):
        # An authored non-default transition is an editorial decision — a chapter
        # break dipping to black, a whip into a reveal — and the variety planner
        # must not roll it away. `cut` is the schema default, i.e. "no opinion",
        # so those scenes are the ones the palette is free to dress.
        authored = scene.transition_in != "cut"
        if i == 0:
            trans = "cut"                       # the hook never fades in
        elif authored:
            trans = scene.transition_in
        elif i in accent_slots:
            trans = palette["accent"]
        else:
            trans = palette["base"]
        scene.transition_in = trans             # type: ignore[assignment]
        p.scene_transitions.append(trans)

        if scene.visual.type == "dataviz":
            motion = "none"                     # the chart supplies the motion
        else:
            motion = motions[i % len(motions)]
        scene.visual.motion = motion            # type: ignore[assignment]
        p.scene_motions.append(motion)

    graph.variety = p.as_dict()
    return graph
