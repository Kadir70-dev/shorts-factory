"""CPU-only cinematic 2.5D finance footage from user-provided stills/cutouts.

This is NOT neural image-to-video: the animation is deterministic layer parallax,
camera and atmosphere. Silent H.264 for existing K70 voice and captions.
No GPU/network required, no chart values or financial evidence fabricated.
"""
from __future__ import annotations
import hashlib
import json
import math
import random
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from PIL import Image, ImageDraw, ImageFilter

ENGINE_VERSION = "f1.0"
ALLOWED_MOTIONS = ("dolly_in", "dolly_out", "truck_left", "truck_right", "static")
MAX_SOURCE_PIXELS = 12_000_000
MAX_CANVAS_PIXELS = 1_200_000


class EngineError(ValueError):
    pass


def _bound(n: Any, low: float, high: float, label: str) -> float:
    try:
        value = float(n)
    except (TypeError, ValueError) as exc:
        raise EngineError(f"{label}: expected a number") from exc
    if not math.isfinite(value) or not low <= value <= high:
        raise EngineError(f"{label}: must be between {low} and {high}")
    return value


def _local(root: Path, path: str) -> Path:
    if not isinstance(path, str) or not path or "://" in path:
        raise EngineError("Image asset must be a relative local file path")
    value = Path(path)
    if value.is_absolute():
        raise EngineError("Image asset must be relative to its spec directory")
    result = (root / value).resolve()
    if not result.is_relative_to(root.resolve()):
        raise EngineError("Image path escapes shot directory")
    if not result.is_file() or result.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise EngineError(f"Image asset missing or unsupported: {path}")
    return result


def _load(path: Path, *, needs_alpha: bool) -> Image.Image:
    with Image.open(path) as source:
        if source.width * source.height > MAX_SOURCE_PIXELS:
            raise EngineError(f"Source image exceeds low-RAM image limit: {path.name}")
        image = source.convert("RGBA")
    if needs_alpha:
        minimum, maximum = image.getchannel("A").getextrema()
        if minimum == 255:
            raise EngineError(f"Layer {path.name} must have real transparency")
        if maximum < 10:
            raise EngineError(f"Layer {path.name} is completely transparent")
    return image


@dataclass(frozen=True)
class Plane:
    image: Image.Image
    depth: float
    opacity: float
    name: str


class FinanceShot:
    """Reusable scene renderer; no per-frame model inference or downloads."""

    def __init__(self, spec: dict[str, Any], root: Path):
        self.root = Path(root).resolve()
        self.w = int(_bound(spec.get("width", 640), 160, 1920, "width"))
        self.h = int(_bound(spec.get("height", 360), 160, 1920, "height"))
        if self.w * self.h > MAX_CANVAS_PIXELS:
            raise EngineError("Canvas exceeds conservative CPU pixel budget")
        self.fps = int(_bound(spec.get("fps", 18), 6, 30, "fps"))
        self.duration = _bound(spec.get("duration_sec", 5), 0.2, 20, "duration_sec")
        self.motion = spec.get("camera", "dolly_in")
        if self.motion not in ALLOWED_MOTIONS:
            raise EngineError(f"camera must be one of {ALLOWED_MOTIONS}")
        self.strength = _bound(spec.get("camera_strength", 0.08), 0, 0.20, "camera_strength")
        self.seed = int(_bound(spec.get("seed", 7), 0, 999999, "seed"))
        self.bg_color = spec.get("background_color", "#081626")
        if not isinstance(self.bg_color, str):
            raise EngineError("background_color must be a color string")
        try:
            Image.new("RGB", (1, 1), self.bg_color)
        except ValueError as exc:
            raise EngineError("Invalid background color") from exc
        image = _local(self.root, spec.get("background", ""))
        self.background = Plane(_load(image, needs_alpha=False), 0.1, 1.0, "background")
        raw_layers = spec.get("layers", [])
        if not isinstance(raw_layers, list) or len(raw_layers) > 4:
            raise EngineError("layers must be a list with up to 4 separate RGBA cutouts")
        self.layers = []
        for i, layer in enumerate(raw_layers):
            if not isinstance(layer, dict):
                raise EngineError(f"layer {i} must be an object")
            self.layers.append(Plane(
                _load(_local(self.root, layer.get("path", "")), needs_alpha=True),
                _bound(layer.get("depth", 0.75), 0, 1, "depth"),
                _bound(layer.get("opacity", 1.0), 0.05, 1, "opacity"),
                f"layer_{i}"))
        effects = spec.get("effects", {})
        if not isinstance(effects, dict):
            raise EngineError("effects must be an object")
        self.clouds = bool(effects.get("clouds", False))
        self.dust = bool(effects.get("dust", True))
        self.glow = bool(effects.get("light_glow", True))
        self._cloud_sheet = self._init_clouds() if self.clouds else None
        rng = random.Random(self.seed)
        self._particles = [(rng.random(), rng.random(), rng.uniform(0.2, 1.0),
                            rng.randint(1, 3)) for _ in range(45)] if self.dust else []
        self._glow_sheet = self._init_glow() if self.glow else None

    def _init_clouds(self) -> Image.Image:
        rng = random.Random(self.seed + 21)
        width = round(self.w * 1.6)
        cloud = Image.new("RGBA", (width, self.h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(cloud)
        for _ in range(8):
            x = rng.randrange(width)
            y = rng.randrange(max(1, self.h // 2))
            rx = rng.randint(max(15, self.w // 13), max(18, self.w // 5))
            ry = rng.randint(max(8, self.h // 35), max(10, self.h // 12))
            draw.ellipse((x-rx, y-ry, x+rx, y+ry), fill=(230, 236, 248, 26))
        return cloud.filter(ImageFilter.GaussianBlur(radius=max(8, round(self.w / 35))))

    def _init_glow(self) -> Image.Image:
        image = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        radius = max(35, self.w // 7)
        cx, cy = round(self.w * .78), round(self.h * .25)
        draw.ellipse((cx-radius, cy-radius, cx+radius, cy+radius),
                     fill=(142, 183, 247, 26))
        return image.filter(ImageFilter.GaussianBlur(radius=max(18, radius // 2)))

    def _camera_factor(self, phase: float, depth: float) -> tuple[float, float, float]:
        eased = phase * phase * (3 - 2 * phase)
        d = 0.35 + 0.65 * depth
        if self.motion == "dolly_in":
            return 1 + self.strength * eased * d, 0, 0
        if self.motion == "dolly_out":
            return 1 + self.strength * (1-eased) * d, 0, 0
        if self.motion == "truck_left":
            return 1.09, -self.strength * (eased-.5) * d, 0
        if self.motion == "truck_right":
            return 1.09, self.strength * (eased-.5) * d, 0
        return 1.0, 0, 0

    def _transformed(self, plane: Plane, t: float) -> Image.Image:
        progress = min(1, max(0, t / self.duration))
        zoom, dx, dy = self._camera_factor(progress, plane.depth)
        w, h = self.w, self.h
        scale = max(w / plane.image.width, h / plane.image.height) * (1.10 + zoom-1)
        sw = max(w, round(plane.image.width * scale))
        sh = max(h, round(plane.image.height * scale))
        resized = plane.image.resize((sw, sh), Image.Resampling.BICUBIC)
        ox = round((sw-w)/2 - dx*w)
        oy = round((sh-h)/2 - dy*h)
        x, y = max(0, min(sw-w, ox)), max(0, min(sh-h, oy))
        cropped = resized.crop((x, y, x+w, y+h))
        if plane.opacity < 1:
            cropped.putalpha(cropped.getchannel("A").point(lambda a: round(a*plane.opacity)))
        return cropped

    def frame(self, t: float) -> Image.Image:
        if not 0 <= t <= self.duration:
            raise EngineError("frame time outside clip duration")
        screen = Image.new("RGBA", (self.w, self.h), self.bg_color)
        screen.alpha_composite(self._transformed(self.background, t))
        if self._cloud_sheet:
            cx = round((t * self.w * .013) % (self._cloud_sheet.width-self.w))
            screen.alpha_composite(self._cloud_sheet.crop((cx, 0, cx+self.w, self.h)))
        for plane in sorted(self.layers, key=lambda x: x.depth):
            screen.alpha_composite(self._transformed(plane, t))
        if self._glow_sheet:
            screen.alpha_composite(self._glow_sheet)
        if self._particles:
            lighting = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))
            draw = ImageDraw.Draw(lighting)
            for x, y, speed, radius in self._particles:
                px = round(((x+t*speed*.006) % 1) * self.w)
                py = round(((y-t*speed*.017) % 1) * self.h)
                draw.ellipse((px-radius, py-radius, px+radius, py+radius),
                             fill=(199, 222, 255, 65))
            screen.alpha_composite(lighting)
        return screen.convert("RGB")


def _validated_probe(path: Path, *, w: int, h: int, fps: int, duration: float) -> bool:
    try:
        probe = subprocess.run(["ffprobe", "-v", "error", "-show_streams",
                                "-show_format", "-of", "json", str(path)],
                               capture_output=True, text=True, timeout=20, check=True)
        result = json.loads(probe.stdout)
        video = [s for s in result["streams"] if s["codec_type"] == "video"]
        if len(video) != 1 or video[0]["codec_name"] != "h264":
            return False
        return (video[0]["width"] == w and video[0]["height"] == h and
                abs(float(result["format"]["duration"]) - duration) <= max(0.12, 1/fps+.05))
    except (FileNotFoundError, KeyError, ValueError, OSError, subprocess.SubprocessError):
        return False


def _key(spec: dict, root: Path) -> str:
    files = [spec["background"]] + [layer["path"] for layer in spec.get("layers", [])]
    digest = hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(",", ":")).encode())
    digest.update(ENGINE_VERSION.encode())
    for rel in files:
        path = _local(root, rel)
        digest.update(str(rel).encode())
        with path.open("rb") as inp:
            for chunk in iter(lambda: inp.read(512*1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def render_clip(spec_file: Path, target: Path, *, cache_dir: Path | None = None) -> dict[str, Any]:
    """Create/reuse an atomic silent MP4 with auditable provenance."""
    spec_file = Path(spec_file).resolve()
    root = spec_file.parent
    spec = json.loads(spec_file.read_text(encoding="utf-8"))
    if not isinstance(spec, dict):
        raise EngineError("Shot spec must be a JSON object")
    shot = FinanceShot(spec, root)
    key = _key(spec, root)
    target = Path(target).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    cached = (Path(cache_dir).resolve() / key / "shot.mp4") if cache_dir else None
    started = time.monotonic()
    hit = bool(cached and cached.is_file() and
               _validated_probe(cached, w=shot.w, h=shot.h, fps=shot.fps,
                                duration=shot.duration))
    if hit:
        if target != cached:
            shutil.copy2(cached, target)
    else:
        temporary = target.with_name(target.stem + ".partial.mp4")
        args = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                "-f", "rawvideo", "-pixel_format", "rgb24", "-video_size",
                f"{shot.w}x{shot.h}", "-framerate", str(shot.fps), "-i", "pipe:0",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                "-pix_fmt", "yuv420p", "-threads", "2", "-an",
                "-movflags", "+faststart", "-t", str(shot.duration), str(temporary)]
        proc = subprocess.Popen(args, stdin=subprocess.PIPE, stderr=subprocess.PIPE,
                                stdout=subprocess.DEVNULL)
        try:
            assert proc.stdin is not None
            for n in range(max(1, round(shot.duration * shot.fps))):
                proc.stdin.write(shot.frame(n / shot.fps).tobytes())
            proc.stdin.close()
            assert proc.stderr is not None
            error = proc.stderr.read().decode(errors="replace")
            status = proc.wait(timeout=60)
            if status:
                raise RuntimeError("ffmpeg render failed: " + error[-1200:])
            if not _validated_probe(temporary, w=shot.w, h=shot.h,
                                    fps=shot.fps, duration=shot.duration):
                raise RuntimeError("MP4 validation failed (codec/dimensions/duration)")
            temporary.replace(target)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            temporary.unlink(missing_ok=True)
        if cached and target != cached:
            cached.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, cached)
    report = {"engine_version": ENGINE_VERSION,
              "status": "cache_hit" if hit else "rendered",
              "asset_kind": "2.5d_composited_video_not_neural_i2v",
              "source_spec": str(spec_file), "path": str(target), "cache_key": key,
              "width": shot.w, "height": shot.h, "fps": shot.fps,
              "duration_sec": shot.duration,
              "elapsed_seconds": round(time.monotonic()-started, 3),
              "source_layer_count": len(shot.layers)+1,
              "note": "Illustrative scenes only; not archival footage or numerical evidence."}
    target.with_suffix(".json").write_text(json.dumps(report, indent=2),
                                           encoding="utf-8")
    return report
