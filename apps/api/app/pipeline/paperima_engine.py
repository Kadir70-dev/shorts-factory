"""
Local adapter for Paperima (github.com/nurimator/paperima, AGPL-3.0-only,
commit afc361527b66, v2.0.0) — an external, unmodified, locally-installed
paper-texture/paper-animation web app. Paperima is NEVER vendored into this
repo (see `apps/remotion/src/paperima/worker.ts`'s module docstring for the
full license reasoning); this module only shells out to a Node/Puppeteer
worker that drives Paperima's own build like a user would, the same pattern
already used for the Three.js integration (`threejs_engine.py`).

Role in the pipeline (per the integration spec): Scribus produces the
factual document (newspaper, dossier, research paper, ...) as a flat PNG.
THIS module, when a beat's decision calls for physical paper motion, takes
that PNG and gets back a short animated clip (paper reveal/fold/wobble,
torn-edge shadow, textured overlay) on a keyable background. It never
originates content and never replaces Scribus, SceneGraph, or the FFmpeg
composite stage — it is a finishing pass on an already-rendered document,
used SPARINGLY (broll.py decides which beats warrant it, not this module).

Capability + fallback contract, matching every other optional engine in
this pipeline (whisper, manim, the AI-image chain): if Paperima isn't
installed/enabled, or a specific render fails, this returns a
`status="unavailable"`/`"unresolved"` provenance record and does NOT raise.
The caller's job is to leave the scene exactly as Scribus produced it
(`visual.type` stays "papercraft", `camera_movement` stays set) when that
happens — `pipeline/render_ffmpeg.py`'s existing `camera_vf` zoompan path
already animates a flat Paper Craft page and needs no changes to keep doing
that. "Fall back to the existing FFmpeg paper animation" means exactly this:
decline to intervene, not synthesize a substitute file.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Literal

from ..config import ROOT, settings
from ..schemas.scene import PaperimaRenderProvenance
from .threejs_engine import find_node  # shared Node-discovery helper

AnimationType = Literal["reveal", "conceal", "dynamic", "wobble", "static"]
BackgroundMode = Literal["greenscreen", "white", "black"]

# Bump to invalidate every cache entry after a worker-logic change that
# alters output for an unchanged (image, params) pair.
WORKER_VERSION = "1.0.0"

_worker: asyncio.subprocess.Process | None = None
_worker_lock = asyncio.Lock()
_worker_jobs = 0


def available() -> bool:
    """Cheap, synchronous, no-subprocess capability check — mirrors
    `find_scribus_binary()`'s spirit: answer "can this even run" before
    anything pays the cost of finding out the hard way."""
    if not settings().paperima_engine_enabled:
        return False
    dist = settings().paperima_dist_dir.strip()
    if not dist:
        return False
    return (Path(dist) / "index.html").is_file()


def _find_chrome() -> str:
    """A real Chrome/Chromium install, preferred over Puppeteer's bundled
    Chromium for this specific worker. Empirically required, not a
    preference: Paperima's export uses WebCodecs H.264 encoding, and the
    bundled open-source Chromium build crashed mid-encode in headless mode
    on this box every time during verification; Google Chrome did not.
    Mirrors `papercraft/binary.py`'s find_scribus_binary() shape — checked
    once via settings(), falls back to Puppeteer's own bundled browser
    (unset) if nothing is found, never hard-fails here."""
    import shutil
    override = settings().paperima_browser_executable.strip()
    if override and Path(override).is_file():
        return override
    found = shutil.which("chrome") or shutil.which("google-chrome") or shutil.which("chrome.exe")
    if found:
        return found
    for root in (Path(r"C:\Program Files"), Path(r"C:\Program Files (x86)")):
        candidate = root / "Google" / "Chrome" / "Application" / "chrome.exe"
        if candidate.is_file():
            return str(candidate)
    for candidate in ("/usr/bin/google-chrome", "/usr/bin/chromium-browser",
                      "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"):
        if Path(candidate).is_file():
            return candidate
    return ""


def _paperima_version(dist_dir: str) -> str:
    """Best-effort version string for cache-key/provenance purposes, read
    from Paperima's OWN built manifest — never assumed, never hardcoded
    beyond the commit this integration was verified against."""
    try:
        manifest = json.loads((Path(dist_dir) / "manifest.webmanifest").read_text())
        return str(manifest.get("version", "")) or "unknown"
    except Exception:
        return "unknown"


def cache_key(image_path: str, animation_type: str, duration_sec: float, fps: int,
             width: int, height: int, shadow_strength: float, texture_index: int,
             wobble_strength: float, background_mode: str) -> str:
    try:
        image_hash = hashlib.sha256(Path(image_path).read_bytes()).hexdigest()[:16]
    except OSError:
        image_hash = "missing"
    payload = json.dumps({
        "worker_version": WORKER_VERSION,
        "paperima_version": _paperima_version(settings().paperima_dist_dir),
        "image_hash": image_hash,
        "animation_type": animation_type,
        "duration_sec": round(duration_sec, 2),
        "fps": fps, "width": width, "height": height,
        "shadow_strength": round(shadow_strength, 1),
        "texture_index": texture_index,
        "wobble_strength": round(wobble_strength, 2),
        "background_mode": background_mode,
    }, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()[:24]


async def _ensure_worker() -> asyncio.subprocess.Process:
    global _worker
    if _worker and _worker.returncode is None:
        return _worker
    app = ROOT / "apps" / "remotion"
    node = find_node()
    compiler = app / "node_modules" / ".bin" / "tsc"
    built = app / "dist-paperima" / "worker.js"
    source = app / "src" / "paperima" / "worker.ts"
    if not node:
        raise RuntimeError(
            "Paperima worker needs Node and none was found (checked $NODE_BIN, "
            "PATH and ~/.nvm/versions/node). Install Node, or set NODE_BIN.")
    if not compiler.is_file():
        raise RuntimeError(
            f"Paperima worker needs its npm packages: run `npm install` in {app}")
    env = os.environ.copy()
    env["PATH"] = f"{Path(node).parent}{os.pathsep}{env.get('PATH', '')}"
    if not built.is_file() or built.stat().st_mtime < source.stat().st_mtime:
        compile_proc = await asyncio.create_subprocess_exec(
            str(compiler), "-p", "tsconfig.paperima.json", cwd=app, env=env,
            stderr=asyncio.subprocess.PIPE)
        _, compile_error = await compile_proc.communicate()
        if compile_proc.returncode:
            raise RuntimeError(compile_error.decode(errors="replace")[-1200:])
    chrome = _find_chrome()
    if chrome:
        env["PAPERIMA_BROWSER_EXECUTABLE"] = chrome
    _worker = await asyncio.create_subprocess_exec(
        node, "dist-paperima/worker.js", cwd=app, env=env,
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE)
    return _worker


async def _stop_worker() -> None:
    global _worker, _worker_jobs
    if _worker and _worker.returncode is None:
        _worker.terminate()
        await _worker.wait()
    _worker = None
    _worker_jobs = 0


async def close_worker() -> None:
    await _stop_worker()


async def _worker_render(payload: dict, timeout_s: float) -> dict:
    async with _worker_lock:
        global _worker_jobs
        if (settings().production_optimizer_enabled and _worker and
                _worker_jobs >= settings().optimizer_paperima_restart_jobs):
            await _stop_worker()
        proc = await _ensure_worker()
        try:
            proc.stdin.write((json.dumps(payload) + "\n").encode())
            await proc.stdin.drain()
            line = await asyncio.wait_for(proc.stdout.readline(), timeout=timeout_s)
            if not line:
                error = (await proc.stderr.read()).decode(errors="replace")[-1200:]
                raise RuntimeError(error or "Paperima worker exited")
            result = json.loads(line)
            if not result.get("ok"):
                raise RuntimeError(result.get("error", "Paperima render failed"))
            _worker_jobs += 1
            return result
        except Exception:
            if settings().production_optimizer_enabled:
                await _stop_worker()
            raise


async def render(scene_id: str, image_path: str, animation_type: AnimationType, *,
                 duration_sec: float, fps: int, width: int, height: int,
                 shadow_strength: float = 60.0, texture_index: int = 0,
                 wobble_strength: float = 1.5,
                 background_mode: BackgroundMode = "greenscreen",
                 timeout_s: float | None = None) -> PaperimaRenderProvenance:
    """Animate one Scribus-produced document PNG through Paperima.

    Never raises. `status`:
      - "cache_hit"   — identical (image, params) already rendered this run
      - "rendered"    — a real Paperima render just completed
      - "unavailable" — Paperima isn't installed/enabled; caller must leave
                        the scene's existing papercraft/camera_movement alone
      - "unresolved"  — Paperima IS available but this specific render failed
                        (worker crash, timeout, bad image, ...); same caller
                        contract as "unavailable"
    """
    started = time.perf_counter()
    key = cache_key(image_path, animation_type, duration_sec, fps, width, height,
                    shadow_strength, texture_index, wobble_strength, background_mode)
    out_dir = settings().data_dir / "cache" / "paperima"
    out_dir.mkdir(parents=True, exist_ok=True)
    output = out_dir / f"{key}.mp4"
    base = dict(scene_id=scene_id, source_image=image_path,
               animation_type=animation_type, cache_key=key, fps=fps,
               width=width, height=height, duration_sec=duration_sec)

    if output.is_file() and output.stat().st_size:
        return PaperimaRenderProvenance(**base, status="cache_hit",
            render_path=str(output), render_ms=0)

    if not available():
        return PaperimaRenderProvenance(**base, status="unavailable",
            render_ms=(time.perf_counter() - started) * 1000,
            error="Paperima not enabled or dist dir not found "
                  "(set PAPERIMA_ENGINE_ENABLED=1 and PAPERIMA_DIST_DIR)",
            used_fallback=True)

    timeout = timeout_s or settings().paperima_render_timeout_s
    payload = {
        "id": scene_id,
        "distDir": settings().paperima_dist_dir.replace("\\", "/"),
        "imagePath": str(image_path).replace("\\", "/"),
        "outputPath": str(output).replace("\\", "/"),
        "animationType": animation_type,
        "durationSec": duration_sec, "fps": fps, "width": width, "height": height,
        "shadowStrength": shadow_strength, "textureIndex": texture_index,
        "wobbleStrength": wobble_strength, "backgroundMode": background_mode,
        "timeoutMs": int(timeout * 1000),
    }
    try:
        result = await _worker_render(payload, timeout + 30.0)
        return PaperimaRenderProvenance(**base, status="rendered",
            render_path=str(output), render_ms=float(result.get("renderMs", 0)),
            downloaded_bytes=int(result.get("downloadedBytes", 0)))
    except Exception as exc:  # noqa: BLE001 — degrade, never break the render
        output.unlink(missing_ok=True)
        return PaperimaRenderProvenance(**base, status="unresolved",
            render_ms=(time.perf_counter() - started) * 1000,
            error=f"{type(exc).__name__}: {str(exc)[:240]}", used_fallback=True)
