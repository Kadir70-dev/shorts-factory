"""Compose a prepared P0 SceneGraph into a NEW documentary MP4 (K70 renderer).

No allocation, no asset generation: the graph is rendered exactly as prepared.
The job's scene clips and manifest are COPIED into a fresh --out-dir so the
renderer's manifest reuse skips every unchanged scene; the job is read-only.
`--override SCENE=PATH` swaps in an already-rendered motion_gfx clip (used for
the near-black stock pick QA failed on the original).

    .venv/bin/python scripts/k70_p0_render_v2.py \
        --graph data/finance_p0/cinematic_balanced/scene_graph_p0_v2.json \
        --job data/jobs/k70_f4_bitcoin_ep01 \
        --override s102=data/finance_f4/k70_f4_bitcoin_ep01_cinematic/visuals/s102_gfx.mp4 \
        --out-dir data/finance_p0/k70_bitcoin_ep01_premium_v2
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "apps" / "api"))


def preset_env(name: str = "documentary_finance") -> None:
    """Same preset env the production run used, so the render context matches."""
    import yaml
    raw = yaml.safe_load((ROOT / "config" / "presets" / f"{name}.yaml").read_text())
    for key, value in (raw.get("env") or {}).items():
        os.environ[key] = str(value)


class MemoryWatch:
    """Peak used RAM and minimum free RAM, sampled from /proc/meminfo."""

    def __init__(self, every: float = 1.0):
        self.peak_used_mb, self.min_free_mb = 0.0, float("inf")
        self._stop, self._every = threading.Event(), every
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self._stop.is_set():
            info = {}
            for line in Path("/proc/meminfo").read_text().splitlines():
                key, value = line.split(":", 1)
                info[key] = int(value.split()[0]) / 1024
            free = info.get("MemAvailable", 0.0)
            self.min_free_mb = min(self.min_free_mb, free)
            self.peak_used_mb = max(self.peak_used_mb, info.get("MemTotal", 0.0) - free)
            self._stop.wait(self._every)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join()


def parse_overrides(values: list[str]) -> dict[str, Path]:
    out = {}
    for value in values:
        sid, _, path = value.partition("=")
        p = Path(path).resolve()
        if not sid or not p.is_file() or p.suffix.lower() != ".mp4":
            raise SystemExit(f"bad --override {value!r}; use SCENE=existing.mp4")
        out[sid] = p
    return out


async def run(a) -> int:
    from app.pipeline import qa, render_ffmpeg, visual_budget
    from app.schemas.scene import SceneGraph

    out = a.out_dir.resolve()
    job = a.job.resolve()
    if out.exists():
        raise SystemExit(f"{out} exists; choose a fresh --out-dir (never overwrite)")
    if out.is_relative_to(job):
        raise SystemExit("--out-dir must be outside the job (the job is read-only)")
    graph = SceneGraph.model_validate_json(a.graph.read_text())
    overrides = parse_overrides(a.override)
    by_id = {s.id: s for s in graph.scenes}
    unknown = set(overrides) - set(by_id)
    if unknown:
        raise SystemExit(f"unknown override scenes: {sorted(unknown)}")
    missing = [s.id for s in graph.scenes
               if s.visual.asset_path and not Path(s.visual.asset_path).is_file()]
    if missing:
        raise SystemExit(f"assets missing on disk: {missing}")

    out.mkdir(parents=True)
    (out / "visuals").mkdir()
    for sid, src in overrides.items():          # copy: the source stays untouched
        dst = out / "visuals" / f"{sid}_{src.name}"
        shutil.copy2(src, dst)
        v = by_id[sid].visual
        v.type, v.asset_path, v.layers, v.motion = "motion_gfx", str(dst), [], "none"
        v.decision_reason = f"[p0-v2] QA dark stock replaced by {src.name}"
    for clip in sorted(job.glob("scene_*.mp4")) + [job / "manifest.json"]:
        shutil.copy2(clip, out / clip.name)     # real copies for manifest reuse
    (out / "scene_graph.json").write_text(graph.model_dump_json(indent=2))

    final = out / a.name
    started = time.monotonic()
    with MemoryWatch() as mem:
        await render_ffmpeg.render(graph, final)
    seconds = time.monotonic() - started
    print(f"[v2] render {seconds:.0f}s -> {final}", flush=True)
    rep = qa.analyze(graph, str(final), render_seconds=seconds,
                     ram_peak_mb=mem.peak_used_mb, min_free_mb=mem.min_free_mb,
                     budget_report=visual_budget.measure(graph))
    text = qa.format_report(rep)
    (out / "qa_report.txt").write_text(text)
    print(text, flush=True)
    (out / "render_summary.json").write_text(json.dumps({
        "graph": str(a.graph), "job": str(job), "final": str(final),
        "render_seconds": round(seconds, 1), "ram_peak_used_mb": round(mem.peak_used_mb),
        "min_free_mb": round(mem.min_free_mb),
        "overrides": {k: str(v) for k, v in overrides.items()}}, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--graph", type=Path, required=True)
    ap.add_argument("--job", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--override", action="append", default=[], metavar="SCENE=MP4")
    ap.add_argument("--name", default="final_p0_v2.mp4")
    ap.add_argument("--preset", default="documentary_finance")
    a = ap.parse_args(argv)
    preset_env(a.preset)
    return asyncio.run(run(a))


if __name__ == "__main__":
    raise SystemExit(main())
