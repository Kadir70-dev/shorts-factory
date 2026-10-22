#!/usr/bin/env python3
"""P3.4 s118 repair: the corralito counter overflowed the 1080 px frame.

The F4 chart drew "$250 pesos / week" as ONE monospace hero number, wider than
the frame, so the master showed "0 pesos / w". The fix is data-only (the shared
dataviz pipeline is untouched): the hero number becomes "$250" and the unit
moves to the label line under it. Wording follows Decree 1570/2001 (1 Dec 2001:
cash withdrawals capped at 250 pesos or dollars a week).

  .venv/bin/python scripts/k70_p34_s118_fix.py \
      --graph data/finance_p34/bitcoin_final_v1/scene_graph_p34.json

Re-renders ONLY s118, backs the graph up once (scene_graph_p34.pre_s118.json)
and repoints s118 to the new clip; every other scene must stay identical.
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCENE = "s118"
DATA = {"title": "Weekly withdrawal limit", "prefix": "$", "suffix": "",
        "label": "Pesos per week, Dec 2001"}


def patch(graph: dict, asset: str) -> dict:
    """Copy of `graph` with only s118's chart data and asset path changed."""
    out = copy.deepcopy(graph)
    scene = next(s for s in out["scenes"] if s["id"] == SCENE)
    d = scene["data"]
    if d["kind"] != "counter" or [p["value"] for p in d["points"]] != [250.0]:
        raise ValueError("s118 is not the 250-peso counter; refusing to patch")
    d.update(title=DATA["title"], prefix=DATA["prefix"], suffix=DATA["suffix"])
    d["points"][0]["label"] = DATA["label"]
    scene["visual"]["asset_path"] = asset
    scene["visual"]["decision_reason"] = ("[P3.4] s118 counter re-rendered: unit moved "
                                          "off the hero number so it fits 1080 px")
    for a, b in zip(graph["scenes"], out["scenes"]):
        if a["id"] != SCENE and a != b:
            raise AssertionError(f"{a['id']}: unexpected change")
    if {k: v for k, v in graph.items() if k != "scenes"} != \
            {k: v for k, v in out.items() if k != "scenes"}:
        raise AssertionError("top-level fields changed")
    return out


async def render(graph: dict, out: Path) -> Path:
    import yaml
    preset = yaml.safe_load((ROOT / "config/presets/documentary_series.yaml").read_text())
    for k, v in (preset.get("env") or {}).items():
        os.environ.setdefault(k, str(v))
    sys.path[:0] = [str(ROOT / "apps" / "api"), str(ROOT)]
    from app.brand.manager import theme_for
    from app.pipeline import dataviz
    from app.schemas.scene import SceneGraph
    sg = SceneGraph.model_validate(graph)
    scene = next(s for s in sg.scenes if s.id == SCENE)
    theme = theme_for(sg, "compositor")
    return await dataviz.render(scene.data, theme, out, sg.width, sg.height, sg.fps,
                                scene.duration_sec)


def main() -> None:
    ap = argparse.ArgumentParser(description="K70 P3.4 s118 chart repair")
    ap.add_argument("--graph", type=Path, required=True)
    a = ap.parse_args()
    graph_path = a.graph.resolve()
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    clip = graph_path.parent / "assets" / "s118_chart_p34fix.mp4"
    patched = patch(graph, str(clip))
    asyncio.run(render(patched, clip))
    backup = graph_path.with_name(graph_path.stem + ".pre_s118.json")
    if not backup.exists():
        shutil.copy2(graph_path, backup)
    graph_path.write_text(json.dumps(patched, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"s118 -> {clip} sha256={hashlib.sha256(clip.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main()
