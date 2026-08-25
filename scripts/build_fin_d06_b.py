#!/usr/bin/env python3
"""K70 Finance Shorts -- Day 06, Short B: "Why $100 Today Is Worth More
Than $100 Next Year" (Time Value of Money). 1080x1920 vertical.

4 beats / 3 modes:
  1. Clay (Blender)        -- open, single $100 block, the hook
  2. Synfig Vector (REAL)  -- can-earn/invest/grow + brief inflation note
  3. 3D Motion Graphics    -- $100 -> $105 hypothetical 5% example
  4. Clay (Blender)        -- close, grown pile, echoes the payoff

Checkpoint/resume discipline matches build_fin_d06_a.py: every beat and
every narration line is skipped on re-run if its output already exists,
so an interrupted build only re-does what's missing.

    .venv-win/Scripts/python.exe scripts/build_fin_d06_b.py
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
GEN_VECTOR_D06B = ROOT / "tools/k70_scene_engine/synfig/gen_vector_d06b.py"
MUSIC_BED = ROOT / "data/assets/music/beds/premium_a.wav"
SFX = ROOT / "data/assets/sfx"

JOB_DIR = ROOT / "data" / "jobs" / "vid_fin_d06_b"
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


def _done(p: Path, min_size: int = 1024) -> bool:
    return p.exists() and p.stat().st_size > min_size


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
    sif_path = JOB_DIR / "vector_d06b.sif"
    subprocess.run([sys.executable, str(GEN_VECTOR_D06B), str(sif_path)], check=True)
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
    dict(id="clay_open", style="CLAY_MINIATURE", duration=8.0,
         narration="$100 today and $100 one year from now are not economically identical.",
         renderer="Blender 4.2.4 LTS EEVEE_NEXT, K70 clay-material system",
         specialized_tool=False),
    dict(id="vector", style="PREMIUM_2D_VECTOR", duration=13.0,
         narration="Because $100 today can start earning right away, through interest or investment, "
                    "while $100 next year is just getting started. Meanwhile inflation quietly works "
                    "the other way, so waiting has a real cost too.",
         renderer="Synfig Studio 1.5.5 (real synfig.exe CLI, github.com/synfig/synfig)",
         specialized_tool=True),
    dict(id="motion_graphics", style="3D_MOTION_GRAPHICS", duration=11.0,
         narration="Here's a simple, hypothetical example: at a hypothetical five percent return, "
                    "one hundred dollars becomes one hundred five dollars after one year.",
         renderer="Blender 4.2.4 LTS EEVEE_NEXT, K70 3D motion graphics system",
         specialized_tool=False),
    dict(id="clay_close", style="CLAY_MINIATURE", duration=7.0,
         narration="Money has a time value. And time is one of the most powerful variables in finance.",
         renderer="Blender 4.2.4 LTS EEVEE_NEXT, K70 clay-material system",
         specialized_tool=False),
]


def main() -> None:
    t0 = time.time()
    print("K70 Finance D06 Short B -- Time Value of Money (1080x1920)")
    clips: dict[str, Path] = {}

    # ---- Beat 1: clay_open -- a single $100 block ---- #
    beat1_out = SHOTS_DIR / "clay_open.mp4"
    if _done(beat1_out):
        print("  [resume] clay_open.mp4 already present, skipping beat 1")
        clips["clay_open"] = beat1_out
    else:
        spec = {
            "growth_stage": {"f_each": 8, "n_blocks": 1},
            "camera_keyframes": [
                {"frame": 0, "location": [0.9, -2.7, 0.8], "look_at": [0, 0, 0.2]},
                {"frame": 40, "location": [0.8, -2.4, 0.7], "look_at": [0, 0, 0.22]},
            ],
            "lens": 150, "fstop": 1.6, "n_frames": 12, "frame_range": [0, 40],
            "render": eng(28),
        }
        d = render_blender("_clay_miniature_script.py", spec, "clay_open")
        clips["clay_open"] = frames_to_clip(d, beat1_out, 12, 8.0)

    # ---- Beat 2: vector -- real Synfig time-value breakdown ---- #
    beat2_out = SHOTS_DIR / "vector.mp4"
    if _done(beat2_out):
        print("  [resume] vector.mp4 already present, skipping beat 2")
        clips["vector"] = beat2_out
    else:
        clips["vector"] = render_synfig_vector(13.0)

    # ---- Beat 3: motion_graphics -- $100 -> $105 ---- #
    beat3_out = SHOTS_DIR / "motion_graphics.mp4"
    if _done(beat3_out):
        print("  [resume] motion_graphics.mp4 already present, skipping beat 3")
        clips["motion_graphics"] = beat3_out
    else:
        spec = {
            "growth_stage": {"spacing": 1.0, "milestones": [
                {"label": "$100", "value_norm": 0.55, "f_grow": 20},
                {"label": "$105", "value_norm": 0.58, "f_grow": 45},
            ]},
            "camera_keyframes": [
                {"frame": 55, "location": [0.0, -8.2, 1.7], "look_at": [0, 0.6, 1.05]},
                {"frame": 75, "location": [0.0, -7.2, 1.55], "look_at": [0, 0.6, 1.0]},
            ],
            "lens": 65, "fstop": 2.2, "n_frames": 16, "frame_range": [55, 75],
            "render": eng(28),
        }
        d = render_blender("_motion_graphics_3d_script.py", spec, "motion_graphics")
        clips["motion_graphics"] = frames_to_clip(d, beat3_out, 16, 11.0)

    # ---- Beat 4: clay_close -- grown pile, echoes the payoff ---- #
    beat4_out = SHOTS_DIR / "clay_close.mp4"
    if _done(beat4_out):
        print("  [resume] clay_close.mp4 already present, skipping beat 4")
        clips["clay_close"] = beat4_out
    else:
        spec = {
            "growth_stage": {"f_each": 10, "n_blocks": 2},
            "camera_keyframes": [
                {"frame": 10, "location": [0.9, -2.7, 0.9], "look_at": [0, 0, 0.32]},
                {"frame": 35, "location": [0.75, -2.3, 0.8], "look_at": [0, 0, 0.35]},
            ],
            "lens": 150, "fstop": 1.6, "n_frames": 10, "frame_range": [10, 35],
            "render": eng(28),
        }
        d = render_blender("_clay_miniature_script.py", spec, "clay_close")
        clips["clay_close"] = frames_to_clip(d, beat4_out, 10, 7.0)

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

    narr_offsets = []
    cum = 0.0
    for i, d_ in enumerate(durations):
        narr_offsets.append(cum)
        cum += d_ - (XFADE_DUR if i < len(durations) - 1 else 0)

    foley_events = []
    for i in range(1, len(order)):
        foley_events.append((SFX / "whoosh.wav", narr_offsets[i], 0.4))
    mg_start = narr_offsets[order.index("motion_graphics")]
    foley_events.append((SFX / "bell.wav", mg_start + durations[order.index("motion_graphics")] * 0.5, 0.4))

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

    final_mp4 = JOB_DIR / "final.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(video_only), "-i", str(final_audio),
         "-c:v", "libx264", "-crf", "18", "-c:a", "aac", "-shortest", str(final_mp4)],
        capture_output=True, text=True, check=True,
    )

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

    total_build_time = round(time.time() - t0, 1)
    dur_actual = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                 "-of", "default=noprint_wrappers=1:nokey=1", str(final_mp4)],
                                capture_output=True, text=True).stdout.strip()
    metadata = {
        "title": "Why $100 Today Is Worth More Than $100 Next Year",
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
        "fact_check_notes": "5% return is explicitly labeled hypothetical; 100*1.05=105 is exact "
                            "arithmetic, not invented. Inflation's effect is described qualitatively "
                            "('quietly shrinks buying power') without an invented CPI figure.",
        "total_build_time_sec": total_build_time,
    }
    (JOB_DIR / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print(f"\nFINAL: {final_mp4} ({dur_actual}s)")
    print(f"CONTACT SHEET: {JOB_DIR / 'contact_sheet.jpg'}")
    print(f"METADATA: {JOB_DIR / 'metadata.json'}")
    print(f"Total build time: {total_build_time}s")


if __name__ == "__main__":
    main()
