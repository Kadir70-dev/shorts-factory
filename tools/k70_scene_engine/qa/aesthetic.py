"""Deterministic AESTHETIC QA (production-fix brief, "Phase 11" of the
premium-visual-engine rebuild) -- a SEPARATE layer from perceptual.py's
structural/distribution QA.

perceptual.py answers "is the MIX of visual modes healthy" (percentages,
card-run length, shot diversity). It cannot tell a beautifully-lit house
from a flat-gray one, or a detailed character from a blurry blob -- its
own code says so. This module adds cheap, deterministic, no-GPU-required
computer-vision metrics that catch the specific failure classes a human
forensic audit found by eye: near-black/blown-out frames, suspiciously
flat/untextured regions, and near-empty low-detail compositions.

Explicitly NOT a substitute for human judgment -- this catches gross,
obvious technical failures (the kind "aesthetic QA" can realistically
detect without an ML model), not art direction, anatomy correctness, or
whether a shot is beautiful. Contact-sheet human inspection remains
mandatory (brief: "Do not merely create the file. ACTUALLY INSPECT IT.").

No new dependencies: numpy + Pillow only (both already in the venv), so
this runs on CPU today and is a trivial drop-in for the planned GPU
worker later (nothing here assumes GPU).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image


@dataclass
class AestheticReport:
    path: str
    width: int
    height: int
    mean_luma: float               # 0-255; very low/high = crushed/blown
    dark_fraction: float           # fraction of pixels near-black (<12/255)
    bright_fraction: float         # fraction of pixels near-white (>248/255)
    sharpness: float                # Laplacian-variance proxy; low = blurry/flat
    color_std: float                 # per-channel std dev averaged; low = flat/untextured
    edge_density: float              # fraction of pixels that are strong edges; low = empty/simple
    warnings: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.warnings

    def format(self) -> str:
        lines = [f"Aesthetic QA -- {Path(self.path).name} ({self.width}x{self.height})"]
        lines.append(f"  mean_luma={self.mean_luma:.1f}  dark%={self.dark_fraction*100:.1f}  "
                     f"bright%={self.bright_fraction*100:.1f}")
        lines.append(f"  sharpness={self.sharpness:.1f}  color_std={self.color_std:.1f}  "
                     f"edge_density={self.edge_density*100:.2f}%")
        for w in self.warnings:
            lines.append(f"  [WARN] {w}")
        lines.append(f"  AESTHETIC QA: {'PASS' if self.passed else 'FAIL'}")
        return "\n".join(lines)


def _laplacian_variance(gray: np.ndarray) -> float:
    """Cheap sharpness/detail proxy without cv2: convolve with a discrete
    Laplacian kernel, return the variance of the response. A blurry or
    flat-shaded (untextured) image has a low-variance response; a
    detailed, in-focus one has a high-variance response."""
    k = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float32)
    h, w = gray.shape
    padded = np.pad(gray, 1, mode="edge")
    resp = (
        padded[0:h, 1:w + 1] * k[0, 1] + padded[2:h + 2, 1:w + 1] * k[2, 1] +
        padded[1:h + 1, 0:w] * k[1, 0] + padded[1:h + 1, 2:w + 2] * k[1, 2] +
        padded[1:h + 1, 1:w + 1] * k[1, 1]
    )
    return float(resp.var())


def analyze_frame(image_path: Path, *,
                  min_sharpness: float = 8.0, min_color_std: float = 8.0,
                  min_edge_density: float = 0.015, max_dark_fraction: float = 0.55,
                  max_bright_fraction: float = 0.35) -> AestheticReport:
    """Thresholds are deliberately loose -- this is a coarse net for
    gross failures (a near-solid-black frame, a totally flat-shaded
    surface filling most of frame, an almost featureless composition),
    not a fine-grained beauty score. Tune against real examples, not
    guessed numbers, before trusting it as a hard gate."""
    img = Image.open(image_path).convert("RGB")
    arr = np.asarray(img).astype(np.float32)
    gray = arr.mean(axis=2)

    mean_luma = float(gray.mean())
    dark_fraction = float((gray < 12).mean())
    bright_fraction = float((gray > 248).mean())
    sharpness = _laplacian_variance(gray)
    color_std = float(arr.std(axis=(0, 1)).mean())

    gx = np.abs(np.diff(gray, axis=1))
    gy = np.abs(np.diff(gray, axis=0))
    edge_density = float(((gx[:-1, :] + gy[:, :-1]) > 25).mean())

    warnings = []
    if dark_fraction > max_dark_fraction:
        warnings.append(f"{dark_fraction*100:.1f}% of frame is near-black (>{max_dark_fraction*100:.0f}%) "
                        "-- likely underlit/crushed")
    if bright_fraction > max_bright_fraction:
        warnings.append(f"{bright_fraction*100:.1f}% of frame is near-white (>{max_bright_fraction*100:.0f}%) "
                        "-- likely blown out / empty background")
    if sharpness < min_sharpness:
        warnings.append(f"sharpness {sharpness:.1f} below {min_sharpness} -- blurry or suspiciously flat/detail-less")
    if color_std < min_color_std:
        warnings.append(f"color_std {color_std:.1f} below {min_color_std} -- frame is unusually flat/untextured")
    if edge_density < min_edge_density:
        warnings.append(f"edge_density {edge_density*100:.2f}% below {min_edge_density*100:.1f}% "
                        "-- composition looks empty/low-detail")

    return AestheticReport(
        path=str(image_path), width=img.width, height=img.height,
        mean_luma=mean_luma, dark_fraction=dark_fraction, bright_fraction=bright_fraction,
        sharpness=sharpness, color_std=color_std, edge_density=edge_density, warnings=warnings,
    )


def analyze_video_frames(frame_paths: list[Path], **kwargs) -> list[AestheticReport]:
    return [analyze_frame(p, **kwargs) for p in frame_paths]


def extract_scene_frames(video_path: Path, scene_graph: dict, out_dir: Path) -> list[tuple[Path, str]]:
    """One frame per scene, at that scene's own midpoint, paired with its
    scene id -- more meaningful than blind evenly-spaced time slicing
    (which can land on transitions, and can't be traced back to which
    beat produced a flagged frame without guessing from the timestamp)."""
    import subprocess
    out_dir.mkdir(parents=True, exist_ok=True)
    t = 0.0
    results = []
    for scene in scene_graph["scenes"]:
        dur = scene["duration_sec"]
        mid = t + dur / 2
        out_path = out_dir / f"{scene['id']}.jpg"
        subprocess.run(
            ["ffmpeg", "-y", "-ss", f"{mid:.3f}", "-i", str(video_path),
             "-frames:v", "1", "-q:v", "3", str(out_path)],
            capture_output=True, text=True,
        )
        if out_path.exists():
            results.append((out_path, scene["id"]))
        t += dur
    return results


def extract_sample_frames(video_path: Path, out_dir: Path, n: int = 10) -> list[Path]:
    """Pulls N evenly-spaced individual frames from a video via ffmpeg --
    same sampling idea as perceptual.py's contact sheet, but as separate
    files so aesthetic.analyze_frame() can score each one instead of one
    combined tile image."""
    import subprocess
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
        capture_output=True, text=True, check=True,
    )
    duration = float(probe.stdout.strip())
    interval = duration / n
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i in range(n):
        t = interval * i + interval / 2
        out_path = out_dir / f"sample_{i:02d}.jpg"
        subprocess.run(
            ["ffmpeg", "-y", "-ss", f"{t:.3f}", "-i", str(video_path),
             "-frames:v", "1", "-q:v", "3", str(out_path)],
            capture_output=True, text=True,
        )
        if out_path.exists():
            paths.append(out_path)
    return paths
