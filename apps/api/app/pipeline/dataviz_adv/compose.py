"""FFmpeg compositor: real footage (graded, push-in) + a streamed RGBA graphics layer -> one scene clip.

    render_video(out, frames, segments, overlay_fn, bg=Bg("blur"))

`segments` hard-cut inside the scene (every cut is a real clip, never a generated filler).  `Bg` picks how the footage
sits behind the graphics:
    plain         graded footage
    blur          blurred + darkened (chart/map panels)
    ramp_to_blur  footage -> blurred between t0 and t0+dur   (footage-to-chart transition)
    ramp_to_clear blurred -> footage                         (chart-to-footage transition)
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PIL import Image

from .core import FPS, H, W

GRADE_PLAIN = ("eq=contrast=1.12:saturation=1.08:brightness=-0.035,"
               "colorbalance=rs=-0.04:bs=0.07:rm=-0.01:bm=0.03:rh=0.06:bh=-0.05")
GRADE_BLUR = "gblur=sigma=16,eq=contrast=1.05:saturation=0.85:brightness=-0.24"


@dataclass
class Bg:
    mode: str = "plain"
    t0: float = 0.0
    dur: float = 0.6

    def __post_init__(self):
        if self.mode not in ("plain", "blur", "ramp_to_blur", "ramp_to_clear"):
            raise ValueError(f"unknown background mode {self.mode!r}")


def build_filter(n_seg: int, seg_durs: list[float], bg: Bg, first_scene: bool, zoom: float = 0.07) -> str:
    parts = []
    for k, dur in enumerate(seg_durs):
        bump = "" if (k > 0 or first_scene) else "+0.075*max(0,1-t/0.22)"
        z = f"(1+{zoom}*t/{max(dur, 0.2):.3f}{bump})"
        parts.append(f"[{k}:v]scale=w='ceil({W}*{z}/2)*2':h='ceil({H}*{z}/2)*2':eval=frame:force_original_aspect_ratio=increase,"
                     f"crop={W}:{H},fps={FPS},trim=duration={dur:.3f},setpts=PTS-STARTPTS,setsar=1[v{k}]")
    cat = ("".join(f"[v{k}]" for k in range(n_seg)) + f"concat=n={n_seg}:v=1:a=0[bg0]") if n_seg > 1 else "[v0]null[bg0]"
    if bg.mode == "plain":
        graded = f"[bg0]{GRADE_PLAIN}[bg]"
    elif bg.mode == "blur":
        graded = f"[bg0]{GRADE_BLUR}[bg]"
    else:
        p = f"min(1,max(0,(T-{bg.t0:.3f})/{bg.dur:.3f}))"
        if bg.mode == "ramp_to_clear":
            p = f"(1-{p})"
        graded = (f"[bg0]split[ba][bb];[ba]{GRADE_PLAIN}[bc];[bb]{GRADE_BLUR}[bd];"
                  f"[bc][bd]blend=all_expr='A*(1-{p})+B*{p}'[bg]")
    return ";".join(parts) + ";" + cat + ";" + graded + f";[bg][{n_seg}:v]overlay=0:0:format=auto,vignette=PI/4.6,noise=alls=6:allf=t+u,format=yuv420p[v]"


def render_video(out: Path, frames: int, segments: list[tuple[Path, float, float]], overlay_fn: Callable[[float], Image.Image],
                 bg: Bg = Bg(), first_scene: bool = False) -> None:
    """segments = [(clip, start_seconds, seconds)]; overlay_fn(t) -> RGBA PIL image (W x H)."""
    n = len(segments)
    inputs = []
    for clip, start, dur in segments:
        inputs += ["-ss", f"{start:.3f}", "-t", f"{dur + 0.25:.3f}", "-i", str(clip)]
    chain = build_filter(n, [d for _, _, d in segments], bg, first_scene)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", *inputs, "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}", "-r", str(FPS),
           "-i", "pipe:0", "-filter_complex", chain, "-map", "[v]", "-frames:v", str(frames), "-c:v", "libx264", "-preset", "fast",
           "-crf", "17", "-pix_fmt", "yuv420p", "-r", str(FPS), str(out)]
    log = out.with_suffix(".log")
    with open(log, "wb") as lf:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=lf)
        try:
            for f in range(frames):
                proc.stdin.write(overlay_fn(f / FPS).tobytes())
            proc.stdin.close()
        except BrokenPipeError:
            pass
        rc = proc.wait()
    if rc != 0:
        raise RuntimeError(f"ffmpeg scene render failed ({out.name}): {log.read_text()[-400:]}")
    log.unlink(missing_ok=True)


def render_graphics_only(out: Path, frames: int, overlay_fn: Callable[[float], Image.Image], bg_color=(8, 21, 37)) -> None:
    """Chart on the theme background (no footage): used for tests and demo clips."""
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c=#{bg_color[0]:02x}{bg_color[1]:02x}{bg_color[2]:02x}:s={W}x{H}:r={FPS}",
           "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "pipe:0", "-filter_complex",
           "[0:v][1:v]overlay=format=auto,format=yuv420p[v]", "-map", "[v]", "-frames:v", str(frames), "-c:v", "libx264", "-preset", "veryfast",
           "-crf", "19", "-pix_fmt", "yuv420p", "-r", str(FPS), str(out)]
    log = out.with_suffix(".log")
    with open(log, "wb") as lf:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=lf)
        try:
            for f in range(frames):
                proc.stdin.write(overlay_fn(f / FPS).tobytes())
            proc.stdin.close()
        except BrokenPipeError:
            pass
        rc = proc.wait()
    if rc != 0:
        raise RuntimeError(f"ffmpeg failed: {log.read_text()[-400:]}")
    log.unlink(missing_ok=True)
