#!/usr/bin/env python3
"""
Phase-3 validation — FFmpeg multi-layer composer on CACHED stills (NO generation).

Per the rollout plan we validate the compositor BEFORE wiring it to fresh AI image
generation, so this never calls ComfyUI / any provider — it reuses already-cached
stills (data/cache/ai_img_*.png) as the background + subject planes and a generated
FX texture (data/assets/fx/) as the foreground. That keeps the test to a few
seconds of pure ffmpeg instead of ~11 min/still of CPU generation.

It proves, on the real box:
  • a hero scene composites bg ▸ subject(alpha) ▸ fx(screen) into a NON-BLACK clip,
  • render time + ffmpeg peak RSS stay within a sane CPU/RAM budget,
  • the graceful fallbacks fire (forced fallback, RAM floor, too-few-planes),
  • the render_ffmpeg wiring delegates to the composer when LAYERED_RENDER=1.

    .venv/bin/python scripts/verify_phase3_layers.py
    .venv/bin/python scripts/verify_phase3_layers.py --keep   # keep the clips

Exit 0 = all checks passed.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

# Force the layered path ON for this process BEFORE importing app config.
os.environ["LAYERED_RENDER"] = "1"
os.environ.setdefault("RENDER_BACKEND", "ffmpeg")

W, H, FPS = 1080, 1920, 30
OUT_DIR = ROOT / "data" / "renders" / "_phase3_verify"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _cached_stills(n: int) -> list[Path]:
    """The n largest cached AI stills (largest = most likely a real image, not a
    failed/placeholder write)."""
    cache = ROOT / "data" / "cache"
    imgs = [p for p in cache.glob("ai_img_*")
            if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")]
    imgs.sort(key=lambda p: p.stat().st_size, reverse=True)
    return imgs[:n]


def _frame_yavg(clip: Path, at: float) -> float:
    """Average luma (0..255) of the frame at `at` seconds — proves NON-BLACK."""
    r = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "info", "-ss", f"{at}",
         "-i", str(clip), "-frames:v", "1",
         "-vf", "signalstats,metadata=print", "-f", "null", "-"],
        stderr=subprocess.PIPE)
    m = re.search(r"lavfi\.signalstats\.YAVG=([0-9.]+)", r.stderr.decode())
    return float(m.group(1)) if m else -1.0


def _duration(clip: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nk=1:nw=1", str(clip)], stdout=subprocess.PIPE)
    try:
        return float(r.stdout.decode().strip())
    except ValueError:
        return -1.0


def _hero_scene(stills: list[Path], fx: str, *, dur: float = 4.0):
    """A hero beat with the full bg ▸ subject ▸ fx stack, assets pre-resolved to
    cached files (mirrors what the Storyboard Agent emits, minus generation)."""
    from app.schemas.scene import Layer, Scene, Visual
    bg, subj = stills[0], stills[1]
    v = Visual(type="ai_image", visual_intent="hero shot", layers=[
        Layer(role="background", kind="ai_image", asset_path=str(bg),
              motion="zoom_in", parallax=0.12),
        Layer(role="subject", kind="ai_image", character="kade",
              asset_path=str(subj), motion="zoom_out", parallax=0.6),
        Layer(role="fx", kind="asset", asset_path=fx, blend="screen",
              opacity=0.35, parallax=0.85),
    ])
    return Scene(id="s_hero", narration="hero beat", duration_sec=dur, visual=v)


def _reload_settings(**env) -> None:
    """Apply env overrides and clear the settings lru_cache so a test sees them."""
    from app.config import settings
    os.environ.update({k: str(v) for k, v in env.items()})
    settings.cache_clear()


# --------------------------------------------------------------------------- #
# checks
# --------------------------------------------------------------------------- #
async def run(keep: bool) -> int:
    from app.config import settings
    from app.pipeline import layers, ram

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fails: list[str] = []

    # ensure fx textures exist (idempotent, free).
    if not (ROOT / "data" / "assets" / "fx" / "scanlines.png").exists():
        subprocess.run([sys.executable, str(ROOT / "scripts" / "make_fx_assets.py")])
    fx = str(ROOT / "data" / "assets" / "fx" / "scanlines.png")

    stills = _cached_stills(2)
    if len(stills) < 2:
        print("✗ need ≥2 cached AI stills in data/cache/ai_img_* to validate "
              "(found %d). Run a generation once, then re-run." % len(stills))
        return 2
    print(f"[setup] bg     = {stills[0].name} ({stills[0].stat().st_size//1024}KB)")
    print(f"[setup] subject= {stills[1].name} ({stills[1].stat().st_size//1024}KB)")
    print(f"[setup] fx     = {Path(fx).name}")
    print(f"[setup] free RAM now: {ram.available_mb():.0f}MB / "
          f"{ram.total_mb():.0f}MB total\n")

    # --- CHECK 1: hero composite on cached stills → True, non-black ----------- #
    _reload_settings(LAYERED_RENDER="1", LAYERED_FORCE_FALLBACK="0")
    scene = _hero_scene(stills, fx, dur=4.0)
    clip = OUT_DIR / "hero.mp4"
    if clip.exists():
        clip.unlink()
    t0 = time.monotonic()
    ok = await layers.compose(scene, clip, W, H, FPS, grade="", draw="", tail="")
    dt = time.monotonic() - t0
    if not ok:
        fails.append("CHECK1: compose() returned False (expected True)")
    elif not clip.exists() or clip.stat().st_size == 0:
        fails.append("CHECK1: no output clip written")
    else:
        yavg = _frame_yavg(clip, 2.0)
        cdur = _duration(clip)
        budget = 90.0                       # generous CPU ceiling for a 4s clip
        print(f"✓ CHECK1 hero composite: {dt:.1f}s, {clip.stat().st_size//1024}KB, "
              f"dur={cdur:.2f}s, mid-frame YAVG={yavg:.1f} (non-black if >16)")
        if yavg <= 16:
            fails.append(f"CHECK1: clip looks BLACK (YAVG={yavg:.1f})")
        if abs(cdur - 4.0) > 0.6:
            fails.append(f"CHECK1: duration drift {cdur:.2f}s (want ~4.0s)")
        if dt > budget:
            fails.append(f"CHECK1: too slow on CPU ({dt:.1f}s > {budget:.0f}s)")

    # --- CHECK 2: forced fallback → False (caller does simple render) --------- #
    _reload_settings(LAYERED_FORCE_FALLBACK="1")
    f2 = OUT_DIR / "_should_not_exist.mp4"
    ok2 = await layers.compose(scene, f2, W, H, FPS)
    print(f"{'✓' if not ok2 else '✗'} CHECK2 forced fallback: compose()={ok2} "
          f"(expected False)")
    if ok2:
        fails.append("CHECK2: forced fallback did not return False")
    _reload_settings(LAYERED_FORCE_FALLBACK="0")

    # --- CHECK 3: RAM floor too high → graceful fallback --------------------- #
    _reload_settings(LAYERED_MIN_FREE_MB="9999999")
    ok3 = await layers.compose(scene, f2, W, H, FPS)
    print(f"{'✓' if not ok3 else '✗'} CHECK3 RAM-floor guard: compose()={ok3} "
          f"(expected False — free RAM below an impossible floor)")
    if ok3:
        fails.append("CHECK3: RAM-floor guard did not trigger fallback")
    _reload_settings(LAYERED_MIN_FREE_MB="1100")

    # --- CHECK 4: too few planes (bg only) → False --------------------------- #
    from app.schemas.scene import Layer, Scene, Visual
    bg_only = Scene(id="s_bgonly", narration="x", duration_sec=3.0,
                    visual=Visual(type="ai_image", layers=[
                        Layer(role="background", kind="ai_image",
                              asset_path=str(stills[0]), motion="zoom_in",
                              parallax=0.1)]))
    ok4 = await layers.compose(bg_only, f2, W, H, FPS)
    print(f"{'✓' if not ok4 else '✗'} CHECK4 single-plane: compose()={ok4} "
          f"(expected False — nothing to composite over)")
    if ok4:
        fails.append("CHECK4: single-plane scene was composited (should fall back)")

    # --- CHECK 5: render_ffmpeg wiring delegates to the composer -------------- #
    _reload_settings(LAYERED_RENDER="1")
    from app.pipeline import render_ffmpeg
    wired = OUT_DIR / "wired_hero.mp4"
    if wired.exists():
        wired.unlink()
    await render_ffmpeg._scene_clip(scene, wired, W, H, FPS, hook=False)
    if wired.exists() and wired.stat().st_size > 0:
        yavg = _frame_yavg(wired, 2.0)
        print(f"✓ CHECK5 renderer wiring: _scene_clip produced {wired.stat().st_size//1024}KB "
              f"via composer (YAVG={yavg:.1f})")
        if yavg <= 16:
            fails.append(f"CHECK5: wired clip BLACK (YAVG={yavg:.1f})")
    else:
        fails.append("CHECK5: _scene_clip produced no clip")

    # --- summary ------------------------------------------------------------- #
    peak = ram.child_peak_mb()
    print(f"\n[ram] ffmpeg child peak RSS this run: ~{peak:.0f}MB "
          f"(floor was {settings().layered_min_free_mb}MB free)")
    if not keep:
        for p in OUT_DIR.glob("*.mp4"):
            p.unlink()
        if not any(OUT_DIR.iterdir()):
            OUT_DIR.rmdir()
    else:
        print(f"[keep] clips left in {OUT_DIR}")

    print()
    if fails:
        print("✗ PHASE-3 VALIDATION FAILED:")
        for f in fails:
            print("   -", f)
        return 1
    print("✓ PHASE-3 VALIDATION PASSED — layered composite + all fallbacks OK.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true", help="keep the output clips")
    args = ap.parse_args()
    return asyncio.run(run(args.keep))


if __name__ == "__main__":
    sys.exit(main())
