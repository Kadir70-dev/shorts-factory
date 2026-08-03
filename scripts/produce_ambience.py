#!/usr/bin/env python
"""
Produce a long-form ambience video from a YAML preset.

    .venv/bin/python scripts/produce_ambience.py --preset ambience_fireplace
    .venv/bin/python scripts/produce_ambience.py --preset ambience_fireplace \
        --smoke            # 20s proof at 1/3 res, for verifying the chain

Mirrors scripts/produce.py: the preset carries the creative decisions, this
script only wires the preset into the pipeline. Stages are resumable, so an
interrupted run picks up from whichever artefacts already exist in the workdir.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.pipeline.ambience.longform import AmbienceSpec, produce  # noqa: E402


def load_spec(preset: str) -> AmbienceSpec:
    data = yaml.safe_load((ROOT / "config" / "presets" / f"{preset}.yaml").read_text())
    v, seo = data["video"], data["seo"]
    return AmbienceSpec(
        slug=data.get("slug", preset),
        total_seconds=float(v["total_seconds"]),
        loop_seconds=float(v["loop_seconds"]),
        width=int(v["width"]), height=int(v["height"]), fps=int(v["fps"]),
        seed=int(v.get("seed", 7)),
        sim_divisor=int(v.get("sim_divisor", 3)),
        crf=int(v.get("crf", 17)),
        preset=str(v.get("preset", "medium")),
        title=seo["title"].strip(),
        description=" ".join(seo["description"].split()),
        tags=list(seo["tags"]),
        thumbnail_prompt=seo.get("thumbnail", "").strip(),
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preset", default="ambience_fireplace")
    ap.add_argument("--out", default=None, help="workdir (default data/ambience/<slug>)")
    ap.add_argument("--smoke", action="store_true",
                    help="fast end-to-end proof: 1280x720, 10s loop, 60s total")
    ap.add_argument("--loop-seconds", type=float, default=None)
    ap.add_argument("--total-seconds", type=float, default=None)
    args = ap.parse_args()

    spec = load_spec(args.preset)
    if args.smoke:
        spec.width, spec.height = 1280, 720
        spec.sim_divisor = 1
        spec.loop_seconds, spec.total_seconds = 10.0, 60.0
        spec.preset = "veryfast"
        spec.slug += "_smoke"
    if args.loop_seconds:
        spec.loop_seconds = args.loop_seconds
    if args.total_seconds:
        spec.total_seconds = args.total_seconds

    workdir = Path(args.out) if args.out else ROOT / "data" / "ambience" / spec.slug
    produce(spec, workdir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
