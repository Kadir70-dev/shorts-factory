#!/usr/bin/env python3
"""P3.1: repair *copies* of voiced K70 finance SceneGraphs without touching masters.

Default is a read-only report. --apply requires >=2GiB free and generates only
the lost sourced chart clips, then prefers verified existing licensed archive
files to stock. No external APIs, full-film render, voiceover or caption edits.

  .venv/bin/python scripts/k70_p31_evidence_repair.py \
    --graph data/finance_p0/cinematic_balanced/scene_graph_p0.json \
    --baseline data/series/bitcoin_history/ep01_f4/scene_graph.json \
    --out-dir data/finance_p31/bitcoin_review_v1

  # AFTER freeing enough disk space, separate new folder:
  .venv/bin/python scripts/k70_p31_evidence_repair.py \
    --graph data/finance_p0/cinematic_balanced/scene_graph_p0.json \
    --baseline data/series/bitcoin_history/ep01_f4/scene_graph.json \
    --out-dir data/finance_p31/bitcoin_repaired_v1 --apply
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import json
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

# Named real people require deliberate frame verification, not solely license
# validation. This is a specific known risk in the Bitcoin history film.
REQUIRES_IDENTITY_REVIEW = frozenset({"s42", "s82"})
CHART_SUFFIXES = {".mp4", ".mov", ".webm"}


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("scenes"), list):
        raise ValueError(f"not a SceneGraph object: {path}")
    return value


def _source_chart(before: dict, after: dict) -> bool:
    """A sourced chart authored in the baseline but lost in the voiced graph."""
    if before.get("visual", {}).get("type") not in ("dataviz", "manim"):
        return False
    data = before.get("data") or after.get("data")
    if not isinstance(data, dict) or not str(data.get("source") or "").strip():
        return False
    points = data.get("points")
    if not isinstance(points, list) or not points:
        return False
    if not all(isinstance(x, dict) and
               isinstance(x.get("value"), (float, int)) and
               not isinstance(x.get("value"), bool) for x in points):
        return False
    return (after.get("visual", {}).get("type") not in ("dataviz", "threejs", "ai_video")
            and before.get("narration") == after.get("narration"))


def _usable_archive(scene: dict, graph: dict, root: Path) -> dict | None:
    """Reuse only provenance-selected, legally documented and cached media."""
    visual = scene.get("visual") or {}
    if (visual.get("type") != "broll" or
            visual.get("budget_channel") not in ("stock", "ai_broll")):
        return None
    sid = str(scene["id"])
    if sid in REQUIRES_IDENTITY_REVIEW:
        return None
    allowed = {"wikimedia_commons", "government_public_domain", "sec_regulatory", "company_ir"}
    # Existing asset engine is the policy authority; it provides license rules
    # without network calls, but only when explicitly evaluating an asset.
    beats = {row.get("scene_id") for row in
             (graph.get("storyboard") or {}).get("scenes", [])
             if row.get("source_scene_id") == sid}
    if not beats:
        return None
    from app.pipeline.asset_engine import SAFE_LICENSES
    for record in graph.get("asset_provenance", []):
        if record.get("status") != "resolved" or record.get("scene_id") not in beats:
            continue
        for c in record.get("candidates", []):
            if c.get("source_url") != record.get("selected_source_url"):
                continue
            if (c.get("provider_institution") not in allowed
                    or c.get("commercial_use_status") != "allowed"
                    or str(c.get("license") or "").lower().strip() not in SAFE_LICENSES
                    or float(c.get("relevance_score") or 0) < 0.75
                    or float(c.get("subject_specificity") or 0) < 0.65
                    or float(c.get("confidence") or 0) < 0.5):
                continue
            local = c.get("local_cache_path")
            if not local:
                continue
            path = Path(str(local)).expanduser().resolve()
            # Only trust the repository's local data cache; never display an
            # arbitrary file system path or re-use a filesystem escape.
            if not path.is_relative_to(root / "data") or not path.is_file():
                continue
            if path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp",
                                            ".mp4", ".mov", ".webm"}:
                continue
            if path.stat().st_size <= 0:
                continue
            return {"path": str(path), "provider": c.get("provider_institution"),
                    "source_url": c.get("source_url"), "license": c.get("license"),
                    "attribution_requirement": c.get("attribution_requirement", "")}
    return None


def inspect(original: dict, source: dict, root: Path) -> dict:
    if [s.get("id") for s in original["scenes"]] != [
            s.get("id") for s in source["scenes"]]:
        raise ValueError("baseline and voiced graph need identical scene IDs and order")
    if (source.get("meta") or {}).get("niche") != "usa_finance":
        raise ValueError("finance-only repair refuses a different niche")
    if len(source["scenes"]) < 20:
        raise ValueError("long-form source graph must have >=20 scenes")
    if not (float(source.get("width") or 0) > float(source.get("height") or 0)):
        raise ValueError("finance documentary must be landscape")
    charts, archives, identity = [], [], []
    for a, b in zip(original["scenes"], source["scenes"]):
        sid = b["id"]
        if _source_chart(a, b):
            charts.append({"scene_id": sid, "source": (a.get("data") or b.get("data"))["source"],
                           "before": a["visual"]["type"], "delivered": b["visual"]["type"]})
        if sid in REQUIRES_IDENTITY_REVIEW and b.get("visual", {}).get("type") == "broll":
            identity.append(sid)
        cand = _usable_archive(b, source, root)
        if cand:
            archives.append({"scene_id": sid, **cand})
    return {"mode": "review_only_until_apply", "total_scenes": len(source["scenes"]),
            "lost_sourced_charts": charts, "qualified_archive_replacements": archives,
            "identity_review_only": identity,
            "warnings": ["Citations and archives still require human factual/visual review.",
                         "Previously voiced s30/s126 are NOT repaired by this script.",
                         "P3 visual fixes do NOT constitute a completed documentary render."]}


async def _render_chart(sid: str, data: dict, graph: Any, dest: Path) -> None:
    """Render a single chapter's source-backed chart on the existing CPU engine."""
    from app.brand import theme_for
    from app.pipeline import dataviz
    from app.schemas.scene import DataViz
    viz = DataViz.model_validate(data)
    if not viz.valid() or not viz.source.strip():
        raise ValueError(f"{sid}: no legitimate source-backed chart points")
    scene = next(s for s in graph.scenes if s.id == sid)
    dest.parent.mkdir(parents=True, exist_ok=True)
    await dataviz.render(viz, theme_for(graph, "asset_composition"), dest,
                         graph.width, graph.height, graph.fps,
                         max(2.5, scene.duration_sec))
    if not dest.is_file() or dest.stat().st_size == 0:
        raise RuntimeError(f"{sid}: chart rendering did not create media")


def _apply_archive(scene: dict, receipt: dict) -> None:
    visual = scene["visual"]
    path = Path(receipt["path"])
    visual["type"] = "broll" if path.suffix.lower() in CHART_SUFFIXES else "image"
    visual["asset_path"] = str(path)
    visual["motion"] = "none" if visual["type"] == "broll" else "ken_burns"
    visual["budget_channel"] = "official"
    visual["decision_reason"] = "[P3.1] existing licensed archival source over stock"
    visual["layers"] = []


def _validate_without_retiming(raw: dict):
    """Build a temporary Pydantic graph while preserving the actual 0.747s clips.

    P0's measured TTS can legitimately be shorter than Scene.duration_sec's
    authored 0.8s minimum. Like the existing checkpoint loader, clamp ONLY
    the in-memory validation copy. Never touch the returned/output graph.
    """
    from app.schemas.scene import SceneGraph
    validated = copy.deepcopy(raw)
    for scene in validated.get("scenes", []):
        duration = scene.get("duration_sec")
        if isinstance(duration, (float, int)) and 0 < duration < 0.8:
            scene["duration_sec"] = 0.8
    return SceneGraph.model_validate(validated)


async def repair(source: dict, baseline: dict, report: dict,
                 directory: Path) -> dict:
    graph = _validate_without_retiming(source)
    revised = copy.deepcopy(source)
    lookup = {s["id"]: s for s in revised["scenes"]}
    old = {s["id"]: s for s in baseline["scenes"]}
    for row in report["lost_sourced_charts"]:
        sid = row["scene_id"]
        source_data = (old[sid].get("data") or lookup[sid].get("data"))
        output = directory / "charts" / f"{sid}_sourced_chart.mp4"
        await _render_chart(sid, source_data, graph, output)
        visual = lookup[sid]["visual"]
        visual.update({"type": "dataviz", "strategy": "dataviz",
                       "budget_channel": "charts", "asset_path": str(output),
                       "motion": "none", "layers": [],
                       "decision_reason": "[P3.1] recovered authored sourced chart"})
        lookup[sid]["data"] = copy.deepcopy(source_data)
    for row in report["qualified_archive_replacements"]:
        if row["scene_id"] not in {c["scene_id"] for c in report["lost_sourced_charts"]}:
            _apply_archive(lookup[row["scene_id"]], row)
    # Strict invariant: never touch narration, duration, caption, 3D/cinematic
    # clips, master metadata or audio. A media review still follows.
    assert [s["id"] for s in revised["scenes"]] == [s["id"] for s in source["scenes"]]
    for old_scene, new_scene in zip(source["scenes"], revised["scenes"]):
        for key in ("narration", "duration_sec", "overlays", "beat_role", "transition_in"):
            if old_scene.get(key) != new_scene.get(key):
                raise AssertionError(f"{old_scene['id']}: changed protected field {key}")
        if old_scene.get("visual", {}).get("type") in ("threejs", "ai_video"):
            if old_scene.get("visual") != new_scene.get("visual"):
                raise AssertionError(f"{old_scene['id']}: changed protected cinematic/3D")
    for key in ("audio", "captions", "sfx", "meta", "threejs_provenance", "ai_broll_provenance"):
        if revised.get(key) != source.get(key):
            raise AssertionError(f"changed protected top-level field {key}")
    _validate_without_retiming(revised)
    return revised


def main() -> None:
    ap = argparse.ArgumentParser(description="K70 P3.1 sourced-chart/archive repair; source masters read-only")
    ap.add_argument("--graph", type=Path, required=True, help="P0 voiced graph, read-only")
    ap.add_argument("--baseline", type=Path, required=True, help="original authored graph, read-only")
    ap.add_argument("--out-dir", type=Path, required=True, help="fresh review/output directory")
    ap.add_argument("--apply", action="store_true", help="render lost charts and patch NEW graph copy")
    ap.add_argument("--min-free-gb", type=float, default=2.0,
                    help="minimum free space before --apply (default 2 GiB)")
    args = ap.parse_args()
    try:
        root = ROOT.resolve()
        source_path = args.graph.expanduser().resolve()
        baseline_path = args.baseline.expanduser().resolve()
        out = args.out_dir.expanduser().resolve()
        if not out.is_relative_to(root / "data"):
            raise ValueError("--out-dir must be under the repository data/ folder")
        if out in (source_path, baseline_path) or out.is_relative_to(source_path.parent / source_path.name):
            raise ValueError("cannot write onto input source")
        if out.exists():
            raise FileExistsError("output folder already exists; choose a fresh directory")
        original = _load(baseline_path)
        source = _load(source_path)
        report = inspect(original, source, root)
        free = shutil.disk_usage(root).free
        report["free_space_gib"] = round(free / (1024 ** 3), 2)
        report["apply_requested"] = bool(args.apply)
        if args.apply and free < args.min_free_gb * (1024 ** 3):
            raise ValueError(f"disk too full: {report['free_space_gib']} GiB; "
                             f"need at least {args.min_free_gb} GiB (no files changed)")
        out.mkdir(parents=True, exist_ok=False)
        copy_graph = asyncio.run(repair(source, original, report, out)) if args.apply else None
        (out / "repair_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        if copy_graph is not None:
            (out / "scene_graph_p31_repaired.json").write_text(
                json.dumps(copy_graph, indent=2), encoding="utf-8")
        print(f"P3.1 {len(report['lost_sourced_charts'])} chart repairs, "
              f"{len(report['qualified_archive_replacements'])} licensed archive candidates, "
              f"{len(report['identity_review_only'])} identity scenes for manual review.")
        print(f"Available disk: {report['free_space_gib']} GiB; report: {out / 'repair_report.json'}")
        if not args.apply:
            print("READ ONLY. With sufficient disk, --apply writes a NEW graph; no full render.")
    except (OSError, ValueError, AssertionError, RuntimeError, json.JSONDecodeError) as exc:
        ap.error(str(exc))


if __name__ == "__main__":
    main()
