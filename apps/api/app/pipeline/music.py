"""
Premium documentary MUSIC engine (Phase 5) — the emotional cinematic layer.

Three jobs:
  1. Per-niche PRESETS — each K70 bucket gets its own scoring mood (curiosity,
     dark/suspense, newsroom, financial tension, premium tech).
  2. Copyright-safe BEDS — ambient pads synthesized with ffmpeg into
     data/assets/music/beds/<mood>.wav (no licensed tracks; generated once). If
     the channel's `music_dir` already has a real royalty-free track, that wins.
  3. SMART TIMELINE envelope — an intensity curve over the video: a stronger
     emotional entry on the HOOK, low/subtle under the MIDDLE narration, a
     tension RISE on reveal/stat beats, and a soft UPLIFT into the CTA. Stored as
     `audio.music_envelope` keyframes; both renderers ramp between them (smooth
     swells, never abrupt cuts).

Audio doctrine: narration is ALWAYS dominant. The envelope keeps music low under
speech; the renderer's sidechain ducking dips it further on loud VO; top/tail
fades keep entries and exits smooth. Documentary, never meme/TikTok.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from ..config import ChannelConfig, settings
from ..schemas.scene import MusicKeyframe, SceneGraph

BEDS_DIR = "assets/music/beds"        # under data/ — both renderers resolve here
_EXT = "wav"
_BED_SECONDS = 46                     # covers a full Short (<=45s); no looping needed


@dataclass(frozen=True)
class MusicPreset:
    mood: str                         # human label (shown in logs / metadata)
    bed: str                          # synthesized bed recipe key
    base_gain_db: float               # MIDDLE level — subtle, under narration
    hook_gain_db: float               # stronger emotional entry
    reveal_gain_db: float             # tension rise on a stat/reveal beat
    cta_gain_db: float                # soft uplift to close


# Per-niche scoring. Levels stay low (narration dominant); the SHAPE carries the
# emotion. Dark/finance sit a touch quieter & moodier; newsroom/business a touch
# more present.
_PRESETS: dict[str, MusicPreset] = {
    "usa_facts":    MusicPreset("subtle curiosity · light documentary tension",
                                "curiosity", -23.0, -17.0, -20.0, -19.0),
    "usa_history":  MusicPreset("cinematic dark ambience · mystery / suspense",
                                "dark", -24.0, -17.0, -19.0, -20.0),
    "usa_politics": MusicPreset("urgent but serious · newsroom documentary",
                                "newsroom", -22.0, -16.0, -19.0, -19.0),
    "usa_election": MusicPreset("urgent but serious · newsroom documentary",
                                "newsroom", -22.0, -16.0, -19.0, -19.0),
    "usa_finance":  MusicPreset("Bloomberg · financial tension",
                                "finance", -23.0, -17.0, -20.0, -19.0),
    "usa_business": MusicPreset("premium intelligent tech / business",
                                "business", -22.0, -16.0, -19.0, -18.0),
    "cybersecurity": MusicPreset("dark cinematic cybercrime · suspense / dread",
                                 "dark", -24.0, -17.0, -19.0, -20.0),
}
_DEFAULT = _PRESETS["usa_finance"]


# Ambient-pad recipes: a small chord of detuned sine partials + a post chain
# (lowpass for warmth, slow tremolo for life, aecho for cinematic space). Minor
# chords read tense/serious; brighter triads read curious/premium. All low,
# loopable, copyright-free. `freqs` are Hz; commas live only between list items
# (never inside an ffmpeg expr), so the filtergraph stays clean.
_BEDS: dict[str, dict] = {
    # low A-minor drone, cavernous — dark history / suspense
    "dark":      {"freqs": [55.00, 110.00, 130.81, 164.81],
                  "post": "lowpass=f=760:poles=2,tremolo=f=0.18:d=0.30,aecho=0.8:0.7:60:0.30"},
    # bright C-major pad, gentle — curious, light
    "curiosity": {"freqs": [261.63, 329.63, 392.00],
                  "post": "lowpass=f=2200:poles=2,tremolo=f=0.50:d=0.25,aecho=0.7:0.6:50:0.20"},
    # A-minor with a faint pulse — urgent newsroom
    "newsroom":  {"freqs": [110.00, 164.81, 220.00],
                  "post": "lowpass=f=1500:poles=2,tremolo=f=1.6:d=0.30"},
    # sparse low-E minor — financial tension
    "finance":   {"freqs": [82.41, 110.00, 164.81],
                  "post": "lowpass=f=1200:poles=2,tremolo=f=0.40:d=0.20,aecho=0.8:0.6:55:0.20"},
    # clean bright triad + shimmer — premium tech/business
    "business":  {"freqs": [261.63, 329.63, 392.00, 523.25],
                  "post": "lowpass=f=3000:poles=2,tremolo=f=0.60:d=0.20,aecho=0.7:0.6:45:0.25"},
}


def bed_path(mood: str) -> Path:
    return settings().data_dir / BEDS_DIR / f"{mood}.{_EXT}"


async def ensure_beds() -> None:
    """Synthesize any missing niche beds (idempotent). Failures are swallowed —
    a missing bed just means no music; it never breaks a render."""
    out_dir = settings().data_dir / BEDS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    todo = [m for m in _BEDS if not bed_path(m).exists()]
    await asyncio.gather(*[_synth_bed(m) for m in todo], return_exceptions=True)


async def _synth_bed(mood: str) -> None:
    recipe = _BEDS[mood]
    freqs = recipe["freqs"]
    n = len(freqs)
    inputs: list[str] = []
    for f in freqs:
        inputs += ["-f", "lavfi", "-i", f"sine=frequency={f}:duration={_BED_SECONDS}"]
    labels = "".join(f"[{i}:a]" for i in range(n))
    vol = 0.5 / n                      # sum n sines, keep peak well under clipping
    fc = (f"{labels}amix=inputs={n}:normalize=0,"
          f"volume={vol:.3f},{recipe['post']},"
          f"afade=t=in:st=0:d=2.5,afade=t=out:st={_BED_SECONDS - 3}:d=3,"
          f"aformat=sample_rates=44100:channel_layouts=stereo[a]")
    args = (["ffmpeg", "-hide_banner", "-loglevel", "error", *inputs,
             "-filter_complex", fc, "-map", "[a]", "-y", str(bed_path(mood))])
    proc = await asyncio.create_subprocess_exec(*args, stderr=asyncio.subprocess.PIPE)
    await proc.communicate()


# --------------------------------------------------------------------------- #
# Smart timeline envelope
# --------------------------------------------------------------------------- #
_RAMP = 0.45        # seconds of smooth ramp around each scene boundary


def build_envelope(graph: SceneGraph, preset: MusicPreset) -> list[MusicKeyframe]:
    """Per-scene target level → keyframes that HOLD within a scene and RAMP at
    boundaries. Hook strong, middle subtle, reveal rises, CTA soft uplift."""
    scenes = graph.scenes
    n = len(scenes)
    if n == 0:
        return []

    starts, acc = [], 0.0
    for s in scenes:
        starts.append(acc)
        acc += s.duration_sec

    kfs: list[MusicKeyframe] = []
    for i, s in enumerate(scenes):
        start, end = starts[i], starts[i] + s.duration_sec
        has_stat = any(o.type == "stat" and o.sub for o in s.overlays)
        if i == 0:
            gain, role = preset.hook_gain_db, "hook"
        elif i == n - 1:
            gain, role = preset.cta_gain_db, "cta"
        elif has_stat:
            gain, role = preset.reveal_gain_db, "reveal"
        else:
            gain, role = preset.base_gain_db, "middle"

        # hold the level across the scene; the gap between one scene's end-kf and
        # the next scene's start-kf is the smooth cross-ramp (no abrupt jump).
        if end - start <= 2 * _RAMP:
            kfs.append(MusicKeyframe(at=round((start + end) / 2, 3), gain_db=gain, role=role))
        else:
            kfs.append(MusicKeyframe(at=round(start + _RAMP, 3), gain_db=gain, role=role))
            kfs.append(MusicKeyframe(at=round(end - _RAMP, 3), gain_db=gain, role=role))

    kfs.sort(key=lambda k: k.at)
    return kfs


# --------------------------------------------------------------------------- #
# Stage entrypoint
# --------------------------------------------------------------------------- #
def _user_track(channel: ChannelConfig) -> str | None:
    """Prefer a real royalty-free track the user dropped into the channel's
    music_dir (upgrades quality over the synthesized bed)."""
    d = Path(channel.music_dir)
    if not d.exists():
        return None
    beds = sorted([p for ext in ("*.mp3", "*.wav", "*.m4a", "*.ogg")
                   for p in d.glob(ext)])
    return str(beds[0]) if beds else None


async def add_music(graph: SceneGraph, channel: ChannelConfig) -> SceneGraph:
    """Pipeline stage: choose the niche bed, attach the smart envelope + fades.
    Runs after assets (scene durations are final). Narration stays dominant."""
    preset = _PRESETS.get(channel.niche, _DEFAULT)
    await ensure_beds()
    src = _user_track(channel) or str(bed_path(preset.bed))

    a = graph.audio
    a.music_path = src if Path(src).exists() else a.music_path
    a.music_mood = preset.mood
    a.music_gain_db = preset.base_gain_db
    a.music_envelope = build_envelope(graph, preset)
    return graph
