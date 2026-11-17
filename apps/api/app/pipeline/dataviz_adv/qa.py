"""Frame-level quality checks for the advanced charts.  These inspect real drawn frames (via the Recorder), not
FFmpeg exit codes: clipped text, tiny text (mobile readability at 1080x1920), overlapping value labels,
frame-to-frame continuity and the encoded file's frame rate."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Callable, Iterable

import numpy as np
from PIL import Image

from .core import FPS, H, SAFE_BOTTOM, SAFE_SIDE, SAFE_TOP, W, Recorder, new_layer

MIN_TEXT_PX = 30          # smallest allowed glyph size at 1080 wide (legible on a phone held at arm's length)
SAFE = (W * 0.04, H * 0.045, W * 0.96, H * (1 - SAFE_BOTTOM + 0.03))        # inside the frame, clear of the platform UI strip


def draw_and_record(draw_fn: Callable[[Image.Image, float], None], t: float) -> tuple[Image.Image, list[dict]]:
    L = new_layer()
    Recorder.start()
    try:
        draw_fn(L, t)
        boxes = list(Recorder.active or [])
    finally:
        Recorder.stop()
    return L, boxes


def text_issues(boxes: list[dict], *, safe=SAFE, min_px: int = MIN_TEXT_PX, ignore_tags: Iterable[str] = ()) -> list[str]:
    """Return human-readable problems for one frame's text boxes."""
    ig = set(ignore_tags)
    out = []
    for b in boxes:
        if b["tag"] in ig:
            continue
        if b["x0"] < safe[0] - 1 or b["x1"] > safe[2] + 1 or b["y0"] < safe[1] - 1 or b["y1"] > safe[3] + 1:
            out.append(f"{b['tag'] or 'text'} outside safe area: ({b['x0']:.0f},{b['y0']:.0f})-({b['x1']:.0f},{b['y1']:.0f})")
        if b["size"] and b["size"] < min_px:
            out.append(f"{b['tag']} too small: {b['size']}px < {min_px}px")
    return out


def overlap_issues(boxes: list[dict], tags: tuple[str, ...]) -> list[str]:
    """Pairs of boxes with these tags must not intersect (e.g. bar values vs names)."""
    sel = [b for b in boxes if b["tag"] in tags]
    out = []
    for i, a in enumerate(sel):
        for b in sel[i + 1:]:
            ix = min(a["x1"], b["x1"]) - max(a["x0"], b["x0"])
            iy = min(a["y1"], b["y1"]) - max(a["y0"], b["y0"])
            if ix > 4 and iy > 4:
                out.append(f"{a['tag']}/{b['tag']} overlap {ix:.0f}x{iy:.0f}px")
    return out


def frame_diff_series(draw_fn: Callable[[Image.Image, float], None], times: list[float]) -> list[float]:
    """Mean absolute change between consecutive frames (alpha-weighted, 1/8 scale) -- spikes mean a jump / pop."""
    prev, out = None, []
    for t in times:
        L = new_layer()
        draw_fn(L, t)
        arr = np.asarray(L.resize((W // 8, H // 8), Image.BILINEAR), dtype=np.float32)
        if prev is not None:
            out.append(float(np.abs(arr - prev).mean()))
        prev = arr
    return out


def probe(path: Path) -> dict:
    j = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries",
                                   "stream=width,height,r_frame_rate,avg_frame_rate,nb_read_frames,pix_fmt,codec_name:format=duration",
                                   "-of", "json", str(path)], capture_output=True, text=True, check=True).stdout)
    s = j["streams"][0]
    num, den = (int(x) for x in s["r_frame_rate"].split("/"))
    return {"w": s["width"], "h": s["height"], "fps": num / den, "frames": int(s["nb_read_frames"]), "codec": s["codec_name"],
            "pix_fmt": s["pix_fmt"], "duration": float(j["format"]["duration"])}


def frame_to_image(path: Path, t: float) -> Image.Image:
    p = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(path), "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"],
                       capture_output=True, check=True).stdout
    import io
    return Image.open(io.BytesIO(p)).convert("RGB")


def speech_activity(wav: Path, frame_s: float = 0.05, thresh: float = 800.0) -> list[bool]:
    """True per `frame_s` window where the voice track is louder than `thresh` (16-bit RMS)."""
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", str(wav), "-f", "s16le", "-ar", "16000", "-ac", "1", "-"], capture_output=True, check=True).stdout
    a = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
    n = int(16000 * frame_s)
    return [bool(np.sqrt(np.mean(a[i:i + n] ** 2)) > thresh) for i in range(0, len(a) - n, n)]


def caption_sync(activity: list[bool], words: list[dict], frame_s: float = 0.05, tol: float = 0.15) -> dict:
    """How well do caption word windows line up with real speech?  words = [{'w','s','e'}]."""
    def active(t0: float, t1: float) -> float:
        i0, i1 = int(max(0, t0) / frame_s), max(int(max(0, t1) / frame_s), int(max(0, t0) / frame_s) + 1)
        seg = activity[i0:i1]
        return sum(seg) / len(seg) if seg else 0.0
    quiet = [w["w"] for w in words if active(w["s"], w["e"]) < 0.2]
    cov = [(w["s"] - tol, w["e"] + tol) for w in words]
    loud = [i for i, a in enumerate(activity) if a]
    uncovered = [i for i in loud if not any(a <= i * frame_s <= b for a, b in cov)]
    return {"words": len(words), "words_over_silence": len(quiet), "loud_frames": len(loud), "uncovered_loud_frames": len(uncovered),
            "quiet_words": quiet[:10]}
