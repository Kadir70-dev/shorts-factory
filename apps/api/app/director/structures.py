"""
Story structure library + rotation.

The old pipeline had ONE shape: a fixed 4–7 scene arc, every video, forever. That
is the single strongest "this is automated" signal a channel can emit — a viewer
who watches three uploads has learned the template even if they can't name it.

This module replaces it with a library of nine narrative spines
(config/story_structures.yaml) and a rotation policy:

  * WEIGHTED, SEEDED choice — the seed is derived from the video id, so the same
    short always rebuilds identically (reproducible renders, testable pipeline)
    while different shorts differ.
  * COOLDOWN against the channel's recent history, so structures genuinely take
    turns instead of clustering by luck. Five uploads in a row cannot share a
    spine.
  * NICHE FILTERING — `hidden_strategy` doesn't fire on a history topic.

The chosen structure then drives four things downstream: the Director prompt
(what to write), the sanity gate (how many scenes are valid), the music family,
and the data-viz engine (which beats are `wants_data`).
"""
from __future__ import annotations

import functools
import hashlib
import random
from dataclasses import dataclass, field

import yaml

from ..config import CONFIG_DIR
from .. import state

_FILE = CONFIG_DIR / "story_structures.yaml"
DIMENSION = "structure"


@dataclass(frozen=True)
class Beat:
    role: str
    purpose: str
    words: tuple[int, int] = (10, 22)
    wants_data: bool = False


@dataclass(frozen=True)
class Structure:
    id: str
    name: str
    summary: str
    beats: tuple[Beat, ...]
    scenes: tuple[int, int]
    hook_styles: tuple[str, ...]
    cta_styles: tuple[str, ...]
    music: tuple[str, ...]
    weight: float = 1.0
    niches: tuple[str, ...] = ()

    def allows(self, niche: str) -> bool:
        return not self.niches or niche in self.niches

    def data_roles(self) -> list[str]:
        """Beat roles that should carry a real animated data visualisation."""
        return [b.role for b in self.beats if b.wants_data]

    def word_budget(self) -> tuple[int, int]:
        lo = sum(b.words[0] for b in self.beats)
        hi = sum(b.words[1] for b in self.beats)
        return lo, hi

    def prompt_block(self, scene_count: int, hook_style: str,
                     cta_style: str) -> str:
        """The structure rendered as Director instructions.

        Beats are mapped onto the chosen scene count: when the count exceeds the
        beat list the middle beats expand (never the hook or the CTA — those stay
        single scenes because their jobs are indivisible).
        """
        plan = self.expand(scene_count)
        lines = [
            f"# STORY STRUCTURE FOR THIS SHORT: {self.name}",
            f"{self.summary.strip()}",
            "",
            f"Write EXACTLY {len(plan)} scenes following this spine. Each numbered "
            "beat is one scene, in this order. Do not add, merge or reorder beats.",
            "",
        ]
        for i, beat in enumerate(plan, 1):
            data = ("  ← this beat MUST carry a real, sourced figure; the pipeline "
                    "renders it as a custom animated chart" if beat.wants_data else "")
            lines.append(
                f"  {i}. [{beat.role}] {beat.purpose} "
                f"(~{beat.words[0]}–{beat.words[1]} words){data}")
        lines += [
            "",
            f"HOOK APPROACH: {hook_style}",
            f"CLOSING APPROACH: {cta_style}",
            "",
            "The structure is the SHAPE, not a script template — never announce the "
            "beats ('first, let's look at...'), never number them out loud. The "
            "viewer should feel a story, not a framework.",
        ]
        return "\n".join(lines)

    def expand(self, scene_count: int) -> list[Beat]:
        """Fit the beat list to a scene count by growing/shrinking the middle."""
        beats = list(self.beats)
        n = max(2, int(scene_count))
        if n == len(beats):
            return beats
        if n < len(beats):
            # drop the least load-bearing middles first: prefer keeping data beats
            middle = beats[1:-1]
            middle.sort(key=lambda b: (b.wants_data, b.words[1]))
            drop = len(beats) - n
            dropped = {id(b) for b in middle[:drop]}
            return [b for b in beats if id(b) not in dropped]
        # grow: duplicate the richest middle beats as continuation beats
        extra = n - len(beats)
        middle = sorted(beats[1:-1], key=lambda b: -b.words[1]) or [beats[0]]
        grown = list(beats)
        for i in range(extra):
            src = middle[i % len(middle)]
            grown.insert(
                len(grown) - 1,
                Beat(role=src.role, wants_data=False,
                     purpose=f"Continue the {src.role} beat with a DIFFERENT "
                             f"specific detail — never restate the previous line.",
                     words=src.words),
            )
        return grown


@dataclass
class StructureChoice:
    """What the rotation decided, carried through the pipeline for logging."""
    structure: Structure
    scene_count: int
    hook_style: str
    cta_style: str
    considered: list[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        return self.structure.id

    def prompt_block(self) -> str:
        return self.structure.prompt_block(self.scene_count, self.hook_style,
                                           self.cta_style)


# --------------------------------------------------------------------------- #
# Library
# --------------------------------------------------------------------------- #
@functools.lru_cache(maxsize=1)
def library() -> list[Structure]:
    if not _FILE.exists():
        return []
    raw = yaml.safe_load(_FILE.read_text()) or {}
    out: list[Structure] = []
    for s in raw.get("structures", []) or []:
        beats = tuple(
            Beat(role=str(b.get("role", "context")),
                 purpose=str(b.get("purpose", "")),
                 words=tuple(b.get("words", [10, 22]))[:2],  # type: ignore[arg-type]
                 wants_data=bool(b.get("wants_data", False)))
            for b in s.get("beats", []) or []
        )
        if not beats:
            continue
        scenes = tuple(s.get("scenes", [len(beats), len(beats)]))[:2]
        out.append(Structure(
            id=str(s["id"]), name=str(s.get("name", s["id"])),
            summary=str(s.get("summary", "")), beats=beats,
            scenes=(int(scenes[0]), int(scenes[1])),          # type: ignore[index]
            hook_styles=tuple(s.get("hook_styles", []) or ["Open with the sharpest fact."]),
            cta_styles=tuple(s.get("cta_styles", []) or ["Close with the channel CTA."]),
            music=tuple(s.get("music", []) or ["documentary"]),
            weight=float(s.get("weight", 1.0)),
            niches=tuple(s.get("niches", []) or []),
        ))
    return out


def get(structure_id: str) -> Structure | None:
    return next((s for s in library() if s.id == structure_id), None)


def seed_for(video_id: str, salt: str = "") -> int:
    """Stable per-video seed. Reproducible renders matter: the same short must
    rebuild identically after a crash or a re-run."""
    h = hashlib.sha256(f"{video_id}|{salt}".encode()).hexdigest()
    return int(h[:16], 16)


# --------------------------------------------------------------------------- #
# Rotation
# --------------------------------------------------------------------------- #
def choose(video_id: str, channel_id: str, niche: str,
           forced: str = "", record: bool = True) -> StructureChoice:
    """Pick the structure for one short.

    `forced` (e.g. a preset pinning a structure) bypasses rotation but still
    resolves scene count and hook/CTA style from the seed, so a pinned structure
    still varies between videos.
    """
    lib = library()
    if not lib:
        raise RuntimeError(
            f"no story structures loaded from {_FILE} — the Director cannot "
            "build a short without a narrative spine")

    rng = random.Random(seed_for(video_id, "structure"))
    eligible = [s for s in lib if s.allows(niche)] or lib

    if forced:
        picked = get(forced)
        if picked is None:
            raise ValueError(
                f"unknown story structure {forced!r}; available: "
                f"{', '.join(s.id for s in lib)}")
    else:
        history = state.recent(channel_id, DIMENSION)
        cooldown = state.cooldown_weights([s.id for s in eligible], history)
        weights = [max(1e-4, s.weight * cooldown.get(s.id, 1.0)) for s in eligible]
        picked = rng.choices(eligible, weights=weights, k=1)[0]

    lo, hi = picked.scenes
    choice = StructureChoice(
        structure=picked,
        scene_count=rng.randint(min(lo, hi), max(lo, hi)),
        hook_style=rng.choice(list(picked.hook_styles)),
        cta_style=rng.choice(list(picked.cta_styles)),
        considered=[s.id for s in eligible],
    )
    if record and not forced:
        state.record(channel_id, DIMENSION, picked.id)
    return choice
