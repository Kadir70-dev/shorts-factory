"""
Sound design stage — MICRO-EDITING / RETENTION SFX.

Two jobs:
  1. `ensure_pack()` synthesizes an 8-piece premium documentary SFX palette into
     data/assets/sfx/*.wav with ffmpeg (self-contained — no external sample
     packs). Generated once, content stable, reused forever.
  2. `add_sound_design()` runs AFTER captions/assets (durations are final) and
     fills `graph.sfx` with a RESTRAINED, role-based cue list. Both renderers
     (Remotion `SfxLayer`, pure-ffmpeg `_mux`) consume that one list, so sound
     design is identical across render paths.

Editorial doctrine (documentary, NOT meme):
  - SFX fire on EMPHASIS MOMENTS only — never per word, never on every cut.
  - The HOOK gets the strongest sound design (a deep bass impact on reveal).
  - A big stat/number gets a SUBTLE soft impact + ring.
  - A real SECTION transition (fade / whip / slide — not a plain cut) gets a
    whoosh/swipe. Plain cuts stay silent (avoids the spammy feeling).
  - The CTA gets a subtle riser building into it.
  - Everything sits well under the narration (low gains + music ducking) so
    speech is always clear.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from ..config import settings
from ..schemas.scene import SceneGraph, SfxCue

SFX_DIR = "assets/sfx"          # under data/ — same path both renderers resolve
_EXT = "wav"

# name -> (lavfi source, optional -af filter chain). Kept comma-free inside
# expressions so ffmpeg doesn't mis-split the filtergraph.
_SOUNDS: dict[str, tuple[str, str]] = {
    # short bright click — a tick, used sparingly
    "pop":    ("aevalsrc=0.7*sin(2*PI*900*t)*exp(-t*38):d=0.12", ""),
    # clean decaying tone — the "number landed" ring
    "ring":   ("aevalsrc=0.6*sin(2*PI*1320*t)*exp(-t*6):d=0.6", ""),
    # two-partial bell ding
    "bell":   ("aevalsrc=0.5*(sin(2*PI*784*t)+0.5*sin(2*PI*1568*t))*exp(-t*4):d=0.9", ""),
    # tight mid thud — soft impact under a stat
    "hit":    ("aevalsrc=0.8*sin(2*PI*150*t)*exp(-t*15):d=0.3", ""),
    # deep sub impact — the hook reveal
    "bass":   ("aevalsrc=0.9*sin(2*PI*55*t)*exp(-t*6.5):d=0.8", "lowpass=f=200"),
    # building noise sweep — into the CTA
    "riser":  ("anoisesrc=d=1.1:c=pink:a=0.55",
               "highpass=f=320:poles=2,afade=t=in:st=0:d=1.0,afade=t=out:st=1.0:d=0.1"),
    # airy noise swell — a real section transition
    "whoosh": ("anoisesrc=d=0.5:c=pink:a=0.7",
               "bandpass=f=1100:width_type=h:w=1600,afade=t=in:st=0:d=0.18,afade=t=out:st=0.24:d=0.24"),
    # fast bright swipe — a whip/slide pivot
    "swipe":  ("anoisesrc=d=0.28:c=white:a=0.6",
               "highpass=f=1800:poles=2,afade=t=in:st=0:d=0.07,afade=t=out:st=0.12:d=0.14"),
}


def sfx_path(sound: str) -> Path:
    return settings().data_dir / SFX_DIR / f"{sound}.{_EXT}"


async def ensure_pack() -> None:
    """Synthesize any missing SFX files (idempotent). Failures are swallowed —
    a missing effect simply doesn't play; it never breaks a render."""
    out_dir = settings().data_dir / SFX_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    todo = [(n, src, af) for n, (src, af) in _SOUNDS.items()
            if not sfx_path(n).exists()]
    await asyncio.gather(*[_synth(n, src, af) for n, src, af in todo],
                         return_exceptions=True)


async def _synth(name: str, src: str, af: str) -> None:
    out = sfx_path(name)
    args = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", src]
    if af:
        args += ["-af", af]
    args += ["-ac", "2", "-ar", "44100", "-y", str(out)]
    proc = await asyncio.create_subprocess_exec(*args, stderr=asyncio.subprocess.PIPE)
    await proc.communicate()


# --------------------------------------------------------------------------- #
# Cue builder — the restrained "documentary micro-editor"
# --------------------------------------------------------------------------- #
# Per-role gains (dB). Strong on the hook, whisper-quiet on accents — the
# narration is the star, SFX is seasoning.
_G_HOOK_BASS = -7.0
_G_STAT_HIT = -13.0
_G_STAT_RING = -15.0
_G_WHOOSH = -12.0
_G_SWIPE = -13.0
_G_RISER = -15.0


def build_cues(graph: SceneGraph) -> list[SfxCue]:
    scenes = graph.scenes
    n = len(scenes)
    if n == 0:
        return []

    starts: list[float] = []
    acc = 0.0
    for s in scenes:
        starts.append(acc)
        acc += s.duration_sec
    total = acc

    cues: list[SfxCue] = []

    def emit(sound: str, at: float, gain: float, role: str) -> None:
        cues.append(SfxCue(sound=sound, at=max(0.0, round(min(at, total), 3)),
                           gain_db=gain, role=role))

    for i, s in enumerate(scenes):
        start = starts[i]
        is_hook = i == 0
        is_cta = i == n - 1
        has_stat = any(o.type == "stat" and o.sub for o in s.overlays)

        # HOOK — strongest sound design: a deep bass impact on the reveal.
        if is_hook:
            emit("bass", start + 0.06, _G_HOOK_BASS, "hook")

        # SECTION TRANSITION — only a real animated transition, never a plain
        # cut (that restraint is what keeps it documentary, not meme-y). Lands
        # just BEFORE the scene so it carries the eye across.
        elif s.transition_in in ("fade",):
            emit("whoosh", start - 0.12, _G_WHOOSH, "transition")
        elif s.transition_in in ("whip", "slide_l"):
            emit("swipe", start - 0.10, _G_SWIPE, "transition")

        # BIG STAT — a subtle soft impact + ring as the number lands. Skip on
        # the hook (the bass already owns that beat — no stacking).
        if has_stat and not is_hook:
            emit("hit", start + 0.12, _G_STAT_HIT, "stat")
            emit("ring", start + 0.18, _G_STAT_RING, "stat")

        # CTA — a subtle riser building INTO the closing beat.
        if is_cta and not is_hook:
            emit("riser", max(start - 0.8, starts[i - 1] if i > 0 else 0.0),
                 _G_RISER, "cta")

    cues.sort(key=lambda c: c.at)
    return cues


async def add_sound_design(graph: SceneGraph) -> SceneGraph:
    """Pipeline stage: ensure the SFX pack exists and attach the cue list.
    Runs after captions/assets (scene durations are final by then)."""
    await ensure_pack()
    graph.sfx = build_cues(graph)
    return graph
