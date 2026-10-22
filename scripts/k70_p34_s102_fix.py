#!/usr/bin/env python3
"""P3.4 s102 repair + single-scene verification with the real renderer.

s102's Pexels pick is near-black, so v2 and v3 were rendered with
`--override s102=.../s102_gfx.mp4`. `patch` makes that permanent in the active
graph (same fields the override set), copying the approved card next to the
graph. `verify` re-renders chosen scenes through `render_ffmpeg._scene_clip`
(the production code path) and compares them with a reference render's clips,
and checks every OTHER scene's fingerprint against that render's manifest — so
a full rebuild from the graph is proven to reuse them unchanged.

  .venv/bin/python scripts/k70_p34_s102_fix.py patch \
      --graph data/finance_p34/bitcoin_final_v1/scene_graph_p34.json \
      --card data/finance_f4/k70_f4_bitcoin_ep01_cinematic/visuals/s102_gfx.mp4
  .venv/bin/python scripts/k70_p34_s102_fix.py verify \
      --graph data/finance_p34/bitcoin_final_v1/scene_graph_p34.json \
      --reference data/finance_p34/render_full_v3 --scene s102 --scene s118
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCENE = "s102"
REASON = "[P3.4] dark Pexels pick replaced by approved card s102_gfx.mp4 (was a render-time override)"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def patch(graph: dict, card: str) -> dict:
    """Copy of `graph` with only s102 switched to the approved motion_gfx card."""
    out = copy.deepcopy(graph)
    v = next(s for s in out["scenes"] if s["id"] == SCENE)["visual"]
    if v["type"] == "motion_gfx" and v["asset_path"] == card:
        return out                                     # already patched
    if v["type"] != "broll":
        raise ValueError(f"s102 is {v['type']!r}, expected the broll stock pick")
    v.update(type="motion_gfx", asset_path=card, layers=[], motion="none",
             decision_reason=REASON)
    for a, b in zip(graph["scenes"], out["scenes"]):
        if a["id"] != SCENE and a != b:
            raise AssertionError(f"{a['id']}: unexpected change")
    if {k: v for k, v in graph.items() if k != "scenes"} != \
            {k: v for k, v in out.items() if k != "scenes"}:
        raise AssertionError("top-level fields changed")
    return out


def cmd_patch(a) -> int:
    graph_path = a.graph.resolve()
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    card = graph_path.parent / "assets" / "s102_gfx.mp4"
    if not card.exists():
        card.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(a.card, card)
    if _sha(card) != _sha(a.card):
        raise SystemExit(f"{card} differs from the approved card")
    patched = patch(graph, str(card))
    backup = graph_path.with_name(graph_path.stem + ".pre_s102.json")
    if not backup.exists():
        shutil.copy2(graph_path, backup)
    graph_path.write_text(json.dumps(patched, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"s102 -> {card} sha256={_sha(card)}")
    return 0


def _ssim(a: Path, b: Path) -> float:
    err = subprocess.run(["ffmpeg", "-v", "info", "-i", str(a), "-i", str(b),
                          "-lavfi", "ssim", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    m = re.search(r"All:([\d.]+)", err)
    return float(m.group(1)) if m else 0.0


async def _verify(a) -> dict:
    sys.path[:0] = [str(ROOT / "apps" / "api"), str(ROOT)]
    from scripts.k70_p0_render_v2 import preset_env
    preset_env(a.preset)
    from app.brand import brand_manager, theme_for
    from app.pipeline import render_ffmpeg as rf
    from app.pipeline.production_optimizer import scene_fingerprint
    from app.schemas.scene import SceneGraph

    graph = SceneGraph.model_validate_json(a.graph.read_text(encoding="utf-8"))
    ref = a.reference.resolve()
    manifest = json.loads((ref / "manifest.json").read_text())
    theme = theme_for(graph, "compositor")
    grade = theme.grade(graph.variety.get("grade", ""))
    zoom = rf._zoom_travel(graph)
    context = rf._render_context(graph, theme, grade, zoom)
    changed = [s.id for s in graph.scenes
               if manifest["scenes"].get(s.id) != scene_fingerprint(s, context)]
    report = {"graph": str(a.graph), "reference": str(ref),
              "context_matches": manifest.get("context") == context,
              "fingerprint_changed": changed, "scenes": {}}
    index = {s.id: i for i, s in enumerate(graph.scenes)}
    with tempfile.TemporaryDirectory(dir=a.tmp) as tmp:
        for sid in a.scene:
            i, scene = index[sid], graph.scenes[index[sid]]
            out = Path(tmp) / f"scene_{i:02d}.mp4"
            await rf._scene_clip(scene, out, graph.width, graph.height, graph.fps, theme,
                                 grade, zoom, transition=brand_manager.transition(
                                     graph, scene.transition_in), hook=(i == 0))
            ref_clip = ref / f"scene_{i:02d}.mp4"
            same = _sha(out) == _sha(ref_clip)
            report["scenes"][sid] = {
                "index": i, "asset": scene.visual.asset_path, "type": scene.visual.type,
                "duration_sec": round(rf._probe_duration(out), 3),
                "expected_sec": scene.duration_sec, "byte_identical_to_reference": same,
                "ssim_vs_reference": 1.0 if same else round(_ssim(out, ref_clip), 4)}
    others = [c for c in changed if c not in a.scene]
    report["passed"] = (report["context_matches"] and not others and all(
        r["ssim_vs_reference"] >= 0.99 for r in report["scenes"].values()))
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description="K70 P3.4 s102 repair / scene verification")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("patch")
    p.add_argument("--graph", type=Path, required=True)
    p.add_argument("--card", type=Path, required=True)
    v = sub.add_parser("verify")
    v.add_argument("--graph", type=Path, required=True)
    v.add_argument("--reference", type=Path, required=True)
    v.add_argument("--scene", action="append", required=True)
    v.add_argument("--preset", default="documentary_finance")
    v.add_argument("--tmp", type=Path, default=None)
    v.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()
    if a.cmd == "patch":
        raise SystemExit(cmd_patch(a))
    report = asyncio.run(_verify(a))
    text = json.dumps(report, indent=2)
    if a.out:
        a.out.write_text(text, encoding="utf-8")
    print(text)
    raise SystemExit(0 if report["passed"] else 2)


if __name__ == "__main__":
    main()
