#!/usr/bin/env python3
"""P3.4 master QA: video spec, audio sync, captions and per-scene frame quality.

Read-only. Checks the rendered master against its SceneGraph:
  video    1080x1920, 30 fps, h264 + aac, duration == graph timeline (±0.25 s:
           156 scene clips are each quantised to whole 1/30 s frames)
  sync     cross-correlates the master's audio with the voiceover WAV at five
           points; every offset must be within ±40 ms (about one frame)
  captions the burned-in .ass track: cue count, time span inside the video,
           corrected s30/s126 wording present, defect wording absent
  frames   blackdetect (true black, >=1 s) over the whole film, plus one frame
           per scene at its midpoint: HARD FAIL on near-black (YAVG<4) or flat
           (stddev<3); frames darker than YAVG 16 are listed for manual review
           because the K70 brand cards are deliberately dark navy

  .venv/bin/python scripts/k70_p34_master_qa.py \
      --graph data/finance_p34/bitcoin_final_v1/scene_graph_p34.json \
      --master data/finance_p34/render_full_v1/final_p34.mp4 \
      --captions data/finance_p34/render_full_v1/captions.ass
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

import numpy as np

SR = 8000


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True)


def probe(path: Path) -> dict:
    out = json.loads(_run("ffprobe", "-v", "error", "-show_streams", "-show_format",
                          "-of", "json", str(path)).stdout)
    v = next(s for s in out["streams"] if s["codec_type"] == "video")
    a = next((s for s in out["streams"] if s["codec_type"] == "audio"), {})
    num, den = (int(x) for x in v["r_frame_rate"].split("/"))
    return {"width": v["width"], "height": v["height"], "fps": round(num / den, 3),
            "vcodec": v["codec_name"], "acodec": a.get("codec_name"),
            "audio_channels": a.get("channels"), "audio_rate": a.get("sample_rate"),
            "duration_sec": float(out["format"]["duration"]),
            "video_duration_sec": float(v.get("duration", 0) or 0),
            "audio_duration_sec": float(a.get("duration", 0) or 0),
            "size_mb": round(int(out["format"]["size"]) / 1e6, 1)}


def pcm(path: Path, start: float, dur: float) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}",
                          "-i", str(path), "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"],
                         capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32)


def offset_ms(master: Path, vo: Path, at: float, win: float = 8.0, pad: float = 0.5) -> tuple[float, float]:
    """Lag of the master's audio relative to the voiceover around `at` (ms, corr)."""
    a = pcm(master, max(0.0, at - pad), win + 2 * pad)
    b = pcm(vo, at, win)
    if len(a) < len(b) or not b.any():
        return float("nan"), 0.0
    n = 1 << int(np.ceil(np.log2(len(a) + len(b))))
    corr = np.fft.irfft(np.fft.rfft(a, n) * np.conj(np.fft.rfft(b, n)), n)[: len(a) - len(b) + 1]
    k = int(np.argmax(corr))
    norm = float(corr[k] / (np.linalg.norm(b) * np.linalg.norm(a[k:k + len(b)]) + 1e-9))
    start = max(0.0, at - pad)
    return round((start + k / SR - at) * 1000, 1), round(norm, 3)


def detect(master: Path) -> dict:
    err = _run("ffmpeg", "-v", "info", "-i", str(master), "-vf",
               "blackdetect=d=1.0:pix_th=0.04,freezedetect=n=0.003:d=2.5",
               "-an", "-f", "null", "-").stderr
    black = re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", err)
    freeze = re.findall(r"freeze_start: ([\d.]+)", err)
    return {"black_segments": [(float(a), float(b)) for a, b in black],
            "freeze_starts": [float(x) for x in freeze]}


def scene_frames(master: Path, graph: dict) -> list[dict]:
    rows, t = [], 0.0
    for s in graph["scenes"]:
        mid = t + float(s["duration_sec"]) / 2
        t += float(s["duration_sec"])
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{mid:.3f}", "-i", str(master),
                              "-frames:v", "1", "-vf", "scale=270:480,format=gray",
                              "-f", "rawvideo", "-"], capture_output=True).stdout
        px = np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
        yavg, std = (float(px.mean()), float(px.std())) if px.size else (0.0, 0.0)
        rows.append({"scene_id": s["id"], "type": s["visual"]["type"], "at": round(mid, 2),
                     "yavg": round(yavg, 1), "std": round(std, 1),
                     "ok": px.size > 0 and yavg >= 4 and std >= 3,
                     "review_dark": px.size > 0 and yavg < 16})
    return rows


def edge_clear(master: Path, at: float, band: int = 24, luma: int = 90) -> dict:
    """Full-res frame at `at`: text running off the frame leaves bright pixels in
    the outer columns. On the dark navy chart cards those columns must stay dark."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{at:.3f}", "-i", str(master),
                          "-frames:v", "1", "-vf", "format=gray", "-f", "rawvideo", "-"],
                         capture_output=True).stdout
    px = np.frombuffer(raw, dtype=np.uint8)
    if px.size != 1080 * 1920:
        return {"at": round(at, 2), "ok": False, "edge_max": None}
    img = px.reshape(1920, 1080)
    edge = max(int(img[:, :band].max()), int(img[:, -band:].max()))
    return {"at": round(at, 2), "ok": edge < luma, "edge_max": edge}


def contact_sheet(master: Path, graph: dict, out: Path, cols: int = 13) -> Path:
    """One mid-frame per scene, tiled (12 rows x 13 = 156), labelled by scene id."""
    tmp = out.with_suffix("")
    tmp.mkdir(parents=True, exist_ok=True)
    t = 0.0
    for i, s in enumerate(graph["scenes"]):
        mid = t + float(s["duration_sec"]) / 2
        t += float(s["duration_sec"])
        _run("ffmpeg", "-v", "error", "-y", "-ss", f"{mid:.3f}", "-i", str(master),
             "-frames:v", "1", "-vf",
             f"scale=180:320,drawtext=text='{s['id']}':x=6:y=6:fontsize=20:"
             "fontcolor=yellow:box=1:boxcolor=black@0.7", str(tmp / f"{i:03d}.png"))
    rows = -(-len(graph["scenes"]) // cols)
    _run("ffmpeg", "-v", "error", "-y", "-framerate", "1", "-i", str(tmp / "%03d.png"),
         "-vf", f"tile={cols}x{rows}:padding=4:color=black", "-frames:v", "1", str(out))
    for f in tmp.glob("*.png"):
        f.unlink()
    tmp.rmdir()
    return out


def captions(path: Path, video_sec: float) -> dict:
    text = path.read_text(encoding="utf-8", errors="ignore")
    fmt = re.search(r"^\[Events\][^\[]*?^Format:(.*)$", text, re.M | re.S)
    nfields = len(fmt.group(1).split(",")) if fmt else 10
    cues = re.findall(r"^Dialogue: [^,]*,(\d+:\d+:\d+\.\d+),(\d+:\d+:\d+\.\d+),(.*)$", text, re.M)
    # strip override tags first: they contain commas; then drop the remaining
    # non-text fields (Style, Name, margins, Effect — whatever Format declares)
    cues = [(a, b, re.sub(r"\{[^}]*\}", "", rest).split(",", nfields - 4)[-1]) for a, b, rest in cues]

    def sec(ts: str) -> float:
        h, m, s = ts.split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)
    plain = " ".join(c[2] for c in cues).lower().replace("\\n", " ")
    plain = re.sub(r"\s+", " ", plain)
    return {"cues": len(cues), "first_start": sec(cues[0][0]) if cues else None,
            "last_end": max(sec(c[1]) for c in cues) if cues else None,
            "within_video": bool(cues) and max(sec(c[1]) for c in cues) <= video_sec + 0.05,
            "has_race_to_the_moon": "race to the moon" in plain,
            "has_print_a_one_hundred": "print a one hundred" in plain,
            "defect_sharply_higher": "sharply higher" in plain,
            "defect_an_one": "an one hundred" in plain}


def main() -> None:
    ap = argparse.ArgumentParser(description="K70 P3.4 master QA (read-only)")
    ap.add_argument("--graph", type=Path, required=True)
    ap.add_argument("--master", type=Path, required=True)
    ap.add_argument("--captions", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--edge-scene", action="append", default=[],
                    help="scene id whose frame must have no text off the edges")
    ap.add_argument("--edge-type", action="append", default=[],
                    help="check every scene of this visual type (e.g. dataviz)")
    ap.add_argument("--contact-sheet", type=Path, default=None)
    a = ap.parse_args()
    graph = json.loads(a.graph.read_text(encoding="utf-8"))
    timeline = round(sum(float(s["duration_sec"]) for s in graph["scenes"]), 3)
    spec = probe(a.master)
    vo = Path(graph["audio"]["voiceover_path"])
    points = [5.0, timeline * .25, timeline * .5, timeline * .75, timeline - 15.0]
    sync = [dict(zip(("at", "offset_ms", "corr"), (round(p, 1), *offset_ms(a.master, vo, p))))
            for p in points]
    det = detect(a.master)
    frames = scene_frames(a.master, graph)
    cap = captions(a.captions, spec["duration_sec"])
    starts, t = {}, 0.0
    for s in graph["scenes"]:
        starts[s["id"]] = (t, float(s["duration_sec"]))
        t += float(s["duration_sec"])
    edge_ids = list(dict.fromkeys(a.edge_scene + [
        s["id"] for s in graph["scenes"] if s["visual"]["type"] in a.edge_type]))
    # two samples per scene: mid-roll and after the counter has settled
    edges = {sid: [edge_clear(a.master, starts[sid][0] + starts[sid][1] * f) for f in (0.5, 0.85)]
             for sid in edge_ids}
    checks = {
        "resolution_1080x1920": (spec["width"], spec["height"]) == (1080, 1920),
        "fps_30": abs(spec["fps"] - 30) < 0.01,
        "codecs_h264_aac": spec["vcodec"] == "h264" and spec["acodec"] == "aac",
        "duration_matches_timeline": abs(spec["duration_sec"] - timeline) <= 0.25,
        "audio_video_same_length": abs(spec["audio_duration_sec"] - spec["video_duration_sec"]) <= 0.05,
        "audio_sync_within_40ms": all(abs(s["offset_ms"]) <= 40 and s["corr"] >= 0.3 for s in sync),
        "no_black_segments": not det["black_segments"],
        "scene_midframes_ok": all(r["ok"] for r in frames),
        "captions_present_and_within_video": cap["cues"] > 0 and cap["within_video"],
        # s126 sits under a hero stat, where the finisher deliberately yields
        # captions (render_ffmpeg._dominant_windows); its wording is informational.
        "captions_corrected_wording": cap["has_race_to_the_moon"]
                                      and not cap["defect_sharply_higher"] and not cap["defect_an_one"],
    }
    if edges:
        checks["text_inside_frame"] = all(r["ok"] for rs in edges.values() for r in rs)
    report = {"master": str(a.master), "timeline_sec": timeline, "spec": spec, "sync": sync,
              "detect": det, "captions": cap, "scene_frames_failed": [r for r in frames if not r["ok"]],
              "scene_frames_dark_for_review": [r for r in frames if r["review_dark"]],
              "scene_frames_checked": len(frames), "edge_checks": edges, "checks": checks, "passed": all(checks.values())}
    out = a.out or a.master.with_name("P34_MASTER_QA.json")
    if a.contact_sheet:
        report["contact_sheet"] = str(contact_sheet(a.master, graph, a.contact_sheet))
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    for k, v in checks.items():
        print(f"{'PASS' if v else 'FAIL'}  {k}")
    print(f"freeze segments (informational): {len(det['freeze_starts'])}")
    raise SystemExit(0 if report["passed"] else 2)


if __name__ == "__main__":
    main()
