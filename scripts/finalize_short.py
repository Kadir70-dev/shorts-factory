#!/usr/bin/env python3
"""
Delivery packaging for a rendered Short. Calls the EXISTING post stage — no
pipeline behaviour is changed here, this only runs stages `produce.py` does not
and writes the artefacts to the job folder.

    final.mp4          loudnormed -14 LUFS, faststart (postprocess.finalize)
    thumbnail.jpg      hook frame  (postprocess.finalize)
    metadata.json      title/description/tags/disclosure (postprocess.finalize)
    captions.srt       subtitles from the graph's caption track
    qa_report.json     produce.py's audit, refreshed for the delivered file
    provenance.json    asset / Three.js / motion-graphics / AI b-roll records

This is the SHARED finalizer. Wrapper repos (Fashion-Shorts et al) own only
config/ and data/; they set PROJECT_ROOT and call `main()` rather than forking
this file — see scripts/produce_fashion.py in those repos for the pattern.

    .venv/bin/python scripts/finalize_short.py --job vid_kasai_uae_abaya \
        --render-seconds 300 --ram-peak-mb 1100 --min-free-mb 900
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1]
# A wrapper repo exports PROJECT_ROOT before importing this module; setdefault
# keeps that value and falls back to the engine checkout for a standalone run.
os.environ.setdefault("PROJECT_ROOT", str(ENGINE))
sys.path.insert(0, str(ENGINE / "apps" / "api"))


def _video_stream_md5(path: str) -> str:
    """MD5 of the VIDEO bitstream alone — demuxed, never decoded (~0.1s).

    This is the proof that lets the delivered report reuse produce.py's audit
    rather than repeating it. `loudnorm` is an audio filter and postprocess
    stream-copies the video, so an identical hash means every video check
    (resolution, black frames, per-scene luma) measured these exact frames.
    An empty string means "could not prove it" and forces the full re-audit.
    """
    try:
        result = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", path, "-map", "0:v", "-c", "copy",
             "-f", "md5", "-"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=120)
        return result.stdout.decode().strip() if result.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _probe(path: str, *entries: str) -> str:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", *entries, "-of", "default=nk=1:nw=1", path],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=60)
        return result.stdout.decode().strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _delivered_report(job: Path, master: str, delivered: str, graph, qa):
    """The QA report for the packaged file.

    Reuses produce.py's persisted audit when the video bitstream survived
    packaging untouched, re-probing only the three checks loudnorm can move:
    file size, audio stream, and duration. Falls back to a full analysis when
    there is no prior report (finalize run standalone) or the video changed.
    """
    prior_path = job / "qa_report.json"
    if not prior_path.is_file():
        return None
    master_md5 = _video_stream_md5(master)
    if not master_md5 or master_md5 != _video_stream_md5(delivered):
        return None
    try:
        report = qa.QAReport.model_validate_json(prior_path.read_text())
    except ValueError:
        return None

    size = Path(delivered).stat().st_size
    types = _probe(delivered, "-show_entries", "stream=codec_type").splitlines()
    try:
        duration = float(_probe(delivered, "-show_entries", "format=duration"))
    except ValueError:
        duration = -1.0
    want = graph.total_duration_sec
    refreshed = {
        "playable file written": (size > 50_000, f"{size/1e6:.1f}MB"),
        "has audio stream": ("audio" in types,
                             "audio present" if "audio" in types else "SILENT"),
        "duration matches timeline": (
            duration > 0 and abs(duration - want) <= max(1.0, 0.15 * want),
            f"{duration:.1f}s (timeline {want:.1f}s)"),
    }
    for check in report.checks:
        if check.name in refreshed:
            check.passed, check.detail = refreshed[check.name]
    report.mp4 = delivered
    report.passed = all(c.passed or c.severity == "warn" for c in report.checks)
    report.metrics["size_mb"] = round(size / 1e6, 1)
    report.metrics["duration_s"] = round(duration, 1)
    return report


def _srt_time(seconds: float) -> str:
    ms = max(0, round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


async def run(args) -> int:
    from app.config import load_channel, settings
    from app.pipeline import postprocess, qa
    from app.schemas.scene import SceneGraph

    job = settings().data_dir / "jobs" / args.job
    graph = SceneGraph.model_validate_json((job / "scene_graph.json").read_text())
    channel = load_channel(graph.meta.channel_id)

    # postprocess.finalize writes `final.mp4` beside its input, so the rendered
    # master is kept under its own name rather than being read and written at once.
    raw = job / "render_raw.mp4"
    if not raw.exists():
        (job / "final.mp4").rename(raw)
    result = await postprocess.finalize(graph, str(raw), channel)

    srt = job / "captions.srt"
    lines = [f"{i}\n{_srt_time(c.start)} --> {_srt_time(c.end)}\n{c.text}\n"
             for i, c in enumerate(graph.captions, 1)]
    srt.write_text("\n".join(lines))

    report = _delivered_report(job, str(raw), result["mp4"], graph, qa)
    if report is None:
        print("   [qa] no reusable audit — running the full analysis")
        report = qa.analyze(graph, result["mp4"], render_seconds=args.render_seconds,
                            ram_peak_mb=args.ram_peak_mb,
                            min_free_mb=args.min_free_mb,
                            consistency=None, timed_out=False)
    else:
        print("   [qa] reused produce.py's audit — video bitstream verified "
              "identical; re-probed size/audio/duration only")
    (job / "qa_report.json").write_text(json.dumps(
        {"passed": report.passed, "metrics": report.metrics,
         "checks": [c.__dict__ for c in report.checks]}, indent=2, default=str))
    (job / "qa_report.txt").write_text(qa.format_report(report))

    (job / "provenance.json").write_text(json.dumps({
        "video_id": graph.meta.video_id,
        "assets": [r.model_dump() for r in graph.asset_provenance],
        "threejs": [r.model_dump() for r in graph.threejs_provenance],
        "motion_graphics": [r.model_dump() for r in graph.motion_graphics_provenance],
        "ai_broll": [r.model_dump() for r in graph.ai_broll_provenance],
    }, indent=2, default=str))

    print(qa.format_report(report))
    for name in ("final.mp4", "thumbnail.jpg", "metadata.json", "captions.srt",
                 "qa_report.json", "qa_report.txt", "provenance.json",
                 "visual_breakdown.json", "scene_graph.json"):
        path = job / name
        print(f"   {'✓' if path.exists() else '✗'} {path} "
              f"({path.stat().st_size/1024:.0f}KB)" if path.exists() else
              f"   ✗ {path} MISSING")
    return 0 if report.passed else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", required=True)
    ap.add_argument("--render-seconds", type=float, default=0.0)
    ap.add_argument("--ram-peak-mb", type=float, default=0.0)
    ap.add_argument("--min-free-mb", type=float, default=-1.0)
    return asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
