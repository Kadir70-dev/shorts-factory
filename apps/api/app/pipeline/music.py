"""
Premium documentary MUSIC engine — the emotional layer, now with real rotation.

The audit's complaint was simple and correct: every Short used the same bed. One
bed per niche meant a viewer who watched three finance videos heard the same
loop three times, which reads as cheap long before anyone consciously notices.

What this module does now:

  1. FIVE FAMILIES — finance, documentary, mystery, corporate, premium — each with
     THREE distinct variants (15 beds). Variants differ in harmony, register and
     movement, not just level, so they are genuinely different cues rather than
     the same pad at a different volume.
  2. ROTATION. The family comes from the variety plan (which the story structure
     influences), and the variant is drawn with a cooldown against this channel's
     recent history — so consecutive uploads cannot share a bed.
  3. SMART ENVELOPE (unchanged in spirit, now beat-aware). The intensity curve
     follows the story structure's beat ROLES rather than mere scene position:
     a `reveal` beat swells wherever it falls, instead of only when it happens to
     be the scene with a stat overlay.

Beds are synthesised with ffmpeg — no licensing exposure, no copyright claims, no
Content ID risk on a monetised channel. A real royalty-free track dropped into the
channel's `music_dir` still wins; the synth is the floor, not the ceiling.

Audio doctrine is unchanged: narration is ALWAYS dominant. The envelope keeps
music low under speech, the renderer's sidechain ducks it further on loud VO, and
top/tail fades keep entries and exits smooth.
"""
from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from pathlib import Path

from .. import state
from ..config import ChannelConfig, settings
from ..director.structures import seed_for
from ..schemas.scene import MusicKeyframe, SceneGraph

BEDS_DIR = "assets/music/beds"        # under data/ — both renderers resolve here
_EXT = "wav"
_BED_SECONDS = 46                     # covers a full Short (<=45s); no looping needed
DIMENSION = "music_bed"


# --------------------------------------------------------------------------- #
# Bed recipes
# --------------------------------------------------------------------------- #
# Each recipe is a small chord of detuned sine partials plus a post chain
# (lowpass for warmth, tremolo for life, aecho for space). Minor and suspended
# voicings read tense; open triads read curious and premium. All low, loopable and
# copyright-free.
#
# NOTE on the filtergraph: commas separate FILTERS, so a comma may never appear
# inside an expression here. Everything below is comma-free by construction.
_BEDS: dict[str, dict] = {
    # ── finance: sparse, low, slightly anxious — Bloomberg at 6pm ────────────
    "finance_a":   {"freqs": [82.41, 110.00, 164.81],
                    "post": "lowpass=f=1200:poles=2,tremolo=f=0.40:d=0.20,"
                            "aecho=0.8:0.6:55:0.20"},
    "finance_b":   {"freqs": [73.42, 110.00, 146.83, 220.00],
                    "post": "lowpass=f=1050:poles=2,tremolo=f=0.28:d=0.26,"
                            "aecho=0.8:0.5:70:0.22"},
    "finance_c":   {"freqs": [98.00, 123.47, 196.00],
                    "post": "lowpass=f=1400:poles=2,tremolo=f=0.55:d=0.18,"
                            "aecho=0.7:0.6:45:0.18"},

    # ── documentary: warm, patient, human ───────────────────────────────────
    "documentary_a": {"freqs": [130.81, 196.00, 261.63],
                      "post": "lowpass=f=1900:poles=2,tremolo=f=0.32:d=0.22,"
                              "aecho=0.8:0.6:80:0.26"},
    "documentary_b": {"freqs": [146.83, 220.00, 293.66, 440.00],
                      "post": "lowpass=f=2100:poles=2,tremolo=f=0.24:d=0.20,"
                              "aecho=0.8:0.5:95:0.24"},
    "documentary_c": {"freqs": [110.00, 164.81, 246.94],
                      "post": "lowpass=f=1700:poles=2,tremolo=f=0.38:d=0.24,"
                              "aecho=0.7:0.6:65:0.28"},

    # ── mystery: dark, cavernous, unresolved ────────────────────────────────
    "mystery_a":   {"freqs": [55.00, 110.00, 130.81, 164.81],
                    "post": "lowpass=f=760:poles=2,tremolo=f=0.18:d=0.30,"
                            "aecho=0.8:0.7:60:0.30"},
    "mystery_b":   {"freqs": [49.00, 98.00, 116.54, 155.56],
                    "post": "lowpass=f=680:poles=2,tremolo=f=0.14:d=0.34,"
                            "aecho=0.8:0.7:110:0.34"},
    "mystery_c":   {"freqs": [61.74, 92.50, 123.47, 185.00],
                    "post": "lowpass=f=840:poles=2,tremolo=f=0.22:d=0.28,"
                            "aecho=0.9:0.7:85:0.32"},

    # ── corporate: steady, competent, forward-moving ────────────────────────
    "corporate_a": {"freqs": [110.00, 164.81, 220.00],
                    "post": "lowpass=f=1500:poles=2,tremolo=f=1.60:d=0.30"},
    "corporate_b": {"freqs": [130.81, 196.00, 261.63, 329.63],
                    "post": "lowpass=f=1800:poles=2,tremolo=f=1.20:d=0.26,"
                            "aecho=0.7:0.5:40:0.16"},
    "corporate_c": {"freqs": [123.47, 185.00, 246.94],
                    "post": "lowpass=f=1650:poles=2,tremolo=f=2.00:d=0.22"},

    # ── premium: bright, expensive, a touch of shimmer ──────────────────────
    "premium_a":   {"freqs": [261.63, 329.63, 392.00, 523.25],
                    "post": "lowpass=f=3000:poles=2,tremolo=f=0.60:d=0.20,"
                            "aecho=0.7:0.6:45:0.25"},
    "premium_b":   {"freqs": [220.00, 329.63, 440.00, 659.26],
                    "post": "lowpass=f=3400:poles=2,tremolo=f=0.44:d=0.18,"
                            "aecho=0.8:0.6:60:0.28"},
    "premium_c":   {"freqs": [196.00, 293.66, 392.00, 587.33],
                    "post": "lowpass=f=2700:poles=2,tremolo=f=0.70:d=0.22,"
                            "aecho=0.7:0.6:52:0.22"},
}

FAMILIES = ["finance", "documentary", "mystery", "corporate", "premium"]


def variants(family: str) -> list[str]:
    return sorted(b for b in _BEDS if b.rsplit("_", 1)[0] == family)


@dataclass(frozen=True)
class MusicPreset:
    """Mix levels for one family. The SHAPE carries the emotion; the levels stay
    low so narration is never fighting the bed."""
    mood: str
    base_gain_db: float               # MIDDLE level — subtle, under narration
    hook_gain_db: float               # stronger emotional entry
    reveal_gain_db: float             # tension rise on a reveal/stat beat
    cta_gain_db: float                # soft uplift to close


_PRESETS: dict[str, MusicPreset] = {
    "finance":     MusicPreset("financial tension · sparse and serious",
                               -23.0, -17.0, -20.0, -19.0),
    "documentary": MusicPreset("warm documentary · patient and human",
                               -22.5, -16.5, -19.5, -18.5),
    "mystery":     MusicPreset("dark ambience · mystery and suspense",
                               -24.0, -17.0, -19.0, -20.0),
    "corporate":   MusicPreset("steady corporate · competent and forward-moving",
                               -22.0, -16.0, -19.0, -19.0),
    "premium":     MusicPreset("premium sheen · expensive and confident",
                               -22.0, -16.0, -19.0, -18.0),
}

# Fallback family per niche, used when no variety plan is supplied.
_NICHE_FAMILY: dict[str, str] = {
    "usa_facts": "documentary",
    "usa_history": "mystery",
    "usa_politics": "corporate",
    "usa_election": "corporate",
    "usa_finance": "finance",
    "usa_business": "premium",
    "cybersecurity": "mystery",
}


def bed_path(bed: str) -> Path:
    return settings().data_dir / BEDS_DIR / f"{bed}.{_EXT}"


async def ensure_beds() -> None:
    """Synthesise any missing beds (idempotent). Failures are swallowed — a
    missing bed just means no music; it never breaks a render."""
    out_dir = settings().data_dir / BEDS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    todo = [b for b in _BEDS if not bed_path(b).exists()]
    if todo:
        print(f"[music] synthesising {len(todo)} bed(s): {', '.join(todo)}",
              flush=True)
    await asyncio.gather(*[_synth_bed(b) for b in todo], return_exceptions=True)


async def _synth_bed(bed: str) -> None:
    recipe = _BEDS[bed]
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
    args = ["ffmpeg", "-hide_banner", "-loglevel", "error", *inputs,
            "-filter_complex", fc, "-map", "[a]", "-y", str(bed_path(bed))]
    proc = await asyncio.create_subprocess_exec(*args, stderr=asyncio.subprocess.PIPE)
    await proc.communicate()


# --------------------------------------------------------------------------- #
# Bed selection
# --------------------------------------------------------------------------- #
def choose_bed(video_id: str, channel_id: str, family: str,
               record: bool = True) -> str:
    """Pick a variant within a family, avoiding this channel's recent beds.

    Recording under the FAMILY-agnostic dimension is deliberate: rotating within
    `finance` while the previous two videos also used `finance` would still sound
    repetitive, so the cooldown is applied across all 15 beds.
    """
    pool = variants(family) or variants("documentary") or list(_BEDS)
    rng = random.Random(seed_for(video_id, "music"))
    history = state.recent(channel_id, DIMENSION)
    weights = state.cooldown_weights(pool, history)
    bed = rng.choices(pool, weights=[max(1e-4, weights[b]) for b in pool], k=1)[0]
    if record:
        state.record(channel_id, DIMENSION, bed)
    return bed


def _user_track(channel: ChannelConfig) -> str | None:
    """Prefer a real royalty-free track the user dropped into the channel's
    music_dir — it upgrades quality over any synthesised bed."""
    d = Path(channel.music_dir)
    if not d.exists():
        return None
    tracks = sorted(p for ext in ("*.mp3", "*.wav", "*.m4a", "*.ogg")
                    for p in d.glob(ext))
    return str(tracks[0]) if tracks else None


# --------------------------------------------------------------------------- #
# Smart timeline envelope
# --------------------------------------------------------------------------- #
_RAMP = 0.45        # seconds of smooth ramp around each scene boundary

# Beat roles that deserve a swell. Driving this off the STRUCTURE's roles rather
# than "does the scene happen to have a stat overlay" is what lets the music
# follow the story instead of following the graphics.
_REVEAL_ROLES = {"reveal", "turn", "evidence", "contrast", "payoff"}
_QUIET_ROLES = {"context", "mechanism"}


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
        role = (s.beat_role or "").lower()
        has_stat = any(o.type == "stat" and o.sub for o in s.overlays) or bool(s.data)

        if i == 0 or role == "hook":
            gain, label = preset.hook_gain_db, "hook"
        elif i == n - 1 or role == "cta":
            gain, label = preset.cta_gain_db, "cta"
        elif role in _REVEAL_ROLES or (not role and has_stat):
            gain, label = preset.reveal_gain_db, "reveal"
        elif role in _QUIET_ROLES:
            gain, label = preset.base_gain_db - 1.0, "middle"
        else:
            gain, label = preset.base_gain_db, "middle"

        # hold the level across the scene; the gap between one scene's end-kf and
        # the next scene's start-kf is the smooth cross-ramp (no abrupt jump).
        if end - start <= 2 * _RAMP:
            kfs.append(MusicKeyframe(at=round((start + end) / 2, 3),
                                     gain_db=gain, role=label))
        else:
            kfs.append(MusicKeyframe(at=round(start + _RAMP, 3),
                                     gain_db=gain, role=label))
            kfs.append(MusicKeyframe(at=round(end - _RAMP, 3),
                                     gain_db=gain, role=label))

    kfs.sort(key=lambda k: k.at)
    return kfs


# --------------------------------------------------------------------------- #
# Stage entrypoint
# --------------------------------------------------------------------------- #
async def add_music(graph: SceneGraph, channel: ChannelConfig,
                    family: str = "") -> SceneGraph:
    """Pipeline stage: pick this video's bed, attach the envelope + fades.

    `family` comes from the variety plan. Without one we fall back to the niche
    default, so the stage still works when called standalone.
    """
    fam = family or graph.variety.get("music_family") or \
        _NICHE_FAMILY.get(channel.niche, "documentary")
    preset = _PRESETS.get(fam, _PRESETS["documentary"])
    await ensure_beds()

    bed = choose_bed(graph.meta.video_id, graph.meta.channel_id, fam)
    src = _user_track(channel) or str(bed_path(bed))

    a = graph.audio
    if Path(src).exists():
        a.music_path = src
    a.music_mood = f"{preset.mood} [{bed}]"
    a.music_gain_db = preset.base_gain_db
    a.music_envelope = build_envelope(graph, preset)
    print(f"[music] {fam} · bed={bed} · {len(a.music_envelope)} keyframes",
          flush=True)
    return graph
