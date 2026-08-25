#!/usr/bin/env python3
"""K70 Visual Engine V2 -- 60-second MASTER INTEGRATION BENCHMARK.

ONE continuous story ("Why the first $100,000 feels impossible") told
across all 9 visual modes as different cinematic languages inside a
single documentary, not a 9-style showcase. Reuses every existing style
engine (voxel/vector/collage/clay/2.5D/isometric/sketch, all proven in
prior gold benchmarks) plus ONE new engine (3D Motion Graphics) and the
existing real-footage/voice/music pipelines. See
visual_director_decisions.json (written by this script) for the explicit
semantic-purpose/mode/reason/transition record per beat.

    .venv-win/Scripts/python.exe scripts/build_v2_master_60s.py
"""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BLENDER = ROOT / "tools/k70_scene_engine/.blender_portable/blender-4.2.4-windows-x64/blender.exe"
BDIR = ROOT / "tools/k70_scene_engine/blender"
PROCGEN_CITY_BLEND = ROOT / "tools/k70_voxel_v2/renders/procgen_test_city.blend"
MUSIC_BED = ROOT / "data/assets/music/beds/premium_a.wav"

JOB_DIR = ROOT / "data" / "jobs" / "k70_v2_master_60s"
SHOTS_DIR = JOB_DIR / "shots"
AUDIO_DIR = JOB_DIR / "audio"
SHOTS_DIR.mkdir(parents=True, exist_ok=True)
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

W, H, FPS = 1920, 1080, 24
XFADE_DUR = 0.5


def eng(samples=28):
    return {"engine": "BLENDER_EEVEE_NEXT", "samples": samples, "width": W, "height": H}


def render_blender(script_name: str, spec: dict, tag: str, timeout: int = 900) -> Path:
    out_dir = SHOTS_DIR / tag
    spec["render"]["output_dir"] = str(out_dir)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(spec, f)
        args_path = f.name
    proc = subprocess.run(
        [str(BLENDER), "--background", "--python", str(BDIR / script_name), "--", args_path],
        capture_output=True, text=True, timeout=timeout,
    )
    Path(args_path).unlink(missing_ok=True)
    if "_RENDER_OK" not in proc.stdout:
        raise RuntimeError(f"segment {tag} failed:\nSTDOUT:\n{proc.stdout[-3000:]}\nSTDERR:\n{proc.stderr[-2000:]}")
    print(f"  [{tag}] rendered -> {out_dir}")
    return out_dir


def frames_to_clip(frames_dir: Path, out_mp4: Path, n_frames: int, duration_sec: float) -> Path:
    """Two-stage encode: variable source fps derived from n_frames/duration
    (the permanently-fixed pattern from the fps=10 bug fix), THEN a fixed
    24fps re-encode of EXACT target duration so every segment lands on a
    consistent timeline for the xfade chain below."""
    fps = n_frames / duration_sec
    tmp = out_mp4.with_suffix(".raw.mp4")
    subprocess.run(
        ["ffmpeg", "-y", "-framerate", str(fps), "-i", str(frames_dir / "frame_%03d.png"),
         "-vf", f"scale={W}:{H}", "-pix_fmt", "yuv420p", str(tmp)],
        capture_output=True, text=True, check=True,
    )
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(tmp), "-t", str(duration_sec), "-r", str(FPS),
         "-vf", f"scale={W}:{H}", "-pix_fmt", "yuv420p", "-an", str(out_mp4)],
        capture_output=True, text=True, check=True,
    )
    tmp.unlink(missing_ok=True)
    return out_mp4


async def fetch_real_footage(duration_sec: float) -> Path:
    from app.pipeline import broll
    terms = ["american city street commuting morning workers walking downtown"]
    path = await broll._video(terms, duration_sec, 0, query_text="",
                              rank_key="k70_v2_master_60s:real_footage")
    if path is None:
        path = await broll._image(terms, 0, query_text="",
                                  rank_key="k70_v2_master_60s:real_footage_img")
        if path is None:
            raise RuntimeError("no real footage/image resolved")
        out = SHOTS_DIR / "real_footage.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-loop", "1", "-i", str(path), "-t", str(duration_sec),
             "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                    f"zoompan=z='min(zoom+0.0015,1.08)':d=125:s={W}x{H}",
             "-pix_fmt", "yuv420p", "-r", str(FPS), str(out)],
            capture_output=True, text=True, check=True,
        )
        return out, False
    out = SHOTS_DIR / "real_footage.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(path), "-t", str(duration_sec),
         "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}",
         "-pix_fmt", "yuv420p", "-r", str(FPS), "-an", str(out)],
        capture_output=True, text=True, check=True,
    )
    return out, True


async def synthesize_narration(lines: list[dict]) -> list[Path | None]:
    from app.voice.manager import VoiceManager
    voice = VoiceManager()
    try:
        voice.require_voice()
    except Exception as e:
        print(f"  [voice] unavailable, skipping narration: {e}")
        return [None] * len(lines)
    out_paths = []
    for i, ln in enumerate(lines):
        out = AUDIO_DIR / f"line_{i:02d}.wav"
        try:
            await voice.synthesize(ln["narration"], out)
            out_paths.append(out)
            print(f"  [voice] line_{i:02d}: {ln['narration'][:50]!r} -> {out.name}")
        except Exception as e:
            print(f"  [voice] line_{i:02d} FAILED: {e}")
            out_paths.append(None)
    return out_paths


# ==================================================================== #
# SEGMENT SPECS
# ==================================================================== #

SEGMENTS = []  # filled in build_segment_plan()


def build_segment_plan():
    return [
        dict(id="voxel_open", style="VOXEL_CINEMATIC", duration=10.0, n_frames=18,
            purpose="Open the story like a movie: establish John and his world.",
            narration="Building your first one hundred thousand dollars can feel painfully slow.",
            reason="Story/character action -> Voxel is the hero storytelling mode per the brief."),
        dict(id="real_footage", style="REAL_FOOTAGE", duration=6.0, n_frames=None,
            purpose="Ground the story in the real world John actually lives in.",
            narration="Because before your money can grow, life gets paid first.",
            reason="Real-world evidence beat; motivated by a walking-city match-cut from the voxel street shot."),
        dict(id="vector", style="PREMIUM_2D_VECTOR", duration=7.0, n_frames=16,
            purpose="Explain where John's income actually goes.",
            narration="Income arrives. Rent, food, transport and bills take their share. What's left is small.",
            reason="Simple financial explanation -> Premium 2D Vector, per the brief's default mapping."),
        dict(id="isometric", style="ISOMETRIC_MINIATURE", duration=7.0, n_frames=16,
            purpose="Zoom out from John's wallet to the whole economic system.",
            narration="Zoom out. John is one part of a bigger system -- money moving between employer, landlord, and bank.",
            reason="System/economy/money-flow beat -> Isometric Miniature, per the brief's default mapping."),
        dict(id="sketch", style="HAND_DRAWN_SKETCH", duration=6.0, n_frames=14,
            purpose="Make the compounding math concrete and memorable.",
            narration="Ten thousand at eight percent is eight hundred a year. A hundred thousand -- eight thousand.",
            reason="Formula/complex concept -> Hand-drawn sketch, per the brief's default mapping."),
        dict(id="clay", style="CLAY_MINIATURE", duration=6.0, n_frames=14,
            purpose="Give compounding a physical, tactile feeling.",
            narration="Small savings barely move. But as the pile grows, each new addition gets bigger.",
            reason="Physical metaphor -> Clay/Miniature, per the brief's default mapping; the sketch's drawn "
                  "dollar figure becomes this pile's first block (motivated transition, not a generic cut)."),
        dict(id="collage", style="PAPER_COLLAGE", duration=6.0, n_frames=14,
            purpose="Place John's story in a larger historical/editorial financial context.",
            narration="This isn't new. Markets, banks and paychecks have shaped families for generations.",
            reason="History/news/archival context -> Paper Collage, per the brief's default mapping."),
        dict(id="illustrated_25d", style="ILLUSTRATED_2_5D", duration=6.0, n_frames=14,
            purpose="Return to John emotionally before the climax.",
            narration="For John, this was never just about numbers -- it's the house, the future.",
            reason="Emotional/abstract beat -> 2.5D Illustrated, per the brief's default mapping."),
        dict(id="motion_graphics", style="3D_MOTION_GRAPHICS", duration=4.0, n_frames=10,
            purpose="Deliver the climax: the milestone that changes everything.",
            narration="Ten. Twenty five. Fifty. Seventy five. One hundred thousand.",
            reason="Hard numbers made spatial/dimensional for maximum climax weight, not a flat text card."),
        dict(id="voxel_return", style="VOXEL_CINEMATIC", duration=4.0, n_frames=10,
            purpose="Close the story where it opened -- same John, same world.",
            narration="The first hundred thousand is the hardest part.",
            reason="Return to the hero storytelling mode so every intermediate style reads as an explanation "
                  "INSIDE John's story, not a separate video."),
    ]


def main() -> None:
    t0 = time.time()
    print("K70 V2 MASTER -- 60s integration benchmark")
    plan = build_segment_plan()
    clips: dict[str, Path] = {}

    # ---- 1. voxel_open: street walk, reusing the proven full-combo look ---- #
    spec = {
        "scene_type": "street",
        "lighting_preset": "golden_hour", "hdri_strength": 0.9,
        "characters": [{"role": "john", "location": [0, -2.2, 0], "rotation_z_deg": 0,
                        "animation": {"type": "walk", "params": {"length": 24, "n_cycles": 3, "stride_deg": 27, "forward_dist": 4.0}}}],
        "camera_keyframes": [
            {"frame": 0, "location": [-5.5, -4.5, 1.5], "look_at": [0, -1.8, 0.9]},
            {"frame": 72, "location": [-4.2, 2.0, 1.7], "look_at": [0, 2.2, 0.9]},
        ],
        "dof": True, "fstop": 2.5, "lens": 35, "show_bank_facade": True,
        "procgen_city_blend": str(PROCGEN_CITY_BLEND), "procgen_location": [0, 34, 0],
        "procgen_scale": 0.10, "procgen_max_buildings": 20,
        "n_frames": 18, "frame_range": [0, 72], "render": eng(),
    }
    d = render_blender("_voxel_human_script.py", spec, "voxel_open")
    clips["voxel_open"] = frames_to_clip(d, SHOTS_DIR / "voxel_open.mp4", 18, 10.0)

    # ---- 2. real_footage ---- #
    raw, is_video = asyncio.run(fetch_real_footage(6.0))
    clips["real_footage"] = raw
    plan[1]["is_real_video"] = is_video

    # ---- 3. vector: income/expense waterfall ---- #
    spec = {
        "gesture_start": 6, "gesture_length": 44, "push_in": True, "ortho_scale": 4.6,
        "bars": [
            {"label": "INCOME", "h": 0.95, "color": [0.20, 0.55, 0.30]},
            {"label": "RENT", "h": 0.55, "color": [0.75, 0.30, 0.28]},
            {"label": "FOOD", "h": 0.40, "color": [0.75, 0.40, 0.28]},
            {"label": "TRANSPORT", "h": 0.30, "color": [0.75, 0.50, 0.28]},
            {"label": "BILLS", "h": 0.35, "color": [0.75, 0.55, 0.28]},
            {"label": "LEFT", "h": 0.15, "color": [0.85, 0.70, 0.15]},
        ],
        "n_frames": 16, "frame_range": [0, 50],
        "render": {"engine": "BLENDER_EEVEE_NEXT", "samples": 32, "width": W, "height": H},
    }
    d = render_blender("_vector_2d_script.py", spec, "vector")
    clips["vector"] = frames_to_clip(d, SHOTS_DIR / "vector.mp4", 16, 7.0)

    # ---- 4. isometric: employer -> john -> landlord/business/bank ---- #
    spec = {
        "entities": [
            {"name": "employer", "kind": "employer", "location": [-1.6, 1.2, 0]},
            {"name": "worker", "kind": "worker", "location": [-1.6, -0.6, 0]},
            {"name": "bank", "kind": "bank", "location": [0.2, 1.2, 0]},
            {"name": "business", "kind": "business", "location": [1.8, -0.4, 0]},
            {"name": "investor", "kind": "investor", "location": [0.2, -1.4, 0]},
            {"name": "house", "kind": "house", "location": [-0.2, -2.6, 0]},
        ],
        "roads": [[-1.6, 0.6, -1.6, -0.2], [-1.0, 1.2, -0.2, 1.2], [0.2, 0.6, 0.2, -0.6],
                 [0.2, -0.9, 0.2, -1.0], [-0.2, -1.8, -0.2, -2.2]],
        "flows": [
            {"from": [-1.6, 1.5, 0.3], "to": [-1.6, -0.3, 0.15], "f_start": 4, "f_end": 22, "color": [0.75, 0.6, 0.2]},
            {"from": [-1.6, -0.3, 0.15], "to": [-0.2, -2.3, 0.4], "f_start": 25, "f_end": 42, "color": [0.65, 0.25, 0.22]},
            {"from": [-1.6, -0.3, 0.15], "to": [1.8, -0.6, 0.4], "f_start": 25, "f_end": 46, "color": [0.55, 0.42, 0.8]},
            {"from": [1.8, -0.6, 0.4], "to": [0.2, 1.0, 0.4], "f_start": 48, "f_end": 62, "color": [0.20, 0.55, 0.28]},
        ],
        "lighting_preset": "exterior_day", "hdri_strength": 1.0,
        "yaw_deg": 40, "ortho_scale": 6.3, "look_at": [0, -0.4, 0.2], "orbit_deg": 18,
        "n_frames": 16, "frame_range": [0, 62], "render": eng(24),
    }
    d = render_blender("_isometric_miniature_script.py", spec, "isometric")
    clips["isometric"] = frames_to_clip(d, SHOTS_DIR / "isometric.mp4", 16, 7.0)

    # ---- 5. sketch: compounding formula ---- #
    spec = {
        "lines": [
            {"text": "$10,000 x 8% = $800", "y": 0.6, "size": 0.42, "f_start": 2, "f_end": 26},
            {"text": "$100,000 x 8% = $8,000", "y": -0.6, "size": 0.42, "f_start": 30, "f_end": 54},
        ],
        "ortho_scale": 6.4, "n_frames": 14, "frame_range": [0, 58], "render": eng(32),
    }
    d = render_blender("_sketch_script.py", spec, "sketch")
    clips["sketch"] = frames_to_clip(d, SHOTS_DIR / "sketch.mp4", 14, 6.0)

    # ---- 6. clay: growing savings pile ---- #
    spec = {
        "growth_stage": {"f_each": 9, "n_blocks": 6},
        "camera_keyframes": [
            {"frame": 0, "location": [1.5, -1.5, 0.95], "look_at": [0, 0, 0.25]},
            {"frame": 54, "location": [1.1, -1.15, 1.05], "look_at": [0, 0, 0.35]},
        ],
        "lens": 65, "fstop": 2.0, "n_frames": 14, "frame_range": [0, 54], "render": eng(28),
    }
    d = render_blender("_clay_miniature_script.py", spec, "clay")
    clips["clay"] = frames_to_clip(d, SHOTS_DIR / "clay.mp4", 14, 6.0)

    # ---- 7. collage: editorial context ---- #
    spec = {
        "stage": {"f_bills": 8, "f_doc": 22, "f_house": 38},
        "camera_keyframes": [
            {"frame": 0, "location": [0.4, -2.6, 1.6], "look_at": [-0.1, 1.5, 1.0]},
            {"frame": 54, "location": [0.0, -1.9, 1.35], "look_at": [-0.1, 1.3, 0.95]},
        ],
        "lens": 45, "fstop": 2.2, "n_frames": 14, "frame_range": [0, 54], "render": eng(28),
    }
    d = render_blender("_paper_collage_script.py", spec, "collage")
    clips["collage"] = frames_to_clip(d, SHOTS_DIR / "collage.mp4", 14, 6.0)

    # ---- 8. 2.5D: emotional return to John ---- #
    spec = {
        "gesture_start": 8, "gesture_length": 40,
        "camera_keyframes": [
            {"frame": 0, "location": [0.2, -3.4, 1.3], "look_at": [0, 1.5, 1.0]},
            {"frame": 54, "location": [0.0, -2.8, 1.15], "look_at": [0, 1.2, 0.9]},
        ],
        "lens": 42, "fstop": 2.0, "n_frames": 14, "frame_range": [0, 54], "render": eng(28),
    }
    d = render_blender("_illustrated_25d_script.py", spec, "illustrated_25d")
    clips["illustrated_25d"] = frames_to_clip(d, SHOTS_DIR / "illustrated_25d.mp4", 14, 6.0)

    # ---- 9. 3D motion graphics: the climax ---- #
    spec = {
        "growth_stage": {"spacing": 0.62, "milestones": [
            {"label": "$10K", "value_norm": 0.10, "f_grow": 6},
            {"label": "$25K", "value_norm": 0.25, "f_grow": 13},
            {"label": "$50K", "value_norm": 0.50, "f_grow": 20},
            {"label": "$75K", "value_norm": 0.75, "f_grow": 27},
            {"label": "$100K", "value_norm": 1.0, "f_grow": 34},
        ]},
        "camera_keyframes": [
            {"frame": 0, "location": [0.0, -2.6, 1.0], "look_at": [0, 0.6, 0.4]},
            {"frame": 36, "location": [0.9, -1.3, 1.4], "look_at": [0.5, 0.6, 1.0]},
        ],
        "lens": 50, "fstop": 2.2, "n_frames": 10, "frame_range": [0, 36], "render": eng(28),
    }
    d = render_blender("_motion_graphics_3d_script.py", spec, "motion_graphics")
    clips["motion_graphics"] = frames_to_clip(d, SHOTS_DIR / "motion_graphics.mp4", 10, 4.0)

    # ---- 10. voxel_return: John reaches the house ---- #
    spec = {
        "scene_type": "house", "house_location": [0, 2.3, 0], "house_scale": 1.0,
        "lighting_preset": "golden_hour", "hdri_strength": 1.0,
        "characters": [{"role": "john", "location": [0, -1.0, 0], "rotation_z_deg": -25,
                        "animation": {"type": "idle", "params": {"length": 40}}}],
        "camera_keyframes": [
            {"frame": 0, "location": [-2.6, -3.2, 1.4], "look_at": [0, 0.3, 0.9]},
            {"frame": 40, "location": [-5.2, -6.5, 2.0], "look_at": [0, 0.7, 1.0]},
        ],
        "dof": True, "fstop": 2.5, "lens": 35, "n_frames": 10, "frame_range": [0, 40], "render": eng(),
    }
    d = render_blender("_voxel_human_script.py", spec, "voxel_return")
    clips["voxel_return"] = frames_to_clip(d, SHOTS_DIR / "voxel_return.mp4", 10, 4.0)

    order = [s["id"] for s in plan]
    for s in plan:
        s["clip"] = str(clips[s["id"]])

    # ---- Narration ---- #
    narration_paths = asyncio.run(synthesize_narration(plan))
    for s, p in zip(plan, narration_paths):
        s["narration_audio"] = str(p) if p else None

    # ---- Assemble video with xfade crossfades ---- #
    durations = [s["duration"] for s in plan]
    offsets = []
    cum = 0.0
    for i, d_ in enumerate(durations):
        cum += d_
        if i < len(durations) - 1:
            offsets.append(cum - XFADE_DUR * (i + 1))
    inputs = []
    for sid in order:
        inputs += ["-i", str(clips[sid])]
    filter_parts = []
    prev_label = "0:v"
    running_total = durations[0]
    for i in range(1, len(order)):
        out_label = f"v{i}" if i < len(order) - 1 else "vout"
        offset = running_total - XFADE_DUR
        filter_parts.append(
            f"[{prev_label}][{i}:v]xfade=transition=fade:duration={XFADE_DUR}:offset={offset:.3f}[{out_label}]")
        running_total = running_total + durations[i] - XFADE_DUR
        prev_label = out_label
    filter_complex = ";".join(filter_parts)
    video_only = JOB_DIR / "video_only.mp4"
    subprocess.run(
        ["ffmpeg", "-y", *inputs, "-filter_complex", filter_complex, "-map", "[vout]",
         "-pix_fmt", "yuv420p", "-r", str(FPS), str(video_only)],
        capture_output=True, text=True, check=True,
    )
    final_video_duration = running_total
    print(f"  [assemble] video_only duration ~{final_video_duration:.2f}s")

    # ---- Audio: narration placed at segment starts + looped music bed ---- #
    narr_offsets = []
    cum = 0.0
    for i, d_ in enumerate(durations):
        narr_offsets.append(cum)
        cum += d_ - (XFADE_DUR if i < len(durations) - 1 else 0)
    audio_inputs = []
    audio_filter = []
    valid_idx = 0
    amix_labels = []
    for i, (s, off) in enumerate(zip(plan, narr_offsets)):
        if s["narration_audio"]:
            audio_inputs += ["-i", s["narration_audio"]]
            lbl = f"a{valid_idx}"
            delay_ms = int(max(0, off) * 1000)
            # all=1 broadcasts the single delay to every channel regardless
            # of whether the narration clip is mono or stereo -- the
            # channel-count-specific "X|X" form errors on mono input.
            audio_filter.append(f"[{valid_idx}:a]adelay=delays={delay_ms}:all=1,volume=1.6[{lbl}]")
            amix_labels.append(f"[{lbl}]")
            valid_idx += 1
    music_input_idx = valid_idx
    audio_inputs += ["-stream_loop", "-1", "-i", str(MUSIC_BED)]
    audio_filter.append(f"[{music_input_idx}:a]atrim=0:{final_video_duration:.3f},volume=0.16[music]")
    amix_labels.append("[music]")
    audio_filter.append(f"{''.join(amix_labels)}amix=inputs={len(amix_labels)}:duration=longest:normalize=0[aout]")
    final_audio = JOB_DIR / "audio_mix.mp3"
    subprocess.run(
        ["ffmpeg", "-y", *audio_inputs, "-filter_complex", ";".join(audio_filter),
         "-map", "[aout]", "-t", f"{final_video_duration:.3f}", str(final_audio)],
        capture_output=True, text=True, check=True,
    )

    # ---- Mux ---- #
    final_mp4 = JOB_DIR / "final.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(video_only), "-i", str(final_audio),
         "-c:v", "copy", "-c:a", "aac", "-shortest", str(final_mp4)],
        capture_output=True, text=True, check=True,
    )

    # ---- Contact sheet (sampled across final timeline) ---- #
    from PIL import Image
    import subprocess as sp
    n_thumbs = 9
    thumbs = []
    for i in range(n_thumbs):
        t = final_video_duration * (i + 0.5) / n_thumbs
        tp = JOB_DIR / f"thumb_{i}.jpg"
        sp.run(["ffmpeg", "-y", "-ss", f"{t:.2f}", "-i", str(final_mp4), "-vframes", "1", str(tp)],
              capture_output=True, text=True)
        thumbs.append(Image.open(tp))
    cols, rows = 3, 3
    tw, th = 480, 270
    sheet = Image.new("RGB", (tw * cols, th * rows), (20, 20, 20))
    for i, im in enumerate(thumbs):
        sheet.paste(im.resize((tw, th)), ((i % cols) * tw, (i // cols) * th))
    sheet.save(JOB_DIR / "contact_sheet.jpg", quality=92)

    # ---- Comparison sheet: one representative frame per mode ---- #
    comp_sources = [
        ("Voxel", SHOTS_DIR / "voxel_open"), ("Real Footage", None),
        ("2D Vector", SHOTS_DIR / "vector"), ("Isometric", SHOTS_DIR / "isometric"),
        ("Sketch", SHOTS_DIR / "sketch"), ("Clay", SHOTS_DIR / "clay"),
        ("Collage", SHOTS_DIR / "collage"), ("2.5D", SHOTS_DIR / "illustrated_25d"),
        ("3D Motion Graphics", SHOTS_DIR / "motion_graphics"),
    ]
    comp_thumbs = []
    for label, d_ in comp_sources:
        if d_ is None:
            tp = JOB_DIR / "comp_realfootage.jpg"
            sp.run(["ffmpeg", "-y", "-ss", "2.5", "-i", str(clips["real_footage"]), "-vframes", "1", str(tp)],
                  capture_output=True, text=True)
            comp_thumbs.append(Image.open(tp))
        else:
            frames = sorted(d_.glob("frame_*.png"))
            comp_thumbs.append(Image.open(frames[len(frames) // 2]))
    comp_sheet = Image.new("RGB", (tw * 3, th * 3 + 30 * 3), (15, 15, 18))
    for i, im in enumerate(comp_thumbs):
        row, col = i // 3, i % 3
        comp_sheet.paste(im.resize((tw, th)), (col * tw, row * (th + 30)))
    comp_sheet.save(JOB_DIR / "comparison_sheet.jpg", quality=92)

    # ---- visual_director_decisions.json ---- #
    decisions = []
    for i, s in enumerate(plan):
        decisions.append({
            "beat": i + 1, "id": s["id"], "visual_mode": s["style"],
            "duration_sec": s["duration"], "semantic_purpose": s["purpose"],
            "selection_reason": s["reason"], "narration": s["narration"],
            "transition_from_previous": "hard cut (opening beat)" if i == 0 else f"{XFADE_DUR}s crossfade",
        })
    (JOB_DIR / "visual_director_decisions.json").write_text(json.dumps(decisions, indent=2), encoding="utf-8")

    # ---- metadata.json ---- #
    total_render_time = round(time.time() - t0, 1)
    dur_actual = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                 "-of", "default=noprint_wrappers=1:nokey=1", str(final_mp4)],
                                capture_output=True, text=True).stdout.strip()
    metadata = {
        "title": "Why The First $100,000 Feels Impossible -- K70 V2 Master Benchmark",
        "resolution": f"{W}x{H}", "fps": FPS,
        "duration_sec": float(dur_actual) if dur_actual else None,
        "segments": [{"id": s["id"], "style": s["style"], "duration_sec": s["duration"]} for s in plan],
        "modes_rendered": sorted(set(s["style"] for s in plan)),
        "music_bed": str(MUSIC_BED), "narration_engine": "app.voice.manager.VoiceManager",
        "total_build_time_sec": total_render_time,
    }
    (JOB_DIR / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print(f"\nFINAL: {final_mp4} ({dur_actual}s)")
    print(f"CONTACT SHEET: {JOB_DIR / 'contact_sheet.jpg'}")
    print(f"COMPARISON SHEET: {JOB_DIR / 'comparison_sheet.jpg'}")
    print(f"DECISIONS: {JOB_DIR / 'visual_director_decisions.json'}")
    print(f"Total build time: {total_render_time}s")


if __name__ == "__main__":
    main()
