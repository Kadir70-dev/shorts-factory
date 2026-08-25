#!/usr/bin/env python3
"""K70 Finance Shorts -- Day 06, Short A: "Why Credit Card Minimum
Payments Keep You in Debt". First VERTICAL (1080x1920) K70 V2 build.

4 beats / 3 modes (Voxel bookends the story, matching the proven K70
master pattern):
  1. Voxel (Blender)      -- John opens the bill, apartment scene
  2. Synfig Vector (REAL synfig.exe) -- balance/minimum/interest breakdown
  3. 3D Motion Graphics (Blender) -- "minimum only" vs "pay more" comparison
  4. Voxel (Blender)      -- return beat, resolute close

No engine changes beyond one additive, backward-compatible parameter
(_voxel_human_script.py's camera now takes optional "sensor_fit", default
"AUTO" == old behavior). Camera framing for 9:16 was calibrated empirically
(see scratch test renders) -- portrait needs a much longer lens/greater
distance than the existing 16:9 benchmarks used.

    .venv-win/Scripts/python.exe scripts/build_fin_d06_a.py
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
SYNFIG = ROOT / "tools/k70_scene_engine/vendor/synfig_win/extracted/bin/synfig.exe"
GEN_VECTOR_D06A = ROOT / "tools/k70_scene_engine/synfig/gen_vector_d06a.py"
MUSIC_BED = ROOT / "data/assets/music/beds/premium_a.wav"
SFX = ROOT / "data/assets/sfx"

JOB_DIR = ROOT / "data" / "jobs" / "vid_fin_d06_a"
SHOTS_DIR = JOB_DIR / "shots"
AUDIO_DIR = JOB_DIR / "audio"
SHOTS_DIR.mkdir(parents=True, exist_ok=True)
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

W, H, FPS = 1080, 1920, 24
XFADE_DUR = 0.5


def winpath(p: Path) -> str:
    return str(p).replace("\\", "/")


def eng(samples=32):
    return {"engine": "BLENDER_EEVEE_NEXT", "samples": samples, "width": W, "height": H}


def render_blender(script_name: str, spec: dict, tag: str, timeout: int = 900) -> Path:
    out_dir = SHOTS_DIR / tag
    spec["render"]["output_dir"] = winpath(out_dir)
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


def render_synfig_vector(duration_sec: float) -> Path:
    sif_path = JOB_DIR / "vector_d06a.sif"
    subprocess.run([sys.executable, str(GEN_VECTOR_D06A), str(sif_path)], check=True)
    seq_dir = SHOTS_DIR / "vector" / "frames"
    seq_dir.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [str(SYNFIG), "-i", str(sif_path), "-o", str(seq_dir / "frame.png"),
         "-w", str(W), "-h", str(H), "--begin-time", "0s 0f", "--end-time", f"{int(duration_sec)}s 0f", "-T", "4"],
        capture_output=True, text=True, timeout=600,
    )
    n_frames = len(list(seq_dir.glob("frame.*.png")))
    combined = proc.stdout + proc.stderr
    if "DONE" not in combined or n_frames < 50:
        raise RuntimeError(f"Synfig render FAILED/incomplete ({n_frames} frames):\n{combined[-3000:]}")
    print(f"  [vector/synfig] rendered {n_frames} frames -> {seq_dir}")
    out = SHOTS_DIR / "vector.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-framerate", str(FPS), "-i", str(seq_dir / "frame.%04d.png"),
         "-vf", f"scale={W}:{H}", "-pix_fmt", "yuv420p", "-r", str(FPS), "-an", str(out)],
        capture_output=True, text=True, check=True,
    )
    return out


def _done(p: Path, min_size: int = 1024) -> bool:
    return p.exists() and p.stat().st_size > min_size


async def synthesize_narration(lines: list[str]) -> list[Path | None]:
    from app.voice.manager import VoiceManager
    out_paths = []
    missing = [(i, t) for i, t in enumerate(lines) if not _done(AUDIO_DIR / f"line_{i:02d}.wav")]
    voice = None
    if missing:
        voice = VoiceManager()
        try:
            voice.require_voice()
        except Exception as e:
            print(f"  [voice] unavailable, skipping narration for missing lines: {e}")
            voice = None
    for i, text in enumerate(lines):
        out = AUDIO_DIR / f"line_{i:02d}.wav"
        if _done(out):
            print(f"  [resume] line_{i:02d} already present, skipping")
            out_paths.append(out)
            continue
        if voice is None:
            out_paths.append(None)
            continue
        try:
            await voice.synthesize(text, out)
            out_paths.append(out)
            print(f"  [voice] line_{i:02d}: {text[:50]!r} -> {out.name}")
        except Exception as e:
            print(f"  [voice] line_{i:02d} FAILED: {e}")
            out_paths.append(None)
    return out_paths


PLAN = [
    dict(id="voxel_open", style="VOXEL_CINEMATIC", duration=8.0,
         narration="That tiny minimum payment on your credit card bill? "
                    "It's designed to make the debt feel affordable.",
         renderer="Blender 4.2.4 LTS EEVEE_NEXT, K70 voxel_human rig (apartment scene, reused as-is)",
         specialized_tool=False),
    dict(id="vector", style="PREMIUM_2D_VECTOR", duration=13.0,
         narration="Say your balance is five thousand dollars. The minimum might be just two percent "
                    "-- about one hundred dollars. At a hypothetical twenty-two percent interest rate, "
                    "roughly ninety-two dollars of that hundred goes to interest -- leaving only about "
                    "eight dollars to actually reduce what you owe.",
         renderer="Synfig Studio 1.5.5 (real synfig.exe CLI, github.com/synfig/synfig)",
         specialized_tool=True),
    dict(id="motion_graphics", style="3D_MOTION_GRAPHICS", duration=16.0,
         narration="Keep paying only the minimum, and payoff can stretch past a decade -- with total "
                    "interest adding up to more than the original balance. Pay more each month, and "
                    "both the timeline and the interest shrink fast.",
         renderer="Blender 4.2.4 LTS EEVEE_NEXT, K70 3D motion graphics system",
         specialized_tool=False),
    dict(id="voxel_return", style="VOXEL_CINEMATIC", duration=6.0,
         narration="The minimum keeps the account moving. Paying more is what attacks the balance.",
         renderer="Blender 4.2.4 LTS EEVEE_NEXT, K70 voxel_human rig (apartment scene, reused as-is)",
         specialized_tool=False),
]


def main() -> None:
    t0 = time.time()
    print("K70 Finance D06 Short A -- Credit Card Minimum Payments (1080x1920)")
    clips: dict[str, Path] = {}

    # ---- Beat 1: voxel_open -- John at the table with the bill ---- #
    beat1_out = SHOTS_DIR / "voxel_open.mp4"
    if _done(beat1_out):
        print("  [resume] voxel_open.mp4 already present, skipping beat 1")
        clips["voxel_open"] = beat1_out
    else:
        spec = {
            "scene_type": "apartment",
            "characters": [{"role": "john", "location": [0.6, 1.3, 0], "rotation_z_deg": 200,
                            "animation": {"type": "sit_point", "params": {"length": 40}}}],
            "camera": {"location": [0.6, -6.5, 1.35], "look_at": [0.6, 1.0, 1.15]},
            "lens": 175, "sun_energy": 2.0,
            "n_frames": 16, "frame_range": [0, 55], "render": eng(),
        }
        d = render_blender("_voxel_human_script.py", spec, "voxel_open")
        clips["voxel_open"] = frames_to_clip(d, beat1_out, 16, 8.0)

    # ---- Beat 2: vector -- real Synfig balance/minimum/interest breakdown ---- #
    beat2_out = SHOTS_DIR / "vector.mp4"
    if _done(beat2_out):
        print("  [resume] vector.mp4 already present, skipping beat 2")
        clips["vector"] = beat2_out
    else:
        clips["vector"] = render_synfig_vector(13.0)

    # ---- Beat 3: motion_graphics -- minimum-only vs pay-more comparison ---- #
    beat3_out = SHOTS_DIR / "motion_graphics.mp4"
    if _done(beat3_out):
        print("  [resume] motion_graphics.mp4 already present, skipping beat 3")
        clips["motion_graphics"] = beat3_out
    else:
        spec = {
            "growth_stage": {"spacing": 1.0, "milestones": [
                {"label": "MIN ONLY", "value_norm": 1.0, "f_grow": 20},
                {"label": "PAY MORE", "value_norm": 0.35, "f_grow": 20},
            ]},
            "camera_keyframes": [
                {"frame": 30, "location": [0.0, -8.2, 1.7], "look_at": [0, 0.6, 1.05]},
                {"frame": 110, "location": [0.0, -7.2, 1.55], "look_at": [0, 0.6, 1.0]},
            ],
            "lens": 60, "fstop": 2.2, "n_frames": 20, "frame_range": [30, 110],
            "render": eng(28),
        }
        d = render_blender("_motion_graphics_3d_script.py", spec, "motion_graphics")
        clips["motion_graphics"] = frames_to_clip(d, beat3_out, 20, 16.0)

    # ---- Beat 4: voxel_return -- standing, resolute, paying more ---- #
    beat4_out = SHOTS_DIR / "voxel_return.mp4"
    if _done(beat4_out):
        print("  [resume] voxel_return.mp4 already present, skipping beat 4")
        clips["voxel_return"] = beat4_out
    else:
        spec = {
            "scene_type": "apartment",
            "characters": [{"role": "john", "location": [0.6, 1.3, 0], "rotation_z_deg": 200,
                            "animation": {"type": "point", "params": {"start": 0, "length": 50}}}],
            "camera": {"location": [0.6, -6.5, 1.35], "look_at": [0.6, 1.0, 1.25]},
            "lens": 175, "sun_energy": 2.0,
            "n_frames": 10, "frame_range": [0, 50], "render": eng(),
        }
        d = render_blender("_voxel_human_script.py", spec, "voxel_return")
        clips["voxel_return"] = frames_to_clip(d, beat4_out, 10, 6.0)

    order = [s["id"] for s in PLAN]
    durations = [s["duration"] for s in PLAN]

    # ---- Narration ---- #
    narration_paths = asyncio.run(synthesize_narration([s["narration"] for s in PLAN]))
    for s, p in zip(PLAN, narration_paths):
        s["narration_audio"] = str(p) if p else None

    # ---- Video: xfade chain ---- #
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

    # ---- narration/foley offsets ---- #
    narr_offsets = []
    cum = 0.0
    for i, d_ in enumerate(durations):
        narr_offsets.append(cum)
        cum += d_ - (XFADE_DUR if i < len(durations) - 1 else 0)

    foley_events = []  # (path, offset_sec, volume)
    for i in range(1, len(order)):
        foley_events.append((SFX / "whoosh.wav", narr_offsets[i], 0.45))
    mg_start = narr_offsets[order.index("motion_graphics")]
    foley_events.append((SFX / "riser.wav", max(0.0, mg_start - 1.0), 0.3))
    foley_events.append((SFX / "hit.wav", mg_start + durations[order.index("motion_graphics")] * 0.55, 0.4))

    # ---- audio mix: narration + music + foley ---- #
    audio_inputs = []
    audio_filter = []
    amix_labels = []
    idx = 0
    for i, p in enumerate(narration_paths):
        if p is None:
            continue
        audio_inputs += ["-i", str(p)]
        lbl = f"n{idx}"
        delay_ms = int(max(0, narr_offsets[i]) * 1000)
        audio_filter.append(f"[{idx}:a]adelay=delays={delay_ms}:all=1,volume=1.6[{lbl}]")
        amix_labels.append(f"[{lbl}]")
        idx += 1
    for path, offset, vol in foley_events:
        audio_inputs += ["-i", str(path)]
        lbl = f"f{idx}"
        delay_ms = int(max(0, offset) * 1000)
        audio_filter.append(f"[{idx}:a]adelay=delays={delay_ms}:all=1,volume={vol}[{lbl}]")
        amix_labels.append(f"[{lbl}]")
        idx += 1
    music_idx = idx
    audio_inputs += ["-stream_loop", "-1", "-i", str(MUSIC_BED)]
    audio_filter.append(f"[{music_idx}:a]atrim=0:{final_video_duration:.3f},volume=0.14[music]")
    amix_labels.append("[music]")
    audio_filter.append(f"{''.join(amix_labels)}amix=inputs={len(amix_labels)}:duration=longest:normalize=0[aout]")
    final_audio = JOB_DIR / "audio_mix.mp3"
    subprocess.run(
        ["ffmpeg", "-y", *audio_inputs, "-filter_complex", ";".join(audio_filter),
         "-map", "[aout]", "-t", f"{final_video_duration:.3f}", str(final_audio)],
        capture_output=True, text=True, check=True,
    )

    # ---- mux ---- #
    final_mp4 = JOB_DIR / "final.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(video_only), "-i", str(final_audio),
         "-c:v", "libx264", "-crf", "18", "-c:a", "aac", "-shortest", str(final_mp4)],
        capture_output=True, text=True, check=True,
    )

    # ---- contact sheet ---- #
    n_thumbs = 9
    thumbs = []
    from PIL import Image
    for i in range(n_thumbs):
        t = final_video_duration * (i + 0.5) / n_thumbs
        tp = JOB_DIR / f"thumb_{i}.jpg"
        subprocess.run(["ffmpeg", "-y", "-ss", f"{t:.2f}", "-i", str(final_mp4), "-vframes", "1", str(tp)],
                      capture_output=True, text=True)
        thumbs.append(Image.open(tp))
    cols, rows = 3, 3
    tw, th = 270, 480
    sheet = Image.new("RGB", (tw * cols, th * rows), (20, 20, 20))
    for i, im in enumerate(thumbs):
        sheet.paste(im.resize((tw, th)), ((i % cols) * tw, (i // cols) * th))
    sheet.save(JOB_DIR / "contact_sheet.jpg", quality=92)

    # ---- metadata.json ---- #
    total_build_time = round(time.time() - t0, 1)
    dur_actual = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                 "-of", "default=noprint_wrappers=1:nokey=1", str(final_mp4)],
                                capture_output=True, text=True).stdout.strip()
    metadata = {
        "title": "Why Credit Card Minimum Payments Keep You in Debt",
        "resolution": f"{W}x{H}", "fps": FPS,
        "duration_sec": float(dur_actual) if dur_actual else None,
        "segments": [{"id": s["id"], "style": s["style"], "duration_sec": s["duration"],
                      "renderer": s["renderer"], "specialized_tool": s["specialized_tool"],
                      "narration": s["narration"]} for s in PLAN],
        "modes_used": sorted(set(s["style"] for s in PLAN)),
        "specialized_tools_used": ["Synfig Studio 1.5.5"],
        "music_bed": str(MUSIC_BED),
        "foley_assets": sorted(set(p.name for p, *_ in foley_events)),
        "narration_engine": "app.voice.manager.VoiceManager",
        "fact_check_notes": "22% APR and 2% minimum are explicitly labeled hypothetical/illustrative; "
                            "$92 interest / $8 principal are calculated from those stated assumptions "
                            "(5000*0.22/12=91.67), not invented; payoff-time and total-interest claims "
                            "in beat 3 are kept qualitative (no invented year count or dollar figure).",
        "total_build_time_sec": total_build_time,
    }
    (JOB_DIR / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print(f"\nFINAL: {final_mp4} ({dur_actual}s)")
    print(f"CONTACT SHEET: {JOB_DIR / 'contact_sheet.jpg'}")
    print(f"METADATA: {JOB_DIR / 'metadata.json'}")
    print(f"Total build time: {total_build_time}s")


if __name__ == "__main__":
    main()
