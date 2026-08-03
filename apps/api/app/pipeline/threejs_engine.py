"""Python orchestration for the reusable TypeScript Three.js browser worker."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from ..brand import load_theme
from ..config import ROOT, settings
from ..schemas.scene import (Scene, SceneGraph, StoryboardScene,
                             ThreeJSRenderProvenance)

TEMPLATE_VERSION = "1.0.1"
TEMPLATES = (
    "number_counter", "comparison_towers", "share_ownership",
    "dividend_cashflow", "timeline_flythrough", "compound_growth",
)
_worker: asyncio.subprocess.Process | None = None
_worker_lock = asyncio.Lock()


@dataclass(frozen=True)
class RenderSpec:
    template: str
    title: str
    label: str
    values: tuple[float, ...]
    labels: tuple[str, ...]


def _number(value: str) -> float | None:
    match = re.search(r"[-+]?\d[\d,]*(?:\.\d+)?", value)
    if not match:
        return None
    number = float(match.group(0).replace(",", ""))
    lower = value.lower()
    if "trillion" in lower or re.search(r"\d\s*t\b", lower): number *= 1e12
    elif "billion" in lower or re.search(r"\d\s*b\b", lower): number *= 1e9
    elif "million" in lower or re.search(r"\d\s*m\b", lower): number *= 1e6
    elif re.search(r"\d\s*k\b", lower): number *= 1e3
    return number


def map_template(beat: StoryboardScene) -> RenderSpec | None:
    """Map validated Phase 2 data only when 3D motion improves comprehension."""
    if not beat.threejs_candidate:
        return None
    text = f"{beat.narration} {beat.visual_objective}".lower()
    values = tuple(value for raw in beat.financial_numbers
                   if (value := _number(raw)) is not None)
    title = (beat.company or beat.primary_entity or "Finance explained")[:48]
    label = (beat.overlay_text[0] if beat.overlay_text else beat.narration)[:72]
    if any(word in text for word in ("ownership", "shareholder", "stake", "owns")):
        template = "share_ownership"
    elif "dividend" in text or "cash flow" in text:
        template = "dividend_cashflow"
    elif any(word in text for word in ("compound", "cagr", "compounded")):
        template = "compound_growth"
    elif beat.year and any(word in text for word in ("since", "timeline", "history", "from")):
        template = "timeline_flythrough"
    elif len(values) >= 2 or any(word in text for word in ("revenue versus", "profit versus", "compared")):
        template = "comparison_towers"
    elif values:
        template = "number_counter"
    else:
        return None
    if template == "share_ownership" and not values: values = (60.0, 40.0)
    if template == "dividend_cashflow" and not values: values = (1.0,)
    if template == "compound_growth" and len(values) < 2: values = (100.0, values[0] if values else 10.0)
    raw_labels = ([str(beat.year)] if beat.year else []) + beat.financial_numbers
    labels = tuple(dict.fromkeys(raw_labels))
    return RenderSpec(template, title, label, values or (0.0,), labels or ("START", "NOW"))


def _quality_dimensions(graph: SceneGraph, quality: str) -> tuple[int, int]:
    if quality == "preview":
        return 360, 640
    return 1080, 1920


def _payload(graph: SceneGraph, scene: Scene, beat: StoryboardScene,
             spec: RenderSpec, quality: str, seed: int, frames_dir: Path) -> dict:
    theme = load_theme(graph.brand_id or "k70")
    width, height = _quality_dimensions(graph, quality)
    fps = graph.fps if graph.fps in (30, 60) else 30
    frames = max(1, round(scene.duration_sec * fps))
    if frames > settings().threejs_max_frames:
        raise ValueError(f"Three.js frame budget exceeded: {frames}")
    return {
        "id": beat.scene_id, "outputDir": str(frames_dir),
        "template": spec.template, "width": width, "height": height,
        "fps": fps, "frames": frames, "seed": seed, "title": spec.title,
        "label": spec.label, "values": spec.values, "labels": spec.labels,
        "palette": theme.palette, "fontFamily": theme.display.name,
    }


def cache_key(graph: SceneGraph, scene: Scene, beat: StoryboardScene,
              spec: RenderSpec, quality: str, seed: int) -> str:
    theme = load_theme(graph.brand_id or "k70")
    body = json.dumps({
        "version": TEMPLATE_VERSION, "template": spec.template,
        "storyboard": beat.model_dump(mode="json"), "duration": scene.duration_sec,
        "fps": graph.fps, "dimensions": _quality_dimensions(graph, quality),
        "quality": quality, "seed": seed, "brand": theme.fingerprint,
    }, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode()).hexdigest()


async def _ensure_worker() -> asyncio.subprocess.Process:
    global _worker
    if _worker and _worker.returncode is None:
        return _worker
    app = ROOT / "apps" / "remotion"
    node = shutil.which("node")
    compiler = app / "node_modules" / ".bin" / "tsc"
    built = app / "dist-threejs" / "worker.js"
    source = app / "src" / "threejs" / "worker.ts"
    if not node or not compiler.is_file():
        raise RuntimeError("Three.js worker dependencies are not installed")
    if not built.is_file() or built.stat().st_mtime < source.stat().st_mtime:
        compile_proc = await asyncio.create_subprocess_exec(
            str(compiler), "-p", "tsconfig.threejs.json", cwd=app,
            stderr=asyncio.subprocess.PIPE)
        _, compile_error = await compile_proc.communicate()
        if compile_proc.returncode:
            raise RuntimeError(compile_error.decode(errors="replace")[-1200:])
    env = os.environ.copy()
    if settings().threejs_browser_executable:
        env["THREEJS_BROWSER_EXECUTABLE"] = settings().threejs_browser_executable
    _worker = await asyncio.create_subprocess_exec(
        node, "dist-threejs/worker.js", cwd=app, env=env,
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE)
    return _worker


async def _worker_render(payload: dict) -> dict:
    if settings().threejs_worker_url.strip():
        async with httpx.AsyncClient(timeout=settings().threejs_render_timeout_s) as client:
            response = await client.post(settings().threejs_worker_url, json=payload)
        response.raise_for_status()
        result = response.json()
        if not result.get("ok"):
            raise RuntimeError(result.get("error", "Three.js render failed"))
        return result
    async with _worker_lock:
        proc = await _ensure_worker()
        proc.stdin.write((json.dumps(payload) + "\n").encode())
        await proc.stdin.drain()
        line = await asyncio.wait_for(proc.stdout.readline(),
                                      timeout=settings().threejs_render_timeout_s)
        if not line:
            error = (await proc.stderr.read()).decode(errors="replace")[-1200:]
            raise RuntimeError(error or "Three.js worker exited")
        result = json.loads(line)
        if not result.get("ok"):
            raise RuntimeError(result.get("error", "Three.js render failed"))
        return result


async def _encode(frames: Path, fps: int, output: Path) -> None:
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-framerate", str(fps),
        "-i", str(frames / "frame_%05d.png"), "-c:v", "libx264", "-preset",
        "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags",
        "+faststart", "-y", str(output), stderr=asyncio.subprocess.PIPE)
    _, stderr = await proc.communicate()
    if proc.returncode or not output.is_file():
        raise RuntimeError(stderr.decode(errors="replace")[-1000:])


async def render(graph: SceneGraph, scene: Scene, beat: StoryboardScene,
                 quality: str | None = None, seed: int | None = None
                 ) -> ThreeJSRenderProvenance:
    """Render one validated beat, returning provenance even on failure."""
    beat = StoryboardScene.model_validate(beat.model_dump())
    quality = quality or settings().threejs_quality.strip().lower()
    if quality not in ("preview", "final"):
        quality = "final"
    fps = graph.fps if graph.fps in (30, 60) else 30
    chosen_seed = seed if seed is not None else int(hashlib.sha256(
        f"{graph.meta.video_id}:{beat.scene_id}".encode()).hexdigest()[:8], 16)
    theme = load_theme(graph.brand_id or "k70")
    mapped = map_template(beat)
    width, height = _quality_dimensions(graph, quality)
    if mapped is None:
        raise ValueError("storyboard beat does not map to a clarity-improving template")
    key = cache_key(graph, scene, beat, mapped, quality, chosen_seed)
    root = settings().data_dir / "cache" / "threejs" / key
    output = root / "render.mp4"
    base = dict(scene_id=scene.id, storyboard_scene_id=beat.scene_id,
                template=mapped.template, template_version=TEMPLATE_VERSION,
                cache_key=key, seed=chosen_seed, fps=fps, width=width, height=height,
                quality=quality, brand_id=graph.brand_id,
                brand_fingerprint=theme.fingerprint,
                legacy_decision=scene.visual.strategy)
    if output.is_file() and output.stat().st_size:
        return ThreeJSRenderProvenance(**base, status="cache_hit",
            render_path=str(output), render_ms=0, peak_rss_mb=0)
    frames = root / "frames"
    started = time.perf_counter()
    try:
        frames.mkdir(parents=True, exist_ok=True)
        payload = _payload(graph, scene, beat, mapped, quality, chosen_seed, frames)
        result = await _worker_render(payload)
        await _encode(frames, fps, output)
        shutil.rmtree(frames, ignore_errors=True)
        return ThreeJSRenderProvenance(**base, status="rendered",
            render_path=str(output), render_ms=(time.perf_counter() - started) * 1000,
            peak_rss_mb=float(result.get("rssMb", 0)))
    except Exception as exc:  # explicit unresolved; never unrelated stock
        shutil.rmtree(frames, ignore_errors=True)
        output.unlink(missing_ok=True)
        return ThreeJSRenderProvenance(**base, status="unresolved",
            render_ms=(time.perf_counter() - started) * 1000, peak_rss_mb=0,
            error=f"{type(exc).__name__}: {str(exc)[:240]}")


async def close_worker() -> None:
    global _worker
    if _worker and _worker.returncode is None:
        _worker.terminate()
        await _worker.wait()
    _worker = None
