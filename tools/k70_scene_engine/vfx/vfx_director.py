"""K70 VFX Director -- top-level orchestrator. Pure Python (shells out to
Blender and NatronRenderer per stage; imports neither bpy nor NatronEngine
directly).

THIS IS A HELPER LAYER, NOT A 10TH K70 VISUAL MODE: apply_vfx() consumes
an ALREADY-RENDERED frame sequence from any compatible K70 visual mode
(voxel, animation, etc.) and adds a story-appropriate cinematic VFX pass
on top. It does not touch, re-render, or depend on the internals of
whatever produced those frames.

Pipeline (matches the requested architecture):
  input frames -> Blender compositor stage (Glare/Sun Beams/Color Balance/
  vignette -- native Blender compositor nodes) -> Natron/OpenFX stage
  (GradePlugin + RainSnow + LightGlow + AddGrain -- confirmed-real,
  isolation-tested plugin IDs) -> ffmpeg (final encode)

Caching / performance:
  - Each stage is skipped entirely if its output directory already has
    every expected frame AND a manifest recording the exact params used
    matches this call's params (param-aware resume-safety, not just
    frame-count resume-safety).
  - LOW/MEDIUM/HERO quality levels scale render resolution (a real,
    meaningful cost lever for both Blender and Natron/GMIC, which are
    resolution-bound) -- samples are not a factor here since neither
    stage does path-traced 3D rendering, only 2D compositing.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vfx_presets import resolve_preset, QUALITY_LEVELS

ROOT = Path(__file__).resolve().parents[3]
BLENDER = ROOT / "tools/k70_scene_engine/.blender_portable/blender-4.2.4-windows-x64/blender.exe"
BDIR = ROOT / "tools/k70_scene_engine/blender"
NATRON_RENDERER = (ROOT / "tools/k70_scene_engine/vendor/natron_win/extracted/"
                  "Natron-2.5.0-Windows-x86_64/bin/NatronRenderer.exe")
NDIR = ROOT / "tools/k70_scene_engine/natron"
GMIC_CACHE_DIR = Path(os.environ.get("APPDATA", "")) / "gmic"


def _manifest_matches(manifest_path: Path, params: dict) -> bool:
    if not manifest_path.exists():
        return False
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8")) == params
    except (json.JSONDecodeError, OSError):
        return False


def _frames_complete(out_dir: Path, frame_count: int, pattern: str) -> bool:
    return out_dir.exists() and all((out_dir / pattern.format(f)).exists() for f in range(frame_count))


def _prescale_frames_if_needed(input_dir: Path, frame_count: int, target_w: int, target_h: int) -> Path:
    """Resize input frames to (target_w, target_h) via PIL BEFORE Blender
    ever sees them, when their native size differs. Blender's own
    CompositorNodeScale was confirmed to have a real, reproducible bug on
    this build: downscaling a landscape (width>height) source frame
    produced a solid-black composite (RGB mean ~0.4/255) regardless of
    scale mode (RENDER_SIZE/FIT or RELATIVE with an explicit factor),
    while the IDENTICAL portrait-oriented case downscaled correctly. A
    PIL-prescaled frame loaded at 1:1 (no Blender-side resize at all)
    rendered perfectly (RGB mean ~167/255) on the exact same failing
    input -- isolating the bug to Blender's Scale node itself, not this
    pipeline's color management or node graph. Doing the resize in
    Python sidesteps it entirely and is simpler than debugging Blender's
    compositor internals further."""
    from PIL import Image
    first = input_dir / "frame_0000.png"
    with Image.open(first) as im:
        native_w, native_h = im.size
    if (native_w, native_h) == (target_w, target_h):
        return input_dir
    prescaled_dir = input_dir.parent / f"{input_dir.name}_prescaled_{target_w}x{target_h}"
    if _frames_complete(prescaled_dir, frame_count, "frame_{:04d}.png"):
        return prescaled_dir
    prescaled_dir.mkdir(parents=True, exist_ok=True)
    for f in range(frame_count):
        src = input_dir / f"frame_{f:04d}.png"
        with Image.open(src) as im:
            im.resize((target_w, target_h), Image.LANCZOS).save(prescaled_dir / f"frame_{f:04d}.png")
    return prescaled_dir


def _run_blender_stage(input_dir: Path, output_dir: Path, frame_count: int, width: int, height: int,
                       blender_cfg: dict, timeout: int = 1200) -> float:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = output_dir / "_manifest.json"
    params = {"frame_count": frame_count, "width": width, "height": height, "blender_cfg": blender_cfg,
             "input_dir": str(input_dir)}
    if _frames_complete(output_dir, frame_count, "frame_{:04d}.png") and _manifest_matches(manifest, params):
        return 0.0
    t0 = time.time()
    input_dir = _prescale_frames_if_needed(input_dir, frame_count, width, height)
    args_spec = {"input_dir": str(input_dir), "output_dir": str(output_dir), "frame_start": 0,
                "frame_count": frame_count, "width": width, "height": height, "blender_cfg": blender_cfg}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(args_spec, f)
        args_path = f.name
    proc = subprocess.run([str(BLENDER), "--background", "--python", str(BDIR / "_vfx_blender_pass.py"),
                          "--", args_path], capture_output=True, text=True, timeout=timeout)
    Path(args_path).unlink(missing_ok=True)
    if "K70_VFX_BLENDER_PASS_OK" not in proc.stdout:
        raise RuntimeError(f"Blender VFX stage failed:\nSTDOUT:{proc.stdout[-3000:]}\nSTDERR:{proc.stderr[-2000:]}")
    manifest.write_text(json.dumps(params), encoding="utf-8")
    return round(time.time() - t0, 1)


NATRON_BATCH_SIZE = 10  # this Natron build hangs (process alive, zero new
# frames) after ~24-25 renders within one continuous process session --
# reproduced identically at two different total frame counts, confirming
# an internal resource/session limit, not content-specific. Restarting the
# NatronRenderer process every N frames (well under that threshold) avoids
# it entirely.


def _validate_png(path: Path, width: int, height: int) -> bool:
    """True only if `path` decodes cleanly AND matches the expected
    canvas size. Used to replace a blind fixed-time kill grace period --
    a real run once killed NatronRenderer mid-write on the very last
    frame of a batch, leaving a 229KB truncated PNG where every sibling
    frame was ~5.3MB; ffmpeg silently dropped it, shorting the final
    video by 2 frames."""
    try:
        with Image.open(path) as im:
            im.verify()
        with Image.open(path) as im:
            return im.size == (width, height)
    except Exception:
        return False


def _run_natron_batch(input_dir: Path, output_dir: Path, frame_start: int, frame_end: int,
                      width: int, height: int, natron_cfg: dict, timeout: int) -> None:
    """Render frames [frame_start, frame_end] (inclusive) in ONE fresh
    NatronRenderer process. Raises on timeout/stall/failure; caller
    decides batch boundaries and resume-safety."""
    args_spec = {"input_dir": str(input_dir).replace("\\", "/"), "output_dir": str(output_dir).replace("\\", "/"),
                "frame_start": frame_start, "frame_end": frame_end, "width": width, "height": height,
                "natron_cfg": natron_cfg}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(args_spec, f)
        args_path = f.name
    env = {**os.environ, "K70_VFX_NATRON_ARGS": args_path}
    # NatronRenderer's script mode does not reliably exit after the
    # intended render completes -- confirmed twice: the OK marker prints,
    # every expected output frame exists on disk, and the process still
    # sits there (an implicit default-range re-render Natron itself
    # starts post-script, per collage_scene.py's own documented gotcha --
    # node.destroy() on the writer reduces but does not eliminate this).
    # Rather than chase this build's internal exit quirks further, poll
    # for the expected files and kill the process once they're all
    # present AND verified -- resilient regardless of whether the hang is
    # a slow implicit re-render or something else.
    expected = [output_dir / f"frame.{f:04d}.png" for f in range(frame_start, frame_end + 1)]
    proc = subprocess.Popen([str(NATRON_RENDERER), "_vfx_natron_pass.py"], cwd=str(NDIR),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    validated = False
    poll_start = time.time()
    # Stall detection: this build has hung mid-render before (process
    # alive, zero new frames for 16+ minutes at HERO resolution) -- track
    # the last time the on-disk frame count actually increased and abort
    # early if it stalls for too long, rather than waiting the full
    # timeout or requiring a manual kill.
    last_progress_time = poll_start
    last_frame_n = 0
    stall_limit = 240
    try:
        # Phase 1: wait for every expected file to exist on disk.
        while True:
            if proc.poll() is not None:
                break
            now = time.time()
            if now - poll_start > timeout:
                proc.kill()
                raise RuntimeError(f"Natron VFX batch [{frame_start}-{frame_end}] timed out after {timeout}s")
            n_done = sum(1 for p in expected if p.exists())
            if n_done > last_frame_n:
                last_frame_n = n_done
                last_progress_time = now
            elif now - last_progress_time > stall_limit:
                proc.kill()
                raise RuntimeError(f"Natron VFX batch [{frame_start}-{frame_end}] stalled: no new frame in "
                                  f"{stall_limit}s ({n_done}/{len(expected)} done)")
            if n_done == len(expected):
                break
            time.sleep(1.0)

        # Phase 2: NEVER accept a partially flushed PNG. Instead of a
        # fixed sleep, actively confirm each expected file's size has
        # stopped changing across a poll interval AND that it decodes
        # with PIL at the exact expected dimensions, before killing the
        # process. Bounded by its own deadline so a genuinely corrupt/
        # stuck frame still fails loudly rather than hanging forever.
        validate_deadline = time.time() + 60
        last_sizes = None
        while True:
            cur_sizes = {p: p.stat().st_size for p in expected if p.exists()}
            if len(cur_sizes) == len(expected) and cur_sizes == last_sizes:
                if all(_validate_png(p, width, height) for p in expected):
                    validated = True
                    break
            last_sizes = cur_sizes
            if time.time() > validate_deadline:
                bad = [p.name for p in expected if not _validate_png(p, width, height)]
                proc.kill()
                proc.wait(timeout=10)
                raise RuntimeError(f"Natron VFX batch [{frame_start}-{frame_end}] frames never "
                                  f"stabilized/validated as clean {width}x{height} PNGs: {bad}")
            time.sleep(1.0)
        proc.kill()
        proc.wait(timeout=10)
    finally:
        Path(args_path).unlink(missing_ok=True)
    if not validated:
        out = proc.stdout.read() if proc.stdout else ""
        err = proc.stderr.read() if proc.stderr else ""
        raise RuntimeError(f"Natron VFX batch [{frame_start}-{frame_end}] failed:\n"
                          f"STDOUT:{out[-3000:]}\nSTDERR:{err[-2000:]}")


def _run_natron_stage(input_dir: Path, output_dir: Path, frame_count: int, width: int, height: int,
                      natron_cfg: dict, timeout: int = 1800) -> float:
    output_dir.mkdir(parents=True, exist_ok=True)
    GMIC_CACHE_DIR.mkdir(parents=True, exist_ok=True)  # eu.gmic.AddGrain silently outputs
    # a blank frame if this cache directory doesn't exist -- confirmed via an isolated test.
    manifest = output_dir / "_manifest.json"
    params = {"frame_count": frame_count, "width": width, "height": height, "natron_cfg": natron_cfg,
             "input_dir": str(input_dir)}
    if (_frames_complete(output_dir, frame_count, "frame.{:04d}.png") and _manifest_matches(manifest, params)
            and all(_validate_png(output_dir / f"frame.{f:04d}.png", width, height) for f in range(frame_count))):
        return 0.0
    t0 = time.time()
    for batch_start in range(0, frame_count, NATRON_BATCH_SIZE):
        batch_end = min(batch_start + NATRON_BATCH_SIZE, frame_count) - 1  # inclusive
        batch_expected = [output_dir / f"frame.{f:04d}.png" for f in range(batch_start, batch_end + 1)]
        # Per-batch resume-safety: skip only if every frame in this range
        # both exists AND decodes cleanly at the right size -- a cached
        # but truncated/corrupt frame (e.g. from a prior kill-timing bug)
        # must never be silently trusted as "already done".
        if all(p.exists() and _validate_png(p, width, height) for p in batch_expected):
            continue
        _run_natron_batch(input_dir, output_dir, batch_start, batch_end, width, height, natron_cfg, timeout)
    manifest.write_text(json.dumps(params), encoding="utf-8")
    return round(time.time() - t0, 1)


def _run_ffmpeg(frames_glob: str, fps: int, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(["ffmpeg", "-y", "-framerate", str(fps), "-i", frames_glob,
                          "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", str(out_path)],
                         capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {proc.stderr[-2000:]}")


def apply_vfx(input_dir: str | Path, output_dir: str | Path, preset: str, intensity: float = 0.65,
             scene_type: str = "city", quality: str = "MEDIUM", frame_count: int | None = None,
             fps: int = 24, width: int = 1080, height: int = 1920) -> dict:
    """Apply a semantic VFX preset to an already-rendered K70 frame
    sequence. Deterministic -- no LLM/API/cloud dependency.

    input_dir: directory of frame_0000.png.. frames from any compatible
      K70 visual mode/animation.
    output_dir: where blender_pass/, natron_pass/, and the final MP4 land.
    preset: one of vfx_presets.PRESETS.
    intensity: 0..1 (scales every knob toward/away from neutral).
    scene_type: informational only right now (kept for the documented
      API shape -- future presets may branch on it, e.g. interior vs.
      exterior atmosphere defaults).
    quality: LOW/MEDIUM/HERO -- scales render resolution.
    """
    input_dir = Path(input_dir).resolve()
    output_dir = Path(output_dir).resolve()
    if frame_count is None:
        frame_count = len(list(input_dir.glob("frame_*.png")))
    if frame_count == 0:
        raise ValueError(f"no frame_*.png files found in {input_dir}")

    q = QUALITY_LEVELS.get(quality, QUALITY_LEVELS["MEDIUM"])
    render_w = max(64, int(width * q["scale"]))
    render_h = max(64, int(height * q["scale"]))

    resolved = resolve_preset(preset, intensity)

    # Quality-aware tuning (on top of the preset's own knobs):
    # - grain_scale: LOW/MEDIUM previews don't need full grain fidelity.
    # - sun_beams: reserved for HERO -- profiled as the dominant Blender-
    #   stage cost (~8.4x vs no sun beams at HERO resolution); LOW/MEDIUM
    #   fall back to Glare(FOG_GLOW) alone, which is visually close for
    #   atmosphere/depth at a fraction of the render time.
    resolved["natron"]["grain_opacity"] *= q["grain_scale"]
    if not q["sun_beams"]:
        resolved["blender"]["sun_beams"] = False
        resolved["blender"]["sun_beams_strength"] = 0.0

    timings = {}
    t0 = time.time()
    blender_dir = output_dir / "blender_pass"
    timings["blender_sec"] = _run_blender_stage(input_dir, blender_dir, frame_count, render_w, render_h,
                                                resolved["blender"])

    natron_dir = output_dir / "natron_pass"
    timings["natron_sec"] = _run_natron_stage(blender_dir, natron_dir, frame_count, render_w, render_h,
                                              resolved["natron"])

    final_path = output_dir / "final.mp4"
    if not final_path.exists():
        _run_ffmpeg(str(natron_dir / "frame.%04d.png"), fps, final_path)
    timings["total_sec"] = round(time.time() - t0, 1)

    return {"preset": preset, "intensity": intensity, "scene_type": scene_type, "quality": quality,
           "frame_count": frame_count, "resolution": f"{render_w}x{render_h}", "fps": fps,
           "resolved_preset": resolved, "timings": timings, "final_path": str(final_path),
           "blender_pass_dir": str(blender_dir), "natron_pass_dir": str(natron_dir)}
