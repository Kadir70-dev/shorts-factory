#!/usr/bin/env python3
"""K70 Finance Shorts -- Day 06, Short C: "How Banks Actually Make Money
From Your Deposits". 1080x1920 vertical.

4 beats / 3 modes:
  1. Real Footage         -- open, hook, stock b-roll (deposit/bank context)
  2. Isometric (Blender)  -- main flow: deposit -> balance sheet -> loans/securities
  3. Synfig Vector (REAL) -- funding costs / net interest margin breakdown
  4. Isometric (Blender)  -- closing wide shot, same system, echoes the point

Checkpoint/resume discipline matches build_fin_d06_a.py/_b.py.

    .venv-win/Scripts/python.exe scripts/build_fin_d06_c.py
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
GEN_VECTOR_D06C = ROOT / "tools/k70_scene_engine/synfig/gen_vector_d06c.py"
MUSIC_BED = ROOT / "data/assets/music/beds/premium_a.wav"
SFX = ROOT / "data/assets/sfx"

JOB_DIR = ROOT / "data" / "jobs" / "vid_fin_d06_c"
SHOTS_DIR = JOB_DIR / "shots"
AUDIO_DIR = JOB_DIR / "audio"
SHOTS_DIR.mkdir(parents=True, exist_ok=True)
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

W, H, FPS = 1080, 1920, 24
XFADE_DUR = 0.5


def winpath(p: Path) -> str:
    return str(p).replace("\\", "/")


def eng(samples=28):
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
    sif_path = JOB_DIR / "vector_d06c.sif"
    subprocess.run([sys.executable, str(GEN_VECTOR_D06C), str(sif_path)], check=True)
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


async def fetch_real_footage(duration_sec: float) -> Path:
    from app.pipeline import broll
    terms = ["bank teller counter customer depositing check savings"]
    out = SHOTS_DIR / "real_footage.mp4"
    path = await broll._video(terms, duration_sec, 0, query_text="",
                              rank_key="vid_fin_d06_c:real_footage")
    if path is None:
        path = await broll._image(terms, 0, query_text="",
                                  rank_key="vid_fin_d06_c:real_footage_img")
        if path is None:
            raise RuntimeError("no real footage/image resolved")
        subprocess.run(
            ["ffmpeg", "-y", "-loop", "1", "-i", str(path), "-t", str(duration_sec),
             "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                    f"zoompan=z='min(zoom+0.0015,1.08)':d=125:s={W}x{H}",
             "-pix_fmt", "yuv420p", "-r", str(FPS), str(out)],
            capture_output=True, text=True, check=True,
        )
        return out
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(path), "-t", str(duration_sec),
         "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}",
         "-pix_fmt", "yuv420p", "-r", str(FPS), "-an", str(out)],
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


ISO_ENTITIES = [
    {"name": "depositor", "kind": "worker", "location": [-1.6, 1.3, 0]},
    {"name": "bank", "kind": "bank", "location": [0.0, 0.6, 0]},
    {"name": "loans", "kind": "business", "location": [1.6, -0.3, 0]},
    {"name": "securities", "kind": "investor", "location": [0.0, -1.6, 0]},
]
ISO_ROADS = [[-1.6, 1.0, 0.0, 0.6], [0.0, 0.3, 1.6, -0.3], [0.0, 0.2, 0.0, -1.2]]

PLAN = [
    dict(id="real_footage", style="REAL_FOOTAGE", duration=6.5,
         narration="You deposit $1,000. The bank doesn't simply put your exact cash in a vault and wait.",
         renderer="stock real-world footage (app.pipeline.broll)",
         specialized_tool=False),
    dict(id="isometric_flow", style="ISOMETRIC_MINIATURE", duration=15.0,
         narration="Instead, your deposit becomes part of the bank's balance sheet. From there, much of "
                    "it gets put to work, as loans to other customers, or in interest-bearing securities, "
                    "earning the bank interest income.",
         renderer="Blender 4.2.4 LTS EEVEE_NEXT, K70 isometric economy system",
         specialized_tool=False),
    dict(id="vector", style="PREMIUM_2D_VECTOR", duration=15.0,
         narration="That's not pure profit, though. Banks pay interest to depositors, cover operating "
                    "costs, absorb credit losses when loans aren't repaid, and hold capital and liquid "
                    "reserves as a safety cushion required by regulators.",
         renderer="Synfig Studio 1.5.5 (real synfig.exe CLI, github.com/synfig/synfig)",
         specialized_tool=True),
    dict(id="isometric_close", style="ISOMETRIC_MINIATURE", duration=8.0,
         narration="The basic business is earning more on assets than the bank pays for its funding, "
                    "while managing risk.",
         renderer="Blender 4.2.4 LTS EEVEE_NEXT, K70 isometric economy system",
         specialized_tool=False),
]


def main() -> None:
    t0 = time.time()
    print("K70 Finance D06 Short C -- How Banks Make Money (1080x1920)")
    clips: dict[str, Path] = {}

    # ---- Beat 1: real_footage ---- #
    beat1_out = SHOTS_DIR / "real_footage.mp4"
    if _done(beat1_out):
        print("  [resume] real_footage.mp4 already present, skipping beat 1")
        clips["real_footage"] = beat1_out
    else:
        clips["real_footage"] = asyncio.run(fetch_real_footage(6.5))

    # ---- Beat 2: isometric_flow ---- #
    beat2_out = SHOTS_DIR / "isometric_flow.mp4"
    if _done(beat2_out):
        print("  [resume] isometric_flow.mp4 already present, skipping beat 2")
        clips["isometric_flow"] = beat2_out
    else:
        spec = {
            "entities": ISO_ENTITIES, "roads": ISO_ROADS,
            "flows": [
                {"from": [-1.6, 1.6, 0.3], "to": [0.0, 0.9, 0.4], "f_start": 6, "f_end": 30, "color": [0.75, 0.6, 0.2]},
                {"from": [0.0, 0.9, 0.4], "to": [1.6, 0.0, 0.3], "f_start": 34, "f_end": 58, "color": [0.55, 0.42, 0.8]},
                {"from": [0.0, 0.9, 0.4], "to": [0.0, -1.3, 0.65], "f_start": 34, "f_end": 62, "color": [0.20, 0.55, 0.28]},
            ],
            "lighting_preset": "exterior_day", "hdri_strength": 1.0,
            "yaw_deg": 40, "ortho_scale": 4.6, "look_at": [0, -0.2, 0.2], "orbit_deg": 14,
            "n_frames": 20, "frame_range": [0, 70], "render": eng(),
        }
        d = render_blender("_isometric_miniature_script.py", spec, "isometric_flow")
        clips["isometric_flow"] = frames_to_clip(d, beat2_out, 20, 15.0)

    # ---- Beat 3: vector -- real Synfig funding-cost breakdown ---- #
    beat3_out = SHOTS_DIR / "vector.mp4"
    if _done(beat3_out):
        print("  [resume] vector.mp4 already present, skipping beat 3")
        clips["vector"] = beat3_out
    else:
        clips["vector"] = render_synfig_vector(15.0)

    # ---- Beat 4: isometric_close -- wide shot, same system ---- #
    beat4_out = SHOTS_DIR / "isometric_close.mp4"
    if _done(beat4_out):
        print("  [resume] isometric_close.mp4 already present, skipping beat 4")
        clips["isometric_close"] = beat4_out
    else:
        spec = {
            "entities": ISO_ENTITIES, "roads": ISO_ROADS, "flows": [],
            "lighting_preset": "exterior_day", "hdri_strength": 1.0,
            "yaw_deg": 55, "ortho_scale": 6.5, "look_at": [0, -0.2, 0.2], "orbit_deg": -10,
            "n_frames": 10, "frame_range": [0, 40], "render": eng(),
        }
        d = render_blender("_isometric_miniature_script.py", spec, "isometric_close")
        clips["isometric_close"] = frames_to_clip(d, beat4_out, 10, 8.0)

    order = [s["id"] for s in PLAN]
    durations = [s["duration"] for s in PLAN]

    narration_paths = asyncio.run(synthesize_narration([s["narration"] for s in PLAN]))
    for s, p in zip(PLAN, narration_paths):
        s["narration_audio"] = str(p) if p else None

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
        "title": "How Banks Actually Make Money From Your Deposits",
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
        "fact_check_notes": "Deliberately avoids the misleading 'bank lends your exact $900' framing -- "
                            "narration says deposits 'become part of the balance sheet' and 'much of it "
                            "gets put to work', not a literal dollar-tracing claim. Funding costs "
                            "(interest paid, operating costs, credit losses, capital/liquidity "
                            "requirements) are named per the brief, not omitted for simplicity.",
        "total_build_time_sec": total_build_time,
    }
    (JOB_DIR / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print(f"\nFINAL: {final_mp4} ({dur_actual}s)")
    print(f"CONTACT SHEET: {JOB_DIR / 'contact_sheet.jpg'}")
    print(f"METADATA: {JOB_DIR / 'metadata.json'}")
    print(f"Total build time: {total_build_time}s")


if __name__ == "__main__":
    main()
