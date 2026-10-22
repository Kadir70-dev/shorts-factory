#!/usr/bin/env python3
"""P3.4 chart-title repair: 8 F4 chart titles ran into / off the right edge.

The shared dataviz renderer wraps a title to the full frame width, so a long
title gets the 80 px left pad but no right margin (s140, s144 visibly cut).
The fix is data-only, like s118: shorter titles; sources, values and labels
are untouched. Every new title is measured with the theme's real title font
and must fit inside the plot width (frame minus both pads) on ONE line before
anything is rendered.

  .venv/bin/python scripts/k70_p34_chart_titles_fix.py \
      --graph data/finance_p34/bitcoin_final_v1/scene_graph_p34.json

Re-renders ONLY these charts, backs the graph up once
(scene_graph_p34.pre_titles.json) and repoints them; every other scene must
stay identical.
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
# scene id -> (current title, new title)
TITLES = {
    "s51": ("Purchasing power of one 1971 dollar", "Value of a 1971 dollar"),
    "s61": ("Effective federal funds rate, peak", "Fed funds rate, peak"),
    "s66": ("U.S. savings & loans, 1986-1995", "S&L failures, 1986-95"),
    "s120": ("Argentine sovereign default, 2001", "Argentina's 2001 default"),
    "s125": ("Zimbabwe price-doubling time, Nov 2008", "Zimbabwe, Nov 2008"),
    "s134": ("Runs on a British retail bank", "Runs on a British bank"),
    "s140": ("Lehman Brothers assets at filing", "Lehman assets at filing"),
    "s144": ("Completed U.S. foreclosures from 2007", "U.S. foreclosures"),
}


def patch(graph: dict, assets: dict[str, str]) -> dict:
    """Copy of `graph` with only the listed charts' titles and asset paths changed."""
    out = copy.deepcopy(graph)
    for scene in out["scenes"]:
        if scene["id"] not in TITLES:
            continue
        old, new = TITLES[scene["id"]]
        d = scene.get("data") or {}
        if scene["visual"]["type"] != "dataviz" or d.get("title") not in (old, new):
            raise ValueError(f"{scene['id']}: not the expected chart; refusing to patch")
        d["title"] = new
        scene["visual"]["asset_path"] = assets[scene["id"]]
        scene["visual"]["decision_reason"] = ("[P3.4] chart re-rendered with a shorter "
                                              "title that fits inside the frame")
    for a, b in zip(graph["scenes"], out["scenes"]):
        if a["id"] not in TITLES and a != b:
            raise AssertionError(f"{a['id']}: unexpected change")
    if {k: v for k, v in graph.items() if k != "scenes"} != \
            {k: v for k, v in out.items() if k != "scenes"}:
        raise AssertionError("top-level fields changed")
    return out


def _setup():
    import yaml
    preset = yaml.safe_load((ROOT / "config/presets/documentary_series.yaml").read_text())
    for k, v in (preset.get("env") or {}).items():
        os.environ.setdefault(k, str(v))
    sys.path[:0] = [str(ROOT / "apps" / "api"), str(ROOT)]


def title_fit(sg) -> dict[str, dict]:
    """Rendered width of each new title vs the plot width, with the real font."""
    from PIL import ImageFont
    from app.brand.manager import theme_for
    from app.pipeline import dataviz
    theme = theme_for(sg, "compositor")
    lay = dataviz._layout(theme, sg.width, sg.height)
    size = theme.size("chart_title", lay.h)
    font = ImageFont.truetype(str(theme.display.path), size)
    out = {}
    for sid, (_, new) in TITLES.items():
        w = font.getlength(theme.display.apply_case(new))
        out[sid] = {"title": new, "width_px": round(w), "max_px": lay.plot_w,
                    "fits": w <= lay.plot_w}
    return out


async def render(graph: dict, clips: dict[str, Path]) -> dict:
    from app.brand.manager import theme_for
    from app.pipeline import dataviz
    from app.schemas.scene import SceneGraph
    sg = SceneGraph.model_validate(graph)
    theme = theme_for(sg, "compositor")
    for s in sg.scenes:
        if s.id in clips:
            await dataviz.render(s.data, theme, clips[s.id], sg.width, sg.height, sg.fps,
                                 s.duration_sec)
    return {sid: hashlib.sha256(p.read_bytes()).hexdigest() for sid, p in clips.items()}


def main() -> None:
    ap = argparse.ArgumentParser(description="K70 P3.4 chart-title repair")
    ap.add_argument("--graph", type=Path, required=True)
    a = ap.parse_args()
    _setup()
    from app.schemas.scene import SceneGraph
    graph_path = a.graph.resolve()
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    fit = title_fit(SceneGraph.model_validate(graph))
    print(json.dumps(fit, indent=2))
    if not all(r["fits"] for r in fit.values()):
        raise SystemExit("a new title does not fit on one line; nothing changed")
    clips = {sid: graph_path.parent / "assets" / f"{sid}_chart_p34title.mp4" for sid in TITLES}
    patched = patch(graph, {sid: str(p) for sid, p in clips.items()})
    shas = asyncio.run(render(patched, clips))
    backup = graph_path.with_name(graph_path.stem + ".pre_titles.json")
    if not backup.exists():
        shutil.copy2(graph_path, backup)
    graph_path.write_text(json.dumps(patched, indent=2, ensure_ascii=False), encoding="utf-8")
    for sid, sha in shas.items():
        print(f"{sid} -> {clips[sid].name} sha256={sha}")


if __name__ == "__main__":
    main()
