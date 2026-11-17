"""
Media analysis with plain ffmpeg/ffprobe — no PySceneDetect, no OpenCV, no GPU.

  probe()          duration / resolution / fps / audio presence
  motion_curve()   per-0.1s scene-change score (cut detection AND motion energy)
  loudness_curve() per-0.1s momentary loudness (LUFS) — laughs, crashes, screams
  dhash()          64-bit difference hash of one frame for near-duplicate checks
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

SAMPLE_HZ = 10          # analysis resolution: one value per 0.1 s


def _run(cmd: list[str], timeout: int = 900) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def sha256(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while b := f.read(chunk):
            h.update(b)
    return h.hexdigest()


def _rate(value: str) -> float:
    try:
        num, _, den = value.partition("/")
        return float(num) / float(den or 1)
    except (ValueError, ZeroDivisionError):
        return 0.0


def probe(path: Path) -> dict:
    r = _run(["ffprobe", "-v", "error", "-show_streams", "-show_format",
              "-of", "json", str(path)], timeout=60)
    if r.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {path}: {r.stderr[:300]}")
    data = json.loads(r.stdout)
    v = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in data["streams"] if s["codec_type"] == "audio"), None)
    if v is None:
        raise ValueError(f"no video stream: {path}")
    dur = float(data["format"].get("duration") or v.get("duration") or 0)
    return {
        "duration": round(dur, 3),
        "width": int(v["width"]), "height": int(v["height"]),
        "fps": round(_rate(v.get("avg_frame_rate") or v.get("r_frame_rate", "0")), 3),
        "has_audio": a is not None,
        "vcodec": v.get("codec_name", ""), "acodec": (a or {}).get("codec_name", ""),
    }


def motion_curve(path: Path) -> list[float]:
    vf = (f"fps={SAMPLE_HZ},scale=160:-2,select='gte(scene,0)',"
          "metadata=print:key=lavfi.scene_score")
    r = _run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-vf", vf,
              "-an", "-f", "null", "-"])
    return [float(m) for m in re.findall(r"lavfi\.scene_score=([\d.]+)", r.stderr)]


def loudness_curve(path: Path) -> list[float]:
    r = _run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-vn",
              "-af", "ebur128=framelog=info", "-f", "null", "-"])
    return [max(-70.0, float(m)) for m in re.findall(r"\bM:\s*(-?[\d.]+)", r.stderr)]


def scene_cuts(motion: list[float], threshold: float = 0.32,
               min_gap: float = 0.6) -> list[float]:
    """Timestamps (s) where the scene score spikes past `threshold`."""
    cuts: list[float] = []
    for i, s in enumerate(motion):
        t = i / SAMPLE_HZ
        if s >= threshold and (not cuts or t - cuts[-1] >= min_gap) and t > 0.2:
            cuts.append(round(t, 2))
    return cuts


def dhash(path: Path, at: float) -> int | None:
    """9x8 grayscale difference hash of the frame at `at` seconds."""
    r = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{max(0, at):.3f}",
         "-i", str(path), "-frames:v", "1", "-vf", "scale=9:8:flags=area,format=gray",
         "-f", "rawvideo", "-"], capture_output=True, timeout=60)
    b = r.stdout
    if len(b) < 72:
        return None
    bits = 0
    for row in range(8):
        for col in range(8):
            bits = (bits << 1) | (b[row * 9 + col] > b[row * 9 + col + 1])
    return bits


def segment_hash(path: Path, start: float, end: float) -> str:
    """Three frame hashes (25/50/75 %) — robust to a re-trim of a few frames."""
    span = end - start
    hs = [dhash(path, start + span * f) for f in (0.25, 0.5, 0.75)]
    return ",".join(f"{h:016x}" for h in hs if h is not None)


def hash_distance(a: str, b: str) -> int:
    """Mean Hamming distance between two segment hashes (64 = unrelated)."""
    ha = [int(x, 16) for x in a.split(",") if x]
    hb = [int(x, 16) for x in b.split(",") if x]
    if not ha or not hb:
        return 64
    # best match per frame, so a clip trimmed or shifted by a second still hits
    best = [min(bin(x ^ y).count("1") for y in hb) for x in ha]
    return round(sum(best) / len(best))


def footage_signature(path: Path, start: float, end: float, crop: str = "",
                      n: int = 8) -> str:
    """n dHashes across a clip, taken from the live picture only (crop), for
    "same original footage" checks across different compilations."""
    pre = f"crop={crop}," if crop else ""
    out = []
    for k in range(n):
        t = start + (end - start) * (k + 0.5) / n
        r = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{max(0, t):.3f}",
             "-i", str(path), "-frames:v", "1", "-vf", f"{pre}scale=9:8:flags=area,format=gray",
             "-f", "rawvideo", "-"], capture_output=True, timeout=60)
        b = r.stdout
        if len(b) >= 72:
            bits = 0
            for row in range(8):
                for col in range(8):
                    bits = (bits << 1) | (b[row * 9 + col] > b[row * 9 + col + 1])
            out.append(f"{bits:016x}")
    return ",".join(out)


def min_pair_distance(a: str, b: str) -> int:
    """Closest frame pair between two footage signatures (64 = unrelated).
    Measured on the fixtures: different footage never came closer than 16."""
    ha = [int(x, 16) for x in a.split(",") if x]
    hb = [int(x, 16) for x in b.split(",") if x]
    if not ha or not hb:
        return 64
    return min(bin(x ^ y).count("1") for x in ha for y in hb)
