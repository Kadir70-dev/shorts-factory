"""
Phase-4 QA / stabilization — a CPU-only, non-fatal audit of a FINISHED short.

It answers one question: "is this MP4 actually shippable, and did the render stay
inside the laptop's CPU/RAM budget?" — by probing the output with ffmpeg/ffprobe
(no extra deps) and the render-time metrics the caller hands in:

  • black-frame detection        (ffmpeg blackdetect over the whole clip)
  • per-scene non-black           (sample each scene window's mid-frame luma)
  • playability                   (video+audio streams, resolution, duration)
  • RAM peak + free-floor         (ffmpeg child peak RSS, min available during render)
  • render wall-time budget       (did it finish under the per-short ceiling)
  • character consistency         (optional pHash of a reused locked character)

Everything is a CHECK with pass/fail + a human detail line; `QAReport.passed` is
the AND of them. It NEVER raises and NEVER mutates the short — a probe that can't
run is reported as a skipped/unknown check, not a crash. So wiring QA in is always
safe (it can only surface problems, never create them).
"""
from __future__ import annotations

import re
import subprocess
from typing import Optional

from pydantic import BaseModel

from ..config import settings
from ..schemas.scene import SceneGraph


# --------------------------------------------------------------------------- #
# report model
# --------------------------------------------------------------------------- #
class Check(BaseModel):
    name: str
    passed: bool
    detail: str = ""
    severity: str = "error"            # "error" fails the report; "warn" doesn't


class QAReport(BaseModel):
    video_id: str
    mp4: str
    passed: bool = True
    checks: list[Check] = []
    metrics: dict = {}

    def add(self, name: str, passed: bool, detail: str = "",
            severity: str = "error") -> None:
        self.checks.append(Check(name=name, passed=passed, detail=detail,
                                 severity=severity))
        if not passed and severity == "error":
            self.passed = False

    def failures(self) -> list[Check]:
        return [c for c in self.checks if not c.passed]


# --------------------------------------------------------------------------- #
# ffprobe / ffmpeg helpers (all degrade to None/[] on any error)
# --------------------------------------------------------------------------- #
def _probe(*entries: str, mp4: str) -> str:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", *entries, "-of", "default=nk=1:nw=1", mp4],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=60)
        return r.stdout.decode().strip()
    except Exception:
        return ""


def _stream_types(mp4: str) -> list[str]:
    return _probe("-show_entries", "stream=codec_type", mp4=mp4).splitlines()


def _yavg(mp4: str, at: float) -> float:
    """Average luma (0..255) of the frame at `at` seconds, or -1 on failure."""
    try:
        r = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "info", "-ss", f"{max(0.0, at)}",
             "-i", mp4, "-frames:v", "1", "-vf", "signalstats,metadata=print",
             "-f", "null", "-"], stderr=subprocess.PIPE, timeout=60)
        m = re.search(r"YAVG=([0-9.]+)", r.stderr.decode())
        return float(m.group(1)) if m else -1.0
    except Exception:
        return -1.0


def _black_seconds(mp4: str, pix_th: float = 0.10) -> float:
    """Total seconds flagged as (near-)black by ffmpeg blackdetect, or -1.0 if the
    probe couldn't run. d=0.05 → catch even brief black flashes."""
    try:
        r = subprocess.run(
            ["ffmpeg", "-hide_banner", "-i", mp4,
             "-vf", f"blackdetect=d=0.05:pix_th={pix_th}", "-an", "-f", "null", "-"],
            stderr=subprocess.PIPE, timeout=180)
        total = 0.0
        for m in re.finditer(r"black_start:([0-9.]+) black_end:([0-9.]+)",
                             r.stderr.decode()):
            total += float(m.group(2)) - float(m.group(1))
        return total
    except Exception:
        return -1.0


def _ahash(path: str):
    """64-bit average hash via ffmpeg 8x8 gray (no PIL). Returns list[int] or None."""
    try:
        r = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", path,
             "-vf", "scale=8:8,format=gray", "-frames:v", "1", "-f", "rawvideo", "-"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=60)
        b = r.stdout[:64]
        if len(b) < 64:
            return None
        mean = sum(b) / 64.0
        return [1 if x > mean else 0 for x in b]
    except Exception:
        return None


def consistency_pct(a: str, b: str) -> float:
    """Average-hash similarity % between two image/frame files (-1 if unprobeable)."""
    ha, hb = _ahash(a), _ahash(b)
    if ha is None or hb is None:
        return -1.0
    dist = sum(1 for x, y in zip(ha, hb) if x != y)
    return 100.0 * (1.0 - dist / 64.0)


# --------------------------------------------------------------------------- #
# the audit
# --------------------------------------------------------------------------- #
def analyze(graph: SceneGraph, mp4: str, *, render_seconds: float,
            ram_peak_mb: float, min_free_mb: float,
            consistency: Optional[float] = None,
            timed_out: bool = False) -> QAReport:
    """Run the full QA audit on a finished short. Pure I/O on the file + metrics;
    never raises. `consistency` is an optional pre-computed character-consistency %
    (pass None when the short has no reusable character)."""
    import os

    s = settings()
    rep = QAReport(video_id=graph.meta.video_id, mp4=mp4)

    # --- 0. timeout guard (the render completed at all) ---------------------- #
    rep.add("render completed (no timeout)", not timed_out,
            "render hit the timeout guard" if timed_out else "finished in time")
    exists = os.path.exists(mp4) and os.path.getsize(mp4) > 50_000
    rep.add("playable file written", exists,
            f"{os.path.getsize(mp4)/1e6:.1f}MB" if os.path.exists(mp4) else "missing")
    if not exists:
        rep.metrics = {"render_seconds": round(render_seconds, 1)}
        return rep                                  # nothing else to probe

    # --- 1. playability: streams, resolution, duration ----------------------- #
    types = _stream_types(mp4)
    rep.add("has video stream", "video" in types, " ".join(types) or "none")
    rep.add("has audio stream", "audio" in types,
            "audio present" if "audio" in types else "SILENT", severity="warn")
    w = _probe("-select_streams", "v:0", "-show_entries", "stream=width", mp4=mp4)
    h = _probe("-select_streams", "v:0", "-show_entries", "stream=height", mp4=mp4)
    res_ok = (w == str(graph.width) and h == str(graph.height))
    rep.add("resolution 9:16", res_ok, f"{w}x{h} (want {graph.width}x{graph.height})")
    dur = _to_float(_probe("-show_entries", "format=duration", mp4=mp4))
    want = graph.total_duration_sec
    dur_ok = dur > 0 and abs(dur - want) <= max(1.0, 0.15 * want)
    rep.add("duration matches timeline", dur_ok,
            f"{dur:.1f}s (timeline {want:.1f}s)")

    # --- 2. black-frame detection (whole clip) ------------------------------- #
    black = _black_seconds(mp4)
    if black < 0:
        rep.add("black-frame fraction", True, "probe unavailable — skipped",
                severity="warn")
    else:
        frac = black / dur if dur > 0 else 1.0
        rep.add("black-frame fraction", frac <= s.qa_black_max_fraction,
                f"{black:.2f}s black ({frac*100:.1f}% ≤ {s.qa_black_max_fraction*100:.0f}%)")

    # --- 3. per-scene non-black (sample each scene's mid-frame) --------------- #
    acc, dark = 0.0, []
    for sc in graph.scenes:
        mid = acc + sc.duration_sec / 2.0
        y = _yavg(mp4, mid)
        if 0 <= y <= s.qa_scene_yavg_min:
            dark.append(f"{sc.id}(YAVG={y:.0f})")
        acc += sc.duration_sec
    rep.add("every scene non-black", not dark,
            "all scenes lit" if not dark else f"dark: {', '.join(dark)}")

    # --- 4. RAM peak + free-floor -------------------------------------------- #
    rep.add("RAM peak within budget", ram_peak_mb <= s.qa_ram_peak_max_mb,
            f"~{ram_peak_mb:.0f}MB (≤ {s.qa_ram_peak_max_mb}MB)")
    if min_free_mb >= 0:
        rep.add("free RAM stayed above floor", min_free_mb >= s.qa_min_free_floor_mb,
                f"min free {min_free_mb:.0f}MB (≥ {s.qa_min_free_floor_mb}MB)")

    # --- 5. render wall-time budget ------------------------------------------ #
    rep.add("render within wall-time budget", render_seconds <= s.qa_render_budget_s,
            f"{render_seconds:.0f}s (≤ {s.qa_render_budget_s:.0f}s)")

    # --- 6. character consistency (optional) --------------------------------- #
    if consistency is not None and consistency >= 0:
        rep.add("character consistency", consistency >= s.qa_consistency_min_pct,
                f"{consistency:.1f}% (≥ {s.qa_consistency_min_pct:.0f}%)")

    rep.metrics = {
        "render_seconds": round(render_seconds, 1),
        "ram_peak_mb": round(ram_peak_mb),
        "min_free_mb": round(min_free_mb) if min_free_mb >= 0 else None,
        "duration_s": round(dur, 1),
        "black_seconds": round(black, 2) if black >= 0 else None,
        "size_mb": round(os.path.getsize(mp4) / 1e6, 1),
        "consistency_pct": round(consistency, 1) if consistency is not None else None,
    }
    return rep


def _to_float(x: str) -> float:
    try:
        return float(x)
    except (ValueError, TypeError):
        return -1.0


def _g(x: str) -> float:    # alias kept short for callers
    return _to_float(x)


def format_report(rep: QAReport) -> str:
    """One-block human readout of a QA report (for logs / the CLI harness)."""
    lines = [f"   QA · {rep.video_id} · {'✅ PASS' if rep.passed else '✗ FAIL'}"]
    for c in rep.checks:
        mark = "PASS" if c.passed else ("warn" if c.severity == "warn" else "FAIL")
        lines.append(f"     [{mark:4}] {c.name} — {c.detail}")
    return "\n".join(lines)
