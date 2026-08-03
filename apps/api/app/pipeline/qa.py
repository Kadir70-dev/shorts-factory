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
import json
import time
from pathlib import Path
from difflib import SequenceMatcher
from typing import Literal
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


def _black_seconds(mp4: str, pix_th: float = 0.04) -> float:
    """Total seconds flagged as (near-)black by ffmpeg blackdetect, or -1.0 if the
    probe couldn't run. d=0.05 → catch even brief black flashes.

    `pix_th` is a LUMA FRACTION, and it is calibrated against the brand, not
    picked for sensitivity. This check exists to catch MISSING VIDEO — a failed
    asset that renders pure black. It is not a brightness check.

    The finance-documentary palette has a near-black base (`#0b1220`, luma ≈ 17.5
    of 255 ≈ 0.069). At the old 0.10 threshold every correctly-rendered frame of
    a dark-brand short counted as black: a clean render reported 56% black while
    ffmpeg's own default-threshold blackdetect found none at all. At 0.04 only
    pixels below luma ≈ 10 count, so genuine black (#000, luma 0) is still caught
    while the brand's intentional darkness is not.
    """
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


# --------------------------------------------------------------------------- #
# Phase 8 blocking production-readiness report
# --------------------------------------------------------------------------- #
class ProductionCheck(BaseModel):
    category: Literal["visual", "text", "audio", "motion", "finance", "legal", "youtube"]
    check: str
    status: Literal["PASS", "WARNING", "FAIL"]
    reason: str
    scene: str = ""
    timestamp: float | None = None
    suggested_fix: str = ""


class ProductionQAReport(BaseModel):
    version: str = "1.0"
    video_id: str
    media_path: str
    status: Literal["PASS", "WARNING", "FAIL"] = "PASS"
    generated_at: str
    runtime_ms: float = 0
    checks: list[ProductionCheck] = []
    metrics: dict = {}

    def add(self, category: str, check: str, status: str, reason: str,
            *, scene: str = "", timestamp: float | None = None,
            fix: str = "") -> None:
        # Machine consumers must never special-case a failure with no location.
        # Export-wide failures use the explicit pseudo-scene and t=0.
        if status == "FAIL":
            scene = scene or "__export__"
            timestamp = 0.0 if timestamp is None else timestamp
        self.checks.append(ProductionCheck(
            category=category, check=check, status=status, reason=reason,
            scene=scene, timestamp=timestamp, suggested_fix=fix))
        if status == "FAIL":
            self.status = "FAIL"
        elif status == "WARNING" and self.status == "PASS":
            self.status = "WARNING"


def _run_json(command: list[str]) -> dict:
    try:
        result = subprocess.run(command, capture_output=True, text=True,
                                timeout=180, check=False)
        return json.loads(result.stdout) if result.returncode == 0 else {}
    except Exception:
        return {}


def _filter_log(mp4: str, vf: str = "", af: str = "") -> str:
    command = ["ffmpeg", "-hide_banner", "-nostats", "-i", mp4]
    if vf: command += ["-vf", vf]
    if af: command += ["-af", af]
    command += ["-f", "null", "-"]
    try:
        return subprocess.run(command, capture_output=True, text=True,
                              timeout=240).stderr
    except Exception:
        return ""


def _media_probe(mp4: str) -> dict:
    return _run_json(["ffprobe", "-v", "error", "-show_streams", "-show_format",
                      "-of", "json", mp4])


def _fps(value: str) -> float:
    try:
        a, b = value.split("/")
        return float(a) / float(b)
    except Exception:
        return 0.0


def _atoms_faststart(path: Path) -> bool:
    try:
        data = path.read_bytes()[:2_000_000]
        moov, mdat = data.find(b"moov"), data.find(b"mdat")
        return moov >= 0 and (mdat < 0 or moov < mdat)
    except OSError:
        return False


def _times(log: str, pattern: str) -> list[float]:
    return [float(match) for match in re.findall(pattern, log)]


def _scene_at(graph: SceneGraph, timestamp: float) -> str:
    cursor = 0.0
    for scene in graph.scenes:
        if cursor <= timestamp < cursor + scene.duration_sec:
            return scene.id
        cursor += scene.duration_sec
    return graph.scenes[-1].id if graph.scenes else ""


def _numbers(text: str) -> set[str]:
    return {re.sub(r"[,$]", "", value).lower() for value in re.findall(
        r"(?:[$€£])?\d[\d,]*(?:\.\d+)?(?:\s?(?:%|percent|million|billion|trillion|[kmbt]))?",
        text, flags=re.I)}


def production_analyze(graph: SceneGraph, mp4: str, *, thumbnail: str = "",
                       metadata_path: str = "", report_path: str = ""
                       ) -> ProductionQAReport:
    """Inspect the composed export and graph. No network and no frame extraction.

    The function always returns and optionally persists a structured report. The
    worker owns the blocking policy so tests and CLI tools can inspect failures.
    """
    from datetime import datetime, timezone
    started = time.perf_counter()
    report = ProductionQAReport(video_id=graph.meta.video_id, media_path=mp4,
        generated_at=datetime.now(timezone.utc).isoformat())
    path = Path(mp4)
    probe = _media_probe(mp4) if path.is_file() else {}
    streams = probe.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio = next((s for s in streams if s.get("codec_type") == "audio"), {})
    fmt = probe.get("format", {})
    duration = _to_float(str(fmt.get("duration", "")))
    width, height = int(video.get("width", 0)), int(video.get("height", 0))
    fps = _fps(video.get("avg_frame_rate") or video.get("r_frame_rate", "0/1"))
    bitrate = int(fmt.get("bit_rate") or 0) / 1000

    def add(category, check, ok, good, bad, fix, *, warning=False,
            scene="", timestamp=None):
        report.add(category, check, "PASS" if ok else ("WARNING" if warning else "FAIL"),
                   good if ok else bad, scene=scene, timestamp=timestamp, fix="" if ok else fix)

    # VISUAL / MOTION — decoded-media measurements.
    add("visual", "playable video", bool(video), "video stream decoded", "missing video stream",
        "Re-render the composed video with libx264.")
    black_log = _filter_log(mp4, vf="blackdetect=d=0.08:pix_th=0.10") if video else ""
    black_spans = [(float(a), float(b)) for a, b in re.findall(
        r"black_start:([0-9.]+) black_end:([0-9.]+)", black_log)]
    black_total = sum(b-a for a, b in black_spans)
    black_ok = duration > 0 and black_total / duration <= settings().qa_black_max_fraction
    first_black = black_spans[0][0] if black_spans else None
    add("visual", "black frames", black_ok, f"{black_total:.3f}s black",
        f"{black_total:.3f}s black exceeds limit", "Replace or rerender the affected scene.",
        scene=_scene_at(graph, first_black) if first_black is not None else "",
        timestamp=first_black)
    freeze_log = _filter_log(mp4, vf="freezedetect=n=-55dB:d=0.7") if video else ""
    freeze_durations = _times(freeze_log, r"freeze_duration:\s*([0-9.]+)")
    longest_freeze = max(freeze_durations, default=0.0)
    add("visual", "frozen frames", longest_freeze <= 2.0,
        f"longest freeze {longest_freeze:.2f}s", f"frozen sequence {longest_freeze:.2f}s",
        "Repair the source clip or animation frame sequence.")
    aspect_ok = width > 0 and height > 0 and abs(width / height - 9 / 16) < .002
    add("visual", "aspect ratio and crop", aspect_ok, f"{width}x{height} is 9:16",
        f"{width}x{height} is not 9:16", "Render with scale/crop to a 9:16 canvas.")
    resolution_ok = width >= 1080 and height >= 1920
    add("visual", "production resolution", resolution_ok, f"{width}x{height}",
        f"low resolution {width}x{height}", "Use final quality at 1080x1920.")
    blur_log = _filter_log(mp4, vf="blurdetect=block_width=32:block_height=32:block_pct=80") if video else ""
    blur_values = _times(blur_log, r"blur mean:\s*([0-9.]+)")
    blur = sum(blur_values)/len(blur_values) if blur_values else -1
    add("visual", "blur detection", blur < 0 or blur <= 8.0,
        "blur probe clear" if blur < 0 else f"mean blur {blur:.2f}", f"mean blur {blur:.2f}",
        "Replace or sharpen the low-detail source.", warning=blur < 0)

    unsafe = [(scene.id, overlay.y) for scene in graph.scenes for overlay in scene.overlays
              if overlay.y < .09 or overlay.y > .81]
    add("visual", "safe margins", not unsafe, "all overlays inside safe margins",
        f"unsafe overlay anchors: {unsafe}", "Move text inside the configured mobile safe area.",
        scene=unsafe[0][0] if unsafe else "")
    clipped = [(i, c.text) for i, c in enumerate(graph.captions)
               if len(c.text.split()) > 6 or len(c.text) > 52]
    add("visual", "caption clipping and overflow", not clipped,
        "caption segments fit mobile bounds", f"oversized captions: {clipped[:2]}",
        "Re-segment captions to four to six short words.")
    top_overlays = [s.id for s in graph.scenes for o in s.overlays
                    if o.y < .18 and o.type not in ("source",)]
    add("visual", "logo and watermark overlap", not top_overlays,
        "watermark zone clear", f"overlays enter watermark zone: {top_overlays}",
        "Move overlays below the top safe/title region.", warning=True,
        scene=top_overlays[0] if top_overlays else "")
    brand = graph.brand_identity_provenance
    add("visual", "brand consistency", bool(brand and all(brand.consistency_checks.values())),
        "central brand receipt is consistent", "missing or invalid central brand receipt",
        "Render with BRAND_IDENTITY_ENABLED=1.")
    add("visual", "color consistency", bool(brand and brand.palette),
        "palette provenance attached", "brand palette provenance missing",
        "Route every visual engine through BrandManager.")
    transitions_ok = all(s.transition_in in
        ("cut", "fade", "dip_to_black", "push_up") for s in graph.scenes)
    add("motion", "transition continuity", transitions_ok, "transitions follow brand policy",
        "unapproved transition detected", "Use the Brand Manager transition policy.")
    add("motion", "animation and camera continuity", longest_freeze <= 2.0,
        "motion cadence is continuous", "motion cadence contains a long hold",
        "Shorten static holds or add restrained camera motion.", warning=True)
    add("motion", "transition timing", not any((b-a) > .6 for a,b in black_spans),
        "transition blackout timing is restrained", "transition blackout is too long",
        "Reduce dip-to-black duration below 0.6 seconds.")
    add("motion", "timeline continuity", duration > 0 and abs(duration-graph.total_duration_sec) <= .25,
        "encoded duration matches SceneGraph", f"media {duration:.3f}s vs graph {graph.total_duration_sec:.3f}s",
        "Rebuild scene clips without consuming transition frames.")

    # TEXT / FINANCE — validated graph compared with the rendered timeline source.
    captions_ordered = all(c.start >= 0 and c.end > c.start and
        (i == 0 or c.start >= graph.captions[i-1].start)
        for i, c in enumerate(graph.captions))
    add("text", "caption timing", captions_ordered and
        all(c.end <= duration + .2 for c in graph.captions), "captions ordered and in bounds",
        "caption timing is invalid or outside media", "Regenerate word timings from final narration.")
    narration = " ".join(s.narration for s in graph.scenes).lower()
    caption_text = " ".join(c.text for c in graph.captions).lower()
    similarity = SequenceMatcher(None, re.sub(r"\W+", " ", narration),
                                 re.sub(r"\W+", " ", caption_text)).ratio()
    add("text", "caption spelling", similarity >= .45, f"caption/narration similarity {similarity:.2f}",
        f"caption/narration similarity only {similarity:.2f}",
        "Correct caption spelling against the narration transcript.", warning=True)
    add("text", "font consistency", bool(brand and brand.fonts), "font roles centrally bound",
        "font provenance missing", "Use BrandManager typography for every overlay.")
    add("text", "readability", not clipped and not unsafe, "text is mobile-readable",
        "text overflow or unsafe placement detected", "Shorten and reposition the affected text.")
    graph_text = " ".join([narration, caption_text] +
        [o.text + " " + (o.sub or "") for s in graph.scenes for o in s.overlays])
    bad_number = re.findall(r"\$\s+\d|\d\s+%", graph_text)
    add("text", "number and financial notation", not bad_number,
        "currency and percentages use compact notation", f"invalid notation: {bad_number}",
        "Use $4.2B and 10% without internal spaces.")
    board_text = " ".join(n for b in (graph.storyboard.scenes if graph.storyboard else [])
                          for n in b.financial_numbers)
    board_numbers, narration_numbers = _numbers(board_text), _numbers(narration)
    add("finance", "number and chart consistency",
        not board_numbers or board_numbers.issubset(narration_numbers),
        "storyboard figures agree with narration",
        f"storyboard-only figures: {sorted(board_numbers-narration_numbers)}",
        "Correct the storyboard/chart values to match narration.")
    years = {str(b.year) for b in (graph.storyboard.scenes if graph.storyboard else []) if b.year}
    add("finance", "timeline and date consistency", not years or years.issubset(_numbers(narration)),
        "dates agree with narration", f"dates not present in narration: {sorted(years-_numbers(narration))}",
        "Align timeline dates with the spoken script.")
    companies = {b.company.lower() for b in
        (graph.storyboard.scenes if graph.storyboard else []) if b.company}
    add("finance", "company names", not companies or all(c in narration for c in companies),
        "company names agree", "storyboard company missing from narration",
        "Use the exact legal/company name consistently.", warning=True)
    pct_bad = [n for n in _numbers(graph_text) if "percent" in n and "%" in n]
    add("finance", "currency and percentage formatting", not pct_bad,
        "financial units are consistently formatted", f"mixed percentage notation: {pct_bad}",
        "Choose one percentage notation per value.")

    # AUDIO — objective measurements plus graph-level continuity contracts.
    add("audio", "missing narration", bool(audio) and bool(graph.audio.voiceover_path),
        "narration track present", "narration stream or source path missing",
        "Restore the cloned-voice narration and rerender.")
    audio_log = _filter_log(mp4, af="ebur128=peak=true,silencedetect=n=-45dB:d=0.5") if audio else ""
    loudness_values = _times(audio_log, r"I:\s*(-?[0-9.]+) LUFS")
    lufs = loudness_values[-1] if loudness_values else -99.0
    loud_ok = settings().visual_qa_loudness_min_lufs <= lufs <= settings().visual_qa_loudness_max_lufs
    add("audio", "loudness", loud_ok, f"integrated {lufs:.1f} LUFS",
        f"integrated {lufs:.1f} LUFS outside target", "Normalize final audio near -14 LUFS.")
    peaks = _times(audio_log, r"Peak:\s*(-?[0-9.]+) dBFS")
    peak = peaks[-1] if peaks else -99.0
    add("audio", "clipping", peak <= -.1, f"true peak {peak:.1f} dBFS",
        f"true peak {peak:.1f} dBFS may clip", "Apply a -1.5 dBTP limiter.")
    silence_starts = _times(audio_log, r"silence_start:\s*([0-9.]+)")
    silence_ends = _times(audio_log, r"silence_end:\s*([0-9.]+)")
    silence = sum(max(0,b-a) for a,b in zip(silence_starts, silence_ends))
    silence_ok = duration > 0 and silence/duration <= settings().visual_qa_max_silence_fraction
    add("audio", "silence and voice continuity", silence_ok,
        f"detected silence {silence:.2f}s", f"excess silence {silence:.2f}s",
        "Repair missing narration segments or gaps.")
    audio_duration = _to_float(str(audio.get("duration", "")))
    sync_ok = audio_duration < 0 or abs(audio_duration-duration) <= .25
    add("audio", "audio/video sync", sync_ok, "stream durations aligned",
        f"audio {audio_duration:.2f}s vs video {duration:.2f}s", "Remux aligned final streams.")
    add("audio", "music ducking", not graph.audio.music_path or graph.audio.duck_music,
        "music ducking enabled or no music bed", "music bed is not ducked",
        "Enable sidechain ducking under narration.")

    # LEGAL — every selected or generated visual remains auditable.
    selected = [c for r in graph.asset_provenance for c in r.candidates
                if c.source_url == r.selected_source_url]
    visible_attribution = " ".join(
        o.text for scene in graph.scenes for o in scene.overlays if o.type == "source").lower()
    unresolved_attr = [c.scene_id for c in selected if c.attribution_requirement and
        c.attribution_requirement.lower() not in visible_attribution and
        c.provider_institution.lower() not in visible_attribution]
    legal_bad = [c.scene_id for c in selected if c.commercial_use_status != "allowed"
                 or not c.license.strip()]
    add("legal", "license and commercial-use validation", not legal_bad,
        "selected external assets are commercially cleared",
        f"uncleared assets: {legal_bad}", "Replace with an explicitly compatible asset.")
    add("legal", "attribution", not unresolved_attr, "required attribution is identified",
        f"incomplete attribution: {unresolved_attr}", "Add provider/creator attribution.")
    generated_scenes = [s.id for s in graph.scenes if s.visual.type in ("ai_image", "ai_video")]
    tracked_ai = {p.scene_id for p in graph.ai_broll_provenance if p.synthetic}
    add("legal", "synthetic content tracking", set(generated_scenes).issubset(tracked_ai),
        "all generated visuals are marked synthetic",
        f"untracked synthetic scenes: {sorted(set(generated_scenes)-tracked_ai)}",
        "Attach AI provider/model/prompt provenance and disclosure flags.")
    provenance_ok = all(s.visual.type in ("solid", "branded", "motion_gfx", "threejs") or
        any(r.scene_id == s.id and (r.selected_source_url or r.status != "resolved")
            for r in graph.asset_provenance) or s.id in tracked_ai for s in graph.scenes)
    add("legal", "asset provenance", provenance_ok, "scene provenance is complete",
        "one or more scene assets lack provenance", "Attach source or synthetic provenance per scene.")

    # YOUTUBE export contract.
    add("youtube", "1080x1920", width == 1080 and height == 1920,
        "production canvas is 1080x1920", f"export is {width}x{height}",
        "Export final quality at 1080x1920.")
    audio_contract = (audio.get("codec_name") == "aac" and
                      int(audio.get("sample_rate") or 0) == 48000 and
                      str(audio.get("profile", "")).lower() in ("lc", "aac lc"))
    add("youtube", "H.264 and AAC-LC/48kHz",
        video.get("codec_name") == "h264" and audio_contract,
        "H.264 video with AAC-LC at 48 kHz",
        f"video={video.get('codec_name')} audio={audio.get('codec_name')}/"
        f"{audio.get('profile')}/{audio.get('sample_rate')}Hz",
        "Transcode using libx264 and AAC-LC at 48 kHz.")
    add("youtube", "correct FPS", abs(fps-graph.fps) < .01 and graph.fps in (30,60),
        f"{fps:.2f} fps", f"unexpected {fps:.2f} fps", "Export at the SceneGraph 30 or 60 fps.")
    add("youtube", "safe bitrate", settings().visual_qa_min_bitrate_kbps <= bitrate <=
        settings().visual_qa_max_bitrate_kbps, f"{bitrate:.0f} kbps",
        f"bitrate {bitrate:.0f} kbps outside safe range", "Adjust H.264 CRF/bitrate settings.")
    add("youtube", "faststart", _atoms_faststart(path), "moov atom precedes media data",
        "MP4 is not faststart optimized", "Mux with -movflags +faststart.")
    add("youtube", "Shorts duration", 0 < duration <= 60.0, f"{duration:.2f}s",
        f"duration {duration:.2f}s is outside Shorts target", "Keep the final Short at 60 seconds or less.")
    add("youtube", "thumbnail", bool(thumbnail and Path(thumbnail).is_file()),
        "thumbnail generated", "thumbnail missing", "Generate a readable hook thumbnail.")
    try:
        metadata = json.loads(Path(metadata_path).read_text()) if metadata_path else {}
    except (OSError, json.JSONDecodeError):
        metadata = {}
    meta_ok = all(metadata.get(k) for k in ("title", "description", "tags", "thumbnail_text"))
    add("youtube", "metadata completeness", meta_ok, "required metadata present",
        "title, description, tags, or thumbnail text missing", "Complete the export metadata package.")

    report.metrics = {"duration_s": duration, "width": width, "height": height,
        "fps": round(fps, 3), "bitrate_kbps": round(bitrate),
        "black_seconds": round(black_total, 3), "longest_freeze_s": round(longest_freeze, 3),
        "blur_mean": round(blur, 3), "loudness_lufs": lufs,
        "true_peak_dbfs": peak, "silence_seconds": round(silence, 3),
        "checks": len(report.checks)}
    report.runtime_ms = (time.perf_counter()-started)*1000
    if report_path:
        destination = Path(report_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(report.model_dump_json(indent=2))
    return report


def format_production_report(report: ProductionQAReport) -> str:
    lines = [f"QA · {report.video_id} · {report.status} · {report.runtime_ms:.0f}ms"]
    for item in report.checks:
        if item.status != "PASS":
            where = f" scene={item.scene}" if item.scene else ""
            at = f" t={item.timestamp:.2f}s" if item.timestamp is not None else ""
            lines.append(f"[{item.status}] {item.category}/{item.check}{where}{at}: "
                         f"{item.reason} Fix: {item.suggested_fix}")
    return "\n".join(lines)
